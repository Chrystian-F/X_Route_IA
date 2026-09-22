import folium
import os
from pathlib import Path
from grafo import cargar_grafo, cargar_instancia

def mapear_instancias_reales():
    print("Cargando grafo e instancias (esto asegura que graficamos NODOS reales)...")
    G = cargar_grafo()
    datos = cargar_instancia(G)
    
    mapa = folium.Map(
        location=[19.469323, -99.136283], 
        zoom_start=15, 
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
        attr='Tiles &copy; Esri'
    )
    
    # 1. Dibujar Depósito
    dep = datos["deposito"]
    nodo_dep = dep["nodo"]
    lat_nodo_dep, lon_nodo_dep = G.nodes[nodo_dep]['y'], G.nodes[nodo_dep]['x']
    
    # Línea gris punteada mostrando el "snap" de la coordenada original al nodo real
    folium.PolyLine([(dep["lat"], dep["lon"]), (lat_nodo_dep, lon_nodo_dep)], color="gray", weight=2, dash_array="5").add_to(mapa)
    folium.Marker([lat_nodo_dep, lon_nodo_dep], popup=f"DEPÓSITO REAL: {dep['nombre']}", icon=folium.Icon(color="red", icon="home")).add_to(mapa)
    
    # 2. Dibujar Entregas
    for i, ent in enumerate(datos["entregas"]):
        nodo_ent = ent["nodo"]
        lat_nodo, lon_nodo = G.nodes[nodo_ent]['y'], G.nodes[nodo_ent]['x']
        
        folium.PolyLine([(ent["lat"], ent["lon"]), (lat_nodo, lon_nodo)], color="gray", weight=1, dash_array="5").add_to(mapa)
        folium.Marker([lat_nodo, lon_nodo], popup=f"Entrega {i+1}: {ent['nombre']}", icon=folium.Icon(color="blue", icon="info-sign")).add_to(mapa)
        
    # 3. Dibujar Pares de Prueba
    for i, par in enumerate(datos["pares_prueba"]):
        n_orig, n_dest = par["origen"]["nodo"], par["destino"]["nodo"]
        lat_o, lon_o = G.nodes[n_orig]['y'], G.nodes[n_orig]['x']
        lat_d, lon_d = G.nodes[n_dest]['y'], G.nodes[n_dest]['x']
        
        # Marcadores Origen (Verde) y Destino (Naranja)
        folium.Marker([lat_o, lon_o], popup=f"Origen Prueba {i+1}", icon=folium.Icon(color="green", icon="play")).add_to(mapa)
        folium.Marker([lat_d, lon_d], popup=f"Destino Prueba {i+1}: {par['tipo']}", icon=folium.Icon(color="orange", icon="flag")).add_to(mapa)
        
        # Línea morada conectando el par para visualizarlos
        folium.PolyLine([(lat_o, lon_o), (lat_d, lon_d)], color="purple", weight=2, dash_array="10", opacity=0.6).add_to(mapa)

    # 4. Guardar en carpeta resultados/
    directorio_raiz = Path(__file__).resolve().parent.parent
    carpeta_resultados = directorio_raiz / "resultados"
    os.makedirs(carpeta_resultados, exist_ok=True)
    
    ruta_mapa = carpeta_resultados / "mapa_nodos_reales.html"
    mapa.save(ruta_mapa)
    print(f"¡Mapa de nodos reales generado en: {ruta_mapa}!")

if __name__ == "__main__":
    mapear_instancias_reales()