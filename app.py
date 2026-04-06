import json
import os
import re
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st


# -----------------------------
# Configuración general
# -----------------------------
st.set_page_config(
    page_title="Sistema Inteligente de Costos y Presupuestos",
    page_icon="🏗️",
    layout="wide",
)

ARCHIVO_JSON = "suplementos_tecnicos_extraccion_completa.json"


# -----------------------------
# Utilidades
# -----------------------------
def _to_float(valor: Any) -> Optional[float]:
    """Convierte strings tipo 'S/. 1,234.50' a float."""
    if valor is None:
        return None

    if isinstance(valor, (int, float)):
        return float(valor)

    texto = str(valor).strip()
    if not texto:
        return None

    # Mantener solo dígitos, coma, punto y signo
    texto = re.sub(r"[^0-9,.\-]", "", texto)

    # Heurísticas para separadores miles/decimal
    if texto.count(",") > 0 and texto.count(".") > 0:
        # Si el último separador es punto, asumimos decimal '.'
        if texto.rfind(".") > texto.rfind(","):
            texto = texto.replace(",", "")
        else:
            texto = texto.replace(".", "").replace(",", ".")
    else:
        # Solo coma -> decimal
        if "," in texto and "." not in texto:
            texto = texto.replace(",", ".")
        # Solo punto -> decimal usual, no tocar

    try:
        return float(texto)
    except ValueError:
        return None


def _extraer_registros(data: Any) -> Optional[List[Dict[str, Any]]]:
    """
    Extrae una lista de diccionarios desde JSON con estructura variable.
    Soporta:
    - list[dict]
    - dict con clave que contenga list[dict]
    - dict[clave] = dict (se convierte a list(dict.values()))
    """
    if isinstance(data, list):
        if len(data) == 0:
            return []
        if all(isinstance(x, dict) for x in data):
            return data
        return None

    if isinstance(data, dict):
        # 1) Buscar clave candidata con list[dict]
        claves_prioridad = [
            "data",
            "registros",
            "records",
            "items",
            "resultados",
            "suplementos",
            "detalle",
            "rows",
        ]

        for k in claves_prioridad:
            if k in data and isinstance(data[k], list) and (
                len(data[k]) == 0 or isinstance(data[k][0], dict)
            ):
                return data[k]

        # 2) Buscar automáticamente la primera list[dict]
        for _, v in data.items():
            if isinstance(v, list) and (len(v) == 0 or isinstance(v[0], dict)):
                return v

        # 3) Si es dict de dicts -> convertir valores a lista
        if all(isinstance(v, dict) for v in data.values()) and len(data) > 0:
            return list(data.values())

    return None


def _normalizar_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza columnas de costo/precio y limpia strings vacíos."""
    # Limpiar strings vacíos
    for col in df.columns:
        if df[col].dtype == "object":
            df[col] = df[col].replace(r"^\s*$", pd.NA, regex=True)

    # Detectar columnas monetarias por nombre
    patrones_monto = [
        "precio",
        "costo",
        "importe",
        "total",
        "parcial",
        "s/.",
        "monto",
        "valor",
    ]

    for col in df.columns:
        col_lower = col.lower()
        if any(p in col_lower for p in patrones_monto):
            df[col] = df[col].apply(_to_float)

    return df


# -----------------------------
# Carga de datos
# -----------------------------
@st.cache_data(show_spinner=True)
def cargar_base_datos(nombre_json: str) -> Optional[pd.DataFrame]:
    if not os.path.exists(nombre_json):
        st.error(f"No se encontró el archivo: {nombre_json}")
        return None

    try:
        with open(nombre_json, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        st.error(f"JSON inválido: {e}")
        return None
    except Exception as e:
        st.error(f"Error leyendo el archivo: {e}")
        return None

    registros = _extraer_registros(data)
    if registros is None:
        st.error(
            "No se pudo identificar una estructura tabular en el JSON. "
            "Debe contener una lista de objetos (dict)."
        )
        # Debug amigable
        st.write("Tipo raíz detectado:", type(data).__name__)
        if isinstance(data, dict):
            st.write("Claves raíz:", list(data.keys())[:20])
        return None

    try:
        df = pd.json_normalize(registros, sep=".")
    except Exception as e:
        st.error(f"No se pudo normalizar el JSON a DataFrame: {e}")
        return None

    if df.empty:
        st.warning("El archivo JSON se cargó, pero no contiene registros.")
        return df

    df = _normalizar_dataframe(df)
    return df


# -----------------------------
# App principal
# -----------------------------
def main():
    st.title("🏗️ Sistema Inteligente de Costos y Presupuestos")
    st.caption("Data Maestra: Revista Costos (Agosto 2025 - Marzo 2026)")

    df = cargar_base_datos(ARCHIVO_JSON)
    if df is None:
        st.stop()

    if df.empty:
        st.info("No hay datos para mostrar.")
        st.stop()

    # Sidebar: búsqueda y columnas
    st.sidebar.header("Filtros")
    busqueda = st.sidebar.text_input("Buscar texto (en todas las columnas):").strip()

    columnas = df.columns.tolist()
    col_mostrar = st.sidebar.multiselect(
        "Columnas a mostrar:",
        options=columnas,
        default=columnas[: min(12, len(columnas))],
    )

    # Filtro por texto global
    df_filtrado = df.copy()
    if busqueda:
        mask = pd.Series(False, index=df_filtrado.index)
        for col in df_filtrado.columns:
            mask = mask | df_filtrado[col].astype(str).str.contains(
                busqueda, case=False, na=False
            )
        df_filtrado = df_filtrado[mask]

    # KPIs
    st.subheader("Resumen")
    c1, c2, c3 = st.columns(3)
    c1.metric("Registros", f"{len(df_filtrado):,}")
    c2.metric("Columnas", f"{len(df_filtrado.columns):,}")

    # Suma de posibles columnas de monto
    cols_monto = [
        c
        for c in df_filtrado.columns
        if any(x in c.lower() for x in ["precio", "costo", "importe", "total", "monto"])
        and pd.api.types.is_numeric_dtype(df_filtrado[c])
    ]
    total_montos = (
        float(df_filtrado[cols_monto].sum(numeric_only=True).sum())
        if cols_monto
        else 0.0
    )
    c3.metric("Suma de montos detectados", f"S/ {total_montos:,.2f}")

    st.divider()

    # Tabla
    st.subheader("Datos")
    if col_mostrar:
        st.dataframe(df_filtrado[col_mostrar], use_container_width=True, height=520)
    else:
        st.dataframe(df_filtrado, use_container_width=True, height=520)

    # Descarga CSV
    csv_bytes = df_filtrado.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Descargar resultado en CSV",
        data=csv_bytes,
        file_name="costos_filtrados.csv",
        mime="text/csv",
    )

    # Debug opcional
    with st.expander("Debug (estructura de columnas)"):
        st.write(df.dtypes.astype(str))


if __name__ == "__main__":
    main()
