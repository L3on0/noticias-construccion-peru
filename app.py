import streamlit as st
import pandas as pd
import json
import os

st.set_page_config(page_title="IA Presupuestos Perú - Mauro", layout="wide", page_icon="🏗️")

# Estilo personalizado para que se vea más profesional
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; border: 1px solid #e1e4e8; }
    </style>
    """, unsafe_allow_html=True)

st.title("🏗️ Sistema Inteligente de Costos y Presupuestos")
st.caption("Data Maestra: Revista Costos (Agosto 2025 - Marzo 2026)")

# --- CARGA DE DATOS ESTRUCTURADOS ---
nombre_json = "suplementos_tecnicos_extraccion_completa.json"

@st.cache_data
def cargar_base_datos():
    if os.path.exists(nombre_json):
        with open(nombre_json, 'r', encoding='utf-8') as f:
            data = json.load(f)
        df = pd.DataFrame(data)
        # Limpieza rápida de columnas de precios para asegurar que sean números
        for col in df.columns:
            if 'Precio' in col or 'S/.' in col:
                df[col] = df[col].replace(',', '', regex=True).astype(float)
        return df
    return None

df = cargar_base_datos()

if df is not None:
    # --- PESTAÑAS ESTRATÉGICAS ---
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🔍 Explorador General", "🧱 Materiales", "👷 Mano de Obra", "📈 Histórico & Curvas", "🧮 Estimador de Costos"
    ])

    # Función auxiliar para mostrar fichas técnicas
    def ficha_tecnica(item_sel, dataframe):
        detalle = dataframe[dataframe.iloc[:, 0] == item_sel].iloc[0]
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            st.info("### 📋 Especificaciones")
            for k, v in detalle.items():
                if 'Precio' not in str(k): st.write(f"**{k}:** {v}")
        with col_f2:
            st.warning("### 💰 Precios Actualizados")
            cols_p = [c for c in detalle.index if 'Precio' in str(c) or 'S/.' in str(c)]
            st.table(detalle[cols_p])

    # --- TABS 1, 2 y 3: BÚSQUEDA SEGMENTADA ---
    with tab1:
        q_todo = st.text_input("Buscar insumo en toda la base:", key="q_todo")
        if q_todo:
            res = df[df.iloc[:, 0].str.contains(q_todo, case=False, na=False)]
            if not res.empty:
                sel = st.selectbox("Seleccione ítem:", res.iloc[:, 0].unique(), key="s_todo")
                ficha_tecnica(sel, res)

    with tab2:
        q_mat = st.text_input("Buscar Materiales (Insumos):", key="q_mat")
        if q_mat:
            res = df[df.iloc[:, 0].str.contains(q_mat, case=False, na=False)]
            if not res.empty:
                sel = st.selectbox("Seleccione Material:", res.iloc[:, 0].unique(), key="s_mat")
                ficha_tecnica(sel, res)

    with tab3:
        q_mo = st.text_input("Buscar Mano de Obra (Operario, Oficial, Peón):", key="q_mo")
        if q_mo:
            res = df[df.iloc[:, 0].str.contains(q_mo, case=False, na=False)]
            if not res.empty:
                sel = st.selectbox("Seleccione Categoría:", res.iloc[:, 0].unique(), key="s_mo")
                ficha_tecnica(sel, res)

    # --- TAB 4: HISTÓRICO Y CURVAS (Análisis de Tendencia) ---
    with tab4:
        st.subheader("📊 Análisis de Variación de Costos")
        item_curva = st.selectbox("Insumo para análisis histórico:", df.iloc[:, 0].unique(), key="s_curva")
        if item_curva:
            row = df[df.iloc[:, 0] == item_curva].iloc[0]
            cols_p = [c for c in row.index if 'Precio' in str(c) or 'S/.' in str(c)]
            if len(cols_p) > 1:
                meses = [c.replace('Precio ', '').replace('S/. ', '') for c in cols_p]
                precios = row[cols_p].values
                df_chart = pd.DataFrame({'Mes': meses, 'S/.': precios}).set_index('Mes')
                
                c1, c2 = st.columns([1, 2])
                with c1:
                    var_p = ((precios[-1] - precios[0]) / precios[0]) * 100
                    st.metric("Variación Acumulada", f"{var_p:.2f}%", delta=f"{var_p:.2f}%")
                    st.dataframe(df_chart)
                with c2:
                    st.area_chart(df_chart, use_container_width=True)
            else:
                st.warning("No hay suficiente historial para generar una curva.")

    # --- TAB 5: ESTIMADOR DE COSTOS (NUEVO) ---
    with tab5:
        st.subheader("🧮 Estimador Rápido de Partidas")
        st.write("Calcula el costo total de un insumo basado en su metrado actual.")
        
        col_e1, col_e2 = st.columns(2)
        with col_e1:
            insumo_est = st.selectbox("Selecciona el Insumo:", df.iloc[:, 0].unique(), key="s_est")
            metrado = st.number_input("Ingresa el Metrado / Cantidad:", min_value=0.0, value=1.0, step=1.0)
        
        if insumo_est:
            row_est = df[df.iloc[:, 0] == insumo_est].iloc[0]
            # Tomamos el precio más reciente (Marzo 2026 o el último disponible)
            cols_p = [c for c in row_est.index if 'Precio' in str(c) or 'S/.' in str(c)]
            precio_actual = row_est[cols_p[-1]]
            unidad = row_est.get('Unidad', 'unid')
            
            total = metrado * precio_actual
            
            with col_e2:
                st.write("### 💰 Resultado del Cálculo")
                st.metric(label=f"Costo Total (Precio Unit: S/. {precio_actual})", value=f"S/. {total:,.2f}")
                st.write(f"**Insumo:** {insumo_est}")
                st.write(f"**Cantidad:** {metrado} {unidad}")
                
        st.divider()
        st.info("💡 Este estimador usa el precio de Marzo 2026 para el cálculo final.")

else:
    st.error("❌ Archivo de datos no encontrado en GitHub.")

st.markdown("---")
st.write("🔧 *Desarrollado por Ing. Mauro - Especialista en Costos y Presupuestos*")
