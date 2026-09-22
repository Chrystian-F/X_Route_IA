# X-Route — Agente planificador de rutas

Práctica de Laboratorio 1 de Inteligencia Artificial (ESCOM-IPN). Agente que planifica rutas de entrega de última milla sobre el grafo real de calles de la zona norte y centro de la Ciudad de México, descargado de OpenStreetMap con `osmnx`. Compara búsqueda a ciegas (BFS, DFS, UCS), búsqueda informada (A\*, Greedy) y búsqueda local (Algoritmo Genético, Simulated Annealing).

## Requisitos

- Python 3.13 (probado con 3.13.2; debería funcionar desde 3.10)
- Librerías principales: `osmnx 2.1.1`, `networkx 3.6.1`, `folium 0.20.0`, `pandas 3.0.6` y `scikit-learn` (osmnx lo necesita para buscar el nodo más cercano en un grafo sin proyectar). La lista está en `requirements.txt`.

## Instalación

Desde la raíz del proyecto, en PowerShell:

```powershell
python -m venv env
.\env\Scripts\Activate.ps1
pip install -r requirements.txt
```

En Linux o macOS, la activación es `source env/bin/activate`.

## Uso rápido

```python
from grafo import cargar_grafo, construir_adyacencia, cargar_instancia
from metricas import Medicion

G = cargar_grafo()               # carga el grafo desde data/ (no descarga)
ady = construir_adyacencia(G)    # {nodo: [(vecino, metros), ...]}
inst = cargar_instancia(G)       # depósito, 15 entregas y 5 pares de prueba, ya con su nodo
```

Scripts que se pueden ejecutar directamente desde la raíz:

| Comando | Qué hace |
|---|---|
| `python src/grafo.py` | Tabla de diagnóstico de cada punto de las instancias (nodo, distancia, tipo de calle, sentido) |
| `python src/visualizar.py` | Genera `resultados/mapa_nodos_reales.html` con depósito, entregas y pares de prueba |
| `python src/metricas.py` | Verifica la clase `Medicion` sobre un grafo de juguete de 3 nodos |
| `python src/area_estudio.py` | Reproduce la tabla de radios (requiere descargar de Overpass; ver Notas) |

## Área de estudio

| Parámetro | Valor |
|---|---|
| Centro | Metro La Raza (19.469323, -99.136283) |
| Radio | 1500 m (cuadrado de 3 km × 3 km) |
| Tipo de red | `drive` |
| Tamaño | 1683 nodos (intersecciones), 3810 arcos (tramos de calle) |

**Centro.** La Raza está en la frontera entre las alcaldías Gustavo A. Madero (zona norte) y Cuauhtémoc (zona centro), así que el área cubre ambas zonas que pide la práctica sin necesidad de un radio grande.

**Tipo de red.** Se usa `drive` porque el problema es de reparto en vehículo: sólo interesan las calles por donde puede circular un auto, respetando los sentidos de circulación.

**Radio.** Se descargó el grafo con cuatro radios desde el mismo centro:

| Radio (m) | Nodos | Arcos |
|---:|---:|---:|
| 500 | 220 | 444 |
| 1000 | 747 | 1639 |
| 1500 | 1683 | 3810 |
| 2000 | 2634 | 6043 |

Elegí 1500 m (1683 nodos) porque los radios menores (500 m y 1000 m) quedaban muy apretados para separar adecuadamente las 15 entregas y notar diferencias reales entre los algoritmos. Aunque 2000 m también era viable, preferí el área de 3x3 km con la expectativa de mantener tiempos de ejecución más ágiles al correr BFS y DFS múltiples veces durante las pruebas y la demostración en vivo.

El parámetro `dist` de `osmnx` define un cuadrado de `dist` metros hacia cada lado del centro, no un círculo. Por eso el número de nodos crece aproximadamente con el cuadrado del radio.

## Estructura del proyecto

```
x-route/
├── data/
│   ├── grafo_la_raza_1500.graphml   Grafo descargado (caché local)
│   └── instancias_la_raza.json      Depósito, entregas y pares de prueba
├── resultados/
│   └── mapa_nodos_reales.html       Mapa de las instancias sobre el grafo
├── src/
│   ├── grafo.py                     Carga del grafo, adyacencia, coordenadas a nodos, instancias
│   ├── metricas.py                  Clase Medicion para instrumentar los algoritmos
│   ├── visualizar.py                Mapa folium de las instancias
│   └── area_estudio.py              Experimento para elegir el radio
├── requirements.txt
├── README.md
└── ai_log.md                        Bitácora de uso de IA generativa
```

### Funciones de `grafo.py`

- `cargar_grafo(lat, lon, radio)`: si el `.graphml` existe en `data/`, lo carga; si no, lo descarga y lo guarda.
- `construir_adyacencia(G)`: convierte el `MultiDiGraph` de osmnx en un diccionario `{nodo: [(vecino, metros), ...]}`. Entre dos nodos con arcos paralelos conserva sólo el más corto (en cada dirección por separado) y descarta los bucles `u == v`.
- `nodo_mas_cercano(G, lat, lon, distancia_max=200)`: devuelve el nodo más cercano a una coordenada. Lanza `ValueError` si el nodo está a más de `distancia_max` metros, para detectar coordenadas fuera del área en lugar de pegarlas en silencio a un nodo de la orilla.
- `cargar_instancia(G, ruta_archivo)`: lee el JSON de instancias y agrega a cada punto su nodo.
- `diagnosticar_punto(G, lat, lon)`: nodo, distancia, tipos de calle, sentido y grado de entrada/salida de una coordenada.

## Convenciones del equipo

**Firma común de los algoritmos de búsqueda (Fases 1 y 2):**

```python
algoritmo(ady, origen, destino, medicion) -> list[int] | None
```

Reciben el diccionario de adyacencia, los nodos de origen y destino y un objeto `Medicion`. Devuelven el camino como lista de nodos, o `None` si no existe.

**Conteo de métricas** (para que la tabla comparativa sea válida entre algoritmos):

- La prueba de meta se hace al **sacar** un nodo de la frontera, nunca al generarlo. Es obligatorio para que UCS y A\* conserven la optimalidad.
- Se llama a `medicion.registrar_expansion()` en cada *pop*, incluido el del nodo destino.
- Después de cada *push* o *pop*, se llama a `medicion.actualizar_frontera(len(frontera))`.
- Con `heapq`, las entradas obsoletas que quedan en el heap (*lazy deletion*) se cuentan en el tamaño de la frontera.
- El tiempo se mide sólo durante la búsqueda: `iniciar_cronometro()` al empezar y `detener_cronometro()` al encontrar la meta, antes de reconstruir el camino.

**Prueba rápida:** en el grafo de juguete de `metricas.py`, de 1 a 3, BFS debe devolver `[1, 3]` (1 arco, 50 m) y UCS `[1, 2, 3]` (2 arcos, 35.5 m).

## Notas

- **El `.graphml` viene incluido en el repositorio a propósito.** Descargar desde el servidor público de Overpass puede tardar más de 15 minutos o fallar por saturación, así que el grafo se versiona para que todos trabajen con exactamente el mismo mapa y los experimentos sean reproducibles.
- **Si hay que volver a descargar**, `cargar_grafo()` usa el espejo `https://maps.mail.ru/osm/tools/overpass/api`, que fue el que respondió durante el desarrollo. El servidor principal (`overpass-api.de`) y el espejo de Kumi Systems fallaron por tiempo de espera.
- **Limitaciones conocidas de los datos:** los puntos de entrega se asocian a la intersección más cercana, así que el tramo entre la coordenada original y el nodo (hasta ~85 m en esta instancia) no se cuenta en el costo de la ruta. Además, OpenStreetMap incluye algunos tramos marcados con `access: no` (por ejemplo, un túnel de Congreso de la Unión) que osmnx conserva en el grafo.
