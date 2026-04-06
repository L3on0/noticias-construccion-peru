import json
import os
import re
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Sistema Inteligente de Costos y Presupuestos",
    page_icon="🏗️",
    layout="wide",
)

ARCHIVO_JSON = "suplementos_tecnicos_extraccion_completa.json"


# -----------------------------
# Utilidades de extracción
# -----------------------------
def _extraer_texto_recursivo(obj: Any) -> List[str]:
    """
    Recorre cualquier estructura (dict/list/str) y extrae strings útiles.
    """
    textos: List[str] = []

    if obj is None:
        return textos

    if isinstance(obj, str):
        t = obj.strip()
        if t:
            textos.append(t)
        return textos

    if isinstance(obj, (int, float, bool)):
        return textos

    if isinstance(obj, list):
        for item in obj:
            textos.extend(_extraer_texto_recursivo(item))
        return textos

    if isinstance(obj, dict):
        # Priorizar claves típicas de OCR/PDF
        claves_texto = [
            "text",
            "texto",
            "content",
            "contenido",
            "value",
            "line",
            "lines",
            "paragraph",
            "paragraphs",
            "words",
            "tokens",
            "raw_text",
            "page_text",
        ]

        for k in claves_texto:
            if k in obj:
                textos.extend(_extraer_texto_recursivo(obj[k]))

        # Recorre todo el dict (por si usa otra estructura)
        for _, v in obj.items():
            textos.extend(_extraer_texto_recursivo(v))

        return textos

    return textos


def _unir_textos_limpios(textos: List[str]) -> str:
    # Eliminar duplicados conservando orden
    vistos = set()
    ordenados = []
    for t in textos:
        t2 = re.sub(r"\s+", " ", t).strip()
        if t2 and t2 not in vistos:
            vistos.add(t2)
            ordenados.append(t2)
    return " ".join(ordenados)


def _extraer_precio_soles(texto: str) -> Optional[float]:
    """
    Extrae el primer precio tipo:
    S/ 12.50, S/. 1,250.00, etc.
    """
    if not texto:
        return None

    patron = r"(?:S\/\.?\s*)(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)"
    m = re.search(patron, texto, flags=re.IGNORECASE)
    if not m:
        return None

    raw = m.group(1).strip()

    # Normalizar separadores
    if "," in raw and "." in raw:
        # decidir decimal por última aparición
        if raw.rfind(".") > raw.rfind(","):
            raw = raw.replace(",", "")
        else:
            raw = raw.replace(".", "").replace(",", ".")
    elif "," in raw and "." not in raw:
        raw = raw.replace(",", ".")

    try:
        return float(raw)
    except ValueError:
        return None


def _extraer_num_pagina(page_obj: Dict[str, Any], idx_fallback: int) -> int:
    for k in ["page", "page_number", "page_num", "numero_pagina", "nro_pagina", "number"]:
        if k in page_obj and isinstance(page_obj[k], (int, float)):
            return int(page_obj[k])
    return idx_fallback + 1


# -----------------------------
# Carga y transformación
# -----------------------------
@st.cache_data(show_spinner=True)
def cargar_json(path: str) -> Any:
    if not os.path.exists(path):
        raise FileNotFoundError(f"No se encontró: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def construir_df_paginas(data: Any) -> pd.DataFrame:
    """
    Espera estructura raíz tipo list[dict] con:
      file_name, file_path, page_count, sha256, pages
    y convierte a una fila por página.
    """
    if not isinstance(data, list):
        raise ValueError("La raíz del JSON no es una lista de archivos.")

    filas = []

    for archivo in data:
        if not isinstance(archivo, dict):
            continue

        file_name = archivo.get("file_name", "")
        file_path = archivo.get("file_path", "")
        page_count = archivo.get("page_count", None)
        sha256 = archivo.get("sha256", "")

        pages = archivo.get("pages", [])
        if not isinstance(pages, list):
            pages = []

        for i, p in enumerate(pages):
            if not isinstance(p, dict):
                # Si la página no es dict, igual intentamos convertir a texto
                page_obj = {"raw_page": p}
            else:
                page_obj = p

            num_pagina = _extraer_num_pagina(page_obj, i)
            textos = _extraer_texto_recursivo(page_obj)
            texto_pagina = _unir_textos_limpios(textos)
            precio_detectado = _extraer_precio_soles(texto_pagina)

            filas.append(
                {
                    "file_name": file_name,
                    "file_path": file_path,
                    "page_count": page_count,
                    "sha256": sha256,
                    "page_number": num_pagina,
                    "texto_pagina": texto_pagina,
                    "precio_detectado": precio_detectado,
                }
            )

    df = pd.DataFrame(filas)
    if df.empty:
        raise ValueError("No se pudieron construir filas por página. Revisa estructura de 'pages'.")
    return df


# -----------------------------
# UI
# -----------------------------
def main():
    st.title("🏗️ Sistema Inteligente de Costos y Presupuestos")
    st.caption("Data Maestra: Revista Costos (Agosto 2025 - Marzo 2026)")

    try:
        data = cargar_json(ARCHIVO_JSON)
        df = construir_df_paginas(data)
    except Exception as e:
        st.error(f"Error cargando datos: {e}")
        st.stop()

    st.sidebar.header("Filtros")

    termino = st.sidebar.text_input(
        "Buscar material/palabra en texto de páginas:",
        value="Ladrillo"
    ).strip()

    # Filtro por archivo opcional
    archivos = sorted(df["file_name"].dropna().unique().tolist())
    archivo_sel = st.sidebar.multiselect(
        "Filtrar por archivo:",
        options=archivos,
        default=[]
    )

    # Aplicar filtros
    dff = df.copy()

    if archivo_sel:
        dff = dff[dff["file_name"].isin(archivo_sel)]

    if termino:
        dff = dff[dff["texto_pagina"].str.contains(termino, case=False, na=False)]

    # KPIs
    c1, c2, c3 = st.columns(3)
    c1.metric("Páginas analizadas", f"{len(df):,}")
    c2.metric("Resultados filtrados", f"{len(dff):,}")

    suma_precios = dff["precio_detectado"].dropna().sum() if "precio_detectado" in dff.columns else 0.0
    c3.metric("Suma precios detectados", f"S/ {suma_precios:,.2f}")

    st.divider()

    # Tabla principal
    cols_view = [
        "file_name",
        "page_number",
        "precio_detectado",
        "texto_pagina",
    ]
    st.subheader("Resultados")
    st.dataframe(
        dff[cols_view].sort_values(["file_name", "page_number"]),
        use_container_width=True,
        height=520
    )

    # CSV
    csv = dff.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Descargar resultados CSV",
        data=csv,
        file_name="resultados_materiales.csv",
        mime="text/csv"
    )

    # Debug opcional
    with st.expander("Debug estructura"):
        st.write("Columnas df:", df.columns.tolist())
        st.write("Ejemplo texto (primeras 800 chars):")
        if len(df) > 0:
            st.code(str(df.iloc[0]["texto_pagina"])[:800])


if __name__ == "__main__":
    main()
