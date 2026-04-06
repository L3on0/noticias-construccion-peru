import json
import os
import re
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st


# =====================================
# Configuración
# =====================================
st.set_page_config(
    page_title="Sistema Inteligente de Costos y Presupuestos",
    page_icon="🏗️",
    layout="wide",
)

ARCHIVO_JSON = "suplementos_tecnicos_extraccion_completa.json"


# =====================================
# Utilidades
# =====================================
def _extraer_texto_recursivo(obj: Any) -> List[str]:
    """Extrae texto desde estructuras anidadas (dict/list/str)."""
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
        # Primero intentamos claves comunes de texto
        claves_prioridad = [
            "text", "texto", "content", "contenido", "value",
            "line", "lines", "paragraph", "paragraphs",
            "words", "tokens", "raw_text", "page_text",
            "ocr_text", "message", "description"
        ]
        for k in claves_prioridad:
            if k in obj:
                textos.extend(_extraer_texto_recursivo(obj[k]))

        # Luego recorremos todo por seguridad
        for _, v in obj.items():
            textos.extend(_extraer_texto_recursivo(v))

        return textos

    return textos


def _limpiar_y_unir_textos(textos: List[str]) -> str:
    """Limpia espacios, elimina duplicados y une en un solo texto."""
    vistos = set()
    salida = []
    for t in textos:
        t2 = re.sub(r"\s+", " ", t).strip()
        if t2 and t2 not in vistos:
            vistos.add(t2)
            salida.append(t2)
    return " ".join(salida)


def _extraer_precio_soles(texto: str) -> Optional[float]:
    """
    Detecta primer monto tipo:
    S/ 12.50, S/. 1,250.00, S/12,50, etc.
    """
    if not texto:
        return None

    patron = r"(?:S\/\.?\s*)(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)"
    m = re.search(patron, texto, flags=re.IGNORECASE)
    if not m:
        return None

    raw = m.group(1).strip()

    # Normalización de separadores
    if "," in raw and "." in raw:
        # El último separador se asume decimal
        if raw.rfind(".") > raw.rfind(","):
            raw = raw.replace(",", "")
        else:
            raw = raw.replace(".", "").replace(",", ".")
    elif "," in raw and "." not in raw:
        raw = raw.replace(",", ".")
    # Si solo hay punto, lo dejamos

    try:
        return float(raw)
    except ValueError:
        return None


def _es_lista_dicts(v: Any) -> bool:
    return isinstance(v, list) and (len(v) == 0 or isinstance(v[0], dict))


def _buscar_lista_archivos(obj: Any, profundidad: int = 0, max_profundidad: int = 6) -> Optional[List[Dict[str, Any]]]:
    """
    Busca recursivamente una lista de dicts que represente archivos.
    Soporta JSON con raíz list o dict anidado.
    """
    if profundidad > max_profundidad:
        return None

    # Caso directo list[dict]
    if _es_lista_dicts(obj):
        return obj  # type: ignore

    if isinstance(obj, dict):
        # Prioridad a claves típicas
        claves_prioridad = [
            "data", "files", "documents", "records", "items",
            "resultados", "suplementos", "payload", "output"
        ]
        for k in claves_prioridad:
            if k in obj and _es_lista_dicts(obj[k]):
                return obj[k]  # type: ignore

        # Buscar recursivamente en valores
        for _, v in obj.items():
            encontrado = _buscar_lista_archivos(v, profundidad + 1, max_profundidad)
            if encontrado is not None:
                return encontrado

    if isinstance(obj, list):
        # Si es lista pero no list[dict], buscar dentro
        for item in obj:
            encontrado = _buscar_lista_archivos(item, profundidad + 1, max_profundidad)
            if encontrado is not None:
                return encontrado

    return None


def _obtener_paginas_desde_archivo(archivo: Dict[str, Any]) -> List[Any]:
    """
    Extrae 'pages' desde distintas posibles claves.
    """
    posibles = ["pages", "paginas", "content", "chunks", "sections"]
    for k in posibles:
        v = archivo.get(k)
        if isinstance(v, list):
            return v

    # fallback: si no existe pages, devolvemos lista vacía
    return []


def _obtener_num_pagina(page_obj: Dict[str, Any], fallback: int) -> int:
    claves = ["page", "page_number", "page_num", "numero_pagina", "nro_pagina", "number", "index"]
    for k in claves:
        v = page_obj.get(k)
        if isinstance(v, int):
            return v
        if isinstance(v, float):
            return int(v)
        if isinstance(v, str) and v.isdigit():
            return int(v)
    return fallback


@st.cache_data(show_spinner=True)
def cargar_datos(path_json: str) -> pd.DataFrame:
    if not os.path.exists(path_json):
        raise FileNotFoundError(f"No se encontró el archivo: {path_json}")

    with open(path_json, "r", encoding="utf-8") as f:
        raw = json.load(f)

    archivos = _buscar_lista_archivos(raw)
    if archivos is None:
        # Mensaje útil para debug
        tipo = type(raw).__name__
        if isinstance(raw, dict):
            claves = list(raw.keys())[:20]
            raise ValueError(
                f"No se encontró una lista de archivos dentro del JSON. "
                f"Tipo raíz: {tipo}. Claves raíz detectadas: {claves}"
            )
        raise ValueError(f"No se encontró una lista de archivos dentro del JSON. Tipo raíz: {tipo}")

    filas: List[Dict[str, Any]] = []

    for archivo in archivos:
        if not isinstance(archivo, dict):
            continue

        file_name = archivo.get("file_name", archivo.get("name", "sin_nombre"))
        file_path = archivo.get("file_path", archivo.get("path", ""))
        page_count = archivo.get("page_count", archivo.get("num_pages"))
        sha256 = archivo.get("sha256", "")

        pages = _obtener_paginas_desde_archivo(archivo)

        # Si no hay pages, igual creamos una fila con texto del archivo completo
        if not pages:
            texto_archivo = _limpiar_y_unir_textos(_extraer_texto_recursivo(archivo))
            filas.append(
                {
                    "file_name": file_name,
                    "file_path": file_path,
                    "page_count": page_count,
                    "sha256": sha256,
                    "page_number": None,
                    "texto_pagina": texto_archivo,
                    "precio_detectado": _extraer_precio_soles(texto_archivo),
                }
            )
            continue

        # Una fila por página
        for i, p in enumerate(pages, start=1):
            page_obj = p if isinstance(p, dict) else {"raw_page": p}
            page_number = _obtener_num_pagina(page_obj, i)

            texto = _limpiar_y_unir_textos(_extraer_texto_recursivo(page_obj))
            precio = _extraer_precio_soles(texto)

            filas.append(
                {
                    "file_name": file_name,
                    "file_path": file_path,
                    "page_count": page_count,
                    "sha256": sha256,
                    "page_number": page_number,
                    "texto_pagina": texto,
                    "precio_detectado": precio,
                }
            )

    if not filas:
        raise ValueError("Se encontró estructura JSON, pero no se pudieron construir filas.")

    df = pd.DataFrame(filas)
    return df


# =====================================
# App
# =====================================
def main():
    st.title("🏗 Sistema Inteligente de Costos y Presupuestos")
    st.caption("Data Maestra: Revista Costos (Agosto 2025 - Marzo 2026)")

    try:
        df = cargar_datos(ARCHIVO_JSON)
    except Exception as e:
        st.error(f"Error cargando datos: {e}")
        st.stop()

    # ---------------- Sidebar ----------------
    st.sidebar.header("Filtros")

    termino = st.sidebar.text_input(
        "Buscar material/palabra (en texto de páginas):",
        value="Ladrillo"
    ).strip()

    archivos_disponibles = sorted(df["file_name"].dropna().astype(str).unique().tolist())
    archivos_sel = st.sidebar.multiselect("Filtrar por archivo:", archivos_disponibles, default=[])

    # ---------------- Filtros ----------------
    dff = df.copy()

    if archivos_sel:
        dff = dff[dff["file_name"].astype(str).isin(archivos_sel)]

    if termino:
        dff = dff[dff["texto_pagina"].astype(str).str.contains(termino, case=False, na=False)]

    # ---------------- KPIs ----------------
    c1, c2, c3 = st.columns(3)
    c1.metric("Registros filtrados", f"{len(dff):,}")
    c2.metric("Archivos únicos", f"{dff['file_name'].nunique():,}")

    suma_precios = dff["precio_detectado"].dropna().sum() if "precio_detectado" in dff.columns else 0.0
    c3.metric("Suma de precios detectados", f"S/ {suma_precios:,.2f}")

    st.divider()

    # ---------------- Tabla principal ----------------
    columnas_default = ["file_name", "page_number", "precio_detectado", "texto_pagina"]
    columnas_default = [c for c in columnas_default if c in dff.columns]

    columnas_sel = st.multiselect(
        "Columnas a mostrar:",
        options=dff.columns.tolist(),
        default=columnas_default if columnas_default else dff.columns.tolist(),
    )

    mostrar = dff[columnas_sel] if columnas_sel else dff
    st.dataframe(mostrar.sort_values(by=["file_name", "page_number"], na_position="last"),
                 use_container_width=True, height=520)

    # ---------------- Descarga ----------------
    csv_bytes = dff.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Descargar resultados CSV",
        data=csv_bytes,
        file_name="resultados_filtrados.csv",
        mime="text/csv",
    )

    # ---------------- Debug ----------------
    with st.expander("Debug (estructura)"):
        st.write("Columnas del DataFrame:")
        st.write(df.columns.tolist())
        st.write("Tipos de columnas:")
        st.write(df.dtypes.astype(str))
        st.write("Primeras 2 filas:")
        st.dataframe(df.head(2), use_container_width=True)


if __name__ == "__main__":
    main()
