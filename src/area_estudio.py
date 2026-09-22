import osmnx as ox
import time
import pandas as pd

# Correcciones exactas para osmnx 2.x
ox.settings.requests_timeout = 90
ox.settings.overpass_url = "https://maps.mail.ru/osm/tools/overpass/api"

# Punto central: Metro La Raza L5
lat, lon = 19.469323, -99.136283

radios = [500, 1000, 1500, 2000]
resultados = []

print("Iniciando pruebas de descarga con servidor espejo Kumi...")
# Imprimimos la URL para estar 100% seguros de que el cambio se aplicó
print(f"Verificación de servidor: {ox.settings.overpass_url}\n")

for dist in radios:
    print(f"Descargando grafo con radio de {dist} metros...")
    
    try:
        inicio = time.perf_counter()
        G = ox.graph_from_point((lat, lon), dist=dist, network_type="drive")
        fin = time.perf_counter()
        
        tiempo_total = round(fin - inicio, 2)
        resultados.append({
            "Radio (m)": dist,
            "Nodos": len(G.nodes),
            "Arcos": len(G.edges),
            "Tiempo de descarga (s)": tiempo_total
        })
        print(f"-> ¡Éxito! {len(G.nodes)} nodos procesados en {tiempo_total} segundos.")
        
    except Exception as e:
        print(f"-> Error en el radio de {dist}m: {type(e).__name__} - {e}")
    
    time.sleep(5)

if resultados:
    df = pd.DataFrame(resultados)
    print("\n=== TABLA PARA EL REPORTE (DISEÑO EXPERIMENTAL) ===")
    print(df.to_string(index=False))
else:
    print("\nNo se pudo descargar ningún grafo.")