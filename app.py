import streamlit as st
import pandas as pd

st.set_page_config(page_title="IA Construcción Perú - Mauro", layout="wide")

st.title("🏗️ Buscador de Inteligencia en Construcción - Mauro")
st.caption("Analizando: suplementos_tecnicos_extraccion_completa.txt")

# 1. FUNCIÓN PARA LEER TU ARCHIVO TXT
@st.cache_data
def cargar_base_conocimiento():
    try:
        with open('suplementos_tecnicos_extraccion_completa.txt', 'r', encoding='utf-8') as f:
            contenido = f.read()
        return contenido
    except FileNotFoundError:
        return "Error: No se encontró el archivo en GitHub. Verifica el nombre."

base_texto = cargar_base_conocimiento()

# 2. BUSCADOR DE INFORMACIÓN
st.subheader("🔍 Consultar Precios o Noticias")
query = st.text_input("¿Qué insumo o análisis técnico buscas?", placeholder="Ej: Ladrillo, Cemento Tipo I, Tendencia Acero...")

if query:
    # Buscamos los párrafos donde aparece lo que el usuario quiere
    lineas = base_texto.split('\n')
    resultados = [linea for linea in lineas if query.lower() in linea.lower()]
    
    if resultados:
        st.success(f"Se encontraron {len(resultados)} menciones para '{query}':")
        for res in resultados[:15]: # Mostramos las primeras 15 coincidencias
            st.info(res)
    else:
        st.warning("No se encontró información específica. Intenta con una palabra más general.")

st.markdown("---")
st.sidebar.write("### 📂 Archivo de Datos")
st.sidebar.info("Estás usando la extracción completa de los suplementos 2025-2026.")
