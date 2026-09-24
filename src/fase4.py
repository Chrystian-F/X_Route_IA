"""
X-Route — Fase 4: Visualización, pruebas y reporte
===================================================
Reúne los algoritmos de las Fases 1-3 SIN modificarlos y genera todo el
material visual del reporte:

  1. Snapshots de la frontera (3 obligatorios por algoritmo: 10 %, 50 % y
     100 % de las expansiones) como figura estática (PNG) y como mapa
     folium con una capa por momento.
  2. Mapas folium comparativos por par de prueba (una capa por algoritmo),
     dibujados sobre la geometría real de cada calle.
  3. Benchmark de los 9 algoritmos de búsqueda (BFS, DFS, UCS, A* x 3,
     Greedy x 3) en los 5 pares, con tiempo = mediana de varias
     repeticiones, y gráficas de rendimiento con matplotlib.
  4. Figuras estáticas del área de estudio, de rutas por par, de la ruta
     DFS y de la ruta óptima del TSP (Fase 3).

Cómo se toman los snapshots sin tocar el código de Fases 1 y 2
--------------------------------------------------------------
Todos los algoritmos del equipo llaman a `medicion.registrar_expansion()`
justo después de sacar un nodo de la frontera. `MedicionConSnapshots`
hereda de `Medicion` y, en las expansiones pedidas, lee las variables
locales del algoritmo que la llamó (`frontera`, `visitados`/`expandidos`,
`nodo`, `camino`) con `inspect`. Así el snapshot refleja exactamente la
frontera del algoritmo real, no la de una copia reimplementada.

Todas las entradas de la frontera del equipo son tuplas cuyo penúltimo
elemento es el nodo y el último el camino:
    BFS/DFS (nodo, camino) · UCS (g, nodo, camino) · A* (f, g, nodo, camino)
    Greedy (h, nodo, camino)

Ejecutar desde la raíz del proyecto (~30 s):
    python src/fase4.py
"""

import sys
import math
import inspect
import statistics
from pathlib import Path

import folium
import matplotlib
matplotlib.use("Agg")  # sin ventana: sólo se guardan PNG
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D
import pandas as pd

# ── Asegura que `src/` sea importable desde la raíz del proyecto ──────────────
sys.path.insert(0, str(Path(__file__).resolve().parent))
from grafo import cargar_grafo, construir_adyacencia, cargar_instancia
from metricas import Medicion
from fase1 import bfs, dfs, ucs, verificar_alcanzabilidad
from fase2 import (a_estrella, greedy_best_first, extraer_coordenadas,
                   heuristica_haversine, heuristica_euclidiana,
                   heuristica_personalizada, factor_ramificacion_efectiva,
                   distancias_reales_hacia_destino, verificar_admisibilidad)
from fase3 import matriz_distancias_astar, optimo_held_karp


# =============================================================================
# 0. Catálogo de algoritmos y estilo común
# =============================================================================
ORDEN_ALGORITMOS = [
    "BFS", "DFS", "UCS",
    "A*-Euclidiana", "A*-Haversine", "A*-Personalizada",
    "Greedy-Euclidiana", "Greedy-Haversine", "Greedy-Personalizada",
]

COLORES = {
    "BFS": "#1f77b4", "DFS": "#7f3c8d", "UCS": "#ff7f0e",
    "A*-Euclidiana": "#2ca02c", "A*-Haversine": "#17becf",
    "A*-Personalizada": "#98df8a",
    "Greedy-Euclidiana": "#d62728", "Greedy-Haversine": "#e377c2",
    "Greedy-Personalizada": "#8c564b",
}

FRACCIONES_SNAPSHOT = (0.10, 0.50, 1.00)


def catalogo_algoritmos(coords: dict, ady: dict, destino: int) -> list:
    """
    Lista [(nombre, funcion, heuristica_o_None), ...] en ORDEN_ALGORITMOS.
    Las heurísticas se precalculan una vez para `destino`, igual que en Fase 2.
    """
    h = {
        "Euclidiana": heuristica_euclidiana(coords, destino),
        "Haversine": heuristica_haversine(coords, destino),
        "Personalizada": heuristica_personalizada(coords, ady, destino),
    }
    catalogo = [("BFS", bfs, None), ("DFS", dfs, None), ("UCS", ucs, None)]
    for nombre_h in ("Euclidiana", "Haversine", "Personalizada"):
        catalogo.append((f"A*-{nombre_h}", a_estrella, h[nombre_h]))
    for nombre_h in ("Euclidiana", "Haversine", "Personalizada"):
        catalogo.append((f"Greedy-{nombre_h}", greedy_best_first, h[nombre_h]))
    return catalogo


def correr(funcion, ady: dict, origen: int, destino: int, medicion: Medicion,
           heuristica: dict = None):
    """Llama al algoritmo con la firma de Fase 1 o de Fase 2 según haga falta."""
    if heuristica is None:
        return funcion(ady, origen, destino, medicion)
    return funcion(ady, origen, destino, medicion, heuristica)


# =============================================================================
# 1. Snapshots de la frontera
# =============================================================================
class MedicionConSnapshots(Medicion):
    """
    `Medicion` que, además de contar, guarda una foto del estado de la
    búsqueda en las expansiones indicadas en `pasos`.

    Cada snapshot es un dict con:
        paso            número de expansión (1 = el origen)
        nodo_actual     nodo recién sacado de la frontera
        camino_actual   camino del origen a nodo_actual
        frontera        set de nodos en la frontera que aún no se cierran
        tam_frontera    len(frontera) tal cual (con entradas obsoletas, como
                        la convención de métricas del equipo)
        explorados      set de nodos ya cerrados (incluye nodo_actual)
    """

    def __init__(self, nombre_algoritmo: str, pasos):
        super().__init__(nombre_algoritmo)
        self.pasos = set(pasos)
        self.snapshots = []

    def registrar_expansion(self):
        super().registrar_expansion()
        if self.nodos_expandidos not in self.pasos:
            return
        marco = inspect.currentframe().f_back
        try:
            self.snapshots.append(leer_estado_busqueda(marco.f_locals,
                                                       self.nodos_expandidos))
        finally:
            del marco  # evita ciclos de referencia con el frame


def leer_estado_busqueda(variables: dict, paso: int) -> dict:
    """Extrae frontera y explorados de las variables locales del algoritmo."""
    if "frontera" not in variables:
        raise RuntimeError(
            "El algoritmo no tiene una variable local `frontera`; "
            "MedicionConSnapshots sólo funciona con la convención del equipo.")

    nodos_frontera = {entrada[-2] if isinstance(entrada, tuple) else entrada
                      for entrada in variables["frontera"]}

    if "expandidos" in variables:            # UCS, A*
        cerrados = set(variables["expandidos"])
    elif "visitados" in variables:           # BFS, DFS, Greedy
        cerrados = set(variables["visitados"])
    else:
        cerrados = set()

    nodo_actual = variables.get("nodo")
    # En BFS `visitados` son los nodos ALCANZADOS (incluye la frontera);
    # lo explorado es lo alcanzado que ya salió de la frontera.
    explorados = (cerrados - nodos_frontera) | ({nodo_actual} if nodo_actual is not None else set())
    frontera = nodos_frontera - explorados

    return {
        "paso": paso,
        "nodo_actual": nodo_actual,
        "camino_actual": list(variables.get("camino") or []),
        "frontera": frontera,
        "tam_frontera": len(variables["frontera"]),
        "explorados": explorados,
    }


def pasos_por_fraccion(total: int, fracciones=FRACCIONES_SNAPSHOT) -> list:
    """Convierte fracciones del total de expansiones en números de paso."""
    return sorted({min(total, max(1, math.ceil(f * total))) for f in fracciones})


def capturar_snapshots(nombre: str, funcion, ady: dict, origen: int, destino: int,
                       heuristica: dict = None, fracciones=FRACCIONES_SNAPSHOT) -> dict:
    """
    Corre el algoritmo dos veces: la primera para conocer el total N de
    expansiones y la segunda para capturar la frontera en los pasos
    correspondientes a `fracciones` de N. Verifica que ambas corridas
    coincidan (los algoritmos son deterministas).
    """
    med_base = Medicion(nombre)
    camino_base = correr(funcion, ady, origen, destino, med_base, heuristica)
    total = med_base.nodos_expandidos

    med = MedicionConSnapshots(nombre, pasos_por_fraccion(total, fracciones))
    camino = correr(funcion, ady, origen, destino, med, heuristica)

    if camino != camino_base or med.nodos_expandidos != total:
        raise RuntimeError(f"{nombre}: la corrida instrumentada no coincide con la original")

    return {"algoritmo": nombre, "camino": camino, "total_expandidos": total,
            "snapshots": med.snapshots}


# =============================================================================
# 2. Geometría: del camino de nodos a coordenadas sobre la calle real
# =============================================================================
def _xy_arco(G, u: int, v: int) -> list:
    """Puntos (lon, lat) del arco u→v más corto, orientados de u a v."""
    datos = G.get_edge_data(u, v)
    if not datos:
        raise ValueError(f"No existe el arco {u} → {v} en el grafo")
    arco = min(datos.values(), key=lambda a: float(a.get("length", math.inf)))
    geom = arco.get("geometry")
    ux, uy = G.nodes[u]["x"], G.nodes[u]["y"]
    vx, vy = G.nodes[v]["x"], G.nodes[v]["y"]
    if geom is None:
        return [(ux, uy), (vx, vy)]
    xy = list(geom.coords)
    d_inicio = (xy[0][0] - ux) ** 2 + (xy[0][1] - uy) ** 2
    d_fin = (xy[-1][0] - ux) ** 2 + (xy[-1][1] - uy) ** 2
    return xy[::-1] if d_fin < d_inicio else xy


def coordenadas_camino(G, camino: list) -> list:
    """Lista de (lat, lon) que sigue la forma real de cada calle del camino."""
    if not camino:
        return []
    puntos = [(G.nodes[camino[0]]["y"], G.nodes[camino[0]]["x"])]
    for u, v in zip(camino, camino[1:]):
        puntos.extend((lat, lon) for lon, lat in _xy_arco(G, u, v)[1:])
    return puntos


def segmentos_grafo(G) -> list:
    """Segmentos [(lon, lat), ...] de todas las calles, para el fondo de las figuras."""
    segmentos = []
    for u, v, datos in G.edges(data=True):
        geom = datos.get("geometry")
        if geom is not None:
            segmentos.append(list(geom.coords))
        else:
            segmentos.append([(G.nodes[u]["x"], G.nodes[u]["y"]),
                              (G.nodes[v]["x"], G.nodes[v]["y"])])
    return segmentos


def _xy_nodos(G, nodos) -> tuple:
    nodos = list(nodos)
    return ([G.nodes[n]["x"] for n in nodos], [G.nodes[n]["y"] for n in nodos])


# =============================================================================
# 3. Figuras estáticas (matplotlib)
# =============================================================================
def _eje_mapa(ax, G, segmentos, titulo: str = None):
    """Dibuja el fondo de calles y fija la proporción de un mapa real."""
    ax.add_collection(LineCollection(segmentos, colors="#cfcfcf", linewidths=0.5, zorder=1))
    xs = [G.nodes[n]["x"] for n in G.nodes]
    ys = [G.nodes[n]["y"] for n in G.nodes]
    ax.set_xlim(min(xs), max(xs))
    ax.set_ylim(min(ys), max(ys))
    lat_media = (min(ys) + max(ys)) / 2
    ax.set_aspect(1 / math.cos(math.radians(lat_media)))
    ax.set_xticks([])
    ax.set_yticks([])
    if titulo:
        ax.set_title(titulo, fontsize=9)


def _dibujar_camino(ax, G, camino, color, ancho=2.2, etiqueta=None, estilo="-", zorder=4):
    if not camino or len(camino) < 2:
        return
    latlon = coordenadas_camino(G, camino)
    ax.plot([p[1] for p in latlon], [p[0] for p in latlon], estilo, color=color,
            linewidth=ancho, label=etiqueta, zorder=zorder, solid_capstyle="round")


def _marcar_origen_destino(ax, G, origen, destino):
    ax.scatter(*_xy_nodos(G, [origen]), s=70, c="#2ca02c", marker="o",
               edgecolors="black", linewidths=0.8, zorder=6)
    ax.scatter(*_xy_nodos(G, [destino]), s=110, c="#d62728", marker="*",
               edgecolors="black", linewidths=0.8, zorder=6)


def figura_snapshots(G, segmentos, capturas: list, origen: int, destino: int,
                     ruta_salida: Path, titulo: str) -> None:
    """
    Cuadrícula filas = algoritmos, columnas = los 3 momentos de la búsqueda.
    Azul = explorados, naranja = frontera, negro = camino al nodo actual.
    En la última columna se dibuja además el camino final.
    """
    filas = len(capturas)
    fig, ejes = plt.subplots(filas, 3, figsize=(12, 4.6 * filas))
    if filas == 1:
        ejes = [ejes]
    for fila, captura in zip(ejes, capturas):
        total = captura["total_expandidos"]
        for col, (ax, snap) in enumerate(zip(fila, captura["snapshots"])):
            pct = 100 * snap["paso"] / total
            _eje_mapa(ax, G, segmentos,
                      f"{captura['algoritmo']} — {pct:.0f} % (expansión {snap['paso']}/{total})\n"
                      f"explorados {len(snap['explorados'])} · frontera {snap['tam_frontera']}")
            if snap["explorados"]:
                ax.scatter(*_xy_nodos(G, snap["explorados"]), s=5, c="#4a78c2",
                           alpha=0.55, zorder=2, linewidths=0)
            if snap["frontera"]:
                ax.scatter(*_xy_nodos(G, snap["frontera"]), s=13, c="#ff8c00",
                           zorder=3, linewidths=0)
            if col == len(fila) - 1 and captura["camino"]:
                _dibujar_camino(ax, G, captura["camino"], "black", ancho=2.4)
            else:
                _dibujar_camino(ax, G, snap["camino_actual"], "black", ancho=1.6)
            _marcar_origen_destino(ax, G, origen, destino)

    leyenda = [
        Line2D([], [], marker="o", color="w", markerfacecolor="#4a78c2", markersize=6, label="Explorados"),
        Line2D([], [], marker="o", color="w", markerfacecolor="#ff8c00", markersize=7, label="Frontera"),
        Line2D([], [], color="black", linewidth=2, label="Camino al nodo actual / final"),
        Line2D([], [], marker="o", color="w", markerfacecolor="#2ca02c", markeredgecolor="black", markersize=8, label="Origen"),
        Line2D([], [], marker="*", color="w", markerfacecolor="#d62728", markeredgecolor="black", markersize=12, label="Destino"),
    ]
    fig.legend(handles=leyenda, loc="lower center", ncol=5, fontsize=9, frameon=False)
    fig.suptitle(titulo, fontsize=12)
    fig.tight_layout(rect=(0, 0.04, 1, 0.97), h_pad=2.5)
    fig.savefig(ruta_salida, dpi=150)
    plt.close(fig)


def figura_area_estudio(G, segmentos, datos: dict, alcanzabilidad: dict,
                        ruta_salida: Path) -> None:
    """Grafo completo con depósito, entregas (coloreadas por alcanzabilidad) y pares."""
    fig, ax = plt.subplots(figsize=(8.5, 8.5))
    _eje_mapa(ax, G, segmentos)
    ax.collections[0].set_color("#9a9a9a")

    dep = datos["deposito"]["nodo"]
    ax.scatter(*_xy_nodos(G, [dep]), s=220, c="#d62728", marker="s",
               edgecolors="black", zorder=6, label="Depósito")
    for i, ent in enumerate(datos["entregas"], start=1):
        alcanzable = alcanzabilidad.get(ent["nodo"], False)
        x, y = _xy_nodos(G, [ent["nodo"]])
        ax.scatter(x, y, s=210, c="#1f77b4" if alcanzable else "black",
                   edgecolors="white", zorder=5)
        ax.annotate(str(i), (x[0], y[0]), color="white", fontsize=8, ha="center",
                    va="center", zorder=7, fontweight="bold")
    for k, par in enumerate(datos["pares_prueba"], start=1):
        xo, yo = _xy_nodos(G, [par["origen"]["nodo"]])
        xd, yd = _xy_nodos(G, [par["destino"]["nodo"]])
        ax.plot([xo[0], xd[0]], [yo[0], yd[0]], "--", color="#7f3c8d", linewidth=1.2, zorder=4)
        ax.scatter(xo, yo, s=60, c="#2ca02c", marker="^", edgecolors="black", zorder=6)
        ax.scatter(xd, yd, s=60, c="#ff8c00", marker="v", edgecolors="black", zorder=6)
        ax.annotate(f"P{k}", ((xo[0] + xd[0]) / 2, (yo[0] + yd[0]) / 2), fontsize=9,
                    color="#7f3c8d", fontweight="bold", zorder=7,
                    bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.8))

    leyenda = [
        Line2D([], [], marker="s", color="w", markerfacecolor="#d62728", markeredgecolor="black", markersize=11, label="Depósito"),
        Line2D([], [], marker="o", color="w", markerfacecolor="#1f77b4", markersize=10, label="Entrega (número)"),
        Line2D([], [], marker="^", color="w", markerfacecolor="#2ca02c", markeredgecolor="black", markersize=8, label="Origen de par"),
        Line2D([], [], marker="v", color="w", markerfacecolor="#ff8c00", markeredgecolor="black", markersize=8, label="Destino de par"),
    ]
    ax.legend(handles=leyenda, loc="upper left", fontsize=9, framealpha=0.9)
    ax.set_title(f"Área de estudio: La Raza, radio 1500 m — {G.number_of_nodes()} nodos, "
                 f"{G.number_of_edges()} arcos", fontsize=11)
    fig.tight_layout()
    fig.savefig(ruta_salida, dpi=150)
    plt.close(fig)


def figura_rutas_pares(G, segmentos, pares: list, caminos: dict, ruta_salida: Path,
                       algoritmos=("BFS", "UCS", "Greedy-Haversine")) -> None:
    """Un panel por par con las rutas de `algoritmos`, recortado a la zona del par."""
    n = len(pares)
    columnas = 3
    filas_fig = math.ceil(n / columnas)
    fig, ejes = plt.subplots(filas_fig, columnas, figsize=(12, 4.3 * filas_fig))
    ejes = list(ejes.flat)
    estilos = {"BFS": ("-", 4.2), "UCS": ("-", 2.4), "Greedy-Haversine": ("--", 2.0)}

    for k, (ax, par) in enumerate(zip(ejes, pares), start=1):
        o, d = par["origen"]["nodo"], par["destino"]["nodo"]
        _eje_mapa(ax, G, segmentos, f"Par {k}: {par['tipo'].split(':')[0]}")
        nodos_zona = set()
        for nombre in algoritmos:
            camino = caminos.get((k, nombre))
            if camino:
                nodos_zona.update(camino)
                estilo, ancho = estilos.get(nombre, ("-", 2.0))
                _dibujar_camino(ax, G, camino, COLORES[nombre], ancho=ancho,
                                estilo=estilo, etiqueta=nombre)
        _marcar_origen_destino(ax, G, o, d)
        # Recorte cuadrado (en metros) alrededor de las rutas del par
        xs, ys = _xy_nodos(G, nodos_zona | {o, d})
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        escala_x = math.cos(math.radians(cy))
        medio = max((max(xs) - min(xs)) * escala_x, max(ys) - min(ys), 0.003) * 0.58
        ax.set_xlim(cx - medio / escala_x, cx + medio / escala_x)
        ax.set_ylim(cy - medio, cy + medio)

    for ax in ejes[n:]:
        ax.axis("off")
    leyenda = [Line2D([], [], color=COLORES[a], linewidth=3,
                      linestyle=estilos.get(a, ("-", 2))[0],
                      label=a + (" (= A*)" if a == "UCS" else "")) for a in algoritmos]
    fig.legend(handles=leyenda, loc="lower right", bbox_to_anchor=(0.95, 0.18),
               fontsize=10, frameon=False)
    fig.suptitle("Rutas encontradas en los 5 pares de prueba", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(ruta_salida, dpi=150)
    plt.close(fig)


def figura_ruta_dfs(G, segmentos, camino_dfs: list, camino_ucs: list, origen: int,
                    destino: int, metros_dfs: float, metros_ucs: float,
                    ruta_salida: Path) -> None:
    """Contraste entre la ruta de DFS y la óptima para el mismo par."""
    fig, ax = plt.subplots(figsize=(8, 8))
    _eje_mapa(ax, G, segmentos)
    _dibujar_camino(ax, G, camino_dfs, COLORES["DFS"], ancho=1.2,
                    etiqueta=f"DFS: {len(camino_dfs) - 1} arcos, {metros_dfs / 1000:.1f} km")
    _dibujar_camino(ax, G, camino_ucs, COLORES["UCS"], ancho=4,
                    etiqueta=f"UCS (óptima): {len(camino_ucs) - 1} arcos, {metros_ucs:.0f} m",
                    zorder=5)
    _marcar_origen_destino(ax, G, origen, destino)
    ax.legend(loc="upper left", fontsize=10, framealpha=0.9)
    ax.set_title("Par 1: ruta de DFS contra la ruta óptima", fontsize=11)
    fig.tight_layout()
    fig.savefig(ruta_salida, dpi=150)
    plt.close(fig)


def figura_ruta_tsp(G, segmentos, puntos: list, perm: list, caminos: dict,
                    costo: float, ruta_salida: Path) -> None:
    """Recorrido óptimo del TSP (Fase 3) con el orden de visita numerado."""
    fig, ax = plt.subplots(figsize=(8.5, 8.5))
    _eje_mapa(ax, G, segmentos)
    paradas = [0] + list(perm) + [0]
    cmap = plt.get_cmap("viridis")
    for t, (a, b) in enumerate(zip(paradas, paradas[1:])):
        _dibujar_camino(ax, G, caminos[(a, b)], cmap(t / (len(paradas) - 1)), ancho=2.6)
    dep = puntos[0]["nodo"]
    ax.scatter(*_xy_nodos(G, [dep]), s=240, c="#d62728", marker="s", edgecolors="black", zorder=7)
    for orden, idx in enumerate(perm, start=1):
        x, y = _xy_nodos(G, [puntos[idx]["nodo"]])
        ax.scatter(x, y, s=190, c="white", edgecolors="black", zorder=7)
        ax.annotate(str(orden), (x[0], y[0]), fontsize=8, ha="center", va="center",
                    zorder=8, fontweight="bold")
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(1, len(paradas) - 1))
    barra = fig.colorbar(sm, ax=ax, fraction=0.035, pad=0.02)
    barra.set_label("Tramo del recorrido (1 = sale del depósito)")
    ax.set_title(f"Ruta óptima de reparto (Held-Karp = mejor GA): {costo / 1000:.2f} km", fontsize=11)
    fig.tight_layout()
    fig.savefig(ruta_salida, dpi=150)
    plt.close(fig)


# ── Gráficas de rendimiento ──────────────────────────────────────────────────
def grafica_barras_por_par(df: pd.DataFrame, columna: str, etiqueta_y: str,
                           titulo: str, ruta_salida: Path, escala: str = "linear",
                           algoritmos=ORDEN_ALGORITMOS) -> None:
    """Barras agrupadas: eje x = par, una barra por algoritmo."""
    pares = sorted(df["Par"].unique())
    ancho = 0.8 / len(algoritmos)
    fig, ax = plt.subplots(figsize=(10, 5.2))
    for i, alg in enumerate(algoritmos):
        sub = df[df["Algoritmo"] == alg].set_index("Par")
        valores = [sub.loc[p, columna] if p in sub.index else float("nan") for p in pares]
        xs = [p - 0.4 + ancho * (i + 0.5) for p in pares]
        ax.bar(xs, valores, width=ancho, color=COLORES[alg], label=alg,
               edgecolor="black", linewidth=0.3)
    if escala == "log":
        ax.set_yscale("log")
    elif escala == "symlog":
        ax.set_yscale("symlog", linthresh=1)
    ax.set_xticks(pares)
    ax.set_xticklabels([f"Par {p}" for p in pares])
    ax.set_ylabel(etiqueta_y)
    ax.set_title(titulo, fontsize=11)
    ax.grid(axis="y", alpha=0.3, which="both")
    ax.legend(ncol=5, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.09), frameon=False)
    fig.tight_layout()
    fig.savefig(ruta_salida, dpi=150)
    plt.close(fig)


def grafica_esfuerzo_vs_calidad(df: pd.DataFrame, ruta_salida: Path) -> None:
    """Dispersión: nodos expandidos (esfuerzo) contra exceso sobre el óptimo (calidad)."""
    marcadores = {1: "o", 2: "s", 3: "^", 4: "D", 5: "P"}
    fig, ax = plt.subplots(figsize=(9, 5.5))
    for alg in ORDEN_ALGORITMOS:
        sub = df[df["Algoritmo"] == alg]
        for _, fila in sub.iterrows():
            ax.scatter(fila["Expandidos"], fila["Gap_pct"], s=60,
                       c=COLORES[alg], marker=marcadores.get(int(fila["Par"]), "o"),
                       edgecolors="black", linewidths=0.4)
    ax.set_xscale("log")
    ax.set_yscale("symlog", linthresh=1)
    ax.set_xlabel("Nodos expandidos (escala log)")
    ax.set_ylabel("Exceso sobre la ruta óptima (%, escala symlog)")
    ax.set_title("Esfuerzo de búsqueda contra calidad de la solución", fontsize=11)
    ax.grid(alpha=0.3, which="both")
    leyenda_alg = [Line2D([], [], marker="o", color="w", markerfacecolor=COLORES[a],
                          markeredgecolor="black", markersize=8, label=a) for a in ORDEN_ALGORITMOS]
    leyenda_par = [Line2D([], [], marker=m, color="w", markerfacecolor="lightgray",
                          markeredgecolor="black", markersize=8, label=f"Par {p}")
                   for p, m in marcadores.items()]
    l1 = ax.legend(handles=leyenda_alg, fontsize=8, loc="upper left", bbox_to_anchor=(1.0, 1.0))
    ax.add_artist(l1)
    ax.legend(handles=leyenda_par, fontsize=8, loc="lower left", bbox_to_anchor=(1.0, 0.0))
    fig.tight_layout()
    fig.savefig(ruta_salida, dpi=150)
    plt.close(fig)


def grafica_admisibilidad(df_adm: pd.DataFrame, ruta_salida: Path) -> None:
    """Porcentaje de nodos que violan h(n) <= h*(n) y exceso máximo, por heurística y par."""
    heuristicas = ["Euclidiana", "Haversine", "Personalizada"]
    colores = {"Euclidiana": COLORES["A*-Euclidiana"], "Haversine": COLORES["A*-Haversine"],
               "Personalizada": COLORES["Greedy-Personalizada"]}
    pares = sorted(df_adm["Par"].unique())
    ancho = 0.26
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.2))
    for i, h in enumerate(heuristicas):
        sub = df_adm[df_adm["Heuristica"] == h].set_index("Par")
        xs = [p - 0.26 + ancho * i for p in pares]
        ax1.bar(xs, [sub.loc[p, "Pct_violaciones"] for p in pares], width=ancho,
                color=colores[h], label=h, edgecolor="black", linewidth=0.3)
        ax2.bar(xs, [sub.loc[p, "Max_exceso_m"] for p in pares], width=ancho,
                color=colores[h], label=h, edgecolor="black", linewidth=0.3)
    for ax, titulo, ylab in ((ax1, "Nodos que sobreestiman", "% de nodos con h(n) > h*(n)"),
                             (ax2, "Peor sobreestimación", "Exceso máximo (m)")):
        ax.set_xticks(pares)
        ax.set_xticklabels([f"P{p}" for p in pares])
        ax.set_title(titulo, fontsize=10)
        ax.set_ylabel(ylab)
        ax.grid(axis="y", alpha=0.3)
    ax2.set_yscale("symlog", linthresh=1)
    ax1.legend(fontsize=9)
    fig.suptitle("Verificación empírica de admisibilidad (Dijkstra inverso sobre todo el grafo)",
                 fontsize=11)
    fig.tight_layout()
    fig.savefig(ruta_salida, dpi=150)
    plt.close(fig)


# =============================================================================
# 4. Mapas folium
# =============================================================================
def _mapa_base(G, centro=None, zoom=15):
    if centro is None:
        ys = [G.nodes[n]["y"] for n in G.nodes]
        xs = [G.nodes[n]["x"] for n in G.nodes]
        centro = ((min(ys) + max(ys)) / 2, (min(xs) + max(xs)) / 2)
    return folium.Map(location=centro, zoom_start=zoom, tiles="OpenStreetMap")


def mapa_comparativo_par(G, par: dict, indice: int, filas: list, caminos: dict,
                         ruta_salida: Path) -> None:
    """
    Una capa por algoritmo (activables desde el control de capas). DFS y las
    variantes con la misma ruta que UCS inician ocultas para no saturar.
    """
    o, d = par["origen"]["nodo"], par["destino"]["nodo"]
    centro = ((G.nodes[o]["y"] + G.nodes[d]["y"]) / 2, (G.nodes[o]["x"] + G.nodes[d]["x"]) / 2)
    mapa = _mapa_base(G, centro, zoom=16)
    visibles = {"BFS", "UCS", "Greedy-Haversine"}

    for fila in filas:
        nombre = fila["Algoritmo"]
        camino = caminos.get((indice, nombre))
        if not camino:
            continue
        capa = folium.FeatureGroup(name=f"{nombre} — {fila['Metros']:.0f} m", show=nombre in visibles)
        folium.PolyLine(
            coordenadas_camino(G, camino), color=COLORES[nombre],
            weight=6 if nombre == "BFS" else 4, opacity=0.8,
            dash_array="8" if nombre.startswith("Greedy") else None,
            tooltip=(f"{nombre}: {fila['Metros']:.1f} m, {fila['Arcos']} arcos, "
                     f"{fila['Expandidos']} expandidos, {fila['Tiempo_ms']:.3f} ms"),
        ).add_to(capa)
        capa.add_to(mapa)

    folium.Marker((G.nodes[o]["y"], G.nodes[o]["x"]), popup=f"Origen par {indice}",
                  icon=folium.Icon(color="green", icon="play")).add_to(mapa)
    folium.Marker((G.nodes[d]["y"], G.nodes[d]["x"]), popup=f"Destino par {indice}: {par['tipo']}",
                  icon=folium.Icon(color="red", icon="flag")).add_to(mapa)
    folium.LayerControl(collapsed=False).add_to(mapa)
    mapa.save(str(ruta_salida))


def mapa_snapshots(G, captura: dict, origen: int, destino: int, ruta_salida: Path) -> None:
    """Mapa interactivo con una capa por snapshot (sólo la primera visible)."""
    mapa = _mapa_base(G)
    total = captura["total_expandidos"]
    for i, snap in enumerate(captura["snapshots"]):
        pct = 100 * snap["paso"] / total
        capa = folium.FeatureGroup(
            name=f"{pct:.0f} % — expansión {snap['paso']}: {len(snap['explorados'])} explorados, "
                 f"frontera {snap['tam_frontera']}", show=(i == 0))
        for n in snap["explorados"]:
            folium.CircleMarker((G.nodes[n]["y"], G.nodes[n]["x"]), radius=2, color="#4a78c2",
                                fill=True, fill_opacity=0.6, weight=0).add_to(capa)
        for n in snap["frontera"]:
            folium.CircleMarker((G.nodes[n]["y"], G.nodes[n]["x"]), radius=4, color="#ff8c00",
                                fill=True, fill_opacity=0.9, weight=1,
                                tooltip=f"Frontera: nodo {n}").add_to(capa)
        if len(snap["camino_actual"]) > 1:
            folium.PolyLine(coordenadas_camino(G, snap["camino_actual"]), color="black",
                            weight=3, tooltip="Camino al nodo actual").add_to(capa)
        capa.add_to(mapa)
    if captura["camino"]:
        capa_final = folium.FeatureGroup(name="Camino final", show=True)
        folium.PolyLine(coordenadas_camino(G, captura["camino"]), color="#d62728",
                        weight=4, opacity=0.8).add_to(capa_final)
        capa_final.add_to(mapa)
    folium.Marker((G.nodes[origen]["y"], G.nodes[origen]["x"]), popup="Origen",
                  icon=folium.Icon(color="green", icon="play")).add_to(mapa)
    folium.Marker((G.nodes[destino]["y"], G.nodes[destino]["x"]), popup="Destino",
                  icon=folium.Icon(color="red", icon="flag")).add_to(mapa)
    folium.LayerControl(collapsed=False).add_to(mapa)
    mapa.save(str(ruta_salida))


# =============================================================================
# 5. Benchmark de los algoritmos de búsqueda
# =============================================================================
def medir_algoritmos(ady: dict, coords: dict, pares: list, repeticiones: int = 15) -> tuple:
    """
    Corre los 9 algoritmos en cada par `repeticiones` veces. Nodos
    expandidos, frontera y camino son deterministas; el tiempo reportado es
    la MEDIANA (una sola corrida de < 1 ms es muy ruidosa).

    Returns:
        (df, caminos) — df con una fila por (par, algoritmo) y
        caminos = {(par, algoritmo): [nodos]}.
    """
    filas, caminos = [], {}
    for k, par in enumerate(pares, start=1):
        o, d = par["origen"]["nodo"], par["destino"]["nodo"]
        for nombre, funcion, h in catalogo_algoritmos(coords, ady, d):
            tiempos = []
            for _ in range(repeticiones):
                med = Medicion(nombre)
                camino = correr(funcion, ady, o, d, med, h)
                tiempos.append(med.tiempo_total_ms())
            fila = med.generar_diccionario(camino, ady)
            fila["Tiempo_ms"] = round(statistics.median(tiempos), 4)
            fila["Tiempo_min_ms"] = round(min(tiempos), 4)
            fila["Par"] = k
            fila["Tipo"] = par["tipo"].split(":")[0]
            fila["b_estrella"] = (factor_ramificacion_efectiva(fila["Expandidos"], fila["Arcos"])
                                  if fila["Arcos"] else None)
            filas.append(fila)
            caminos[(k, nombre)] = camino

    df = pd.DataFrame(filas)
    optimo = df[df["Algoritmo"] == "UCS"].set_index("Par")["Metros"]
    df["Optimo_m"] = df["Par"].map(optimo)
    df["Gap_pct"] = (100 * (df["Metros"] - df["Optimo_m"]) / df["Optimo_m"]).round(2)
    df["Es_optima"] = df["Gap_pct"].abs() < 1e-6
    df["Algoritmo"] = pd.Categorical(df["Algoritmo"], ORDEN_ALGORITMOS, ordered=True)
    df = df.sort_values(["Par", "Algoritmo"]).reset_index(drop=True)
    df["Algoritmo"] = df["Algoritmo"].astype(str)
    return df, caminos


def resumir_por_algoritmo(df: pd.DataFrame) -> pd.DataFrame:
    """Promedios sobre los 5 pares y cuántas veces cada algoritmo halló el óptimo."""
    resumen = df.groupby("Algoritmo", sort=False).agg(
        Expandidos_medio=("Expandidos", "mean"),
        Frontera_max_media=("Frontera_Max", "mean"),
        Tiempo_mediano_ms=("Tiempo_ms", "mean"),
        Metros_medio=("Metros", "mean"),
        Gap_medio_pct=("Gap_pct", "mean"),
        Gap_max_pct=("Gap_pct", "max"),
        Veces_optimo=("Es_optima", "sum"),
        b_estrella_medio=("b_estrella", "mean"),
    ).reindex(ORDEN_ALGORITMOS)
    return resumen.round(3).reset_index()


def tabla_admisibilidad(ady: dict, coords: dict, pares: list) -> pd.DataFrame:
    """Repite la verificación de Fase 2 para graficarla con los datos actuales."""
    filas = []
    for k, par in enumerate(pares, start=1):
        d = par["destino"]["nodo"]
        reales = distancias_reales_hacia_destino(ady, d)
        for nombre, h in (("Euclidiana", heuristica_euclidiana(coords, d)),
                          ("Haversine", heuristica_haversine(coords, d)),
                          ("Personalizada", heuristica_personalizada(coords, ady, d))):
            fila = verificar_admisibilidad(h, reales, nombre)
            fila["Par"] = k
            filas.append(fila)
    return pd.DataFrame(filas)


# =============================================================================
# 6. Experimento principal
# =============================================================================
PAR_SNAPSHOTS = 2          # ruta larga perimetral: máxima diferencia UCS vs A*
REPETICIONES = 15


def ejecutar_fase4():
    print("=" * 70)
    print("  X-ROUTE — FASE 4: VISUALIZACIÓN, PRUEBAS Y REPORTE")
    print("=" * 70)

    raiz = Path(__file__).resolve().parent.parent
    carpeta = raiz / "resultados" / "fase4"
    carpeta.mkdir(parents=True, exist_ok=True)

    print("\n[1/7] Cargando grafo e instancias...")
    G = cargar_grafo()
    ady = construir_adyacencia(G)
    datos = cargar_instancia(G)
    coords = extraer_coordenadas(G)
    pares = datos["pares_prueba"]
    segmentos = segmentos_grafo(G)
    print(f"      {G.number_of_nodes()} nodos, {G.number_of_edges()} arcos, {len(pares)} pares")

    # ── Área de estudio ──────────────────────────────────────────────────────
    print("\n[2/7] Figura del área de estudio...")
    alcanzabilidad = verificar_alcanzabilidad(ady, datos["deposito"]["nodo"],
                                              [e["nodo"] for e in datos["entregas"]])
    figura_area_estudio(G, segmentos, datos, alcanzabilidad, carpeta / "fig_area_estudio.png")
    print(f"      Entregas alcanzables desde el depósito: "
          f"{sum(alcanzabilidad.values())}/{len(alcanzabilidad)}")

    # ── Benchmark ────────────────────────────────────────────────────────────
    print(f"\n[3/7] Benchmark: 9 algoritmos x {len(pares)} pares x {REPETICIONES} repeticiones...")
    df, caminos = medir_algoritmos(ady, coords, pares, REPETICIONES)
    columnas = ["Par", "Tipo", "Algoritmo", "Expandidos", "Frontera_Max", "Tiempo_ms",
                "Tiempo_min_ms", "Arcos", "Metros", "Optimo_m", "Gap_pct", "Es_optima",
                "b_estrella", "Camino"]
    df[columnas].to_csv(carpeta / "rendimiento_fase4.csv", index=False)
    resumen = resumir_por_algoritmo(df)
    resumen.to_csv(carpeta / "resumen_algoritmos_fase4.csv", index=False)
    pd.set_option("display.width", 160)
    print(resumen.to_string(index=False))

    # ── Gráficas de rendimiento ──────────────────────────────────────────────
    print("\n[4/7] Gráficas de rendimiento (matplotlib)...")
    grafica_barras_por_par(df, "Expandidos", "Nodos expandidos (log)",
                           "Nodos expandidos por algoritmo y par", carpeta / "fig_expandidos.png", "log")
    grafica_barras_por_par(df, "Tiempo_ms", "Tiempo mediano (ms, log)",
                           f"Tiempo de búsqueda (mediana de {REPETICIONES} corridas)",
                           carpeta / "fig_tiempo.png", "log")
    grafica_barras_por_par(df, "Frontera_Max", "Tamaño máximo de la frontera",
                           "Memoria: tamaño máximo de la frontera", carpeta / "fig_frontera.png", "log")
    grafica_barras_por_par(df, "Gap_pct", "Exceso sobre el óptimo (%, symlog)",
                           "Calidad: longitud del camino respecto al óptimo de UCS",
                           carpeta / "fig_calidad.png", "symlog")
    grafica_barras_por_par(df, "b_estrella", "b*", "Factor de ramificación efectiva b*",
                           carpeta / "fig_bestrella.png",
                           algoritmos=[a for a in ORDEN_ALGORITMOS if a != "DFS"])
    grafica_esfuerzo_vs_calidad(df, carpeta / "fig_esfuerzo_calidad.png")
    df_adm = tabla_admisibilidad(ady, coords, pares)
    df_adm.to_csv(carpeta / "admisibilidad_fase4.csv", index=False)
    grafica_admisibilidad(df_adm, carpeta / "fig_admisibilidad.png")

    # ── Snapshots de frontera ────────────────────────────────────────────────
    print(f"\n[5/7] Snapshots de la frontera (par {PAR_SNAPSHOTS})...")
    par_s = pares[PAR_SNAPSHOTS - 1]
    o_s, d_s = par_s["origen"]["nodo"], par_s["destino"]["nodo"]
    cat = {n: (f, h) for n, f, h in catalogo_algoritmos(coords, ady, d_s)}
    capturas = {}
    filas_snap = []
    for nombre in ("BFS", "DFS", "UCS", "A*-Haversine", "Greedy-Haversine"):
        funcion, h = cat[nombre]
        captura = capturar_snapshots(nombre, funcion, ady, o_s, d_s, h)
        capturas[nombre] = captura
        slug = nombre.lower().replace("*", "estrella").replace("-", "_")
        mapa_snapshots(G, captura, o_s, d_s, carpeta / f"mapa_snapshots_{slug}.html")
        for s in captura["snapshots"]:
            filas_snap.append({"Algoritmo": nombre, "Paso": s["paso"],
                               "Pct": round(100 * s["paso"] / captura["total_expandidos"], 1),
                               "Explorados": len(s["explorados"]),
                               "Frontera_nodos": len(s["frontera"]),
                               "Frontera_len": s["tam_frontera"]})
        print(f"      {nombre:<17} {captura['total_expandidos']:>5} expansiones → "
              f"snapshots en {[s['paso'] for s in captura['snapshots']]}")
    pd.DataFrame(filas_snap).to_csv(carpeta / "snapshots_fase4.csv", index=False)

    figura_snapshots(G, segmentos, [capturas["BFS"], capturas["UCS"]], o_s, d_s,
                     carpeta / "fig_snapshots_bfs_ucs.png",
                     f"Snapshots de la frontera — búsqueda a ciegas (par {PAR_SNAPSHOTS})")
    figura_snapshots(G, segmentos, [capturas["A*-Haversine"], capturas["Greedy-Haversine"]],
                     o_s, d_s, carpeta / "fig_snapshots_astar_greedy.png",
                     f"Snapshots de la frontera — búsqueda informada (par {PAR_SNAPSHOTS})")
    figura_snapshots(G, segmentos, [capturas["DFS"]], o_s, d_s,
                     carpeta / "fig_snapshots_dfs.png",
                     f"Snapshots de la frontera — DFS (par {PAR_SNAPSHOTS})")

    # ── Mapas y figuras de rutas ─────────────────────────────────────────────
    print("\n[6/7] Mapas folium comparativos y figuras de rutas...")
    for k, par in enumerate(pares, start=1):
        filas = df[df["Par"] == k].to_dict("records")
        mapa_comparativo_par(G, par, k, filas, caminos, carpeta / f"mapa_comparativo_par{k}.html")
    figura_rutas_pares(G, segmentos, pares, caminos, carpeta / "fig_rutas_pares.png")
    fila_dfs = df[(df["Par"] == 1) & (df["Algoritmo"] == "DFS")].iloc[0]
    fila_ucs = df[(df["Par"] == 1) & (df["Algoritmo"] == "UCS")].iloc[0]
    figura_ruta_dfs(G, segmentos, caminos[(1, "DFS")], caminos[(1, "UCS")],
                    pares[0]["origen"]["nodo"], pares[0]["destino"]["nodo"],
                    fila_dfs["Metros"], fila_ucs["Metros"], carpeta / "fig_ruta_dfs_par1.png")

    # ── Ruta del TSP (Fase 3) ────────────────────────────────────────────────
    print("\n[7/7] Figura de la ruta óptima del TSP (matriz A* + Held-Karp)...")
    puntos = [datos["deposito"]] + datos["entregas"]
    D, caminos_tsp, _ = matriz_distancias_astar(ady, coords, [p["nodo"] for p in puntos])
    indices = [k for k in range(1, len(puntos))
               if all(D[k][m] < math.inf and D[m][k] < math.inf for m in range(len(puntos)))]
    perm_opt, costo_opt = optimo_held_karp(D, indices)
    figura_ruta_tsp(G, segmentos, puntos, perm_opt, caminos_tsp, costo_opt,
                    carpeta / "fig_ruta_tsp.png")
    print(f"      Óptimo: {costo_opt:,.1f} m — orden: "
          f"{' → '.join(puntos[i]['nombre'].replace('Cliente ', 'C') for i in perm_opt)}")

    print("\n" + "=" * 70)
    print(f"  Fase 4 completada. Archivos en resultados/fase4/ "
          f"({len(list(carpeta.iterdir()))} archivos)")
    print("=" * 70)
    return df, resumen


if __name__ == "__main__":
    ejecutar_fase4()
