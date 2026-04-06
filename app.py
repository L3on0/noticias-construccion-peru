import streamlit as st
import pandas as pd

st.title("🏗️ Monitor de Construcción Perú - Mauro")
st.sidebar.header("Opciones de Análisis")

# Simulación de carga de datos que ya tienes en GitHub
data = {
    'Mes': ['Ago 2025', 'Set 2025', 'Nov 2025', 'Mar 2026'],
    'Acero 3/8"': [30.50, 30.90, 31.40, 32.20],
    'Cemento I': [26.80, 27.10, 27.50, 28.50]
}
df = pd.DataFrame(data)

st.subheader("📈 Tendencias de Precios")
material = st.selectbox("Selecciona un material para comparar:", ['Acero 3/8"', 'Cemento I'])
st.line_chart(df.set_index('Mes')[material])

st.subheader("📰 Noticias y Suplementos Técnicos")
st.write("Selecciona un mes para ver el análisis de la Revista Costos:")
mes_seleccionado = st.selectbox("Mes:", ["Marzo 2026", "Noviembre 2025", "Setiembre 2025", "Agosto 2025"])

if st.button("Ver Resumen de Noticias"):
    st.info(f"Aquí la IA extraerá las noticias del PDF de {mes_seleccionado}...")
