import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import streamlit as st

# 1. Obtener las rutas de las carpetas
CURRENT_DIR = Path(__file__).resolve().parent  # Carpeta python_app
ROOT_DIR = CURRENT_DIR.parent                   # Raíz del proyecto

# Añadir la raíz al sys.path para evitar ModuleNotFoundError
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# 2. Cargar el .env ubicado en la RAÍZ del proyecto
ENV_PATH = ROOT_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH)

# Imports de tu aplicación
from python_app.meterless import MeterlessConfig, MeterlessClient
from python_app.scout_intent import route_intent
from python_app.agent_loop import process_user_query

# Configuración de la página
st.set_page_config(
    page_title="Colombia Data Intelligence",
    page_icon="🇨🇴",
    layout="centered"
)

st.title("🇨🇴 Colombia Data Intelligence Multi-Agent")
st.subheader("Análisis socioeconómico y territorial mediante datos del DANE y Nemotron")

# Inicializar cliente de Meterless en la sesión
@st.cache_resource
def get_meterless_client():
    config = MeterlessConfig.from_env()
    return MeterlessClient(config)

try:
    client = get_meterless_client()
except Exception as e:
    st.error(f"Error al conectar con Meterless Runtime: {e}")
    st.stop()

# Historial de chat visual en pantalla
if "messages" not in st.session_state:
    st.session_state.messages = []

# Mostrar mensajes anteriores
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Entrada de texto del usuario
if user_input := st.chat_input("Escribe tu pregunta socioeconómica (ej. Población de Antioquia)..."):
    # Mostrar mensaje del usuario
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # Procesar la respuesta con el agente
    with st.chat_message("assistant"):
        with st.spinner("Analizando consulta y consultando fuentes de datos..."):
            # 1. Detectar intención
            intent_info = route_intent(user_input)
            st.caption(f"🔍 Intención detectada por Scout Intent: `{intent_info['intent']}`")
            
            # 2. Ejecutar agente (con Nemotron + Zetaris SQL + H-Mem)
            answer = process_user_query(client, user_input)
            
            # 3. Mostrar respuesta
            st.markdown(answer)
            
            # Guardar en el historial visual
            st.session_state.messages.append({"role": "assistant", "content": answer})