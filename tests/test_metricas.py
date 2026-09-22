import pytest
from metricas import Medicion

@pytest.fixture
def grafo_prueba():
    return {
        1: [(2, 15.5), (3, 50.0)],
        2: [(3, 20.0)],
        3: []
    }

def test_camino_bfs(grafo_prueba):
    med = Medicion()
    arcos, metros = med.procesar_camino([1, 3], grafo_prueba)
    assert arcos == 1
    assert metros == pytest.approx(50.0)

def test_camino_ucs(grafo_prueba):
    med = Medicion()
    arcos, metros = med.procesar_camino([1, 2, 3], grafo_prueba)
    assert arcos == 2
    assert metros == pytest.approx(35.5)

def test_camino_un_nodo(grafo_prueba):
    med = Medicion()
    arcos, metros = med.procesar_camino([1], grafo_prueba)
    assert arcos == 0
    assert metros == pytest.approx(0.0)

def test_camino_none(grafo_prueba):
    med = Medicion()
    arcos, metros = med.procesar_camino(None, grafo_prueba)
    assert arcos is None
    assert metros is None

def test_arco_inexistente(grafo_prueba):
    med = Medicion()
    with pytest.raises(ValueError):
        med.procesar_camino([1, 4], grafo_prueba)

def test_arco_sentido_contrario(grafo_prueba):
    med = Medicion()
    # Verifica que respete el sentido de la calle (hay arco de 1 a 2, pero no de 2 a 1)
    with pytest.raises(ValueError):
        med.procesar_camino([2, 1], grafo_prueba)

def test_actualizar_frontera():
    med = Medicion()
    assert med.frontera_maxima == 0
    med.actualizar_frontera(5)
    assert med.frontera_maxima == 5
    med.actualizar_frontera(3)
    assert med.frontera_maxima == 5

def test_registrar_expansion():
    med = Medicion()
    assert med.nodos_expandidos == 0
    med.registrar_expansion()
    med.registrar_expansion()
    assert med.nodos_expandidos == 2

def test_generar_diccionario(grafo_prueba):
    med = Medicion("Test")
    
    # Caso 1: Ruta válida
    dict_valido = med.generar_diccionario([1, 2], grafo_prueba)
    assert dict_valido["Algoritmo"] == "Test"
    assert dict_valido["Arcos"] == 1
    assert dict_valido["Metros"] == pytest.approx(15.5)
    
    # Caso 2: Sin ruta (None)
    dict_none = med.generar_diccionario(None, grafo_prueba)
    assert dict_none["Arcos"] is None
    assert dict_none["Metros"] is None
    assert dict_none["Camino"] is None