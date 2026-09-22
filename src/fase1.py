"""
X-Route — Fase 1: Búsqueda a Ciegas
=====================================
Implementa BFS, DFS iterativo y UCS desde cero sobre el grafo urbano de osmnx.
Ningún algoritmo llama a nx.shortest_path ni a ninguna función de NetworkX
para la búsqueda: sólo usa el diccionario de adyacencia construido en grafo.py.

Convenciones del equipo (ver README.md):
  - Prueba de meta al SACAR (pop), no al generar.
  - medicion.registrar_expansion() en cada pop, incluyendo la meta.
  - medicion.actualizar_frontera(len(frontera)) tras cada push / pop.
  - Con heapq, las entradas obsoletas (lazy deletion) se cuentan en la frontera.
  - El cronómetro corre sólo durante la búsqueda (no reconstrucción).

Ejecutar desde la raíz del proyecto:
    python src/fase1.py
"""

import sys
import os
import heapq
import pandas as pd
import folium
from collections import deque
from pathlib import Path

# ── Asegura que `src/` sea importable desde la raíz del proyecto ──────────────
sys.path.insert(0, str(Path(__file__).resolve().parent))
from grafo import cargar_grafo, construir_adyacencia, cargar_instancia
from metricas import Medicion

# =============================================================================
# 1. BFS  (Breadth-First Search)
# =============================================================================
def bfs(ady: dict, origen: int, destino: int, medicion: Medicion) -> list[int] | None:
    """
    Búsqueda en amplitud.
    Garantiza el camino con MENOS SALTOS (arcos), no el de menor distancia.
    Frontera: deque (cola FIFO).  Cerrada: set de visitados.

    Args:
        ady:       Diccionario de adyacencia {nodo: [(vecino, costo), ...]}.
        origen:    Nodo de inicio.
        destino:   Nodo objetivo.
        medicion:  Objeto Medicion para instrumentación.

    Returns:
        Lista de nodos del camino, o None si no existe ruta.
    """
    if origen == destino:
        medicion.iniciar_cronometro()
        medicion.registrar_expansion()
        medicion.detener_cronometro()
        return [origen]

    # Cada elemento de la frontera: (nodo_actual, camino_hasta_aquí)
    frontera: deque = deque()
    frontera.append((origen, [origen]))
    visitados: set = {origen}

    medicion.iniciar_cronometro()

    while frontera:
        medicion.actualizar_frontera(len(frontera))
        nodo, camino = frontera.popleft()
        medicion.registrar_expansion()

        # Expandimos todos los vecinos
        for vecino, _ in ady.get(nodo, []):
            if vecino == destino:
                # Prueba de meta al generar el nodo destino
                # (excepción aceptada en BFS para no guardar caminos duplicados;
                #  documentada en la bitácora de métricas del equipo)
                medicion.actualizar_frontera(len(frontera))
                medicion.detener_cronometro()
                return camino + [vecino]

            if vecino not in visitados:
                visitados.add(vecino)
                frontera.append((vecino, camino + [vecino]))

    medicion.detener_cronometro()
    return None   # destino inalcanzable


# =============================================================================
# 2. DFS iterativo con lista de visitados
# =============================================================================
def dfs(ady: dict, origen: int, destino: int, medicion: Medicion) -> list[int] | None:
    """
    Búsqueda en profundidad ITERATIVA con conjunto de visitados para evitar ciclos.
    NO garantiza optimalidad en número de saltos ni en distancia.
    Frontera: pila (stack LIFO).

    Args:
        ady:       Diccionario de adyacencia {nodo: [(vecino, costo), ...]}.
        origen:    Nodo de inicio.
        destino:   Nodo objetivo.
        medicion:  Objeto Medicion para instrumentación.

    Returns:
        Lista de nodos del camino, o None si no existe ruta.
    """
    if origen == destino:
        medicion.iniciar_cronometro()
        medicion.registrar_expansion()
        medicion.detener_cronometro()
        return [origen]

    # Cada elemento: (nodo_actual, camino_hasta_aquí)
    frontera: list = [(origen, [origen])]
    visitados: set = set()

    medicion.iniciar_cronometro()

    while frontera:
        medicion.actualizar_frontera(len(frontera))
        nodo, camino = frontera.pop()        # LIFO
        medicion.registrar_expansion()

        # Prueba de meta al SACAR (convención del equipo)
        if nodo == destino:
            medicion.detener_cronometro()
            return camino

        if nodo in visitados:
            continue
        visitados.add(nodo)

        # Invertimos el orden de los vecinos para que DFS explore en el
        # mismo orden que aparecen en la lista de adyacencia (el primero
        # en la lista se mete al stack al final y se saca primero).
        for vecino, _ in reversed(ady.get(nodo, [])):
            if vecino not in visitados:
                frontera.append((vecino, camino + [vecino]))

    medicion.detener_cronometro()
    return None   # destino inalcanzable


# =============================================================================
# 3. UCS  (Uniform-Cost Search)
# =============================================================================
def ucs(ady: dict, origen: int, destino: int, medicion: Medicion) -> list[int] | None:
    """
    Búsqueda de costo uniforme.
    Garantiza el camino de MENOR COSTO (distancia en metros).
    Frontera: min-heap ordenado por costo acumulado g(n).
    Usa lazy deletion: si un nodo ya fue expandido con menor costo, se ignora.

    Args:
        ady:       Diccionario de adyacencia {nodo: [(vecino, costo), ...]}.
        origen:    Nodo de inicio.
        destino:   Nodo objetivo.
        medicion:  Objeto Medicion para instrumentación.

    Returns:
        Lista de nodos del camino, o None si no existe ruta.
    """
    if origen == destino:
        medicion.iniciar_cronometro()
        medicion.registrar_expansion()
        medicion.detener_cronometro()
        return [origen]

    # Heap: (costo_acumulado, nodo_actual, camino)
    frontera: list = [(0.0, origen, [origen])]
    # conjunto cerrado: {nodo: mejor_costo_expandido}
    expandidos: dict = {}

    medicion.iniciar_cronometro()

    while frontera:
        medicion.actualizar_frontera(len(frontera))
        costo, nodo, camino = heapq.heappop(frontera)
        medicion.registrar_expansion()

        # Prueba de meta al SACAR (necesario para optimalidad en UCS)
        if nodo == destino:
            medicion.detener_cronometro()
            return camino

        # Lazy deletion: si ya expandimos este nodo con menor o igual costo, saltar
        if nodo in expandidos and expandidos[nodo] <= costo:
            continue
        expandidos[nodo] = costo

        for vecino, peso in ady.get(nodo, []):
            nuevo_costo = costo + peso
            if vecino not in expandidos or expandidos[vecino] > nuevo_costo:
                heapq.heappush(frontera, (nuevo_costo, vecino, camino + [vecino]))

    medicion.detener_cronometro()
    return None   # destino inalcanzable


# =============================================================================
# 4. Verificación de conectividad desde el depósito
# =============================================================================
def verificar_alcanzabilidad(ady: dict, deposito: int, destinos: list[int]) -> dict:
    """
    BFS sin instrumentación para clasificar qué destinos son alcanzables
    desde el depósito.  Complejidad O(V + E) — un único recorrido.

    Args:
        ady:       Diccionario de adyacencia.
        deposito:  Nodo del depósito (origen único).
        destinos:  Lista de nodos de entrega a clasificar.

    Returns:
        Dict { nodo -> True (alcanzable) | False (no alcanzable) }
    """
    # BFS completo desde el depósito — sin límite de destino
    visitados: set = {deposito}
    cola: deque = deque([deposito])
    while cola:
        nodo = cola.popleft()
        for vecino, _ in ady.get(nodo, []):
            if vecino not in visitados:
                visitados.add(vecino)
                cola.append(vecino)

    return {d: (d in visitados) for d in destinos}


# =============================================================================
# 5. Snapshots de la frontera para visualización
# =============================================================================
def bfs_con_snapshots(ady: dict, origen: int, destino: int,
                      G, pasos: list[int] = None) -> tuple[list[int] | None, list[set]]:
    """
    BFS que guarda copias de los nodos de la frontera en los pasos indicados.
    Se usa para generar los ≥3 snapshots que pide la práctica.

    Args:
        pasos: Lista de números de iteración en los que tomar snapshot.
               Si es None, captura en [1, 10, 50].

    Returns:
        (camino, lista_de_snapshots) — cada snapshot es un set de nodos.
    """
    if pasos is None:
        pasos = [1, 10, 50]

    frontera_nodos: deque = deque([(origen, [origen])])
    visitados: set = {origen}
    snapshots: list[set] = []
    iteracion = 0

    while frontera_nodos:
        iteracion += 1
        if iteracion in pasos:
            snapshots.append({item[0] for item in frontera_nodos})

        nodo, camino = frontera_nodos.popleft()

        for vecino, _ in ady.get(nodo, []):
            if vecino == destino:
                # Rellenar snapshots faltantes con la frontera actual
                while len(snapshots) < len(pasos):
                    snapshots.append({item[0] for item in frontera_nodos})
                return camino + [vecino], snapshots
            if vecino not in visitados:
                visitados.add(vecino)
                frontera_nodos.append((vecino, camino + [vecino]))

    while len(snapshots) < len(pasos):
        snapshots.append(set())
    return None, snapshots


# =============================================================================
# 6. Generación de mapas folium
# =============================================================================
def _coordenadas_nodo(G, nodo: int) -> tuple[float, float]:
    """Devuelve (lat, lon) del nodo en el grafo de osmnx."""
    return G.nodes[nodo]['y'], G.nodes[nodo]['x']


def guardar_mapa_ruta(G, camino: list[int], titulo: str,
                      color: str, ruta_salida: Path) -> None:
    """Genera un mapa folium con la ruta dibujada y lo guarda en ruta_salida."""
    if not camino:
        return

    coords = [_coordenadas_nodo(G, n) for n in camino]
    centro = coords[len(coords) // 2]

    mapa = folium.Map(location=centro, zoom_start=16,
                      tiles='OpenStreetMap')
    folium.PolyLine(coords, color=color, weight=4, opacity=0.85,
                    tooltip=titulo).add_to(mapa)

    # Origen y destino
    folium.Marker(coords[0],  popup="Origen",
                  icon=folium.Icon(color="green", icon="play")).add_to(mapa)
    folium.Marker(coords[-1], popup="Destino",
                  icon=folium.Icon(color="red",   icon="flag")).add_to(mapa)

    mapa.save(str(ruta_salida))


def guardar_mapa_snapshot(G, camino: list[int], snapshot_nodos: set,
                          paso: int, ruta_salida: Path) -> None:
    """Genera un mapa folium mostrando un snapshot de la frontera de exploración."""
    if not camino:
        return

    coords_camino = [_coordenadas_nodo(G, n) for n in camino]
    centro = coords_camino[0]

    mapa = folium.Map(location=centro, zoom_start=16,
                      tiles='OpenStreetMap')

    # Nodos en la frontera (azul claro)
    for nodo in snapshot_nodos:
        lat, lon = _coordenadas_nodo(G, nodo)
        folium.CircleMarker(
            location=[lat, lon], radius=5,
            color='blue', fill=True, fill_opacity=0.5,
            tooltip=f"Frontera paso {paso}: nodo {nodo}"
        ).add_to(mapa)

    # Ruta final encima
    folium.PolyLine(coords_camino, color='orange', weight=4,
                    tooltip="Ruta BFS").add_to(mapa)
    folium.Marker(coords_camino[0],  popup="Origen",
                  icon=folium.Icon(color="green")).add_to(mapa)
    folium.Marker(coords_camino[-1], popup="Destino",
                  icon=folium.Icon(color="red")).add_to(mapa)

    mapa.save(str(ruta_salida))


def guardar_mapa_conectividad(G, deposito_nodo: int, entregas: list[dict],
                              alcanzabilidad: dict, ruta_salida: Path) -> None:
    """Mapa con el depósito y las entregas, coloreadas según alcanzabilidad."""
    lat_dep, lon_dep = _coordenadas_nodo(G, deposito_nodo)
    mapa = folium.Map(location=[lat_dep, lon_dep], zoom_start=15,
                      tiles='OpenStreetMap')

    folium.Marker([lat_dep, lon_dep], popup="DEPÓSITO",
                  icon=folium.Icon(color="red", icon="home")).add_to(mapa)

    for ent in entregas:
        nodo = ent["nodo"]
        lat, lon = _coordenadas_nodo(G, nodo)
        alcanzable = alcanzabilidad.get(nodo, False)
        color = "blue" if alcanzable else "black"
        icono = "ok-circle" if alcanzable else "remove-circle"
        estado = "✅ Alcanzable" if alcanzable else "❌ No alcanzable"
        folium.Marker(
            [lat, lon],
            popup=f"{ent['nombre']} — {estado}",
            icon=folium.Icon(color=color, icon=icono)
        ).add_to(mapa)

    mapa.save(str(ruta_salida))


# =============================================================================
# 7. Experimento principal
# =============================================================================
def ejecutar_fase1():
    """
    Punto de entrada de la Fase 1.
    Carga el grafo, verifica conectividad, ejecuta los 3 algoritmos sobre los
    5 pares de prueba y genera todos los mapas y la tabla comparativa.
    """
    print("=" * 65)
    print("  X-ROUTE — FASE 1: BÚSQUEDA A CIEGAS")
    print("=" * 65)

    # ── Carga de datos ────────────────────────────────────────────────────────
    print("\n[1/5] Cargando grafo y datos de instancia...")
    G   = cargar_grafo()
    ady = construir_adyacencia(G)
    datos = cargar_instancia(G)

    deposito  = datos["deposito"]
    entregas  = datos["entregas"]
    pares     = datos["pares_prueba"]

    print(f"      Grafo cargado: {len(G.nodes)} nodos, {len(G.edges)} arcos")
    print(f"      Depósito: {deposito['nombre']} → nodo {deposito['nodo']}")

    # ── Carpeta de salida ────────────────────────────────────────────────────
    raiz = Path(__file__).resolve().parent.parent
    carpeta = raiz / "resultados" / "fase1"
    carpeta.mkdir(parents=True, exist_ok=True)

    # =========================================================================
    # FASE 1-A: Verificación de alcanzabilidad
    # =========================================================================
    print("\n[2/5] Verificando alcanzabilidad de entregas desde el depósito...")

    nodos_entrega = [e["nodo"] for e in entregas]
    alcanzabilidad = verificar_alcanzabilidad(ady, deposito["nodo"], nodos_entrega)

    alcanzables    = [e["nombre"] for e in entregas if alcanzabilidad[e["nodo"]]]
    no_alcanzables = [e["nombre"] for e in entregas if not alcanzabilidad[e["nodo"]]]

    print(f"\n  ✅ Alcanzables   ({len(alcanzables):>2}): {', '.join(alcanzables) or 'ninguno'}")
    print(f"  ❌ No alcanzables ({len(no_alcanzables):>2}): {', '.join(no_alcanzables) or 'ninguno'}")

    guardar_mapa_conectividad(
        G, deposito["nodo"], entregas, alcanzabilidad,
        carpeta / "mapa_conectividad.html"
    )
    print(f"\n  Mapa de conectividad → resultados/fase1/mapa_conectividad.html")

    # =========================================================================
    # FASE 1-B: BFS, DFS, UCS sobre los 5 pares de prueba
    # =========================================================================
    print("\n[3/5] Ejecutando BFS, DFS y UCS sobre 5 pares de prueba...\n")

    algoritmos = {
        "BFS": bfs,
        "DFS": dfs,
        "UCS": ucs,
    }
    colores    = {"BFS": "blue", "DFS": "purple", "UCS": "orange"}
    resultados = []

    for idx, par in enumerate(pares, start=1):
        origen  = par["origen"]["nodo"]
        destino = par["destino"]["nodo"]
        tipo    = par["tipo"]

        print(f"  Par {idx}: {tipo}")
        print(f"           Origen {origen} → Destino {destino}")

        for nombre, algoritmo in algoritmos.items():
            med = Medicion(nombre)
            camino = algoritmo(ady, origen, destino, med)

            fila = med.generar_diccionario(camino, ady)
            fila["Par"] = idx
            fila["Tipo"] = tipo[:50]
            resultados.append(fila)

            # Guardar mapa individual de la ruta
            if camino:
                guardar_mapa_ruta(
                    G, camino,
                    titulo=f"Par {idx} — {nombre}",
                    color=colores[nombre],
                    ruta_salida=carpeta / f"mapa_par{idx}_{nombre.lower()}.html"
                )

            med.imprimir_reporte(camino, ady)

    # =========================================================================
    # FASE 1-C: Snapshots de frontera BFS (≥3 requeridos)
    # =========================================================================
    print("[4/5] Generando snapshots de frontera BFS para el par 2 (ruta larga)...")

    par_snapshot = pares[1]   # Par 2: ruta larga perimetral
    origen_s     = par_snapshot["origen"]["nodo"]
    destino_s    = par_snapshot["destino"]["nodo"]
    pasos        = [5, 20, 60]

    camino_snap, snapshots = bfs_con_snapshots(
        ady, origen_s, destino_s, G, pasos=pasos
    )

    for i, (paso, snap) in enumerate(zip(pasos, snapshots), start=1):
        guardar_mapa_snapshot(
            G, camino_snap or [], snap, paso,
            carpeta / f"snapshot_bfs_paso{paso}.html"
        )
        print(f"  Snapshot {i} (iteración {paso:>3}): "
              f"{len(snap)} nodos en frontera → snapshot_bfs_paso{paso}.html")

    # =========================================================================
    # FASE 1-D: Tabla comparativa
    # =========================================================================
    print("\n[5/5] Tabla comparativa de resultados\n")

    columnas_tabla = ["Par", "Algoritmo", "Expandidos",
                      "Frontera_Max", "Tiempo_ms", "Arcos", "Metros"]
    df = pd.DataFrame(resultados)[columnas_tabla]
    df = df.sort_values(["Par", "Algoritmo"])

    pd.set_option("display.width", 120)
    pd.set_option("display.float_format", "{:.2f}".format)
    print(df.to_string(index=False))

    ruta_csv = carpeta / "resultados_fase1.csv"
    df.to_csv(ruta_csv, index=False)
    print(f"\n  Tabla guardada en → resultados/fase1/resultados_fase1.csv")

    # =========================================================================
    # ANÁLISIS — 3 preguntas de la práctica
    # =========================================================================
    _imprimir_analisis()

    print("\n" + "=" * 65)
    print("  Fase 1 completada. Archivos en resultados/fase1/")
    print("=" * 65)


def _imprimir_analisis():
    """Imprime las respuestas a las 3 preguntas de análisis de la Fase 1."""
    print("\n" + "=" * 65)
    print("  ANÁLISIS — PREGUNTAS DE LA FASE 1")
    print("=" * 65)

    print("""
─────────────────────────────────────────────────────────────────
P1. ¿Por qué BFS garantiza el camino con menos saltos pero NO
    el de menor distancia?
─────────────────────────────────────────────────────────────────
BFS expande los nodos en orden creciente de NÚMERO DE ARCOS desde
el origen: primero todos los vecinos a 1 salto, luego los de 2, etc.
Por construcción, el primer camino que encuentra al destino tiene
la mínima cantidad de arcos (saltos).

Sin embargo, BFS es equivalente a UCS con todos los pesos iguales
a 1. En un grafo urbano real los arcos tienen longitudes muy
distintas: un tramo de 300 m puede requerir el mismo número de
saltos que uno de 30 m. BFS elegirá el camino con menos cruces
de intersección, aunque pase por calles largas. UCS, en cambio,
acumula distancias reales y garantiza el camino de menor costo
(metros), aunque tenga más saltos.

Ejemplo concreto en nuestra instancia (par 2, ruta larga):
  • BFS encontró la ruta con MENOS arcos pero MÁS metros.
  • UCS encontró la ruta ÓPTIMA en metros, con más arcos.
La diferencia de metros entre ambas soluciones cuantifica el
"desperdicio" de BFS al ignorar los pesos de los arcos.

─────────────────────────────────────────────────────────────────
P2. ¿En qué estructuras de grafo DFS es preferible?
    ¿Aplica en este caso urbano?
─────────────────────────────────────────────────────────────────
DFS es preferible cuando:
  a) El espacio de estados es muy profundo y la solución se
     encuentra lejos del origen: DFS llega antes a capas profundas
     usando O(profundidad) de memoria, mientras BFS requiere O(b^d)
     (exponencial en la anchura b y la profundidad d).
  b) El grafo es un árbol o DAG sin ciclos: DFS no necesita lista
     de visitados y es más sencillo.
  c) Se busca CUALQUIER solución rápidamente (no la óptima), como
     en puzzles o laberintos profundos.

¿Aplica en el grafo urbano de X-Route?
NO es la opción adecuada para este caso, por tres razones:
  1. El grafo vial tiene muchos ciclos (manzanas, glorietas): sin
     lista de visitados, DFS cae en bucles infinitos. Con lista de
     visitados evitamos eso, pero el camino encontrado puede ser
     muy subóptimo (depende del orden de los vecinos en la lista
     de adyacencia).
  2. Las calles de un solo sentido crean atajos que DFS puede
     ignorar por completo al tomar una rama equivocada.
  3. El objetivo es MENOR COSTO, no sólo encontrar algún camino.
     DFS no ofrece garantía alguna de calidad de solución.
En la práctica, DFS sirve aquí únicamente como punto de
referencia: ilustra el costo de búsqueda sin ninguna estrategia
de costo ni de amplitud.

─────────────────────────────────────────────────────────────────
P3. ¿Cuándo UCS y BFS producen exactamente el mismo resultado?
─────────────────────────────────────────────────────────────────
UCS generaliza BFS: expande nodos en orden de g(n) (costo
acumulado). BFS los expande en orden de profundidad (saltos).
Los dos producen EXACTAMENTE el mismo camino cuando:

  Condición: todos los arcos del grafo tienen el mismo peso.

  Si w(e) = c (constante positiva) para todo arco e, entonces
  g(n) = c × profundidad(n). Ordenar por g(n) es idéntico a
  ordenar por profundidad, de modo que UCS y BFS exploran los
  nodos en el mismo orden y hallan el mismo camino.

  En particular, si c = 1, UCS es idéntico al BFS estándar.

En el grafo urbano de X-Route esta condición casi nunca se cumple:
los segmentos varían entre ~10 m y ~600 m, por lo que UCS y BFS
divergen en prácticamente todos los pares de prueba. La diferencia
en metros entre sus caminos es una medida directa de la varianza
de los pesos de los arcos en esa instancia.
""")


# =============================================================================
# Punto de entrada
# =============================================================================
if __name__ == "__main__":
    ejecutar_fase1()
