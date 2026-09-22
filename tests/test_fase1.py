"""
X-Route — Pruebas unitarias Fase 1
====================================
Verifica correctitud de BFS, DFS y UCS sobre grafos pequeños controlados
donde el resultado esperado se puede calcular a mano.

Ejecutar desde la raíz del proyecto:
    pytest tests/test_fase1.py -v
"""

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from fase1 import bfs, dfs, ucs
from metricas import Medicion


# =============================================================================
# Grafos de prueba reutilizables
# =============================================================================

@pytest.fixture
def grafo_lineal():
    """
    1 → 2 → 3 → 4
    Todos los arcos pesan 10 m.
    Camino único: [1, 2, 3, 4]
    """
    return {
        1: [(2, 10.0)],
        2: [(3, 10.0)],
        3: [(4, 10.0)],
        4: [],
    }


@pytest.fixture
def grafo_rombo():
    """
    Rombo con dos caminos de 1 a 4:
      - Ruta A (arriba): 1→2→4  pesos 5+5 = 10 m, 2 arcos
      - Ruta B (abajo):  1→3→4  pesos 1+1 = 2 m,  2 arcos

    BFS puede tomar cualquiera (mismo número de saltos).
    UCS debe tomar la ruta B (menor distancia).

         2
        / \
    1       4
        \ /
         3
    """
    return {
        1: [(2, 5.0), (3, 1.0)],
        2: [(4, 5.0)],
        3: [(4, 1.0)],
        4: [],
    }


@pytest.fixture
def grafo_pesos_distintos():
    """
    Tres caminos de 1 a 4:
      - 1→2→4  : 1+100 = 101 m, 2 arcos
      - 1→3→4  : 50+50 = 100 m, 2 arcos
      - 1→2→3→4: 1+2+50 = 53 m,  3 arcos  ← UCS debe elegir éste

    Verifica que UCS no elige por número de arcos sino por costo total.
    """
    return {
        1: [(2, 1.0),  (3, 50.0)],
        2: [(4, 100.0),(3, 2.0)],
        3: [(4, 50.0)],
        4: [],
    }


@pytest.fixture
def grafo_ciclo():
    """
    Grafo con ciclo: 1→2→3→1 (ciclo) y 3→4 (salida)
    Verifica que DFS y BFS no entran en bucle infinito.
    """
    return {
        1: [(2, 10.0)],
        2: [(3, 10.0)],
        3: [(1, 10.0), (4, 10.0)],   # ciclo hacia 1 y salida hacia 4
        4: [],
    }


@pytest.fixture
def grafo_desconectado():
    """
    1→2  y  3→4  (dos componentes separadas).
    No existe ruta de 1 a 4.
    """
    return {
        1: [(2, 5.0)],
        2: [],
        3: [(4, 5.0)],
        4: [],
    }


@pytest.fixture
def grafo_paralelo():
    """
    Dos arcos paralelos de 1 a 2 con distinto peso.
    construir_adyacencia() conserva solo el más corto (5 m).
    Aquí simulamos directamente ese resultado.
    """
    return {
        1: [(2, 5.0)],   # solo el arco más corto
        2: [],
    }


# =============================================================================
# Utilidad auxiliar
# =============================================================================

def med(nombre="test"):
    return Medicion(nombre)


# =============================================================================
# BLOQUE 1 — Casos básicos compartidos por los tres algoritmos
# =============================================================================

class TestCasosBasicos:

    def test_origen_igual_destino_bfs(self, grafo_lineal):
        camino = bfs(grafo_lineal, 1, 1, med())
        assert camino == [1], "BFS: origen==destino debe devolver [origen]"

    def test_origen_igual_destino_dfs(self, grafo_lineal):
        camino = dfs(grafo_lineal, 1, 1, med())
        assert camino == [1], "DFS: origen==destino debe devolver [origen]"

    def test_origen_igual_destino_ucs(self, grafo_lineal):
        camino = ucs(grafo_lineal, 1, 1, med())
        assert camino == [1], "UCS: origen==destino debe devolver [origen]"

    def test_sin_ruta_bfs(self, grafo_desconectado):
        assert bfs(grafo_desconectado, 1, 4, med()) is None

    def test_sin_ruta_dfs(self, grafo_desconectado):
        assert dfs(grafo_desconectado, 1, 4, med()) is None

    def test_sin_ruta_ucs(self, grafo_desconectado):
        assert ucs(grafo_desconectado, 1, 4, med()) is None

    def test_grafo_lineal_bfs(self, grafo_lineal):
        camino = bfs(grafo_lineal, 1, 4, med())
        assert camino == [1, 2, 3, 4]

    def test_grafo_lineal_dfs(self, grafo_lineal):
        camino = dfs(grafo_lineal, 1, 4, med())
        assert camino == [1, 2, 3, 4]

    def test_grafo_lineal_ucs(self, grafo_lineal):
        camino = ucs(grafo_lineal, 1, 4, med())
        assert camino == [1, 2, 3, 4]


# =============================================================================
# BLOQUE 2 — BFS: garantía de menos saltos
# =============================================================================

class TestBFS:

    def test_bfs_menos_saltos_rombo(self, grafo_rombo):
        """BFS debe encontrar UN camino de 2 arcos (el mínimo)."""
        camino = bfs(grafo_rombo, 1, 4, med())
        assert camino is not None
        assert len(camino) - 1 == 2, "BFS debe usar 2 arcos en el rombo"

    def test_bfs_no_garantiza_menor_distancia(self, grafo_pesos_distintos):
        """
        En este grafo, el camino con menos arcos (2) cuesta ≥100 m,
        pero existe uno de 3 arcos que cuesta solo 53 m.
        BFS debe devolver un camino de 2 arcos aunque no sea el más corto.
        """
        camino = bfs(grafo_pesos_distintos, 1, 4, med())
        assert camino is not None
        assert len(camino) - 1 == 2, "BFS debe preferir 2 arcos sobre 3"

    def test_bfs_evita_ciclos(self, grafo_ciclo):
        """BFS no debe entrar en bucle infinito en grafos con ciclos."""
        camino = bfs(grafo_ciclo, 1, 4, med())
        assert camino is not None
        assert camino[0] == 1 and camino[-1] == 4

    def test_bfs_camino_valido(self, grafo_rombo):
        """Cada arco del camino devuelto por BFS debe existir en el grafo."""
        camino = bfs(grafo_rombo, 1, 4, med())
        assert camino is not None
        for i in range(len(camino) - 1):
            vecinos = [v for v, _ in grafo_rombo.get(camino[i], [])]
            assert camino[i + 1] in vecinos, \
                f"Arco inválido: {camino[i]} → {camino[i+1]}"

    def test_bfs_nodos_expandidos_mayor_cero(self, grafo_lineal):
        m = med("BFS")
        bfs(grafo_lineal, 1, 4, m)
        assert m.nodos_expandidos > 0

    def test_bfs_frontera_maxima_mayor_cero(self, grafo_lineal):
        m = med("BFS")
        bfs(grafo_lineal, 1, 4, m)
        assert m.frontera_maxima > 0

    def test_bfs_tiempo_mayor_cero(self, grafo_lineal):
        m = med("BFS")
        bfs(grafo_lineal, 1, 4, m)
        assert m.tiempo_total_ms() >= 0


# =============================================================================
# BLOQUE 3 — DFS: evita ciclos, encuentra algún camino
# =============================================================================

class TestDFS:

    def test_dfs_evita_ciclos(self, grafo_ciclo):
        """DFS iterativo con visitados no debe entrar en bucle."""
        camino = dfs(grafo_ciclo, 1, 4, med())
        assert camino is not None
        assert camino[0] == 1 and camino[-1] == 4

    def test_dfs_camino_valido(self, grafo_rombo):
        """Cada arco del camino de DFS debe existir en el grafo."""
        camino = dfs(grafo_rombo, 1, 4, med())
        assert camino is not None
        for i in range(len(camino) - 1):
            vecinos = [v for v, _ in grafo_rombo.get(camino[i], [])]
            assert camino[i + 1] in vecinos

    def test_dfs_sin_nodos_repetidos(self, grafo_ciclo):
        """DFS con lista de visitados no debe repetir nodos en el camino."""
        camino = dfs(grafo_ciclo, 1, 4, med())
        assert camino is not None
        assert len(camino) == len(set(camino)), \
            "DFS no debe visitar el mismo nodo dos veces"

    def test_dfs_puede_no_ser_optimo(self, grafo_pesos_distintos):
        """
        DFS puede devolver cualquier camino válido.
        Solo verificamos que sea un camino correcto de 1 a 4.
        """
        camino = dfs(grafo_pesos_distintos, 1, 4, med())
        assert camino is not None
        assert camino[0] == 1
        assert camino[-1] == 4

    def test_dfs_nodos_expandidos_mayor_cero(self, grafo_lineal):
        m = med("DFS")
        dfs(grafo_lineal, 1, 4, m)
        assert m.nodos_expandidos > 0


# =============================================================================
# BLOQUE 4 — UCS: garantía de camino óptimo en costo
# =============================================================================

class TestUCS:

    def test_ucs_optimo_rombo(self, grafo_rombo):
        """
        Rombo: ruta B (1→3→4) cuesta 2 m, ruta A (1→2→4) cuesta 10 m.
        UCS debe elegir la ruta B.
        """
        camino = ucs(grafo_rombo, 1, 4, med())
        assert camino == [1, 3, 4], \
            "UCS debe elegir el camino de menor costo (2 m)"

    def test_ucs_optimo_pesos_distintos(self, grafo_pesos_distintos):
        """
        El camino óptimo es 1→2→3→4 con 53 m (3 arcos),
        aunque existen caminos de solo 2 arcos pero más caros.
        """
        camino = ucs(grafo_pesos_distintos, 1, 4, med())
        assert camino == [1, 2, 3, 4], \
            "UCS debe elegir 1→2→3→4 (53 m) sobre caminos de 2 arcos más caros"

    def test_ucs_costo_optimo_rombo(self, grafo_rombo):
        """Verifica el costo numérico del camino óptimo."""
        m = med("UCS")
        camino = ucs(grafo_rombo, 1, 4, m)
        _, metros = m.procesar_camino(camino, grafo_rombo)
        assert metros == pytest.approx(2.0), \
            "El costo óptimo en el rombo debe ser 2.0 m"

    def test_ucs_costo_optimo_lineal(self, grafo_lineal):
        """En el grafo lineal el costo debe ser 30 m (3 arcos × 10 m)."""
        m = med("UCS")
        camino = ucs(grafo_lineal, 1, 4, m)
        _, metros = m.procesar_camino(camino, grafo_lineal)
        assert metros == pytest.approx(30.0)

    def test_ucs_evita_ciclos(self, grafo_ciclo):
        """UCS no debe entrar en bucle con lazy deletion."""
        camino = ucs(grafo_ciclo, 1, 4, med())
        assert camino is not None
        assert camino[0] == 1 and camino[-1] == 4

    def test_ucs_camino_valido(self, grafo_pesos_distintos):
        """Cada arco del camino de UCS debe existir en el grafo."""
        camino = ucs(grafo_pesos_distintos, 1, 4, med())
        assert camino is not None
        for i in range(len(camino) - 1):
            vecinos = [v for v, _ in grafo_pesos_distintos.get(camino[i], [])]
            assert camino[i + 1] in vecinos

    def test_ucs_nodos_expandidos_mayor_cero(self, grafo_lineal):
        m = med("UCS")
        ucs(grafo_lineal, 1, 4, m)
        assert m.nodos_expandidos > 0


# =============================================================================
# BLOQUE 5 — Comparativas entre algoritmos
# =============================================================================

class TestComparativas:

    def test_bfs_ucs_mismo_resultado_pesos_iguales(self, grafo_lineal):
        """
        Con pesos iguales, BFS y UCS deben encontrar el mismo camino.
        Esta es exactamente la condición de la P3 del análisis.
        """
        camino_bfs = bfs(grafo_lineal, 1, 4, med())
        camino_ucs = ucs(grafo_lineal, 1, 4, med())
        assert camino_bfs == camino_ucs, \
            "Con pesos iguales BFS y UCS deben coincidir"

    def test_ucs_mejor_o_igual_que_bfs_en_metros(self, grafo_pesos_distintos):
        """UCS siempre encuentra una ruta con costo ≤ al de BFS."""
        m_bfs = med("BFS")
        m_ucs = med("UCS")
        c_bfs = bfs(grafo_pesos_distintos, 1, 4, m_bfs)
        c_ucs = ucs(grafo_pesos_distintos, 1, 4, m_ucs)
        _, metros_bfs = m_bfs.procesar_camino(c_bfs, grafo_pesos_distintos)
        _, metros_ucs = m_ucs.procesar_camino(c_ucs, grafo_pesos_distintos)
        assert metros_ucs <= metros_bfs, \
            "UCS debe encontrar un camino igual o más corto en metros que BFS"

    def test_todos_encuentran_camino_grafo_lineal(self, grafo_lineal):
        """Los tres algoritmos deben encontrar algún camino en un grafo simple."""
        assert bfs(grafo_lineal, 1, 4, med()) is not None
        assert dfs(grafo_lineal, 1, 4, med()) is not None
        assert ucs(grafo_lineal, 1, 4, med()) is not None

    def test_todos_devuelven_none_sin_ruta(self, grafo_desconectado):
        """Los tres algoritmos deben devolver None cuando no hay ruta."""
        assert bfs(grafo_desconectado, 1, 4, med()) is None
        assert dfs(grafo_desconectado, 1, 4, med()) is None
        assert ucs(grafo_desconectado, 1, 4, med()) is None

    def test_inicio_fin_en_camino(self, grafo_rombo):
        """El camino devuelto siempre debe empezar en origen y terminar en destino."""
        for fn in [bfs, dfs, ucs]:
            camino = fn(grafo_rombo, 1, 4, med())
            assert camino is not None
            assert camino[0] == 1
            assert camino[-1] == 4
