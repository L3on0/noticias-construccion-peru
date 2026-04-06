import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st


# ============================================================
# CONFIG
# ============================================================
st.set_page_config(
    page_title="Sistema Inteligente de Costos y Presupuestos",
    page_icon="🏗️",
    layout="wide",
)

ARCHIVO_JSON = "suplementos_tecnicos_extraccion_completa.json"

# Palabras de ruido para descartar líneas que NO son materiales
STOPWORDS_RUIDO = [
    "indice", "índice", "grupo", "capitulo", "capítulo", "precios sin i.g.v",
    "vigentes al", "tipo de cambio", "factores de reajuste", "área departamento",
    "cemento - producción", "despacho", "exportación", "resumen", "tabla de contenido",
]

# Unidades típicas de construcción (expresiones flexibles)
UNIDAD_REGEX = r"\b(kg|gr|g|tn|ton|t|m2|m3|m|ml|cm|mm|und|unid|u|pza|pieza|bolsa|saco|gal|lt|l)\b"

# Patrón de precio monetario
PRECIO_REGEX = r"(?:S\/\.?\s*)(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)"


# ============================================================
# MODELO
# ============================================================
@dataclass
class RegistroMaterial:
    material: str
    unidad: Optional[str]
    precio: float
    moneda: str
    file_name: str
    page_number: Optional[int]
    fecha_vigencia: Optional[str]
    linea_origen: str


# ============================================================
# UTILIDADES GENERALES
# ============================================================
def _es_lista_dicts(v: Any) -> bool:
    return isinstance(v, list) and (len(v) == 0 or isinstance(v[0], dict))


def _buscar_lista_archivos(obj: Any, profundidad: int = 0, max_profundidad: int = 8) -> Optional[List[Dict[str, Any]]]:
    """
    Encuentra la lista principal de archivos en JSON de estructura variable.
    """
    if profundidad > max_profundidad:
        return None

    if _es_lista_dicts(obj):
        return obj  # type: ignore

    if isinstance(obj, dict):
        claves_prioridad = ["data", "files", "documents", "items", "records", "resultados", "suplementos", "payload"]
        for k in claves_prioridad:
            if k in obj and _es_lista_dicts(obj[k]):
                return obj[k]  # type: ignore

        for _, v in obj.items():
            res = _buscar_lista_archivos(v, profundidad + 1, max_profundidad)
            if res is not None:
                return res

    if isinstance(obj, list):
        for item in obj:
            res = _buscar_lista_archivos(item, profundidad + 1, max_profundidad)
            if res is not None:
                return res

    return None


def _obtener_paginas(archivo: Dict[str, Any]) -> List[Any]:
    """
    Detecta lista de páginas con varias llaves posibles.
    """
    for k in ["pages", "paginas", "content", "chunks", "sections"]:
        v = archivo.get(k)
        if isinstance(v, list):
            return v
    return []


def _obtener_num_pagina(page_obj: Dict[str, Any], fallback: int) -> int:
    for k in ["page", "page_number", "page_num", "numero_pagina", "nro_pagina", "number", "index"]:
        v = page_obj.get(k)
        if isinstance(v, int):
            return v
        if isinstance(v, float):
            return int(v)
        if isinstance(v, str) and v.isdigit():
            return int(v)
    return fallback


def _normalizar_numero(txt_num: str) -> Optional[float]:
    """
    Convierte números con comas/puntos a float robustamente.
    """
    raw = txt_num.strip()

    if "," in raw and "." in raw:
        # última separación suele ser decimal
        if raw.rfind(".") > raw.rfind(","):
            raw = raw.replace(",", "")
        else:
            raw = raw.replace(".", "").replace(",", ".")
    elif "," in raw and "." not in raw:
        raw = raw.replace(",", ".")
    # si solo punto, se deja

    try:
        return float(raw)
    except ValueError:
        return None


def _extraer_textos(obj: Any) -> List[str]:
    """
    Extrae trozos de texto de estructuras anidadas.
    """
    out: List[str] = []

    if obj is None:
        return out

    if isinstance(obj, str):
        t = obj.strip()
        if t:
            out.append(t)
        return out

    if isinstance(obj, (int, float, bool)):
        return out

    if isinstance(obj, list):
        for i in obj:
            out.extend(_extraer_textos(i))
        return out

    if isinstance(obj, dict):
        # priorizar claves textuales típicas OCR
        for k in [
            "text", "texto", "content", "contenido", "line", "lines",
            "paragraph", "paragraphs", "words", "tokens", "raw_text",
            "ocr_text", "message", "description"
        ]:
            if k in obj:
                out.extend(_extraer_textos(obj[k]))

        # fallback total
        for _, v in obj.items():
            out.extend(_extraer_textos(v))
        return out

    return out


def _limpiar_texto(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _split_lineas(textos: List[str]) -> List[str]:
    """
    Divide en líneas candidatas.
    """
    lineas: List[str] = []
    for bloque in textos:
        # primero normaliza saltos
        partes = re.split(r"[\r\n]+", bloque)
        for p in partes:
            p = _limpiar_texto(p)
            if p:
                lineas.append(p)
    return lineas


def _es_linea_ruido(linea: str) -> bool:
    low = linea.lower()
    if len(linea) < 8:
        return True
    for w in STOPWORDS_RUIDO:
        if w in low:
            return True
    return False


def _extraer_fecha_vigencia(linea: str) -> Optional[str]:
    # ej: vigentes al 31/08/2025
    m = re.search(r"(\d{2}/\d{2}/\d{4})", linea)
    return m.group(1) if m else None


def _detectar_unidad(linea: str) -> Optional[str]:
    m = re.search(UNIDAD_REGEX, linea, flags=re.IGNORECASE)
    return m.group(1).lower() if m else None


def _extraer_precios_linea(linea: str) -> List[float]:
    precios: List[float] = []
    for m in re.finditer(PRECIO_REGEX, linea, flags=re.IGNORECASE):
        n = _normalizar_numero(m.group(1))
        if n is not None:
            precios.append(n)
    return precios


def _extraer_material_de_linea(linea: str) -> str:
    """
    Heurística:
    - quita precios
    - quita unidades sueltas repetidas
    - deja texto base del insumo
    """
    s = re.sub(PRECIO_REGEX, " ", linea, flags=re.IGNORECASE)
    s = re.sub(UNIDAD_REGEX, " ", s, flags=re.IGNORECASE)
    s = re.sub(r"\b\d+(?:[.,]\d+)?\b", " ", s)  # números sueltos
    s = re.sub(r"[|;:_\-]{2,}", " ", s)
    s = _limpiar_texto(s)

    # recortes comunes de encabezados
    s = re.sub(r"(?i)\bprecios? de (los )?materiales?\b", "", s)
    s = re.sub(r"(?i)\binsumo\b", "", s)
    s = _limpiar_texto(s)

    return s.upper()


def _linea_es_candidata_material(linea: str) -> bool:
    if _es_linea_ruido(linea):
        return False

    # Debe tener al menos un precio y longitud razonable
    precios = _extraer_precios_linea(linea)
    if len(precios) == 0:
        return False

    # Debe contener letras (nombre de material)
    if not re.search(r"[A-Za-zÁÉÍÓÚáéíóúÑñ]", linea):
        return False

    return True


def _parsear_materiales_desde_linea(
    linea: str,
    file_name: str,
    page_number: Optional[int],
    fecha_ctx: Optional[str]
) -> List[RegistroMaterial]:
    """
    Convierte una línea en 1..n registros de material.
    Regla actual: toma el ÚLTIMO precio de la línea (suele ser precio final).
    """
    if not _linea_es_candidata_material(linea):
        return []

    precios = _extraer_precios_linea(linea)
    if not precios:
        return []

    precio_final = precios[-1]

    # rango de cordura (ajústalo según tu data real)
    if precio_final <= 0 or precio_final > 100000:
        return []

    unidad = _detectar_unidad(linea)
    material = _extraer_material_de_linea(linea)

    # filtros para evitar falsos positivos
    if len(material) < 4:
        return []
    if material.lower().startswith(("s/.", "s/")):
        return []

    reg = RegistroMaterial(
        material=material,
        unidad=unidad,
        precio=precio_final,
        moneda="PEN",
        file_name=file_name,
        page_number=page_number,
        fecha_vigencia=fecha_ctx,
        linea_origen=linea
    )
    return [reg]


# ============================================================
# PIPELINE DE EXTRACCIÓN
# ============================================================
@st.cache_data(show_spinner=True)
def construir_df_materiales(path_json: str) -> pd.DataFrame:
    if not os.path.exists(path_json):
        raise FileNotFoundError(f"No se encontró el archivo: {path_json}")

    with open(path_json, "r", encoding="utf-8") as f:
        raw = json.load(f)

    archivos = _buscar_lista_archivos(raw)
    if archivos is None:
        if isinstance(raw, dict):
            raise ValueError(
                "No se encontró lista de archivos en JSON. "
                f"Claves raíz: {list(raw.keys())[:25]}"
            )
        raise ValueError("No se encontró lista de archivos en JSON.")

    registros: List[RegistroMaterial] = []

    for archivo in archivos:
        if not isinstance(archivo, dict):
            continue

        file_name = str(archivo.get("file_name", archivo.get("name", "sin_nombre")))
        pages = _obtener_paginas(archivo)

        # si no hay pages, intentamos con el objeto completo como fallback
        if not pages:
            textos = _extraer_textos(archivo)
            lineas = _split_lineas(textos)
            fecha_ctx = None
            for ln in lineas:
                fecha_ctx = _extraer_fecha_vigencia(ln) or fecha_ctx
                regs = _parsear_materiales_desde_linea(
                    linea=ln,
                    file_name=file_name,
                    page_number=None,
                    fecha_ctx=fecha_ctx
                )
                registros.extend(regs)
            continue

        # procesamiento normal por página
        for i, p in enumerate(pages, start=1):
            page_obj = p if isinstance(p, dict) else {"raw_page": p}
            page_num = _obtener_num_pagina(page_obj, i)

            textos = _extraer_textos(page_obj)
            lineas = _split_lineas(textos)

            fecha_ctx = None
            for ln in lineas:
                fecha_ctx = _extraer_fecha_vigencia(ln) or fecha_ctx
                regs = _parsear_materiales_desde_linea(
                    linea=ln,
                    file_name=file_name,
                    page_number=page_num,
                    fecha_ctx=fecha_ctx
                )
                registros.extend(regs)

    if not registros:
        raise ValueError(
            "No se extrajeron materiales. "
            "Ajusta reglas de parsing (regex/unidades/stopwords) según tu formato OCR."
        )

    df = pd.DataFrame([r.__dict__ for r in registros])

    # limpieza final
    df["material"] = df["material"].astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
    df = df[df["material"].str.len() > 3]
    df = df[df["precio"] > 0]

    # deduplicación básica
    df = df.drop_duplicates(
        subset=["material", "unidad", "precio", "file_name", "page_number", "linea_origen"]
    ).reset_index(drop=True)

    return df


# ============================================================
# UI
# ============================================================
def main():
    st.title("🏗️ Sistema Inteligente de Costos y Presupuestos")
    st.caption("Vista de materiales y precios (no archivos internos).")

    try:
        df = construir_df_materiales(ARCHIVO_JSON)
    except Exception as e:
        st.error(f"Error cargando datos: {e}")
        st.stop()

    # SIDEBAR
    st.sidebar.header("Filtros")

    material_q = st.sidebar.text_input("Buscar material:", value="ladrillo").strip()

    archivos = sorted(df["file_name"].dropna().unique().tolist())
    archivos_sel = st.sidebar.multiselect("Filtrar por archivo:", archivos, default=[])

    # unidades disponibles
    unidades = sorted([u for u in df["unidad"].dropna().unique().tolist() if str(u).strip()])
    unidades_sel = st.sidebar.multiselect("Filtrar por unidad:", unidades, default=[])

    # rango de precio
    pmin = float(df["precio"].min()) if len(df) else 0.0
    pmax = float(df["precio"].max()) if len(df) else 100.0
    rango_precio = st.sidebar.slider(
        "Rango de precio (S/)",
        min_value=float(max(0.0, pmin)),
        max_value=float(max(pmax, pmin + 1.0)),
        value=(float(max(0.0, pmin)), float(max(pmax, pmin + 1.0))),
    )

    # FILTRADO
    dff = df.copy()

    if material_q:
        dff = dff[dff["material"].str.contains(material_q, case=False, na=False)]

    if archivos_sel:
        dff = dff[dff["file_name"].isin(archivos_sel)]

    if unidades_sel:
        dff = dff[dff["unidad"].isin(unidades_sel)]

    dff = dff[(dff["precio"] >= rango_precio[0]) & (dff["precio"] <= rango_precio[1])]

    # KPIs
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Registros de materiales", f"{len(dff):,}")
    c2.metric("Materiales únicos", f"{dff['material'].nunique():,}")
    c3.metric("Precio promedio", f"S/ {dff['precio'].mean():,.2f}" if len(dff) else "S/ 0.00")
    c4.metric("Precio mínimo - máximo",
              f"S/ {dff['precio'].min():,.2f} - S/ {dff['precio'].max():,.2f}" if len(dff) else "S/ 0.00 - 0.00")

    st.divider()

    # TABLA DETALLE
    st.subheader("Detalle de materiales")
    cols_detalle = [
        "material", "unidad", "precio", "moneda",
        "file_name", "page_number", "fecha_vigencia"
    ]
    st.dataframe(
        dff[cols_detalle].sort_values(["material", "precio"], ascending=[True, True]),
        use_container_width=True,
        height=450
    )

    # RESUMEN AGRUPADO POR MATERIAL
    st.subheader("Resumen por material")
    if len(dff):
        resumen = (
            dff.groupby("material", dropna=False)
            .agg(
                unidad=("unidad", lambda x: x.dropna().mode().iloc[0] if len(x.dropna()) else None),
                n_registros=("precio", "count"),
                precio_min=("precio", "min"),
                precio_prom=("precio", "mean"),
                precio_max=("precio", "max"),
            )
            .reset_index()
            .sort_values("precio_prom")
        )
        st.dataframe(resumen, use_container_width=True, height=350)
    else:
        st.info("No hay resultados con los filtros actuales.")

    # DESCARGA
    st.download_button(
        "⬇️ Descargar detalle CSV",
        dff.to_csv(index=False).encode("utf-8"),
        file_name="materiales_detalle.csv",
        mime="text/csv",
    )

    if len(dff):
        resumen_csv = resumen.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Descargar resumen CSV",
            resumen_csv,
            file_name="materiales_resumen.csv",
            mime="text/csv",
        )

    # DEBUG
    with st.expander("Debug parser"):
        st.write("Columnas detectadas:", df.columns.tolist())
        st.write("Muestra de líneas origen:")
        muestra = dff[["material", "precio", "linea_origen"]].head(10) if len(dff) else df[["material", "precio", "linea_origen"]].head(10)
        st.dataframe(muestra, use_container_width=True)


if __name__ == "__main__":
    main()
