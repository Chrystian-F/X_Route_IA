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
│   ├── fase1.py                     BFS, DFS, UCS (búsqueda a ciegas)
│   ├── fase2.py                     A*, Greedy Best-First, heurísticas, costo_entre_puntos
│   ├── fase3.py                     Simulated Annealing, Algoritmo Genético, 2-opt, Held-Karp
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

## Fase 2 — Búsqueda informada

`src/fase2.py` implementa A* y Greedy Best-First Search sobre el mismo `ady` de Fase 1, con la misma convención de instrumentación (prueba de meta al sacar, `medicion.registrar_expansion()` / `medicion.actualizar_frontera()` en cada pop/push).

**Firma de los algoritmos informados** (extiende la firma común con la heurística ya evaluada para el destino actual):

```python
a_estrella(ady, origen, destino, medicion, heuristica) -> list[int] | None
greedy_best_first(ady, origen, destino, medicion, heuristica) -> list[int] | None
```

`heuristica` es un diccionario `{nodo: h(nodo)}` **precalculado para un destino fijo** por uno de los tres generadores:

- `heuristica_haversine(coords, destino)` — admisible por argumento geométrico exacto (la geodésica es la distancia mínima posible entre dos puntos sobre la esfera).
- `heuristica_euclidiana(coords, destino)` — distancia en un plano tangente local (`proyectar_local()`); admisible en teoría, con violaciones empíricas mínimas (fracciones de metro) por el error numérico de la proyección aproximada.
- `heuristica_personalizada(coords, ady, destino)` — Haversine + penalización por giro estimado; **no admisible en general, a propósito** (ver docstring), para contrastar el trade-off calidad-vs-velocidad.

`coords = extraer_coordenadas(G)` da el diccionario `{nodo: (lat, lon)}` que consumen las tres heurísticas.

**Función de costo para Fase 3** (la que pidió el equipo el lunes en la noche):

```python
from fase2 import costo_entre_puntos
metros = costo_entre_puntos(lat1, lon1, lat2, lon2)   # Haversine directo, sin pasar por el grafo
```

**Verificación de admisibilidad:** `distancias_reales_hacia_destino(ady, destino)` corre un Dijkstra desde el destino sobre el grafo transpuesto (`construir_adyacencia_reversa`) para obtener el costo real óptimo de **cualquier** nodo hacia ese destino — no sólo del origen de un par de prueba. `verificar_admisibilidad(heuristica, distancias_reales, nombre)` compara ambos y reporta cuántos nodos violan `h(n) <= costo_real(n)`.

**Factor de ramificación efectiva:** `factor_ramificacion_efectiva(nodos_expandidos, profundidad)` resuelve numéricamente `N + 1 = 1 + b* + b*² + ... + b*^d` (Russell & Norvig) por bisección.

Ejecutar desde la raíz del proyecto:

```
python src/fase2.py
```

Genera `resultados/fase2/resultados_fase2.csv`, `resultados/fase2/admisibilidad_fase2.csv` y mapas folium de cada ruta A*.

## Fase 3 — Búsqueda local

`src/fase3.py` busca el orden de visita de las 15 entregas que minimiza la distancia total (TSP, NP-hard: 15! ≈ 1.3 × 10¹² órdenes posibles).

**Formulación:**

- **Estado:** permutación de los índices de las entregas. El recorrido es un circuito cerrado: depósito → π₁ → … → π₁₅ → depósito.
- **Función objetivo:** `costo_ruta(perm, D)`, la suma de `D[a][b]` sobre los tramos del recorrido. `D` es la matriz 16 × 16 de distancias **reales sobre calles** calculada una sola vez con A* + Haversine de Fase 2 (`matriz_distancias_astar`, 240 búsquedas, ~0.1 s). No se usa `costo_entre_puntos()` (línea recta) porque en esta instancia las calles son en promedio 73% más largas que la línea recta.
- **Vecindad:** 2-opt (`vecino_2opt`), invertir el tramo `perm[i..j]`.
- **Matriz asimétrica:** por las calles de un solo sentido, `D[i][j] != D[j][i]` (diferencia media de ~420 m). Invertir un tramo con 2-opt cambia el sentido de todas sus calles, por eso `costo_ruta()` recalcula el recorrido completo en vez de usar la fórmula incremental de 2-opt simétrico.

**Algoritmos:**

| Función | Qué hace |
|---|---|
| `simulated_annealing(D, indices, rng, T0, alfa, T_min, iter_por_temp)` | SA con vecindad 2-opt, criterio de Metropolis `exp(-Δ/T)` y enfriamiento geométrico `T ← α·T` |
| `algoritmo_genetico(D, indices, rng, ...)` | GA generacional: permutaciones, cruza OX (`cruza_ox`), mutación por intercambio (`mutacion_intercambio`), torneo k = 3 y elitismo de 2 |
| `busqueda_local_2opt(perm, D)` | Hill climbing de máximo descenso con 2-opt hasta un óptimo local (línea base y muestreo del paisaje) |
| `vecino_mas_cercano(D, indices)` | Heurística constructiva voraz (línea base) |
| `optimo_held_karp(D, indices)` | Óptimo exacto por programación dinámica O(N²·2ᴺ); sólo como referencia para medir el gap, viable porque N = 15 |

**Parámetros de SA y su justificación:**

- **T₀ = −Δ̄ / ln(0.8)** (`calcular_temperatura_inicial`): se muestrean movimientos 2-opt al azar, Δ̄ es el empeoramiento promedio (~1570 m) y T₀ se elige para aceptarlo con 80% de probabilidad al inicio. Queda T₀ ≈ 7036 y se ajusta solo si cambia la instancia.
- **α = 0.99:** ~880 niveles de temperatura. Con α = 0.95 (~170 niveles) SA quedaba en promedio ~10% arriba del óptimo contra ~2% con 0.99: el paisaje bajo 2-opt es muy rugoso en esta matriz asimétrica y hace falta enfriar despacio.
- **T_min = 1 m:** a esa temperatura una ruta 10 m peor se acepta con probabilidad e⁻¹⁰ ≈ 4.5 × 10⁻⁵; SA ya es hill climbing puro.
- **Iteraciones por temperatura = N(N−1)/2 = 105**, el tamaño de la vecindad 2-opt. Total ≈ 92 600 evaluaciones.

**Parámetros del GA:** 200 individuos × 400 generaciones ≈ 79 400 evaluaciones (presupuesto parecido al de SA), cruza 0.9, mutación 0.5. Con mutación 0.2 o 0.3 la población convergía prematuramente en algunas semillas; con 0.7 la mutación destruía lo que construía la cruza.

**Resultados (10 semillas por método, `resultados/fase3/resumen_fase3.csv`):**

| Método | Costo medio (m) | Gap medio vs óptimo | Mejora sobre ruta aleatoria | Tiempo medio |
|---|---:|---:|---:|---:|
| Ruta aleatoria (1000 muestras) | 31 739.7 | 143.8% | — | — |
| Vecino más cercano | 16 615.4 | 27.60% | 47.65% | 0.05 ms |
| 2-opt (hill climbing) | 16 262.0 | 24.89% | 48.76% | 1.4 ms |
| Simulated Annealing | 13 311.6 | 2.23% | 58.06% | ~330 ms |
| Algoritmo Genético | 13 029.3 | 0.06% | 58.95% | ~900 ms |
| Óptimo (Held-Karp) | 13 021.0 | 0% | 58.98% | ~0.6 s |

El análisis del paisaje (2-opt desde 300 arranques aleatorios) encontró 255 óptimos locales distintos y sólo 1 arranque llegó al óptimo global; por eso el hill climbing puro no basta y SA/GA sí aportan.

Ejecutar desde la raíz del proyecto (~25 s):

```
python src/fase3.py
```

Genera en `resultados/fase3/`: `matriz_distancias_astar.csv`, `resultados_fase3.csv` (cada corrida), `resumen_fase3.csv`, `paisaje_fase3.csv`, `temperatura_inicial_fase3.csv`, las gráficas `convergencia_fase3.png`, `calidad_vs_tiempo_fase3.png`, `paisaje_fase3.png`, `temperatura_inicial_fase3.png` y el mapa `mapa_mejor_ruta.html` (la capa "Ruta aleatoria" se activa desde el control de capas). Al final imprime las respuestas a las tres preguntas de análisis con los números de la corrida.

## Notas

- **El `.graphml` viene incluido en el repositorio a propósito.** Descargar desde el servidor público de Overpass puede tardar más de 15 minutos o fallar por saturación, así que el grafo se versiona para que todos trabajen con exactamente el mismo mapa y los experimentos sean reproducibles.
- **Si hay que volver a descargar**, `cargar_grafo()` usa el espejo `https://maps.mail.ru/osm/tools/overpass/api`, que fue el que respondió durante el desarrollo. El servidor principal (`overpass-api.de`) y el espejo de Kumi Systems fallaron por tiempo de espera.
- **Limitaciones conocidas de los datos:** los puntos de entrega se asocian a la intersección más cercana, así que el tramo entre la coordenada original y el nodo (hasta ~85 m en esta instancia) no se cuenta en el costo de la ruta. Además, OpenStreetMap incluye algunos tramos marcados con `access: no` (por ejemplo, un túnel de Congreso de la Unión) que osmnx conserva en el grafo.