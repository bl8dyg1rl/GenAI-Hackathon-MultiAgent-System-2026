import sys
from python_app.meterless import MeterlessClient, MeterlessConfig, MeterlessError
import os
from pathlib import Path
from dotenv import load_dotenv

# Obtener la ruta exacta de la carpeta python_app/
CURRENT_DIR = Path(__file__).resolve().parent
ENV_PATH = CURRENT_DIR / ".env"

# Cargar el archivo .env ubicado en python_app/.env
load_dotenv(dotenv_path=ENV_PATH)

def main():
    print("=== INICIANDO COLOMBIA DATA INTELLIGENCE MULTI-AGENT ===")
    
    # 1. Cargar configuración y verificar conexión
    config = MeterlessConfig.from_env()
    client = MeterlessClient(config)
    
    conn_status = client.check_connection()
    print(f"Estado de Meterless: {conn_status.get('message')}\n")
    
    print("Sistema listo. Escribe tu pregunta (o 'salir' para terminar):")
    
    while True:
        try:
            user_input = input("\n> ")
            if user_input.lower().strip() in ("salir", "exit", "quit"):
                print("Saliendo de la aplicación...")
                break
            if not user_input.strip():
                continue
            
            print(f"Procesando consulta: {user_input}...")
            
            # 2. ENVIAR LA CONSULTA A METERLESS / NEMOTRON
            # (Si tienes un orquestador como `Orchestrator`, llámalo aquí en lugar de client.chat)
            messages = [
                {"role": "system", "content": "Eres un asistente experto en análisis de datos económicos y regionales de Colombia."},
                {"role": "user", "content": user_input}
            ]
            
            response = client.chat(messages)
            
            # 3. IMPRIMIR LA RESPUESTA EN PANTALLA
            print("\n--- RESPUESTA DE NEMOTRON / AGENTE ---")
            print(response.get("answer", "No se obtuvo respuesta."))
            print("---------------------------------------")
            
        except MeterlessError as err:
            print(f"\n[Error de Meterless]: {err}")
        except KeyboardInterrupt:
            print("\nOperación cancelada por el usuario.")
            break
        except Exception as err:
            print(f"\n[Error inesperado]: {err}")

if __name__ == "__main__":
    main()