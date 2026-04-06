import streamlit as st
import pandas as pd
import json
import os

st.set_page_config(page_title="IA Presupuestos Perú - Mauro", layout="wide", page_icon="🏗️")

# Estilo para mejorar la lectura en móviles
st.markdown("""
    <style>
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { height: 50px; white-space: pre-wrap; background-color: #f0f2f6; border-radius: 5px; }
    </style>
    """, unsafe_allow_html=True)

st.title("🏗️ Sistema Inteligente de Costos y Presupuestos")
st.caption("Data Maestra: Revista Costos (Agosto 2025 - Marzo 2026)")

nombre_json = "suplementos_tecnicos_extraccion_completa.json"

@st.cache_data
def cargar_base_datos():
    if os.path.exists(nombre_json):
        with open(nombre_json, 'r', encoding='utf-8') as f:
            data = json.load(f)
        df = pd.DataFrame(data)
        # Limpieza de precios y conversión a número
        for col in df.columns:
            if any(x in col for x in ['Precio', 'S/.']):
                df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '').str.replace('S/.', '').str.strip(), errors='coerce')
        return df
    return None

df = cargar_base_datos()

if df is not None:
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🔍 Buscar", "🧱 Materiales", "👷 Mano de Obra", "📈 Curva Histórica", "🧮 Estimador"
    ])

    # --- TAB 4: CURVA HISTÓRICA (MEJORADA) ---
    with tab4:
        st.subheader("📊 Evolución de Precios")
        insumo = st.selectbox("Selecciona para analizar tendencia:", df.iloc[:, 0].unique(), key="sb_curva")
        if insumo:
            fila = df[df.iloc[:, 0] == insumo].iloc[0]
            # Identificar columnas de precios y ordenarlas cronológicamente
            dict_meses = {"Ago": 1, "Set": 2, "Oct": 3, "Nov": 4, "Dic": 5, "Ene": 6, "Feb": 7, "Mar": 8}
            cols_p = [c for c in fila.index if any(m in c for m in dict_meses.keys())]
            
            # Ordenar columnas por el valor del mes
            cols_p.sort(key=lambda x: next((v for k, v in dict_meses.items() if k in x), 99))
            
            precios = fila[cols_p].values
            meses_labels = [c.split()[-2] + " " + c.split()[-1] for c in cols_p] # Extrae "Marzo 2026" p.ej.

            c1, c2 = st.columns([1, 2])
            with c1:
                st.write("### 📋 Histórico")
                df_tab = pd.DataFrame({'Mes': meses_labels, 'Precio S/.': precios})
                st.dataframe(df_tab, hide_index=True)
                var = ((precios[-1] - precios[0]) / precios[0]) * 100
                st.metric("Variación Total", f"{var:.2f}%", delta=f"{var:.2f}%")
            with c2:
                st.area_chart(df_tab.set_index('Mes'))

    # --- TAB 5: ESTIMADOR (MEJORADO) ---
    with tab5:
        st.subheader("🧮 Cálculo de Presupuesto Rápido")
        c_e1, c_e2 = st.columns(2)
        with c_e1:
            item = st.selectbox("Insumo:", df.iloc[:, 0].unique(), key="sb_est")
            cant = st.number_input("Cantidad / Metrado:", min_value=0.0, value=1.0)
        
        if item:
            r = df[df.iloc[:, 0] == item].iloc[0]
            p_actual = r[[c for c in r.index if 'Mar' in c or '2026' in c][0]]
            und = r.get('Unidad', 'unid')
            total = cant * p_actual
            with c_e2:
                st.metric(label=f"Subtotal (Precio: S/. {p_actual})", value=f"S/. {total:,.2f}")
                st.write(f"**Partida:** {item}")
                st.write(f"**Unidad:** {und}")

    # (Las demás pestañas mantienen su lógica de búsqueda simple)
    with tab1:
        busc = st.text_input("Buscar en todo:")
        if busc:
            res = df[df.iloc[:, 0].str.contains(busc, case=False, na=False)]
            st.dataframe(res)

else:
    st.error("No se encontró la data JSON.")

st.markdown("---")
st.write("🔧 *Ing. Mauro - Gestión de Costos con IA*")
