"""
X-Route — Fase 3: Búsqueda Local
=================================
Dado el depósito y las N entregas de la instancia, busca el ORDEN de visita
que minimiza la distancia total recorrida. Es una variante del Viajante de
Comercio (TSP), NP-hard: el espacio de estados son las N! permutaciones de
las entregas, así que en lugar de búsqueda sistemática se usan métodos de
búsqueda local sobre soluciones completas.

Formulación (ver el enunciado):
  - Estado:     permutación π de los índices de las N entregas.
  - Recorrido:  depósito → π1 → π2 → ... → πN → depósito (circuito cerrado:
                el repartidor sale del almacén y regresa a él).
  - Objetivo:   f(π) = D[0][π1] + Σ D[πi][πi+1] + D[πN][0], donde D es la
                matriz de distancias REALES sobre calles calculada con A* de
                Fase 2 (heurística Haversine, admisible → caminos óptimos).
  - Vecindad:   2-opt, invertir el tramo π[i..j] (equivale a quitar dos
                arcos del recorrido y reconectarlo al revés).

Algoritmos:
  1. Simulated Annealing con enfriamiento geométrico T_{k+1} = α·T_k y
     vecindad 2-opt.
  2. Algoritmo Genético con representación por permutación, cruza OX
     (Order Crossover), mutación por intercambio, selección por torneo y
     elitismo.
  3. Referencias: solución aleatoria (la "trivial"), vecino más cercano,
     búsqueda local 2-opt pura (hill climbing) y el óptimo exacto por
     programación dinámica (Held-Karp), que todavía es calculable para
     N = 15 y permite medir qué tan lejos del óptimo queda cada método.

Como el grafo es DIRIGIDO (calles de un solo sentido), D no es simétrica:
D[i][j] != D[j][i]. Por eso, al invertir un tramo con 2-opt, cambia el
costo de todos los arcos dentro del tramo y no sólo el de los dos arcos
reconectados; costo_ruta() siempre recalcula el recorrido completo, que
con N = 15 cuesta 16 sumas.

Ejecutar desde la raíz del proyecto:
    python src/fase3.py
"""

import sys
import math
import random
import time
from dataclasses import dataclass, field
from pathlib import Path

import folium
import pandas as pd

# ── Asegura que `src/` sea importable desde la raíz del proyecto ──────────────
sys.path.insert(0, str(Path(__file__).resolve().parent))
from grafo import cargar_grafo, construir_adyacencia, cargar_instancia
from metricas import Medicion
from fase2 import a_estrella, heuristica_haversine, extraer_coordenadas, costo_entre_puntos


# =============================================================================
# 1. Matriz de distancias con A* (Fase 2)
# =============================================================================
def matriz_distancias_astar(ady: dict, coords: dict, nodos: list) -> tuple:
    """
    Calcula D[i][j] = metros del camino más corto de nodos[i] a nodos[j]
    sobre las calles, con A* + heurística Haversine de Fase 2.

    Se calcula UNA sola vez antes de optimizar: GA y SA evalúan decenas de
    miles de recorridos y cada evaluación sólo consulta la matriz, en vez
    de volver a correr A* (con 16 puntos son 16·15 = 240 búsquedas A*).
    La heurística se precalcula una vez por destino, igual que en Fase 2.

    Args:
        ady:    Diccionario de adyacencia {nodo: [(vecino, costo), ...]}.
        coords: {nodo: (lat, lon)} (fase2.extraer_coordenadas).
        nodos:  Nodos del grafo a conectar; por convención nodos[0] es el
                depósito y nodos[1:] las entregas.

    Returns:
        (D, caminos, total_expandidos)
        D:        lista de listas n x n en metros (math.inf si no hay ruta).
        caminos:  {(i, j): [nodos del camino]} para dibujar la ruta final.
        total_expandidos: suma de nodos expandidos por las 240 búsquedas A*.
    """
    n = len(nodos)
    D = [[0.0] * n for _ in range(n)]
    caminos = {}
    total_expandidos = 0

    for j, destino in enumerate(nodos):
        h = heuristica_haversine(coords, destino)
        for i, origen in enumerate(nodos):
            if i == j:
                caminos[(i, j)] = [origen]
                continue
            med = Medicion("A*-Haversine")
            camino = a_estrella(ady, origen, destino, med, h)
            total_expandidos += med.nodos_expandidos
            if camino is None:
                D[i][j] = math.inf
            else:
                D[i][j] = med.procesar_camino(camino, ady)[1]
                caminos[(i, j)] = camino

    return D, caminos, total_expandidos


def matriz_distancias_haversine(coords: dict, nodos: list) -> list:
    """D[i][j] = distancia en línea recta (fase2.costo_entre_puntos). Sólo se
    usa para comparar contra la matriz real de A* (factor de rodeo)."""
    return [
        [costo_entre_puntos(*coords[a], *coords[b]) for b in nodos]
        for a in nodos
    ]


# =============================================================================
# 2. Función objetivo y soluciones de referencia
# =============================================================================
def costo_ruta(perm: list, D: list, deposito: int = 0) -> float:
    """
    f(π): metros del circuito depósito → π[0] → ... → π[-1] → depósito.
    `perm` contiene índices de la matriz D (las entregas), nunca el depósito.
    """
    if not perm:
        return 0.0
    total = D[deposito][perm[0]]
    for a, b in zip(perm, perm[1:]):
        total += D[a][b]
    total += D[perm[-1]][deposito]
    return total


def ruta_aleatoria(indices: list, rng: random.Random) -> list:
    """Permutación uniforme de las entregas: la solución "trivial" contra la
    que se mide el % de mejora."""
    perm = list(indices)
    rng.shuffle(perm)
    return perm


def vecino_mas_cercano(D: list, indices: list, deposito: int = 0) -> list:
    """Heurística constructiva voraz: desde el punto actual, ir siempre a la
    entrega pendiente más cercana. Rápida pero miope (no deshace errores)."""
    pendientes = set(indices)
    actual = deposito
    perm = []
    while pendientes:
        siguiente = min(pendientes, key=lambda k: (D[actual][k], k))
        perm.append(siguiente)
        pendientes.remove(siguiente)
        actual = siguiente
    return perm


# =============================================================================
# 3. Operadores sobre permutaciones
# =============================================================================
def vecino_2opt(perm: list, i: int, j: int) -> list:
    """
    Vecino 2-opt: invierte el tramo perm[i..j] (ambos inclusive).

    En el recorrido ... a → [b ... c] → d ... se quitan los arcos (a, b) y
    (c, d) y se reconecta como ... a → [c ... b] → d ...  Por eso se dice
    que 2-opt "intercambia dos arcos". Un recorrido de N entregas tiene
    N·(N-1)/2 vecinos 2-opt (uno por cada par i < j).
    """
    return perm[:i] + perm[i:j + 1][::-1] + perm[j + 1:]


def mutacion_intercambio(perm: list, rng: random.Random) -> list:
    """Mutación por intercambio (swap): escoge dos posiciones al azar e
    intercambia sus entregas. Siempre produce una permutación válida."""
    hijo = perm[:]
    if len(hijo) < 2:
        return hijo
    i, j = rng.sample(range(len(hijo)), 2)
    hijo[i], hijo[j] = hijo[j], hijo[i]
    return hijo


def cruza_ox(padre1: list, padre2: list, rng: random.Random, cortes: tuple = None) -> list:
    """
    Order Crossover (OX, Davis 1985).

      1. Se eligen dos puntos de corte a <= b.
      2. El hijo copia TAL CUAL el segmento padre1[a..b] en las mismas
         posiciones (hereda un sub-recorrido de padre1).
      3. Las posiciones restantes se llenan, empezando en b+1 y dando la
         vuelta circularmente, con las entregas que faltan en el ORDEN
         RELATIVO en que aparecen en padre2 (también leído desde b+1).

    Ejemplo (Eiben & Smith), cortes (3, 6):
        padre1 = [1 2 3 | 4 5 6 7 | 8 9]
        padre2 = [9 3 7 | 8 2 6 5 | 1 4]
        hijo   = [3 8 2 | 4 5 6 7 | 1 9]

    A diferencia de una cruza de un punto, OX nunca repite ni pierde
    entregas: el hijo siempre es una permutación válida.

    Args:
        cortes: (a, b) fijos para pruebas; si es None se sortean.
    """
    n = len(padre1)
    if n < 2:
        return padre1[:]
    a, b = cortes if cortes is not None else sorted(rng.sample(range(n), 2))

    hijo = [None] * n
    hijo[a:b + 1] = padre1[a:b + 1]
    usados = set(hijo[a:b + 1])

    pos = (b + 1) % n
    for k in range(n):
        gen = padre2[(b + 1 + k) % n]
        if gen not in usados:
            hijo[pos] = gen
            usados.add(gen)
            pos = (pos + 1) % n
    return hijo


# =============================================================================
# 4. Resultado común de los algoritmos de búsqueda local
# =============================================================================
@dataclass
class ResultadoLocal:
    """
    Resultado de una corrida de búsqueda local.

    historial: mejor costo encontrado hasta cada iteración (curva de
               convergencia). En SA una iteración = un vecino propuesto;
               en GA una iteración = una generación.
    evaluaciones: número de veces que se llamó a costo_ruta(); es el eje
               justo para comparar GA contra SA, porque una generación del
               GA evalúa toda la población.
    """
    algoritmo: str
    mejor_ruta: list
    mejor_costo: float
    tiempo_ms: float
    evaluaciones: int
    historial: list = field(default_factory=list)
    extra: dict = field(default_factory=dict)


# =============================================================================
# 5. Búsqueda local 2-opt pura (hill climbing)
# =============================================================================
def busqueda_local_2opt(perm: list, D: list, deposito: int = 0) -> ResultadoLocal:
    """
    Hill climbing de máximo descenso con vecindad 2-opt: en cada paso
    evalúa los N·(N-1)/2 vecinos y se mueve al mejor, mientras mejore.
    Se detiene en un ÓPTIMO LOCAL: una ruta que ningún 2-opt mejora.

    Sirve para dos cosas: como línea base (qué tanto aportan SA y GA sobre
    "sólo bajar") y para muestrear el paisaje de optimización desde muchos
    arranques aleatorios (analizar_paisaje()).
    """
    inicio = time.perf_counter()
    actual = perm[:]
    costo = costo_ruta(actual, D, deposito)
    evaluaciones = 1
    historial = [costo]
    n = len(actual)

    while True:
        mejor_vecino, mejor_costo_vecino = None, costo
        for i in range(n - 1):
            for j in range(i + 1, n):
                candidato = vecino_2opt(actual, i, j)
                c = costo_ruta(candidato, D, deposito)
                evaluaciones += 1
                if c < mejor_costo_vecino - 1e-9:
                    mejor_vecino, mejor_costo_vecino = candidato, c
        if mejor_vecino is None:
            break
        actual, costo = mejor_vecino, mejor_costo_vecino
        historial.append(costo)

    return ResultadoLocal(
        algoritmo="2-opt (hill climbing)",
        mejor_ruta=actual,
        mejor_costo=costo,
        tiempo_ms=(time.perf_counter() - inicio) * 1000,
        evaluaciones=evaluaciones,
        historial=historial,
    )


# =============================================================================
# 6. Simulated Annealing con enfriamiento geométrico
# =============================================================================
# Parámetros del esquema de enfriamiento (justificación en el README y en
# los docstrings de calcular_temperatura_inicial / simulated_annealing):
PROB_ACEPTACION_INICIAL = 0.8   # T0: al inicio se acepta ~80% de los empeoramientos
ALFA = 0.99                     # enfriamiento geométrico T <- 0.99·T
T_MIN = 1.0                     # metros; ver docstring de simulated_annealing()


def muestrear_empeoramientos(D: list, indices: list, rng: random.Random,
                             muestras: int = 500, deposito: int = 0) -> list:
    """Propone movimientos 2-opt al azar sobre rutas aleatorias y devuelve
    los Δ > 0 (cuántos metros empeora la ruta cuando el vecino es peor)."""
    n = len(indices)
    deltas = []
    for _ in range(muestras):
        perm = ruta_aleatoria(indices, rng)
        i, j = sorted(rng.sample(range(n), 2))
        delta = costo_ruta(vecino_2opt(perm, i, j), D, deposito) - costo_ruta(perm, D, deposito)
        if delta > 0:
            deltas.append(delta)
    return deltas


def calcular_temperatura_inicial(D: list, indices: list, rng: random.Random,
                                 prob_aceptacion: float = PROB_ACEPTACION_INICIAL,
                                 muestras: int = 500, deposito: int = 0) -> tuple:
    """
    T0 empírico (criterio de Kirkpatrick): se elige T0 para que un
    empeoramiento PROMEDIO Δ̄ se acepte con probabilidad p0 al inicio:

        exp(-Δ̄ / T0) = p0   →   T0 = -Δ̄ / ln(p0)

    Con p0 = 0.8 el recocido arranca casi como una caminata aleatoria
    (explora libremente el espacio). Calcularlo a partir de la propia
    instancia evita un número mágico: si mañana las entregas están a 10 km
    en vez de a 3 km, T0 se escala solo.

    Returns:
        (T0, Δ̄)
    """
    deltas = muestrear_empeoramientos(D, indices, rng, muestras, deposito)
    if not deltas:
        return 1.0, 0.0
    delta_promedio = sum(deltas) / len(deltas)
    return -delta_promedio / math.log(prob_aceptacion), delta_promedio


def simulated_annealing(D: list, indices: list, rng: random.Random,
                        T0: float, alfa: float = ALFA, T_min: float = T_MIN,
                        iter_por_temp: int = None, perm_inicial: list = None,
                        deposito: int = 0) -> ResultadoLocal:
    """
    Simulated Annealing (Kirkpatrick, Gelatt y Vecchi, 1983).

    En cada iteración propone un vecino 2-opt al azar con Δ = f(vecino) - f(actual):
      - Si Δ <= 0 (mejora o empata) se acepta siempre.
      - Si Δ > 0 (empeora) se acepta con probabilidad exp(-Δ / T)
        (criterio de Metropolis).
    Aceptar empeoramientos es lo que le permite salir de óptimos locales,
    cosa que el hill climbing 2-opt no puede hacer.

    Enfriamiento geométrico: después de `iter_por_temp` propuestas,
    T <- α·T, hasta que T <= T_min.

      - T0: ver calcular_temperatura_inicial() (p0 = 0.8).
      - α = 0.99: el número de niveles de temperatura es
        L = ln(T_min/T0) / ln(α); con α = 0.99 son ~880 niveles (~92 000
        iteraciones) para esta instancia. α más cercano a 1 enfría más
        lento: mejor calidad, más tiempo. Se probó α = 0.95 (~170 niveles)
        y quedaba en promedio ~10% arriba del óptimo contra ~2% con 0.99:
        como la matriz es asimétrica, invertir un tramo con 2-opt cambia el
        sentido de todas sus calles y la mayoría de los movimientos
        empeoran mucho, así que el paisaje es muy rugoso y SA necesita
        enfriar despacio para no congelarse en un óptimo local.
      - T_min = 1 m: a esa temperatura, empeorar la ruta 10 m (≈0.1% de un
        recorrido de ~10 km) se acepta con probabilidad e^-10 ≈ 4.5e-5; el
        algoritmo ya se comporta como hill climbing puro y seguir enfriando
        sólo gastaría iteraciones.
      - iter_por_temp = N·(N-1)/2 (tamaño de la vecindad 2-opt, 105 con
        N = 15): en cada temperatura la cadena puede proponer tantos
        movimientos como vecinos tiene una ruta, para acercarse al
        equilibrio antes de enfriar.

    Returns:
        ResultadoLocal con historial = mejor costo tras cada propuesta, y en
        `extra`: historial_actual (costo de la ruta actual, muestra la
        exploración), temperaturas por nivel, soluciones distintas
        visitadas y tasa de aceptación de empeoramientos.
    """
    n = len(indices)
    if iter_por_temp is None:
        iter_por_temp = max(1, n * (n - 1) // 2)

    inicio = time.perf_counter()
    actual = perm_inicial[:] if perm_inicial is not None else ruta_aleatoria(indices, rng)
    costo_actual = costo_ruta(actual, D, deposito)
    evaluaciones = 1
    mejor, mejor_costo = actual[:], costo_actual

    historial = [mejor_costo]
    historial_actual = [costo_actual]
    temperaturas = []
    visitadas = {tuple(actual)}
    propuestas_peores = aceptadas_peores = 0

    T = T0
    while T > T_min and n >= 2:
        temperaturas.append(T)
        for _ in range(iter_por_temp):
            i, j = sorted(rng.sample(range(n), 2))
            candidato = vecino_2opt(actual, i, j)
            costo_candidato = costo_ruta(candidato, D, deposito)
            evaluaciones += 1
            delta = costo_candidato - costo_actual

            if delta > 0:
                propuestas_peores += 1
            if delta <= 0 or rng.random() < math.exp(-delta / T):
                if delta > 0:
                    aceptadas_peores += 1
                actual, costo_actual = candidato, costo_candidato
                visitadas.add(tuple(actual))
                if costo_actual < mejor_costo:
                    mejor, mejor_costo = actual[:], costo_actual

            historial.append(mejor_costo)
            historial_actual.append(costo_actual)
        T *= alfa

    return ResultadoLocal(
        algoritmo="Simulated Annealing",
        mejor_ruta=mejor,
        mejor_costo=mejor_costo,
        tiempo_ms=(time.perf_counter() - inicio) * 1000,
        evaluaciones=evaluaciones,
        historial=historial,
        extra={
            "historial_actual": historial_actual,
            "temperaturas": temperaturas,
            "soluciones_distintas": len(visitadas),
            "tasa_aceptacion_peores": aceptadas_peores / propuestas_peores if propuestas_peores else 0.0,
            "T0": T0, "alfa": alfa, "T_min": T_min, "iter_por_temp": iter_por_temp,
        },
    )


# =============================================================================
# 7. Algoritmo Genético
# =============================================================================
def seleccion_torneo(poblacion: list, costos: list, rng: random.Random, k: int = 3) -> list:
    """Toma k individuos al azar y devuelve el de menor costo. k = 3 da una
    presión selectiva moderada: los buenos se reproducen más, pero los
    mediocres todavía tienen oportunidad (conserva diversidad)."""
    competidores = rng.sample(range(len(poblacion)), k)
    ganador = min(competidores, key=lambda idx: costos[idx])
    return poblacion[ganador]


def algoritmo_genetico(D: list, indices: list, rng: random.Random,
                       tam_poblacion: int = 200, generaciones: int = 400,
                       prob_cruza: float = 0.9, prob_mutacion: float = 0.5,
                       elitismo: int = 2, tam_torneo: int = 3,
                       deposito: int = 0) -> ResultadoLocal:
    """
    Algoritmo Genético generacional con representación por permutación.

    Cada individuo es una permutación de las entregas (el cromosoma ES el
    orden de visita) y su aptitud es costo_ruta() (menor es mejor).
    En cada generación:
      1. Elitismo: los `elitismo` mejores pasan intactos (la curva del
         mejor costo nunca sube).
      2. Hasta completar la población:
           - dos padres por torneo de tamaño `tam_torneo`,
           - con probabilidad `prob_cruza` se cruzan con OX; si no, el
             hijo es copia del primer padre,
           - con probabilidad `prob_mutacion` el hijo sufre una mutación
             por intercambio.

    Parámetros por defecto: 200 individuos x 400 generaciones ≈ 80 000
    evaluaciones, del mismo orden que SA con α = 0.99 (≈92 000), para que
    la comparación calidad/tiempo sea justa. prob_cruza alta (0.9) porque
    OX es el operador que combina sub-recorridos buenos. prob_mutacion =
    0.5 se eligió probando 0.2, 0.3, 0.5 y 0.7 con 10 semillas: con 0.2 y
    0.3 la población pierde diversidad y converge prematuramente (algunas
    corridas quedan >10% arriba del óptimo); con 0.7 la mutación destruye
    demasiado lo que construye la cruza.

    Returns:
        ResultadoLocal con historial = mejor costo por generación (incluye
        la generación 0) y en `extra`: promedio de la población por
        generación y número de individuos distintos al final.
    """
    inicio = time.perf_counter()
    poblacion = [ruta_aleatoria(indices, rng) for _ in range(tam_poblacion)]
    costos = [costo_ruta(p, D, deposito) for p in poblacion]
    evaluaciones = tam_poblacion

    historial = [min(costos)]
    historial_promedio = [sum(costos) / len(costos)]

    for _ in range(generaciones):
        orden = sorted(range(tam_poblacion), key=lambda idx: costos[idx])
        nueva = [poblacion[idx][:] for idx in orden[:elitismo]]
        nuevos_costos = [costos[idx] for idx in orden[:elitismo]]

        while len(nueva) < tam_poblacion:
            padre1 = seleccion_torneo(poblacion, costos, rng, tam_torneo)
            padre2 = seleccion_torneo(poblacion, costos, rng, tam_torneo)
            if rng.random() < prob_cruza:
                hijo = cruza_ox(padre1, padre2, rng)
            else:
                hijo = padre1[:]
            if rng.random() < prob_mutacion:
                hijo = mutacion_intercambio(hijo, rng)
            nueva.append(hijo)
            nuevos_costos.append(costo_ruta(hijo, D, deposito))
            evaluaciones += 1

        poblacion, costos = nueva, nuevos_costos
        historial.append(min(costos))
        historial_promedio.append(sum(costos) / len(costos))

    idx_mejor = min(range(tam_poblacion), key=lambda idx: costos[idx])
    return ResultadoLocal(
        algoritmo="Algoritmo Genético",
        mejor_ruta=poblacion[idx_mejor][:],
        mejor_costo=costos[idx_mejor],
        tiempo_ms=(time.perf_counter() - inicio) * 1000,
        evaluaciones=evaluaciones,
        historial=historial,
        extra={
            "historial_promedio": historial_promedio,
            "individuos_distintos_final": len({tuple(p) for p in poblacion}),
            "tam_poblacion": tam_poblacion, "generaciones": generaciones,
            "prob_cruza": prob_cruza, "prob_mutacion": prob_mutacion,
            "elitismo": elitismo,
        },
    )


# =============================================================================
# 8. Óptimo exacto de referencia: Held-Karp
# =============================================================================
def optimo_held_karp(D: list, indices: list, deposito: int = 0) -> tuple:
    """
    Programación dinámica de Held-Karp (1962) para el TSP.

        C(S, k) = costo mínimo de salir del depósito, visitar exactamente el
                  conjunto S de entregas y terminar en la entrega k ∈ S.
        C({k}, k)   = D[depósito][k]
        C(S, k)     = min_{m ∈ S-{k}} C(S-{k}, m) + D[m][k]
        óptimo      = min_k C(todas, k) + D[k][depósito]

    Tiempo O(N²·2^N) y memoria O(N·2^N): con N = 15 son ~7 millones de
    operaciones, calculable en segundos; con N = 25 ya serían ~2·10^10.
    NO es uno de los algoritmos pedidos: se usa sólo para saber cuál es el
    costo óptimo real y medir qué tan cerca quedan SA y GA.

    Returns:
        (ruta_optima, costo_optimo)
    """
    n = len(indices)
    if n == 0:
        return [], 0.0
    if n > 18:
        raise ValueError(f"Held-Karp con N={n} requiere demasiada memoria (O(N·2^N)).")

    completo = (1 << n) - 1
    costo = [[math.inf] * n for _ in range(1 << n)]
    padre = [[-1] * n for _ in range(1 << n)]
    for k in range(n):
        costo[1 << k][k] = D[deposito][indices[k]]

    for S in range(1, 1 << n):
        fila = costo[S]
        for k in range(n):
            base = fila[k]
            if base == math.inf or not (S >> k) & 1:
                continue
            origen = indices[k]
            for m in range(n):
                if (S >> m) & 1:
                    continue
                S2 = S | (1 << m)
                nuevo = base + D[origen][indices[m]]
                if nuevo < costo[S2][m]:
                    costo[S2][m] = nuevo
                    padre[S2][m] = k

    mejor_costo, ultimo = math.inf, -1
    for k in range(n):
        total = costo[completo][k] + D[indices[k]][deposito]
        if total < mejor_costo:
            mejor_costo, ultimo = total, k

    # Reconstrucción hacia atrás
    ruta, S, k = [], completo, ultimo
    while k != -1:
        ruta.append(indices[k])
        S, k = S & ~(1 << k), padre[S][k]
    ruta.reverse()
    return ruta, mejor_costo


# =============================================================================
# 9. Paisaje de optimización
# =============================================================================
def analizar_paisaje(D: list, indices: list, rng: random.Random,
                     arranques: int = 300, deposito: int = 0) -> dict:
    """
    Muestrea el paisaje de optimización: corre busqueda_local_2opt() desde
    `arranques` rutas aleatorias y guarda el óptimo local al que cae cada
    una. La distribución de esos costos dice qué tan "rugoso" es el
    paisaje: si casi todos los arranques caen en el mismo valle, hill
    climbing bastaría; si hay muchos óptimos locales distintos y peores
    que el global, hace falta un método que escape de ellos (SA, GA).

    Returns:
        dict con costos_aleatorios, costos_optimos_locales y
        optimos_distintos (número de rutas distintas halladas).
    """
    costos_aleatorios, costos_locales, optimos = [], [], set()
    for _ in range(arranques):
        perm = ruta_aleatoria(indices, rng)
        costos_aleatorios.append(costo_ruta(perm, D, deposito))
        res = busqueda_local_2opt(perm, D, deposito)
        costos_locales.append(res.mejor_costo)
        optimos.add(tuple(res.mejor_ruta))
    return {
        "costos_aleatorios": costos_aleatorios,
        "costos_optimos_locales": costos_locales,
        "optimos_distintos": len(optimos),
    }


# =============================================================================
# 10. Utilidades del experimento
# =============================================================================
def pct_mejora(costo: float, referencia: float) -> float:
    """% de mejora de `costo` respecto a `referencia` (positivo = mejor)."""
    return 100 * (referencia - costo) / referencia if referencia else 0.0


def alfa_para_niveles(T0: float, T_min: float, niveles: int) -> float:
    """α tal que el enfriamiento geométrico va de T0 a T_min en `niveles`
    pasos: α = (T_min / T0)^(1 / niveles). Sirve para comparar distintos
    T0 con el MISMO número de iteraciones."""
    return (T_min / T0) ** (1 / niveles)


def ruta_en_nodos(perm: list, caminos: dict, deposito: int = 0) -> list:
    """Concatena los caminos A* de cada tramo del recorrido en una sola
    lista de nodos del grafo (para dibujarla)."""
    paradas = [deposito] + list(perm) + [deposito]
    nodos = []
    for a, b in zip(paradas, paradas[1:]):
        tramo = caminos[(a, b)]
        nodos.extend(tramo if not nodos else tramo[1:])
    return nodos


def guardar_mapa_recorrido(G, puntos: list, perm: list, caminos: dict,
                           ruta_salida: Path, perm_referencia: list = None,
                           titulo: str = "Mejor ruta") -> None:
    """
    Mapa folium con el recorrido completo sobre las calles reales, marcadores
    numerados en el orden de visita y, opcionalmente, una capa con una ruta
    de referencia (la aleatoria) para comparar visualmente.

    Args:
        puntos: lista de dicts con "nombre" y "nodo"; puntos[0] es el depósito.
    """
    def latlon(nodo):
        return G.nodes[nodo]["y"], G.nodes[nodo]["x"]

    dep = latlon(puntos[0]["nodo"])
    mapa = folium.Map(location=dep, zoom_start=15, tiles="OpenStreetMap")

    if perm_referencia is not None:
        capa_ref = folium.FeatureGroup(name="Ruta aleatoria (referencia)", show=False)
        folium.PolyLine([latlon(n) for n in ruta_en_nodos(perm_referencia, caminos)],
                        color="gray", weight=3, opacity=0.7).add_to(capa_ref)
        capa_ref.add_to(mapa)

    capa = folium.FeatureGroup(name=titulo)
    folium.PolyLine([latlon(n) for n in ruta_en_nodos(perm, caminos)],
                    color="blue", weight=4, opacity=0.85, tooltip=titulo).add_to(capa)
    for orden, idx in enumerate(perm, start=1):
        folium.Marker(
            latlon(puntos[idx]["nodo"]),
            tooltip=f"{orden}. {puntos[idx]['nombre']}",
            icon=folium.DivIcon(html=(
                '<div style="background:#1f4e9c;color:white;border-radius:50%;'
                'width:22px;height:22px;text-align:center;font:bold 12px/22px sans-serif;">'
                f'{orden}</div>')),
        ).add_to(capa)
    capa.add_to(mapa)

    folium.Marker(dep, popup=puntos[0]["nombre"],
                  icon=folium.Icon(color="red", icon="home")).add_to(mapa)
    folium.LayerControl().add_to(mapa)
    mapa.save(str(ruta_salida))


# =============================================================================
# 11. Gráficas (matplotlib)
# =============================================================================
def graficar_convergencia(corridas_sa: list, corridas_ga: list, optimo: float,
                          referencia_aleatoria: float, ruta_salida: Path) -> None:
    """Curvas de convergencia: mejor costo vs iteraciones de cada algoritmo
    (SA por propuesta, GA por generación) y ambos vs evaluaciones de f."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ejes = plt.subplots(1, 3, figsize=(17, 4.8))

    for k, res in enumerate(corridas_sa):
        ejes[0].plot(res.historial, color="tab:orange", alpha=0.9 if k == 0 else 0.25,
                     lw=1.4 if k == 0 else 0.8)
    ejes[0].set_title("Simulated Annealing")
    ejes[0].set_xlabel("Iteración (vecinos 2-opt propuestos)")

    for k, res in enumerate(corridas_ga):
        ejes[1].plot(res.historial, color="tab:green", alpha=0.9 if k == 0 else 0.25,
                     lw=1.4 if k == 0 else 0.8)
    ejes[1].set_title("Algoritmo Genético")
    ejes[1].set_xlabel("Generación")

    res_sa, res_ga = corridas_sa[0], corridas_ga[0]
    ejes[2].plot(range(len(res_sa.historial)), res_sa.historial,
                 color="tab:orange", label="SA")
    tam = res_ga.extra["tam_poblacion"]
    elite = res_ga.extra["elitismo"]
    x_ga = [tam + g * (tam - elite) for g in range(len(res_ga.historial))]
    ejes[2].plot(x_ga, res_ga.historial, color="tab:green", label="GA")
    ejes[2].set_title("Comparación con el mismo eje (semilla 0)")
    ejes[2].set_xlabel("Evaluaciones de la función objetivo")
    ejes[2].legend()

    for eje in ejes:
        eje.axhline(optimo, color="black", ls="--", lw=1, label="_óptimo")
        eje.axhline(referencia_aleatoria, color="gray", ls=":", lw=1)
        eje.set_ylabel("Mejor costo encontrado (m)")
        eje.grid(alpha=0.3)
    ejes[0].text(0.98, 0.93, "--- óptimo (Held-Karp)\n··· promedio aleatorio",
                 transform=ejes[0].transAxes, ha="right", va="top", fontsize=8)

    fig.suptitle("Curvas de convergencia (línea fuerte: semilla 0; tenues: otras semillas)")
    fig.tight_layout()
    fig.savefig(ruta_salida, dpi=120)
    plt.close(fig)


def graficar_calidad_vs_tiempo(df_corridas: pd.DataFrame, ruta_salida: Path) -> None:
    """Dispersión % de mejora sobre la solución aleatoria vs tiempo (ms)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, eje = plt.subplots(figsize=(7.5, 5))
    colores = {"Simulated Annealing": "tab:orange", "Algoritmo Genético": "tab:green",
               "2-opt (hill climbing)": "tab:blue", "Vecino más cercano": "tab:purple",
               "Vecino más cercano + 2-opt": "tab:red"}
    for metodo, grupo in df_corridas.groupby("Metodo"):
        eje.scatter(grupo["Tiempo_ms"], grupo["Mejora_pct"], label=metodo,
                    color=colores.get(metodo, "gray"), alpha=0.75)
    eje.set_xscale("log")
    eje.set_xlabel("Tiempo de cómputo (ms, escala log)")
    eje.set_ylabel("% de mejora sobre la ruta aleatoria promedio")
    eje.set_title("Calidad vs tiempo (cada punto = una corrida)")
    eje.grid(alpha=0.3)
    eje.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(ruta_salida, dpi=120)
    plt.close(fig)


def graficar_paisaje(paisaje: dict, optimo: float, finales_sa: list,
                     finales_ga: list, ruta_salida: Path) -> None:
    """Histograma de costos: rutas aleatorias vs óptimos locales 2-opt, con
    el óptimo global y los resultados finales de SA y GA marcados."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ejes = plt.subplots(1, 2, figsize=(14, 4.8))
    ejes[0].hist(paisaje["costos_aleatorios"], bins=30, color="lightgray",
                 edgecolor="gray", label="Rutas aleatorias")
    ejes[0].hist(paisaje["costos_optimos_locales"], bins=30, color="tab:blue",
                 alpha=0.8, label="Óptimos locales 2-opt")
    ejes[0].axvline(optimo, color="black", ls="--", label="Óptimo global")
    ejes[0].set_title("Espacio completo: aleatorias vs óptimos locales")

    ejes[1].hist(paisaje["costos_optimos_locales"], bins=30, color="tab:blue",
                 alpha=0.8, label="Óptimos locales 2-opt")
    ejes[1].axvline(optimo, color="black", ls="--", label="Óptimo global")
    for c in finales_sa:
        ejes[1].axvline(c, color="tab:orange", alpha=0.5, lw=1)
    for c in finales_ga:
        ejes[1].axvline(c, color="tab:green", alpha=0.5, lw=1, ls="-.")
    ejes[1].plot([], [], color="tab:orange", label="Finales SA")
    ejes[1].plot([], [], color="tab:green", ls="-.", label="Finales GA")
    ejes[1].set_title("Acercamiento: distribución de los óptimos locales")

    for eje in ejes:
        eje.set_xlabel("Costo de la ruta (m)")
        eje.set_ylabel("Frecuencia")
        eje.legend(fontsize=8)
        eje.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(ruta_salida, dpi=120)
    plt.close(fig)


def graficar_temperaturas(trazas: dict, ruta_salida: Path) -> None:
    """Costo de la ruta ACTUAL de SA a lo largo de las iteraciones para
    distintos T0: muestra cuánto se mueve (explora) el algoritmo."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, eje = plt.subplots(figsize=(10, 4.8))
    for etiqueta, traza in trazas.items():
        eje.plot(traza, lw=0.7, label=etiqueta)
    eje.set_xlabel("Iteración")
    eje.set_ylabel("Costo de la ruta actual (m)")
    eje.set_title("Efecto de T0 en la exploración de SA (mismo número de iteraciones)")
    eje.grid(alpha=0.3)
    eje.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(ruta_salida, dpi=120)
    plt.close(fig)


# =============================================================================
# 12. Experimento principal
# =============================================================================
SEMILLA = 42
CORRIDAS = 10


def ejecutar_fase3():
    """
    Punto de entrada de la Fase 3:
      1. Matriz de distancias reales con A* (Fase 2) entre depósito y entregas.
      2. Referencias: rutas aleatorias, vecino más cercano, 2-opt y óptimo exacto.
      3. SA y GA con CORRIDAS semillas cada uno.
      4. Curva de convergencia, calidad vs tiempo, paisaje y efecto de T0.
      5. Mapa de la mejor ruta y análisis.
    """
    print("=" * 70)
    print("  X-ROUTE — FASE 3: BÚSQUEDA LOCAL (Simulated Annealing y Genético)")
    print("=" * 70)

    raiz = Path(__file__).resolve().parent.parent
    carpeta = raiz / "resultados" / "fase3"
    carpeta.mkdir(parents=True, exist_ok=True)

    # ── 1. Datos y matriz de distancias ──────────────────────────────────────
    print("\n[1/6] Cargando grafo y calculando la matriz de distancias con A*...")
    G = cargar_grafo()
    ady = construir_adyacencia(G)
    datos = cargar_instancia(G)
    coords = extraer_coordenadas(G)

    puntos = [datos["deposito"]] + datos["entregas"]
    nodos = [p["nodo"] for p in puntos]

    inicio = time.perf_counter()
    D, caminos, expandidos = matriz_distancias_astar(ady, coords, nodos)
    tiempo_matriz = (time.perf_counter() - inicio) * 1000

    # Sólo se pueden recorrer las entregas con ruta de ida y vuelta al depósito
    # y hacia todas las demás (si no, cualquier orden que las incluya es inf).
    indices = [k for k in range(1, len(puntos))
               if all(D[k][m] < math.inf and D[m][k] < math.inf for m in range(len(puntos)))]
    excluidas = [puntos[k]["nombre"] for k in range(1, len(puntos)) if k not in indices]
    N = len(indices)

    print(f"      Grafo: {len(G.nodes)} nodos, {len(G.edges)} arcos")
    print(f"      Matriz {len(puntos)}x{len(puntos)}: {len(puntos) * (len(puntos) - 1)} "
          f"búsquedas A*, {expandidos} nodos expandidos, {tiempo_matriz:.1f} ms")
    if excluidas:
        print(f"      ⚠ Entregas excluidas por no tener ruta: {', '.join(excluidas)}")
    print(f"      Entregas a ordenar: N = {N} → {math.factorial(N):,} permutaciones")

    H = matriz_distancias_haversine(coords, nodos)
    factores = [D[a][b] / H[a][b] for a in range(len(nodos)) for b in range(len(nodos))
                if a != b and H[a][b] > 0 and D[a][b] < math.inf]
    factor_rodeo = sum(factores) / len(factores)
    print(f"      Factor de rodeo promedio (calle / línea recta): {factor_rodeo:.3f}")

    nombres = [p["nombre"] for p in puntos]
    pd.DataFrame(D, index=nombres, columns=nombres).round(1).to_csv(
        carpeta / "matriz_distancias_astar.csv")

    # ── 2. Referencias ───────────────────────────────────────────────────────
    print("\n[2/6] Soluciones de referencia...")
    rng = random.Random(SEMILLA)
    costos_aleatorios = [costo_ruta(ruta_aleatoria(indices, rng), D) for _ in range(1000)]
    referencia = sum(costos_aleatorios) / len(costos_aleatorios)
    perm_aleatoria = ruta_aleatoria(indices, random.Random(SEMILLA))

    inicio = time.perf_counter()
    ruta_opt, costo_opt = optimo_held_karp(D, indices)
    tiempo_hk = (time.perf_counter() - inicio) * 1000

    print(f"      Ruta aleatoria promedio (1000 muestras): {referencia:,.1f} m")
    print(f"      Ruta en orden de la lista (1, 2, ..., N): {costo_ruta(indices, D):,.1f} m")
    print(f"      Óptimo exacto (Held-Karp):               {costo_opt:,.1f} m "
          f"({tiempo_hk:,.0f} ms) → {pct_mejora(costo_opt, referencia):.1f}% de mejora")

    filas = []

    def registrar(metodo, semilla, res):
        filas.append({
            "Metodo": metodo, "Semilla": semilla,
            "Costo_m": round(res.mejor_costo, 1),
            "Mejora_pct": round(pct_mejora(res.mejor_costo, referencia), 2),
            "Gap_optimo_pct": round(100 * (res.mejor_costo - costo_opt) / costo_opt, 2),
            "Tiempo_ms": round(res.tiempo_ms, 2),
            "Evaluaciones": res.evaluaciones,
            "Ruta": str([nombres[k] for k in res.mejor_ruta]),
        })

    inicio = time.perf_counter()
    perm_nn = vecino_mas_cercano(D, indices)
    t_nn = (time.perf_counter() - inicio) * 1000
    registrar("Vecino más cercano", None,
              ResultadoLocal("Vecino más cercano", perm_nn, costo_ruta(perm_nn, D), t_nn, 1))
    res_nn2 = busqueda_local_2opt(perm_nn, D)
    res_nn2.tiempo_ms += t_nn
    registrar("Vecino más cercano + 2-opt", None, res_nn2)

    for s in range(CORRIDAS):
        registrar("2-opt (hill climbing)", s,
                  busqueda_local_2opt(ruta_aleatoria(indices, random.Random(SEMILLA + s)), D))

    # ── 3. SA y GA ───────────────────────────────────────────────────────────
    print(f"\n[3/6] Simulated Annealing y Algoritmo Genético ({CORRIDAS} semillas cada uno)...")
    T0, delta_prom = calcular_temperatura_inicial(D, indices, random.Random(SEMILLA))
    niveles = math.ceil(math.log(T_MIN / T0) / math.log(ALFA))
    iter_temp = N * (N - 1) // 2
    print(f"      SA: Δ̄ de empeoramiento = {delta_prom:.1f} m → T0 = {T0:.1f}, "
          f"α = {ALFA}, T_min = {T_MIN} → {niveles} niveles x {iter_temp} iter "
          f"= {niveles * iter_temp:,} iteraciones")

    corridas_sa, corridas_ga = [], []
    for s in range(CORRIDAS):
        res = simulated_annealing(D, indices, random.Random(SEMILLA + s), T0)
        corridas_sa.append(res)
        registrar("Simulated Annealing", s, res)

        res = algoritmo_genetico(D, indices, random.Random(SEMILLA + s))
        corridas_ga.append(res)
        registrar("Algoritmo Genético", s, res)

    df = pd.DataFrame(filas)
    df.to_csv(carpeta / "resultados_fase3.csv", index=False)

    resumen = df.groupby("Metodo", sort=False).agg(
        Corridas=("Costo_m", "size"),
        Costo_medio=("Costo_m", "mean"),
        Mejor=("Costo_m", "min"),
        Peor=("Costo_m", "max"),
        Desv_std=("Costo_m", "std"),
        Mejora_media_pct=("Mejora_pct", "mean"),
        Gap_medio_pct=("Gap_optimo_pct", "mean"),
        Veces_optimo=("Gap_optimo_pct", lambda g: int((g <= 0.001).sum())),
        Tiempo_medio_ms=("Tiempo_ms", "mean"),
        Evaluaciones_medias=("Evaluaciones", "mean"),
    ).round(2).reset_index()
    resumen.to_csv(carpeta / "resumen_fase3.csv", index=False)

    pd.set_option("display.width", 200)
    print("\n" + resumen.to_string(index=False))
    print("\n      Tablas → resultados/fase3/resultados_fase3.csv y resumen_fase3.csv")

    # ── 4. Paisaje de optimización ───────────────────────────────────────────
    print("\n[4/6] Paisaje de optimización (2-opt desde 300 arranques aleatorios)...")
    paisaje = analizar_paisaje(D, indices, random.Random(SEMILLA + 1000), arranques=300)
    locales = pd.Series(paisaje["costos_optimos_locales"])
    en_optimo = int((locales <= costo_opt + 1e-6).sum())
    print(f"      Óptimos locales distintos: {paisaje['optimos_distintos']} de 300 arranques")
    print(f"      Costo de los óptimos locales: min {locales.min():,.1f}, "
          f"mediana {locales.median():,.1f}, max {locales.max():,.1f} m")
    print(f"      Arranques que llegan al óptimo global: {en_optimo}/300 "
          f"({100 * en_optimo / 300:.1f}%)")
    pd.DataFrame({
        "Costo_aleatorio_inicial": paisaje["costos_aleatorios"],
        "Costo_optimo_local": paisaje["costos_optimos_locales"],
    }).round(1).to_csv(carpeta / "paisaje_fase3.csv", index=False)

    # ── 5. Efecto de T0 ──────────────────────────────────────────────────────
    print("\n[5/6] Efecto de la temperatura inicial T0 (mismo número de iteraciones)...")
    filas_t0, trazas = [], {}
    for factor in (0.01, 0.1, 1.0, 10.0):
        T0_prueba = T0 * factor
        alfa_prueba = alfa_para_niveles(T0_prueba, T_MIN, niveles)
        for s in range(5):
            res = simulated_annealing(D, indices, random.Random(SEMILLA + s), T0_prueba,
                                      alfa=alfa_prueba)
            filas_t0.append({
                "Factor_T0": factor, "T0": round(T0_prueba, 1), "alfa": round(alfa_prueba, 4),
                "Semilla": s, "Costo_final_m": round(res.mejor_costo, 1),
                "Soluciones_distintas": res.extra["soluciones_distintas"],
                "Aceptacion_peores_pct": round(100 * res.extra["tasa_aceptacion_peores"], 2),
            })
            if s == 0:
                trazas[f"T0 = {factor:g}·T0 ({T0_prueba:,.0f})"] = res.extra["historial_actual"]
    df_t0 = pd.DataFrame(filas_t0)
    df_t0.to_csv(carpeta / "temperatura_inicial_fase3.csv", index=False)
    resumen_t0 = df_t0.groupby(["Factor_T0", "T0"]).agg(
        Costo_medio=("Costo_final_m", "mean"),
        Soluciones_distintas=("Soluciones_distintas", "mean"),
        Aceptacion_peores_pct=("Aceptacion_peores_pct", "mean"),
    ).round(1).reset_index()
    print("\n" + resumen_t0.to_string(index=False))

    # ── 6. Gráficas y mapa ───────────────────────────────────────────────────
    print("\n[6/6] Generando gráficas y mapa...")
    graficar_convergencia(corridas_sa, corridas_ga, costo_opt, referencia,
                          carpeta / "convergencia_fase3.png")
    graficar_calidad_vs_tiempo(df, carpeta / "calidad_vs_tiempo_fase3.png")
    graficar_paisaje(paisaje, costo_opt, [r.mejor_costo for r in corridas_sa],
                     [r.mejor_costo for r in corridas_ga], carpeta / "paisaje_fase3.png")
    graficar_temperaturas(trazas, carpeta / "temperatura_inicial_fase3.png")

    mejor = min(corridas_sa + corridas_ga, key=lambda r: r.mejor_costo)
    guardar_mapa_recorrido(G, puntos, mejor.mejor_ruta, caminos,
                           carpeta / "mapa_mejor_ruta.html", perm_referencia=perm_aleatoria,
                           titulo=f"{mejor.algoritmo}: {mejor.mejor_costo:,.0f} m")
    print("      convergencia_fase3.png, calidad_vs_tiempo_fase3.png, paisaje_fase3.png,")
    print("      temperatura_inicial_fase3.png y mapa_mejor_ruta.html en resultados/fase3/")
    print(f"\n      Mejor ruta ({mejor.algoritmo}, {mejor.mejor_costo:,.1f} m):")
    print("      Depósito → " + " → ".join(nombres[k] for k in mejor.mejor_ruta) + " → Depósito")

    _imprimir_analisis(N, resumen, resumen_t0, referencia, costo_opt, factor_rodeo)

    print("\n" + "=" * 70)
    print("  Fase 3 completada. Archivos en resultados/fase3/")
    print("=" * 70)


def _imprimir_analisis(N, resumen, resumen_t0, referencia, costo_opt, factor_rodeo):
    """Respuestas a las tres preguntas de análisis de la Fase 3, con los
    números de la corrida actual."""
    fila = resumen.set_index("Metodo")
    sa, ga = fila.loc["Simulated Annealing"], fila.loc["Algoritmo Genético"]
    arbol = sum(math.factorial(N) // math.factorial(N - k) for k in range(N + 1))
    tabla_t0 = "\n".join(
        f"  {f['Factor_T0']:>5g}·T0 = {f['T0']:>9,.1f}  {f['Soluciones_distintas']:>10,.0f}"
        f"  {f['Aceptacion_peores_pct']:>12.1f}%  {f['Costo_medio']:>12,.1f} m"
        for _, f in resumen_t0.iterrows())
    ga_mejor = ga["Gap_medio_pct"] < sa["Gap_medio_pct"]
    mas_calidad, menos_calidad = ("el GA", "SA") if ga_mejor else ("SA", "el GA")
    razon_tiempo = ga["Tiempo_medio_ms"] / sa["Tiempo_medio_ms"]
    ms_por_eval_sa = sa["Tiempo_medio_ms"] / sa["Evaluaciones_medias"] * 1000
    ms_por_eval_ga = ga["Tiempo_medio_ms"] / ga["Evaluaciones_medias"] * 1000

    print(f"""
{"=" * 70}
  ANÁLISIS — PREGUNTAS DE LA FASE 3
{"=" * 70}

─────────────────────────────────────────────────────────────────
P1. ¿Por qué no se puede aplicar A* directamente al problema de N
    entregas? Tamaño del espacio de estados para N = 15.
─────────────────────────────────────────────────────────────────
Estados completos (órdenes de visita): 15! = {math.factorial(15):,}
En esta corrida N = {N}: {math.factorial(N):,} permutaciones.

A* busca un camino hacia UN nodo meta en un grafo explícito. Aquí la
"meta" no es un lugar sino una condición sobre la secuencia entera
("visité todas las entregas"), y el costo de cada decisión depende de
todo lo que ya se visitó. Para usar A* habría que construir un árbol
de rutas parciales (depósito → a → b → ...): tiene Σ N!/(N-k)!
= {arbol:,} nodos para N = {N}. Aun con una buena heurística
(p. ej. un árbol de expansión mínima de las entregas pendientes), la
frontera de A* crece exponencialmente y se queda sin memoria mucho
antes de terminar. Incluso la programación dinámica exacta (Held-Karp,
O(N²·2^N)) sólo es viable aquí porque N = 15 es chico.

Por eso se usa BÚSQUEDA LOCAL: trabaja sobre rutas completas, guarda
sólo la ruta actual (o una población), y mejora con cambios pequeños
(2-opt, OX, intercambio). No garantiza el óptimo, pero da rutas muy
buenas en milisegundos. A* sí se usa, pero donde sí aplica: para
calcular la distancia real entre cada par de puntos (la matriz D).
El factor de rodeo promedio de esta instancia es {factor_rodeo:.2f}: las
calles son ~{100 * (factor_rodeo - 1):.0f}% más largas que la línea recta, por eso
se usó la matriz de A* y no costo_entre_puntos() (Haversine).

─────────────────────────────────────────────────────────────────
P2. ¿Cómo afecta la temperatura inicial T0 de SA a la diversidad de
    soluciones exploradas?
─────────────────────────────────────────────────────────────────
T0 controla la probabilidad exp(-Δ/T) de aceptar una ruta peor. Se
corrió SA con 4 valores de T0 y el MISMO número de iteraciones (α se
ajusta para llegar a T_min en los mismos niveles), 5 semillas cada uno:

        T0                Soluciones   Empeoramientos    Costo final
                          distintas    aceptados         medio
{tabla_t0}

A mayor T0, más diversidad: se aceptan más empeoramientos y la cadena
visita muchas más rutas distintas (ver temperatura_inicial_fase3.png:
con T0 alto el costo de la ruta actual salta por todo el espacio al
inicio y se va asentando conforme T baja). Con T0 muy bajo SA casi sólo
acepta mejoras: se comporta como hill climbing y se atora en el primer
óptimo local, con rutas mucho peores. A partir de un T0 suficiente para
escapar de los óptimos locales, la calidad final se estabiliza: subir
más T0 sólo agrega exploración inicial poco útil (la ruta actual es casi
aleatoria) y, si α no se ajusta, alarga la corrida. Por eso T0 se
calibra con la instancia (p0 = 0.8 de aceptar el empeoramiento
promedio) en vez de fijarlo a mano.

─────────────────────────────────────────────────────────────────
P3. ¿Cómo se compara el Algoritmo Genético respecto a SA en términos
    de calidad/tiempo?
─────────────────────────────────────────────────────────────────
                      Costo medio   Gap vs óptimo   Veces óptimo   Tiempo medio
  Simulated Annealing {sa['Costo_medio']:>10,.1f} m  {sa['Gap_medio_pct']:>11.2f}%  {int(sa['Veces_optimo']):>8}/{int(sa['Corridas'])}  {sa['Tiempo_medio_ms']:>10,.1f} ms
  Algoritmo Genético  {ga['Costo_medio']:>10,.1f} m  {ga['Gap_medio_pct']:>11.2f}%  {int(ga['Veces_optimo']):>8}/{int(ga['Corridas'])}  {ga['Tiempo_medio_ms']:>10,.1f} ms

(Ruta aleatoria promedio: {referencia:,.1f} m; óptimo Held-Karp: {costo_opt:,.1f} m.)

Con presupuestos parecidos ({sa['Evaluaciones_medias']:,.0f} evaluaciones SA vs
{ga['Evaluaciones_medias']:,.0f} GA), {mas_calidad} quedó más cerca del óptimo que {menos_calidad},
pero el GA tardó {razon_tiempo:.1f} veces más ({ms_por_eval_ga:.1f} µs por evaluación vs
{ms_por_eval_sa:.1f} µs en SA): además de evaluar, cada generación ordena la
población, hace torneos y copia listas, mientras que SA sólo genera un
vecino y lo compara.

¿Por qué el GA puede ganar en calidad en ESTA instancia? La matriz es
asimétrica (calles de un solo sentido). 2-opt invierte un tramo, así
que obliga a recorrer al revés todas sus calles, y la mayoría de esos
movimientos empeoran mucho: el paisaje bajo 2-opt es muy rugoso (ver
paisaje_fase3.png). OX, en cambio, copia sub-recorridos SIN invertirlos
y conserva el orden relativo del otro padre, y la mutación por
intercambio tampoco invierte nada; además la población explora muchos
valles a la vez. SA depende de un solo recorrido y de enfriar despacio.

Conclusión práctica: si se necesita una buena ruta rápido, SA es la
mejor relación calidad/tiempo; si se puede esperar ~1 s y se
quiere acercarse más al óptimo de forma consistente, conviene el GA
(o un híbrido GA + 2-opt, "algoritmo memético"). Revisa
calidad_vs_tiempo_fase3.png y convergencia_fase3.png.
""")


if __name__ == "__main__":
    ejecutar_fase3()
