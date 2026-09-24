"""
X-Route — Pruebas Fase 4
========================
Dos bloques:

  A. Pruebas unitarias de las herramientas de la Fase 4 (instrumentación de
     snapshots, geometría de caminos, gráficas y mapas) sobre grafos de
     juguete donde el resultado se calcula a mano.

  B. Pruebas de INTEGRACIÓN de cada algoritmo de las Fases 1-3 sobre el
     grafo real de La Raza (data/grafo_la_raza_1500.graphml). Como oráculo
     independiente se usa NetworkX (`nx.dijkstra_path_length`,
     `nx.shortest_path_length`, `nx.descendants`). NetworkX sólo aparece
     aquí, en las pruebas, para validar; ningún algoritmo del proyecto lo usa.

Si el .graphml no existe, el bloque B se omite (skip) en vez de fallar.

Ejecutar desde la raíz del proyecto:
    pytest tests/test_fase4.py -v
"""

import math
import random
import sys
from pathlib import Path

import pytest
import networkx as nx
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from metricas import Medicion
from fase1 import bfs, dfs, ucs, verificar_alcanzabilidad
from fase2 import (a_estrella, greedy_best_first, heuristica_haversine,
                   extraer_coordenadas, costo_entre_puntos,
                   distancias_reales_hacia_destino, verificar_admisibilidad)
from fase3 import (matriz_distancias_astar, optimo_held_karp, costo_ruta,
                   vecino_mas_cercano, simulated_annealing, algoritmo_genetico)
from fase4 import (MedicionConSnapshots, leer_estado_busqueda, pasos_por_fraccion,
                   capturar_snapshots, catalogo_algoritmos, correr, coordenadas_camino,
                   medir_algoritmos, resumir_por_algoritmo, grafica_barras_por_par,
                   grafica_esfuerzo_vs_calidad, mapa_comparativo_par,
                   figura_snapshots, segmentos_grafo, ORDEN_ALGORITMOS)

RUTA_GRAPHML = RAIZ / "data" / "grafo_la_raza_1500.graphml"


# =============================================================================
# Grafos de juguete
# =============================================================================
@pytest.fixture
def grafo_rombo_pesado():
    """
        1 --1--> 2 --1--> 4
        1 --5--> 3 --1--> 4
    Óptimo 1→2→4 (2 m). UCS saca 1, luego 2 (g=1), luego 4 (g=2).
    """
    return {1: [(2, 1.0), (3, 5.0)], 2: [(4, 1.0)], 3: [(4, 1.0)], 4: []}


@pytest.fixture
def grafo_lineal():
    return {1: [(2, 10.0)], 2: [(3, 10.0)], 3: [(4, 10.0)], 4: [(5, 10.0)], 5: []}


@pytest.fixture
def heuristica_cero():
    return {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 0.0}


def _algoritmos_juguete(h):
    return [("BFS", bfs, None), ("DFS", dfs, None), ("UCS", ucs, None),
            ("A*", a_estrella, h), ("Greedy", greedy_best_first, h)]


# =============================================================================
# A. Instrumentación de snapshots
# =============================================================================
class TestSnapshots:

    @pytest.mark.parametrize("indice", range(5))
    def test_no_altera_resultado_ni_conteos(self, grafo_rombo_pesado, heuristica_cero, indice):
        nombre, funcion, h = _algoritmos_juguete(heuristica_cero)[indice]
        normal = Medicion(nombre)
        camino_normal = correr(funcion, grafo_rombo_pesado, 1, 4, normal, h)
        inst = MedicionConSnapshots(nombre, pasos=range(1, 50))
        camino_inst = correr(funcion, grafo_rombo_pesado, 1, 4, inst, h)
        assert camino_inst == camino_normal
        assert inst.nodos_expandidos == normal.nodos_expandidos
        assert inst.frontera_maxima == normal.frontera_maxima
        assert len(inst.snapshots) == normal.nodos_expandidos

    def test_frontera_ucs_calculada_a_mano(self, grafo_rombo_pesado):
        med = MedicionConSnapshots("UCS", pasos=[1, 2, 3])
        camino = ucs(grafo_rombo_pesado, 1, 4, med)
        assert camino == [1, 2, 4]
        s1, s2, s3 = med.snapshots
        # Paso 1: se sacó el origen; la frontera quedó vacía.
        assert s1["nodo_actual"] == 1 and s1["frontera"] == set() and s1["explorados"] == {1}
        # Paso 2: se sacó 2 (g=1); en la frontera sigue 3 (g=5).
        assert s2["nodo_actual"] == 2 and s2["frontera"] == {3}
        assert s2["explorados"] == {1, 2}
        # Paso 3: se sacó la meta; 3 sigue sin expandirse.
        assert s3["nodo_actual"] == 4 and s3["camino_actual"] == [1, 2, 4]
        assert 3 in s3["frontera"]

    def test_bfs_separa_alcanzados_de_explorados(self):
        ady = {1: [(2, 1.0), (3, 1.0)], 2: [(4, 1.0)], 3: [(4, 1.0)], 4: [(5, 1.0)], 5: []}
        med = MedicionConSnapshots("BFS", pasos=[2])
        bfs(ady, 1, 5, med)
        snap = med.snapshots[0]
        # BFS guarda en `visitados` los nodos alcanzados; 3 está en la frontera,
        # no debe contarse como explorado.
        assert snap["nodo_actual"] == 2
        assert snap["frontera"] == {3}
        assert snap["explorados"] == {1, 2}

    def test_frontera_y_explorados_son_disjuntos(self, grafo_rombo_pesado, heuristica_cero):
        for nombre, funcion, h in _algoritmos_juguete(heuristica_cero):
            med = MedicionConSnapshots(nombre, pasos=range(1, 50))
            correr(funcion, grafo_rombo_pesado, 1, 4, med, h)
            for snap in med.snapshots:
                assert not (snap["frontera"] & snap["explorados"]), nombre

    def test_sin_variable_frontera_lanza_error(self):
        with pytest.raises(RuntimeError):
            leer_estado_busqueda({"nodo": 1}, paso=1)

    @pytest.mark.parametrize("total, esperado", [
        (10, [1, 5, 10]), (1, [1]), (3, [1, 2, 3]), (1991, [200, 996, 1991]),
    ])
    def test_pasos_por_fraccion(self, total, esperado):
        assert pasos_por_fraccion(total) == esperado

    def test_capturar_snapshots_tres_momentos(self, grafo_lineal):
        captura = capturar_snapshots("UCS", ucs, grafo_lineal, 1, 5)
        assert captura["camino"] == [1, 2, 3, 4, 5]
        assert len(captura["snapshots"]) == 3
        assert captura["snapshots"][-1]["paso"] == captura["total_expandidos"]
        assert captura["snapshots"][-1]["nodo_actual"] == 5


# =============================================================================
# A. Gráficas y mapas (sólo verifican que se generen archivos válidos)
# =============================================================================
def _df_sintetico():
    filas = []
    for par in (1, 2):
        for i, alg in enumerate(ORDEN_ALGORITMOS):
            filas.append({"Par": par, "Algoritmo": alg, "Expandidos": 10 * (i + 1),
                          "Tiempo_ms": 0.1 * (i + 1), "Frontera_Max": i + 2,
                          "Gap_pct": 0.0 if alg.startswith(("UCS", "A*")) else 5.0 * i,
                          "b_estrella": 1.1 + 0.01 * i})
    return pd.DataFrame(filas)


class TestGraficas:

    @pytest.mark.parametrize("escala", ["linear", "log", "symlog"])
    def test_barras_por_par_genera_png(self, tmp_path, escala):
        salida = tmp_path / "barras.png"
        grafica_barras_por_par(_df_sintetico(), "Expandidos", "y", "t", salida, escala)
        assert salida.exists() and salida.read_bytes()[:4] == b"\x89PNG"

    def test_esfuerzo_vs_calidad_genera_png(self, tmp_path):
        salida = tmp_path / "disp.png"
        grafica_esfuerzo_vs_calidad(_df_sintetico(), salida)
        assert salida.exists() and salida.stat().st_size > 1000


# =============================================================================
# B. Integración sobre el grafo real
# =============================================================================
@pytest.fixture(scope="module")
def real():
    if not RUTA_GRAPHML.exists():
        pytest.skip("No está data/grafo_la_raza_1500.graphml")
    from grafo import cargar_grafo, construir_adyacencia, cargar_instancia
    G = cargar_grafo()
    ady = construir_adyacencia(G)
    datos = cargar_instancia(G)
    coords = extraer_coordenadas(G)
    return {"G": G, "ady": ady, "datos": datos, "coords": coords,
            "pares": datos["pares_prueba"]}


@pytest.fixture(scope="module")
def corridas(real):
    """Corre los 9 algoritmos una vez en cada par; lo reutilizan varias pruebas."""
    res = {}
    for k, par in enumerate(real["pares"], start=1):
        o, d = par["origen"]["nodo"], par["destino"]["nodo"]
        optimo = nx.dijkstra_path_length(real["G"], o, d, weight="length")
        saltos = nx.shortest_path_length(real["G"], o, d)
        for nombre, funcion, h in catalogo_algoritmos(real["coords"], real["ady"], d):
            med = Medicion(nombre)
            camino = correr(funcion, real["ady"], o, d, med, h)
            res[(k, nombre)] = {"camino": camino, "med": med, "o": o, "d": d,
                                "optimo": optimo, "saltos": saltos}
    return res


PARES = range(1, 6)


class TestIntegracionBusqueda:

    @pytest.mark.parametrize("par", PARES)
    @pytest.mark.parametrize("algoritmo", ORDEN_ALGORITMOS)
    def test_camino_valido(self, real, corridas, par, algoritmo):
        r = corridas[(par, algoritmo)]
        camino = r["camino"]
        assert camino is not None, f"{algoritmo} no encontró ruta en el par {par}"
        assert camino[0] == r["o"] and camino[-1] == r["d"]
        # procesar_camino lanza ValueError si algún arco no existe
        arcos, metros = r["med"].procesar_camino(camino, real["ady"])
        assert arcos == len(camino) - 1 and metros > 0

    @pytest.mark.parametrize("par", PARES)
    @pytest.mark.parametrize("algoritmo", ["UCS", "A*-Haversine", "A*-Euclidiana"])
    def test_optimos_coinciden_con_dijkstra_de_networkx(self, real, corridas, par, algoritmo):
        r = corridas[(par, algoritmo)]
        metros = r["med"].procesar_camino(r["camino"], real["ady"])[1]
        assert metros == pytest.approx(r["optimo"], abs=0.02)

    @pytest.mark.parametrize("par", PARES)
    def test_bfs_minimiza_saltos(self, corridas, par):
        r = corridas[(par, "BFS")]
        assert len(r["camino"]) - 1 == r["saltos"]

    @pytest.mark.parametrize("par", PARES)
    @pytest.mark.parametrize("algoritmo", ["BFS", "DFS", "A*-Personalizada", "Greedy-Euclidiana",
                                           "Greedy-Haversine", "Greedy-Personalizada"])
    def test_no_optimos_nunca_mejoran_el_optimo(self, real, corridas, par, algoritmo):
        r = corridas[(par, algoritmo)]
        metros = r["med"].procesar_camino(r["camino"], real["ady"])[1]
        assert metros >= r["optimo"] - 0.02

    @pytest.mark.parametrize("par", PARES)
    def test_astar_admisible_expande_menos_que_ucs(self, corridas, par):
        ucs_exp = corridas[(par, "UCS")]["med"].nodos_expandidos
        assert corridas[(par, "A*-Haversine")]["med"].nodos_expandidos <= ucs_exp

    @pytest.mark.parametrize("par", PARES)
    def test_haversine_admisible_en_todo_el_grafo(self, real, par):
        d = real["pares"][par - 1]["destino"]["nodo"]
        reales = distancias_reales_hacia_destino(real["ady"], d)
        resultado = verificar_admisibilidad(heuristica_haversine(real["coords"], d), reales, "H")
        assert resultado["Es_admisible"]

    def test_alcanzabilidad_coincide_con_networkx(self, real):
        dep = real["datos"]["deposito"]["nodo"]
        entregas = [e["nodo"] for e in real["datos"]["entregas"]]
        esperado = nx.descendants(real["G"], dep) | {dep}
        obtenido = verificar_alcanzabilidad(real["ady"], dep, entregas)
        assert obtenido == {n: n in esperado for n in entregas}

    def test_snapshot_final_llega_a_la_meta_en_grafo_real(self, real):
        par = real["pares"][1]
        o, d = par["origen"]["nodo"], par["destino"]["nodo"]
        h = heuristica_haversine(real["coords"], d)
        captura = capturar_snapshots("A*-Haversine", a_estrella, real["ady"], o, d, h)
        pasos = [s["paso"] for s in captura["snapshots"]]
        assert len(pasos) == 3 and pasos == sorted(pasos)
        assert captura["snapshots"][-1]["nodo_actual"] == d
        # La frontera crece desde el primer snapshot
        assert captura["snapshots"][0]["tam_frontera"] < captura["snapshots"][-1]["tam_frontera"]


class TestIntegracionGeometriaYMapas:

    @pytest.mark.parametrize("par", PARES)
    def test_polilinea_mide_lo_mismo_que_el_camino(self, real, corridas, par):
        r = corridas[(par, "UCS")]
        puntos = coordenadas_camino(real["G"], r["camino"])
        largo = sum(costo_entre_puntos(*a, *b) for a, b in zip(puntos, puntos[1:]))
        assert largo == pytest.approx(r["optimo"], rel=0.01)
        G = real["G"]
        assert puntos[0] == (G.nodes[r["o"]]["y"], G.nodes[r["o"]]["x"])
        assert puntos[-1] == (G.nodes[r["d"]]["y"], G.nodes[r["d"]]["x"])

    def test_arco_inexistente_lanza_error(self, real):
        nodos = list(real["G"].nodes)
        u = nodos[0]
        no_vecino = next(v for v in nodos if v != u and not real["G"].has_edge(u, v))
        with pytest.raises(ValueError):
            coordenadas_camino(real["G"], [u, no_vecino])

    def test_benchmark_y_mapa_comparativo(self, real, tmp_path):
        par = real["pares"][0]
        df, caminos = medir_algoritmos(real["ady"], real["coords"], [par], repeticiones=1)
        assert list(df["Algoritmo"]) == ORDEN_ALGORITMOS
        ucs_fila = df[df["Algoritmo"] == "UCS"].iloc[0]
        assert ucs_fila["Gap_pct"] == 0 and ucs_fila["Es_optima"]
        assert (df["Gap_pct"] >= 0).all()
        resumen = resumir_por_algoritmo(df)
        assert len(resumen) == len(ORDEN_ALGORITMOS)

        salida = tmp_path / "par.html"
        mapa_comparativo_par(real["G"], par, 1, df.to_dict("records"), caminos, salida)
        html = salida.read_text(encoding="utf-8")
        assert "UCS" in html and "Greedy-Haversine" in html

    def test_figura_snapshots_genera_png(self, real, tmp_path):
        par = real["pares"][0]
        o, d = par["origen"]["nodo"], par["destino"]["nodo"]
        captura = capturar_snapshots("BFS", bfs, real["ady"], o, d)
        salida = tmp_path / "snap.png"
        figura_snapshots(real["G"], segmentos_grafo(real["G"]), [captura], o, d, salida, "t")
        assert salida.exists() and salida.stat().st_size > 10_000


@pytest.fixture(scope="module")
def matriz(real):
    puntos = [real["datos"]["deposito"]] + real["datos"]["entregas"]
    nodos = [p["nodo"] for p in puntos]
    D, _, _ = matriz_distancias_astar(real["ady"], real["coords"], nodos)
    return {"D": D, "nodos": nodos, "indices": list(range(1, len(nodos)))}


class TestIntegracionFase3:

    def test_matriz_coincide_con_dijkstra(self, real, matriz):
        rng = random.Random(0)
        n = len(matriz["nodos"])
        for _ in range(20):
            i, j = rng.sample(range(n), 2)
            esperado = nx.dijkstra_path_length(real["G"], matriz["nodos"][i],
                                               matriz["nodos"][j], weight="length")
            assert matriz["D"][i][j] == pytest.approx(esperado, abs=0.05)

    def test_matriz_es_asimetrica(self, matriz):
        D = matriz["D"]
        assert any(abs(D[i][j] - D[j][i]) > 1 for i in range(len(D)) for j in range(i))

    def test_held_karp_es_cota_inferior(self, matriz):
        D, indices = matriz["D"], matriz["indices"]
        ruta_opt, costo_opt = optimo_held_karp(D, indices)
        assert sorted(ruta_opt) == indices
        assert costo_ruta(ruta_opt, D) == pytest.approx(costo_opt)
        assert costo_opt <= costo_ruta(vecino_mas_cercano(D, indices), D) + 1e-6

    def test_sa_y_ga_devuelven_permutaciones_validas(self, matriz):
        D, indices = matriz["D"], matriz["indices"]
        _, costo_opt = optimo_held_karp(D, indices)
        sa = simulated_annealing(D, indices, random.Random(1), T0=2000, alfa=0.9)
        ga = algoritmo_genetico(D, indices, random.Random(1), tam_poblacion=30, generaciones=30)
        for res in (sa, ga):
            assert sorted(res.mejor_ruta) == indices
            assert res.mejor_costo == pytest.approx(costo_ruta(res.mejor_ruta, D))
            assert res.mejor_costo >= costo_opt - 1e-6
            # El historial del mejor costo nunca sube
            assert all(b <= a + 1e-9 for a, b in zip(res.historial, res.historial[1:]))
