import pytest
import networkx as nx
from pathlib import Path
from grafo import construir_adyacencia, nodo_mas_cercano, cargar_grafo

# ==========================================
# PARTE 1: Grafo hecho a mano (Falso)
# ==========================================

@pytest.fixture
def grafo_falso():
    G = nx.MultiDiGraph()
    # 1. Dos arcos paralelos con distinta longitud
    G.add_edge(1, 2, length=25.0)
    G.add_edge(1, 2, length=10.0) 
    
    # 2. Un bucle (hacia sí mismo)
    G.add_edge(2, 2, length=5.0)
    
    # 3. Un nodo sin salidas (nodo 3)
    G.add_edge(2, 3, length=15.0)
    
    return G

def test_construir_adyacencia(grafo_falso):
    ady = construir_adyacencia(grafo_falso)
    
    # Que el número de llaves sea igual al número de nodos del grafo
    assert len(ady) == len(grafo_falso.nodes())
    
    # Que entre los arcos paralelos quedó el de longitud menor
    assert ady[1] == [(2, 10.0)]
    
    # Que el bucle desapareció de la lista de vecinos
    assert ady[2] == [(3, 15.0)]
    
    # Que el nodo sin salidas existe como llave y su lista está vacía
    assert 3 in ady
    assert ady[3] == []

# ==========================================
# PARTE 2: Grafo Real
# ==========================================

# scope="module" carga el .graphml una sola vez para todas las pruebas de este archivo
@pytest.fixture(scope="module")
def grafo_real():
    directorio_raiz = Path(__file__).resolve().parent.parent
    ruta_archivo = directorio_raiz / "data" / "grafo_la_raza_1500.graphml"
    
    if not ruta_archivo.exists():
        pytest.skip("Grafo en caché no encontrado. Se omite para evitar descarga de 15 minutos.")
        
    return cargar_grafo()

def test_nodo_mas_cercano_valido(grafo_real):
    # Coordenada válida (Centro de La Raza)
    nodo = nodo_mas_cercano(grafo_real, 19.469323, -99.136283)
    
    # Que devuelva un int y que exista en el grafo
    assert isinstance(nodo, int)
    assert nodo in grafo_real.nodes()

def test_nodo_mas_cercano_invalido(grafo_real):
    # Coordenada inválida (Zócalo CDMX)
    with pytest.raises(ValueError):
        nodo_mas_cercano(grafo_real, 19.432608, -99.133209)