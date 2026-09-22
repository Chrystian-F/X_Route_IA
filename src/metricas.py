import time

class Medicion:
    def __init__(self, nombre_algoritmo="Algoritmo Genérico"):
        self.nombre = nombre_algoritmo
        self.nodos_expandidos = 0
        self.frontera_maxima = 0
        self.tiempo_inicio = 0.0
        self.tiempo_fin = 0.0
        
    def iniciar_cronometro(self):
        self.tiempo_inicio = time.perf_counter()
        
    def detener_cronometro(self):
        self.tiempo_fin = time.perf_counter()
        
    def tiempo_total_ms(self):
        return (self.tiempo_fin - self.tiempo_inicio) * 1000
        
    def registrar_expansion(self):
        """
        Registra la expansión de un nodo.
        Convención del equipo: Prueba de meta al sacar (Pop & Goal Test), 
        contando la meta como expansión (+1 al extraer el nodo destino de la frontera).
        """
        self.nodos_expandidos += 1
        
    def actualizar_frontera(self, tamano_actual):
        """
        Actualiza el tamaño máximo de la frontera. 
        Nota sobre heapq: len(frontera) cuenta nodos repetidos (lazy deletion), 
        lo cual es estándar y aceptado siempre que se mantenga constante entre algoritmos.
        """
        if tamano_actual > self.frontera_maxima:
            self.frontera_maxima = tamano_actual
            
    def procesar_camino(self, camino, grafo_adyacencia):
        if camino is None:
            return None, None
        if len(camino) == 1:
            return 0, 0.0
            
        total_arcos = len(camino) - 1
        distancia_total = 0.0
        
        for i in range(total_arcos):
            nodo_actual = camino[i]
            siguiente_nodo = camino[i+1]
            
            arco_encontrado = False
            for vecino, costo in grafo_adyacencia.get(nodo_actual, []):
                if vecino == siguiente_nodo:
                    distancia_total += costo
                    arco_encontrado = True
                    break
            
            if not arco_encontrado:
                raise ValueError(f"Fallo de ruteo: No existe un arco directo entre el nodo {nodo_actual} y el nodo {siguiente_nodo}.")
            
        return total_arcos, round(distancia_total, 2)
        
    def generar_diccionario(self, camino, grafo_adyacencia):
        """
        Exporta los resultados como diccionario optimizado para DataFrames de Pandas.
        Usa None en lugar de texto para mantener la integridad numérica de las columnas.
        """
        arcos, metros = self.procesar_camino(camino, grafo_adyacencia)
            
        return {
            "Algoritmo": self.nombre,
            "Expandidos": self.nodos_expandidos,
            "Frontera_Max": self.frontera_maxima,
            "Tiempo_ms": round(self.tiempo_total_ms(), 4),
            "Arcos": arcos,
            "Metros": metros,
            "Camino": str(camino) if camino is not None else None
        }

    def imprimir_reporte(self, camino, grafo_adyacencia):
        print(f"\n{'='*40}")
        print(f" RESULTADOS: {self.nombre}")
        print(f"{'='*40}")
        print(f"Nodos expandidos : {self.nodos_expandidos}")
        print(f"Frontera máxima  : {self.frontera_maxima}")
        print(f"Tiempo de cómputo: {self.tiempo_total_ms():.4f} ms")
        
        if camino is None:
            print("Longitud         : NO SE ENCONTRÓ RUTA")
        elif len(camino) == 1:
            print("Longitud (arcos) : 0 arcos (Origen == Destino)")
            print("Distancia física : 0.0 metros")
            print(f"Camino           : {camino}")
        else:
            arcos, metros = self.procesar_camino(camino, grafo_adyacencia)
            print(f"Longitud (arcos) : {arcos} arcos")
            print(f"Distancia física : {metros} metros")
            print(f"Camino           : {camino}")
        print(f"{'='*40}\n")
        
if __name__ == "__main__":
    print("=== PRUEBAS DE VALIDACIÓN DE MÉTRICAS ===")
    grafo_prueba = {
        1: [(2, 15.5), (3, 50.0)],
        2: [(3, 20.0)],
        3: []
    }
    
    # 1. Simulación BFS
    med_bfs = Medicion("BFS Simulado")
    med_bfs.iniciar_cronometro()
    med_bfs.registrar_expansion() # Expande 1
    med_bfs.actualizar_frontera(2)
    med_bfs.registrar_expansion() # Expande 2
    med_bfs.actualizar_frontera(1)
    med_bfs.registrar_expansion() # Expande 3 (meta)
    med_bfs.detener_cronometro()
    med_bfs.imprimir_reporte([1, 3], grafo_prueba)
    
    # 2. Simulación UCS
    med_ucs = Medicion("UCS Simulado")
    med_ucs.iniciar_cronometro()
    med_ucs.registrar_expansion() # Expande 1
    med_ucs.actualizar_frontera(2)
    med_ucs.registrar_expansion() # Expande 2
    med_ucs.actualizar_frontera(2)
    med_ucs.registrar_expansion() # Expande 3 (meta)
    med_ucs.detener_cronometro()
    med_ucs.imprimir_reporte([1, 2, 3], grafo_prueba)
    
    # 3. Prueba de exportación a diccionario (DataFrame ready)
    print("=== PRUEBA DE DICCIONARIO PARA PANDAS ===")
    dict_res = med_ucs.generar_diccionario([1, 2, 3], grafo_prueba)
    print(dict_res)