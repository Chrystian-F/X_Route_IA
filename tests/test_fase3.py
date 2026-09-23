"""
X-Route — Pruebas unitarias Fase 3
====================================
Verifica los operadores sobre permutaciones (2-opt, OX, intercambio), la
función objetivo, el óptimo exacto de Held-Karp y que SA, GA y 2-opt
encuentren el óptimo en instancias pequeñas donde se puede comprobar por
fuerza bruta.

No requiere osmnx: la matriz de A* se prueba con un grafo de juguete y el
resto con matrices de distancias escritas a mano o generadas al azar.

Ejecutar desde la raíz del proyecto:
    pytest tests/test_fase3.py -v
"""

import itertools
import math
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from fase3 import (
    matriz_distancias_astar,
    costo_ruta,
    ruta_aleatoria,
    vecino_mas_cercano,
    vecino_2opt,
    mutacion_intercambio,
    cruza_ox,
    busqueda_local_2opt,
    calcular_temperatura_inicial,
    simulated_annealing,
    seleccion_torneo,
    algoritmo_genetico,
    optimo_held_karp,
    analizar_paisaje,
    pct_mejora,
    alfa_para_niveles,
    ruta_en_nodos,
)


def es_permutacion(perm, indices):
    return sorted(perm) == sorted(indices)


def fuerza_bruta(D, indices):
    """Óptimo por enumeración de todas las permutaciones (sólo N chico)."""
    return min(costo_ruta(list(p), D) for p in itertools.permutations(indices))


def matriz_aleatoria(n, semilla, simetrica=False):
    """Matriz n x n con ceros en la diagonal; asimétrica por defecto, como
    la de calles de un solo sentido."""
    rng = random.Random(semilla)
    D = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j:
                D[i][j] = D[j][i] if simetrica and j < i else rng.uniform(100, 1000)
    return D


@pytest.fixture
def D_circulo():
    """Depósito 0 y 5 entregas en un círculo: el óptimo es recorrerlas en
    orden 1-2-3-4-5 (o al revés), con costo 6 · 100 = 600."""
    n = 6
    D = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            pasos = min(abs(i - j), n - abs(i - j))
            D[i][j] = 100.0 * pasos
    return D


# =============================================================================
# Matriz de distancias con A*
# =============================================================================
class TestMatrizAstar:

    def test_grafo_juguete(self):
        # 1 → 2 → 3 y 3 → 1 (dirigido); coordenadas sobre una línea
        ady = {1: [(2, 100.0)], 2: [(3, 100.0)], 3: [(1, 250.0)]}
        coords = {1: (19.4600, -99.1400), 2: (19.4609, -99.1400), 3: (19.4618, -99.1400)}
        D, caminos, expandidos = matriz_distancias_astar(ady, coords, [1, 2, 3])
        assert D[0][1] == 100.0 and D[1][2] == 100.0
        assert D[0][2] == 200.0          # 1 → 2 → 3
        assert D[2][0] == 250.0          # 3 → 1 directo
        assert D[1][0] == 350.0          # 2 → 3 → 1 (no existe 2 → 1)
        assert D[0][2] != D[2][0]        # asimétrica
        assert caminos[(1, 0)] == [2, 3, 1]
        assert expandidos > 0

    def test_sin_ruta_es_infinito(self):
        ady = {1: [(2, 100.0)], 2: []}
        coords = {1: (19.46, -99.14), 2: (19.461, -99.14)}
        D, caminos, _ = matriz_distancias_astar(ady, coords, [1, 2])
        assert D[0][1] == 100.0
        assert math.isinf(D[1][0])
        assert (1, 0) not in caminos


# =============================================================================
# Función objetivo y construcciones
# =============================================================================
class TestCostoRuta:

    def test_circuito_cerrado(self, D_circulo):
        assert costo_ruta([1, 2, 3, 4, 5], D_circulo) == 600.0

    def test_incluye_ida_y_regreso_al_deposito(self):
        D = [[0, 10, 50], [70, 0, 20], [30, 90, 0]]
        # 0 → 1 → 2 → 0 = 10 + 20 + 30
        assert costo_ruta([1, 2], D) == 60
        # 0 → 2 → 1 → 0 = 50 + 90 + 70 (asimétrica)
        assert costo_ruta([2, 1], D) == 210

    def test_ruta_vacia(self, D_circulo):
        assert costo_ruta([], D_circulo) == 0.0

    def test_ruta_aleatoria_es_permutacion(self):
        rng = random.Random(0)
        for _ in range(20):
            assert es_permutacion(ruta_aleatoria([1, 2, 3, 4, 5], rng), [1, 2, 3, 4, 5])

    def test_vecino_mas_cercano(self):
        D = [[0, 5, 1, 9], [5, 0, 2, 1], [1, 2, 0, 8], [9, 1, 8, 0]]
        # desde 0 el más cercano es 2; desde 2 es 1; luego 3
        assert vecino_mas_cercano(D, [1, 2, 3]) == [2, 1, 3]

    def test_pct_mejora(self):
        assert pct_mejora(75, 100) == 25
        assert pct_mejora(100, 100) == 0
        assert pct_mejora(120, 100) == -20


# =============================================================================
# Operadores
# =============================================================================
class TestOperadores:

    def test_2opt_invierte_tramo(self):
        assert vecino_2opt([1, 2, 3, 4, 5, 6], 1, 4) == [1, 5, 4, 3, 2, 6]
        assert vecino_2opt([1, 2, 3, 4], 0, 3) == [4, 3, 2, 1]

    def test_2opt_no_modifica_original(self):
        perm = [1, 2, 3, 4]
        vecino_2opt(perm, 0, 2)
        assert perm == [1, 2, 3, 4]

    def test_2opt_deshace_cruce_simetrico(self, D_circulo):
        # [1, 3, 2, 4, 5] cruza dos arcos; invertir el tramo [3, 2] lo corrige
        cruzada = [1, 3, 2, 4, 5]
        assert costo_ruta(vecino_2opt(cruzada, 1, 2), D_circulo) < costo_ruta(cruzada, D_circulo)

    def test_intercambio_es_permutacion(self):
        rng = random.Random(1)
        perm = list(range(1, 11))
        for _ in range(50):
            hijo = mutacion_intercambio(perm, rng)
            assert es_permutacion(hijo, perm)
            assert sum(a != b for a, b in zip(hijo, perm)) == 2
        assert perm == list(range(1, 11))

    def test_ox_ejemplo_de_libro(self):
        # Eiben & Smith, "Introduction to Evolutionary Computing"
        p1 = [1, 2, 3, 4, 5, 6, 7, 8, 9]
        p2 = [9, 3, 7, 8, 2, 6, 5, 1, 4]
        assert cruza_ox(p1, p2, None, cortes=(3, 6)) == [3, 8, 2, 4, 5, 6, 7, 1, 9]

    def test_ox_conserva_segmento_y_orden(self):
        rng = random.Random(7)
        indices = list(range(1, 13))
        for _ in range(100):
            p1, p2 = ruta_aleatoria(indices, rng), ruta_aleatoria(indices, rng)
            a, b = sorted(rng.sample(range(len(p1)), 2))
            hijo = cruza_ox(p1, p2, rng, cortes=(a, b))
            assert es_permutacion(hijo, indices)
            assert hijo[a:b + 1] == p1[a:b + 1]
            # el resto aparece en el mismo orden relativo que en padre2
            resto_hijo = [g for g in hijo[b + 1:] + hijo[:a]]
            resto_p2 = [g for g in p2[b + 1:] + p2[:b + 1] if g not in p1[a:b + 1]]
            assert resto_hijo == resto_p2

    def test_ox_padres_iguales_da_el_mismo(self):
        p = [4, 2, 5, 1, 3]
        assert cruza_ox(p, p, random.Random(0)) == p

    def test_torneo_prefiere_menor_costo(self):
        poblacion = [[1], [2], [3]]
        costos = [30.0, 10.0, 20.0]
        # con k = tamaño de la población siempre gana el mejor
        assert seleccion_torneo(poblacion, costos, random.Random(0), k=3) == [2]


# =============================================================================
# Óptimo exacto
# =============================================================================
class TestHeldKarp:

    def test_circulo(self, D_circulo):
        ruta, costo = optimo_held_karp(D_circulo, [1, 2, 3, 4, 5])
        assert costo == 600.0
        assert ruta in ([1, 2, 3, 4, 5], [5, 4, 3, 2, 1])

    @pytest.mark.parametrize("semilla", range(5))
    def test_igual_a_fuerza_bruta_asimetrica(self, semilla):
        D = matriz_aleatoria(8, semilla)
        indices = list(range(1, 8))
        ruta, costo = optimo_held_karp(D, indices)
        assert es_permutacion(ruta, indices)
        assert costo == pytest.approx(costo_ruta(ruta, D))
        assert costo == pytest.approx(fuerza_bruta(D, indices))

    def test_una_entrega(self):
        D = [[0, 7], [3, 0]]
        assert optimo_held_karp(D, [1]) == ([1], 10)


# =============================================================================
# Búsqueda local
# =============================================================================
class TestBusquedaLocal2opt:

    def test_llega_a_optimo_local(self):
        D = matriz_aleatoria(9, 3)
        indices = list(range(1, 9))
        res = busqueda_local_2opt(ruta_aleatoria(indices, random.Random(0)), D)
        assert es_permutacion(res.mejor_ruta, indices)
        # ningún vecino 2-opt mejora la ruta final
        for i in range(len(indices) - 1):
            for j in range(i + 1, len(indices)):
                assert costo_ruta(vecino_2opt(res.mejor_ruta, i, j), D) >= res.mejor_costo - 1e-9
        # el historial nunca sube
        assert all(b < a for a, b in zip(res.historial, res.historial[1:]))

    def test_resuelve_el_circulo(self, D_circulo):
        res = busqueda_local_2opt([3, 1, 5, 2, 4], D_circulo)
        assert res.mejor_costo == 600.0

    def test_paisaje(self):
        D = matriz_aleatoria(7, 4)
        paisaje = analizar_paisaje(D, list(range(1, 7)), random.Random(0), arranques=20)
        assert len(paisaje["costos_optimos_locales"]) == 20
        assert 1 <= paisaje["optimos_distintos"] <= 20
        assert all(l <= a for a, l in zip(paisaje["costos_aleatorios"],
                                          paisaje["costos_optimos_locales"]))


class TestSimulatedAnnealing:

    def test_temperatura_inicial(self):
        D = matriz_aleatoria(8, 0)
        T0, delta = calcular_temperatura_inicial(D, list(range(1, 8)), random.Random(0),
                                                 prob_aceptacion=0.8)
        assert delta > 0
        assert math.exp(-delta / T0) == pytest.approx(0.8)

    def test_alfa_para_niveles(self):
        alfa = alfa_para_niveles(1000.0, 1.0, 100)
        assert 1000.0 * alfa ** 100 == pytest.approx(1.0)

    def test_enfriamiento_geometrico(self):
        D = matriz_aleatoria(6, 1)
        res = simulated_annealing(D, list(range(1, 6)), random.Random(0),
                                  T0=100.0, alfa=0.5, T_min=1.0, iter_por_temp=3)
        temps = res.extra["temperaturas"]
        assert temps == pytest.approx([100.0 * 0.5 ** k for k in range(len(temps))])
        assert temps[-1] > 1.0 and temps[-1] * 0.5 <= 1.0
        assert res.evaluaciones == 1 + 3 * len(temps)

    def test_historial_del_mejor_no_sube(self):
        D = matriz_aleatoria(8, 2)
        res = simulated_annealing(D, list(range(1, 8)), random.Random(0), T0=500.0, alfa=0.9)
        assert all(b <= a for a, b in zip(res.historial, res.historial[1:]))
        assert res.historial[-1] == res.mejor_costo
        assert costo_ruta(res.mejor_ruta, D) == pytest.approx(res.mejor_costo)

    @pytest.mark.parametrize("semilla", range(3))
    def test_encuentra_optimo_instancia_chica(self, semilla):
        D = matriz_aleatoria(8, semilla)
        indices = list(range(1, 8))
        T0, _ = calcular_temperatura_inicial(D, indices, random.Random(semilla))
        res = simulated_annealing(D, indices, random.Random(semilla), T0, alfa=0.97)
        assert es_permutacion(res.mejor_ruta, indices)
        assert res.mejor_costo == pytest.approx(fuerza_bruta(D, indices))

    def test_misma_semilla_mismo_resultado(self):
        D = matriz_aleatoria(8, 5)
        a = simulated_annealing(D, list(range(1, 8)), random.Random(9), T0=300.0, alfa=0.9)
        b = simulated_annealing(D, list(range(1, 8)), random.Random(9), T0=300.0, alfa=0.9)
        assert a.mejor_ruta == b.mejor_ruta and a.historial == b.historial

    def test_temperatura_casi_cero_es_hill_climbing(self):
        D = matriz_aleatoria(8, 6)
        res = simulated_annealing(D, list(range(1, 8)), random.Random(0),
                                  T0=1e-6, alfa=0.5, T_min=1e-7, iter_por_temp=500)
        assert res.extra["tasa_aceptacion_peores"] == 0.0


class TestAlgoritmoGenetico:

    def test_poblacion_valida_y_elitismo(self):
        D = matriz_aleatoria(9, 0)
        indices = list(range(1, 9))
        res = algoritmo_genetico(D, indices, random.Random(0), tam_poblacion=30,
                                 generaciones=40)
        assert es_permutacion(res.mejor_ruta, indices)
        assert costo_ruta(res.mejor_ruta, D) == pytest.approx(res.mejor_costo)
        assert len(res.historial) == 41
        # con elitismo el mejor de cada generación nunca empeora
        assert all(b <= a for a, b in zip(res.historial, res.historial[1:]))
        assert res.evaluaciones == 30 + 40 * (30 - 2)

    @pytest.mark.parametrize("semilla", range(3))
    def test_encuentra_optimo_instancia_chica(self, semilla):
        D = matriz_aleatoria(8, semilla)
        indices = list(range(1, 8))
        res = algoritmo_genetico(D, indices, random.Random(semilla),
                                 tam_poblacion=60, generaciones=100)
        assert res.mejor_costo == pytest.approx(fuerza_bruta(D, indices))


# =============================================================================
# Reconstrucción de la ruta sobre el grafo
# =============================================================================
def test_ruta_en_nodos_concatena_tramos():
    caminos = {
        (0, 1): [10, 11, 20], (1, 2): [20, 21, 30], (2, 0): [30, 10],
    }
    assert ruta_en_nodos([1, 2], caminos) == [10, 11, 20, 21, 30, 10]
