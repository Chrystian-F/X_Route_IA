import osmnx as ox
import os
import json
from pathlib import Path

def cargar_grafo(lat=19.469323, lon=-99.136283, radio=1500):
    ox.settings.requests_timeout = 90
    ox.settings.overpass_url = "https://maps.mail.ru/osm/tools/overpass/api"
    directorio_raiz = Path(__file__).resolve().parent.parent
    carpeta_data = directorio_raiz / "data"
    ruta_archivo = carpeta_data / f"grafo_la_raza_{radio}.graphml"
    os.makedirs(carpeta_data, exist_ok=True)
    
    if ruta_archivo.exists():
        # Descomenta el print si quieres ver cuándo carga desde caché
        # print(f"Cargando grafo desde disco: {ruta_archivo}...")
        G = ox.load_graphml(ruta_archivo)
    else:
        print(f"Descargando grafo de {radio}m desde la API (puede tardar unos minutos)...")
        G = ox.graph_from_point((lat, lon), dist=radio, network_type="drive")
        ox.save_graphml(G, filepath=ruta_archivo)
    return G

def construir_adyacencia(G):
    grafo_simple = {int(nodo): [] for nodo in G.nodes()}
    arcos_minimos = {}
    
    for u, v, data in G.edges(data=True):
        u_int, v_int = int(u), int(v)
        if u_int == v_int:
            continue
            
        costo = float(data.get('length', float('inf')))
        
        if (u_int, v_int) in arcos_minimos:
            if costo < arcos_minimos[(u_int, v_int)]:
                arcos_minimos[(u_int, v_int)] = costo
        else:
            arcos_minimos[(u_int, v_int)] = costo
            
    for (u, v), costo in arcos_minimos.items():
        grafo_simple[u].append((v, costo))
        
    return grafo_simple

def nodo_mas_cercano(G, lat, lon, distancia_max=200):
    nodo, distancia = ox.distance.nearest_nodes(G, X=lon, Y=lat, return_dist=True)
    
    if distancia > distancia_max:
        raise ValueError(f"Coordenada ({lat}, {lon}) fuera de tolerancia. Distancia: {distancia:.2f}m (Máx: {distancia_max}m)")
        
    return int(nodo)

def cargar_instancia(G, ruta_archivo="data/instancias_la_raza.json"):
    directorio_raiz = Path(__file__).resolve().parent.parent
    ruta_completa = directorio_raiz / ruta_archivo
    
    with open(ruta_completa, 'r', encoding='utf-8') as f:
        datos = json.load(f)
        
    # Convertir las coordenadas del depósito a nodo
    dep = datos["deposito"]
    dep["nodo"] = nodo_mas_cercano(G, dep["lat"], dep["lon"])
    
    # Convertir todas las entregas
    for entrega in datos["entregas"]:
        entrega["nodo"] = nodo_mas_cercano(G, entrega["lat"], entrega["lon"])
        
    # Convertir los pares de prueba
    for par in datos["pares_prueba"]:
        par["origen"]["nodo"] = nodo_mas_cercano(G, par["origen"]["lat"], par["origen"]["lon"])
        par["destino"]["nodo"] = nodo_mas_cercano(G, par["destino"]["lat"], par["destino"]["lon"])
        
    return datos

def diagnosticar_punto(G, lat, lon):
    nodo, distancia = ox.distance.nearest_nodes(G, X=lon, Y=lat, return_dist=True)
    
    out_edges = list(G.out_edges(nodo, data=True))
    in_edges = list(G.in_edges(nodo, data=True))
    
    tipos_calle = set()
    sentidos = set()
    
    # Función auxiliar para manejar casos donde OSM devuelve una lista en lugar de un texto
    def procesar_atributo(attr_val, conjunto):
        if isinstance(attr_val, list):
            for val in attr_val:
                conjunto.add(str(val))
        elif attr_val is not None:
            conjunto.add(str(attr_val))

    for _, _, data in out_edges + in_edges:
        procesar_atributo(data.get('highway'), tipos_calle)
        procesar_atributo(data.get('oneway'), sentidos)
        
    return {
        "nodo": int(nodo),
        "distancia": round(distancia, 2),
        "tipos_calle": list(tipos_calle),
        "oneway": list(sentidos),
        "llegadas": len(in_edges),
        "salidas": len(out_edges)
    }

if __name__ == "__main__":
    print("=== INICIANDO DIAGNÓSTICO TOPOLÓGICO ===")
    G = cargar_grafo()
    instancias = cargar_instancia(G)
    
    # Formateo de la cabecera de la tabla
    print("\n{:<12} | {:<12} | {:<4} | {:<4} | {:<7} | {:<25} | {:<15}".format(
        "PUNTO", "NODO", "IN", "OUT", "DIST(m)", "TIPOS DE CALLE", "ONEWAY"
    ))
    print("-" * 95)
    
    def imprimir_fila(nombre, lat, lon):
        diag = diagnosticar_punto(G, lat, lon)
        
        # Alertas visuales para detectar puntos problemáticos
        alerta = ""
        if diag["llegadas"] == 0 or diag["salidas"] == 0:
            alerta = " ⚠️ INALCANZABLE"
        elif any(t in diag["tipos_calle"] for t in ['motorway', 'motorway_link', 'trunk', 'trunk_link']):
            alerta = " ⚠️ VÍA RÁPIDA"
            
        tipos_str = ", ".join(diag["tipos_calle"])
        oneway_str = ", ".join(diag["oneway"])
        
        # Imprimir fila con anchos fijos
        print("{:<12} | {:<12} | {:<4} | {:<4} | {:<7} | {:<25} | {:<15} {}".format(
            nombre[:12], diag["nodo"], diag["llegadas"], diag["salidas"], 
            diag["distancia"], tipos_str[:25], oneway_str[:15], alerta
        ))

    # Evaluar todos los puntos
    imprimir_fila("Depósito", instancias["deposito"]["lat"], instancias["deposito"]["lon"])
    for i, ent in enumerate(instancias["entregas"]):
        imprimir_fila(f"Entrega {i+1}", ent["lat"], ent["lon"])
    for i, par in enumerate(instancias["pares_prueba"]):
        imprimir_fila(f"P{i+1} Origen", par["origen"]["lat"], par["origen"]["lon"])
        imprimir_fila(f"P{i+1} Destino", par["destino"]["lat"], par["destino"]["lon"])