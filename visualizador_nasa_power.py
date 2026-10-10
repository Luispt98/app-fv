#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Panel interactivo para visualizar NASA POWER y resultados del Excel eólico.

Lee la hoja 00_DATOS_NASA sin modificar el libro. Usa solo la biblioteca estándar
para leer el XLSX; Streamlit y Plotly se usan únicamente para el panel de gráficos.
El panel vuelve a comprobar el archivo periódicamente para detectar cambios guardados.
"""
from __future__ import annotations

import math
import os
import posixpath
import re
import zipfile
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
import xml.etree.ElementTree as ET

try:
    import streamlit as st
    import plotly.graph_objects as go
    from streamlit_autorefresh import st_autorefresh
except ImportError as exc:  # error de configuración con instrucciones claras
    raise SystemExit(
        "Faltan dependencias. Abre una terminal y ejecuta:\n"
        "  python -m pip install -r requirements.txt\n"
        f"Detalle: {exc}"
    ) from exc

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"m": MAIN_NS, "r": REL_NS}
ROW_TAG = f"{{{MAIN_NS}}}row"
CELL_TAG = f"{{{MAIN_NS}}}c"

DEFAULT_BOOK = Path(__file__).resolve().with_name("03_CALCULO_INFORME_AUDITADO_AI(1).xlsx")
SECTORS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
           "S", "SSO", "SO", "OSO", "O", "ONO", "NO", "NNO"]
MONTHS = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


def _read_shared_strings(zf: zipfile.ZipFile) -> List[str]:
    name = "xl/sharedStrings.xml"
    if name not in zf.namelist():
        return []
    values: List[str] = []
    with zf.open(name) as fp:
        for _, elem in ET.iterparse(fp, events=("end",)):
            if elem.tag == f"{{{MAIN_NS}}}si":
                values.append("".join(t.text or "" for t in elem.findall(f".//{{{MAIN_NS}}}t")))
                elem.clear()
    return values


def _sheet_paths(zf: zipfile.ZipFile) -> Dict[str, str]:
    workbook = ET.fromstring(zf.read("xl/workbook.xml"))
    rel_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    rels = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rel_root.findall(f"{{{PKG_REL_NS}}}Relationship")}
    result: Dict[str, str] = {}
    for sheet in workbook.find(f"{{{MAIN_NS}}}sheets"):
        rel_id = sheet.attrib[f"{{{REL_NS}}}id"]
        target = rels[rel_id]
        if target.startswith("/"):
            path = target.lstrip("/")
        else:
            path = posixpath.normpath(posixpath.join("xl", target))
        result[sheet.attrib["name"]] = path
    return result


def _cell_value(cell: ET.Element, shared: Sequence[str]) -> Any:
    typ = cell.attrib.get("t", "")
    if typ == "inlineStr":
        return "".join(t.text or "" for t in cell.findall(f".//{{{MAIN_NS}}}t"))
    value = cell.find(f"{{{MAIN_NS}}}v")
    if value is None or value.text is None or value.text == "":
        return None
    raw = value.text
    if typ == "s":
        try:
            return shared[int(raw)]
        except (IndexError, ValueError):
            return None
    if typ in ("str", "e"):
        return raw
    if typ == "b":
        return raw == "1"
    try:
        number = float(raw)
        if math.isfinite(number):
            return int(number) if number.is_integer() else number
        return None
    except ValueError:
        return raw


def _col_index(ref: str) -> int:
    letters = re.match(r"([A-Z]+)", ref.upper())
    if not letters:
        return -1
    value = 0
    for ch in letters.group(1):
        value = value * 26 + ord(ch) - ord("A") + 1
    return value - 1


def _num(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        n = float(value)
        if not math.isfinite(n) or n <= -900:  # -999 es el centinela NASA POWER
            return None
        return n
    except (TypeError, ValueError):
        return None


def _iter_sheet_rows(zf: zipfile.ZipFile, path: str, shared: Sequence[str]) -> Iterable[Tuple[int, Dict[str, Any]]]:
    """Itera filas como {A1: valor}; usa iterparse para no cargar toda la hoja en memoria."""
    with zf.open(path) as fp:
        for _, elem in ET.iterparse(fp, events=("end",)):
            if elem.tag != ROW_TAG:
                continue
            try:
                row_number = int(elem.attrib.get("r", "0"))
            except ValueError:
                row_number = 0
            row_values: Dict[str, Any] = {}
            for cell in elem.findall(CELL_TAG):
                ref = cell.attrib.get("r")
                if ref:
                    row_values[ref] = _cell_value(cell, shared)
            yield row_number, row_values
            elem.clear()


def _read_small_sheet(zf: zipfile.ZipFile, path: str, shared: Sequence[str]) -> Dict[str, Any]:
    cells: Dict[str, Any] = {}
    for _, row in _iter_sheet_rows(zf, path, shared):
        cells.update(row)
    return cells


def _cell(cells: Dict[str, Any], address: str) -> Any:
    return cells.get(address)


def _to_float(value: Any) -> Optional[float]:
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def parse_workbook(path: str) -> Dict[str, Any]:
    """Carga NASA POWER y los resultados resumidos que ya estén guardados en el Excel."""
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"No se encontró el archivo: {file_path}")
    if file_path.suffix.lower() != ".xlsx":
        raise ValueError("Selecciona un archivo .xlsx.")

    records: List[Tuple[datetime, Optional[float], Optional[float], Optional[float], Optional[float], Optional[float], Optional[float]]] = []
    with zipfile.ZipFile(file_path, "r") as zf:
        paths = _sheet_paths(zf)
        if "00_DATOS_NASA" not in paths:
            raise ValueError("No existe la hoja '00_DATOS_NASA' en el libro.")
        shared = _read_shared_strings(zf)
        header_map: Optional[Dict[str, int]] = None
        for row_number, row in _iter_sheet_rows(zf, paths["00_DATOS_NASA"], shared):
            values_by_col: Dict[int, Any] = {}
            for ref, value in row.items():
                idx = _col_index(ref)
                if idx >= 0:
                    values_by_col[idx] = value

            if header_map is None:
                candidate = {str(v).strip().upper(): col for col, v in values_by_col.items() if v is not None}
                required = {"YEAR", "MO", "DY", "HR", "WS10M", "WD10M", "WS50M", "WD50M", "PS", "T2M"}
                if required.issubset(candidate):
                    header_map = {name: candidate[name] for name in required}
                continue

            def raw(name: str) -> Any:
                return values_by_col.get(header_map[name])

            try:
                year = int(float(raw("YEAR")))
                month = int(float(raw("MO")))
                day = int(float(raw("DY")))
                hour = int(float(raw("HR")))
                stamp = datetime(year, month, day, hour)
            except (TypeError, ValueError, OverflowError):
                continue

            records.append((stamp,
                            _num(raw("WS10M")), _num(raw("WD10M")),
                            _num(raw("WS50M")), _num(raw("WD50M")),
                            _num(raw("PS")), _num(raw("T2M"))))

        if header_map is None:
            raise ValueError("No se encontró una fila de encabezados NASA POWER con YEAR, MO, DY, HR, WS10M, WD10M, WS50M, WD50M, PS y T2M.")
        records.sort(key=lambda r: r[0])

        def small(name: str) -> Dict[str, Any]:
            if name not in paths:
                return {}
            return _read_small_sheet(zf, paths[name], shared)

        profile_cells = small("03_PERFIL_VERTICAL")
        balance_cells = small("BALANCE_AEP")
        sensitivity_cells = small("SENSIBILIDADES")
        pre_cells = small("01_PREPROCESAMIENTO")

    # Perfil vertical (filas 4–18 de las columnas D:F).
    profile = []
    for r in range(4, 19):
        h = _to_float(_cell(profile_cells, f"D{r}"))
        p = _to_float(_cell(profile_cells, f"E{r}"))
        log = _to_float(_cell(profile_cells, f"F{r}"))
        if h is not None and (p is not None or log is not None):
            profile.append({"height": h, "power": p, "log": log})

    balance = {
        "Fila": {
            "installed_mw": _to_float(_cell(balance_cells, "B4")),
            "gross": _to_float(_cell(balance_cells, "B5")),
            "after_wake": _to_float(_cell(balance_cells, "B6")),
            "wake_loss": _to_float(_cell(balance_cells, "B7")),
            "net": _to_float(_cell(balance_cells, "B11")),
            "capacity_factor": _to_float(_cell(balance_cells, "B13")),
            "equivalent_hours": _to_float(_cell(balance_cells, "B14")),
            "total_losses": _to_float(_cell(balance_cells, "B15")),
        },
        "Escalonado": {
            "installed_mw": _to_float(_cell(balance_cells, "C4")),
            "gross": _to_float(_cell(balance_cells, "C5")),
            "after_wake": _to_float(_cell(balance_cells, "C6")),
            "wake_loss": _to_float(_cell(balance_cells, "C7")),
            "net": _to_float(_cell(balance_cells, "C11")),
            "capacity_factor": _to_float(_cell(balance_cells, "C13")),
            "equivalent_hours": _to_float(_cell(balance_cells, "C14")),
            "total_losses": _to_float(_cell(balance_cells, "C15")),
        },
    }

    sensitivities = []
    for r in range(2, 20):
        param = _cell(sensitivity_cells, f"A{r}")
        change = _to_float(_cell(sensitivity_cells, f"B{r}"))
        layout = _cell(sensitivity_cells, f"D{r}")
        net = _to_float(_cell(sensitivity_cells, f"G{r}"))
        delta_pct = _to_float(_cell(sensitivity_cells, f"J{r}"))
        if param and layout and net is not None and change is not None:
            sensitivities.append({"parameter": str(param), "change": change,
                                  "layout": str(layout), "net": net, "delta_pct": delta_pct})

    if not records:
        raise ValueError("No se encontraron registros horarios válidos en '00_DATOS_NASA'.")
    return {
        "records": records,
        "profile": profile,
        "balance": balance,
        "sensitivities": sensitivities,
        "preprocessing": {
            "source": _cell(pre_cells, "B3"),
            "period": _cell(pre_cells, "B4"),
            "latitude": _to_float(_cell(pre_cells, "B5")),
            "longitude": _to_float(_cell(pre_cells, "B6")),
        },
        "workbook_path": str(file_path),
        "records_loaded": len(records),
    }


def _mean(values: Iterable[Optional[float]]) -> Optional[float]:
    data = [v for v in values if v is not None and math.isfinite(v)]
    return sum(data) / len(data) if data else None


def _fmt(value: Optional[float], decimals: int = 2, suffix: str = "") -> str:
    return "—" if value is None else f"{value:,.{decimals}f}{suffix}".replace(",", "X").replace(".", ",").replace("X", ".")


def _sector_for_direction(direction: float) -> int:
    return int(math.floor(((direction % 360.0) + 11.25) / 22.5)) % 16


def _year_month_means(records: Sequence[Tuple], field_index: int, year_filter: Optional[int] = None, daily: bool = False) -> Tuple[List[datetime], List[Optional[float]]]:
    grouped: Dict[Any, List[float]] = defaultdict(list)
    for rec in records:
        stamp, value = rec[0], rec[field_index]
        if year_filter is not None and stamp.year != year_filter:
            continue
        if value is None:
            continue
        key = stamp.date() if daily else (stamp.year, stamp.month)
        grouped[key].append(value)
    keys = sorted(grouped)
    x: List[datetime] = []
    y: List[Optional[float]] = []
    for key in keys:
        if daily:
            x.append(datetime.combine(key, datetime.min.time()))
        else:
            x.append(datetime(key[0], key[1], 1))
        y.append(_mean(grouped[key]))
    return x, y


def _monthly_climatology(records: Sequence[Tuple], field_index: int) -> List[Optional[float]]:
    values: Dict[int, List[float]] = defaultdict(list)
    for rec in records:
        val = rec[field_index]
        if val is not None:
            values[rec[0].month].append(val)
    return [_mean(values[m]) for m in range(1, 13)]


def _direction_summary(records: Sequence[Tuple]) -> Tuple[List[float], List[Optional[float]], List[Optional[float]], int]:
    count = [0] * 16
    sum10 = [0.0] * 16
    cnt10 = [0] * 16
    sum50 = [0.0] * 16
    cnt50 = [0] * 16
    valid_direction = 0
    for rec in records:
        direction = rec[2]
        if direction is None or direction < 0 or direction > 360:
            continue
        i = _sector_for_direction(direction)
        valid_direction += 1
        count[i] += 1
        if rec[1] is not None:
            sum10[i] += rec[1]
            cnt10[i] += 1
        if rec[3] is not None:
            sum50[i] += rec[3]
            cnt50[i] += 1
    freq = [100.0 * c / valid_direction if valid_direction else 0.0 for c in count]
    avg10 = [sum10[i] / cnt10[i] if cnt10[i] else None for i in range(16)]
    avg50 = [sum50[i] / cnt50[i] if cnt50[i] else None for i in range(16)]
    return freq, avg10, avg50, valid_direction


def _quality_summary(records: Sequence[Tuple]) -> Dict[str, Any]:
    cols = {"WS10M": 1, "WD10M": 2, "WS50M": 3, "WD50M": 4, "PS": 5, "T2M": 6}
    quality = {}
    n = len(records)
    for name, idx in cols.items():
        valid = sum(1 for r in records if r[idx] is not None)
        quality[name] = {"valid": valid, "missing": n - valid, "coverage": valid / n if n else 0}
    stamps = [r[0] for r in records]
    unique = len(set(stamps))
    gaps = 0
    for previous, current in zip(stamps, stamps[1:]):
        hours = (current - previous).total_seconds() / 3600
        if hours > 1.000001:
            gaps += max(1, int(round(hours)) - 1)
    return {"count": n, "start": stamps[0], "end": stamps[-1],
            "duplicates": n - unique, "gap_hours": gaps, "variables": quality}


def _new_figure(title: str, x_title: str = "", y_title: str = "", height: int = 390) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(title=title, xaxis_title=x_title, yaxis_title=y_title,
                      height=height, template="plotly_white", margin=dict(l=35, r=25, t=65, b=45),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0))
    return fig


@st.cache_data(show_spinner="Leyendo el Excel y preparando las series…", max_entries=4)
def cached_parse(path: str, mtime_ns: int, size_bytes: int) -> Dict[str, Any]:
    # mtime y tamaño forman parte de la clave: se vuelve a leer cuando se guarda el archivo.
    return parse_workbook(path)


def main() -> None:
    st.set_page_config(page_title="Visualizador NASA POWER | Parque eólico", layout="wide")
    st.title("Visualizador del recurso eólico — NASA POWER")
    st.caption("Uribia, La Guajira · Vestas V90 2 MW · Panel de lectura del Excel; no modifica el archivo original.")

    with st.sidebar:
        st.header("Configuración")
        path_text = st.text_input("Ruta del libro Excel", value=str(DEFAULT_BOOK), help="Guarda el Excel actualizado y escribe aquí su ruta completa si está en otra carpeta.")
        auto_refresh = st.checkbox("Detectar cambios guardados automáticamente", value=True)
        refresh_seconds = st.selectbox("Frecuencia de comprobación", [15, 30, 60, 120], index=1, format_func=lambda x: f"Cada {x} segundos")
        st.caption("El Excel debe guardarse después de editar NASA POWER para que el panel detecte los cambios.")
        if st.button("Actualizar ahora", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        st.divider()
        st.caption("Hoja fuente: 00_DATOS_NASA · Encabezados detectados por nombre, no por rango fijo.")

    if auto_refresh:
        st_autorefresh(interval=int(refresh_seconds * 1000), key="nasa_power_auto_refresh")

    book_path = Path(os.path.expandvars(path_text)).expanduser()
    if not book_path.is_absolute():
        book_path = (Path.cwd() / book_path).resolve()
    if not book_path.exists():
        st.error(f"No encuentro el archivo:\n\n`{book_path}`\n\nPon el Excel junto al script o escribe la ruta correcta en la barra lateral.")
        st.stop()

    stat = book_path.stat()
    try:
        data = cached_parse(str(book_path), stat.st_mtime_ns, stat.st_size)
    except (OSError, zipfile.BadZipFile, KeyError, ValueError, ET.ParseError) as exc:
        st.error(f"No pude leer el Excel. Comprueba que sea un archivo .xlsx válido y que no esté en proceso de guardado.\n\nDetalle: {exc}")
        st.stop()

    records = data["records"]
    quality = _quality_summary(records)
    avg10 = _mean(r[1] for r in records)
    avg50 = _mean(r[3] for r in records)
    avg_ps = _mean(r[5] for r in records)
    avg_t = _mean(r[6] for r in records)
    valid10 = quality["variables"]["WS10M"]["valid"]
    valid50 = quality["variables"]["WS50M"]["valid"]

    if quality["duplicates"] > 0 or quality["gap_hours"] > 0:
        st.warning(f"Control temporal: {quality['duplicates']} marcas duplicadas y {quality['gap_hours']} horas ausentes detectadas en la secuencia. Revisa la exportación antes de confiar en los promedios.")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Registros horarios", f"{quality['count']:,}".replace(",", "."))
    c2.metric("Viento medio · 10 m", _fmt(avg10, 2, " m/s"))
    c3.metric("Viento medio · 50 m", _fmt(avg50, 2, " m/s"))
    c4.metric("Presión media", _fmt(avg_ps, 2, " kPa"))
    c5.metric("Temperatura media", _fmt(avg_t, 2, " °C"))
    st.caption(f"Datos leídos: {quality['start']:%d/%m/%Y %H:%M} UTC a {quality['end']:%d/%m/%Y %H:%M} UTC · Archivo guardado por última vez: {datetime.fromtimestamp(stat.st_mtime):%d/%m/%Y %H:%M:%S}.")

    all_years = sorted({r[0].year for r in records})
    years: List[str] = ["Todos"] + [str(y) for y in all_years]
    selected_year = st.selectbox("Año que quieres explorar", years, index=0)
    year_filter = None if selected_year == "Todos" else int(selected_year)
    filtered = records if year_filter is None else [r for r in records if r[0].year == year_filter]

    tab_resource, tab_direction, tab_model, tab_quality = st.tabs(["Recurso temporal", "Dirección del viento", "Modelo eólico", "Calidad de datos"])

    with tab_resource:
        left, right = st.columns(2)
        with left:
            fig = _new_figure("Velocidad media por mes", "Mes", "Velocidad (m/s)")
            fig.add_trace(go.Scatter(x=MONTHS, y=_monthly_climatology(filtered, 1), mode="lines+markers", name="WS10M · 10 m"))
            fig.add_trace(go.Scatter(x=MONTHS, y=_monthly_climatology(filtered, 3), mode="lines+markers", name="WS50M · 50 m"))
            st.plotly_chart(fig, use_container_width=True)
            st.caption("Los promedios mensuales muestran la variación estacional dentro del periodo seleccionado. El promedio no describe por sí solo los extremos ni garantiza la producción de un año concreto.")
        with right:
            var_map = {"Velocidad del viento a 10 m (WS10M)": (1, "m/s"),
                       "Velocidad del viento a 50 m (WS50M)": (3, "m/s"),
                       "Presión superficial (PS)": (5, "kPa"),
                       "Temperatura a 2 m (T2M)": (6, "°C")}
            selected_variable = st.selectbox("Variable de la serie temporal", list(var_map.keys()))
            idx, unit = var_map[selected_variable]
            daily = year_filter is not None
            x, y = _year_month_means(filtered, idx, year_filter=None, daily=daily)
            fig = _new_figure("Evolución temporal de la variable seleccionada", "Fecha" if daily else "Mes", f"Valor ({unit})")
            fig.add_trace(go.Scatter(x=x, y=y, mode="lines", name=selected_variable))
            st.plotly_chart(fig, use_container_width=True)
            st.caption("Con un año concreto, la serie se resume por día; con ‘Todos’, se resume por mes y año para que el gráfico siga siendo legible.")

        left, right = st.columns(2)
        with left:
            fig = _new_figure("Distribución de velocidades", "Velocidad (m/s)", "Número de registros")
            s10 = [r[1] for r in filtered if r[1] is not None]
            s50 = [r[3] for r in filtered if r[3] is not None]
            fig.add_trace(go.Histogram(x=s10, nbinsx=45, opacity=0.65, name="WS10M · 10 m"))
            fig.add_trace(go.Histogram(x=s50, nbinsx=45, opacity=0.65, name="WS50M · 50 m"))
            fig.update_layout(barmode="overlay")
            st.plotly_chart(fig, use_container_width=True)
            st.caption("El histograma ayuda a comparar la frecuencia de velocidades a 10 y 50 m. No sustituye el ajuste formal de Weibull ni una prueba de bondad de ajuste.")
        with right:
            # Medias mensuales conjuntas de temperatura y presión, con ejes separados.
            monthly_temp: Dict[int, List[float]] = defaultdict(list)
            monthly_ps: Dict[int, List[float]] = defaultdict(list)
            for r in filtered:
                if r[6] is not None: monthly_temp[r[0].month].append(r[6])
                if r[5] is not None: monthly_ps[r[0].month].append(r[5])
            fig = _new_figure("Temperatura y presión medias por mes", "Mes", "Temperatura (°C)")
            fig.add_trace(go.Scatter(x=MONTHS, y=[_mean(monthly_temp[m]) for m in range(1,13)], mode="lines+markers", name="T2M (°C)"))
            fig.add_trace(go.Scatter(x=MONTHS, y=[_mean(monthly_ps[m]) for m in range(1,13)], mode="lines+markers", name="PS (kPa)", yaxis="y2"))
            fig.update_layout(yaxis2=dict(title="Presión (kPa)", overlaying="y", side="right", showgrid=False))
            st.plotly_chart(fig, use_container_width=True)
            st.caption("La presión y la temperatura permiten contextualizar la densidad del aire. El gráfico no calcula por sí solo la densidad horaria.")

    with tab_direction:
        freq, avg_sector10, avg_sector50, valid_directions = _direction_summary(filtered)
        left, right = st.columns(2)
        with left:
            fig = go.Figure(go.Barpolar(r=freq, theta=[i * 22.5 for i in range(16)], width=[22.5] * 16, name="Frecuencia"))
            fig.update_layout(title="Rosa de frecuencia de dirección · WD10M", height=450, template="plotly_white",
                              margin=dict(l=30, r=30, t=65, b=35),
                              polar=dict(angularaxis=dict(direction="clockwise", rotation=90, tickmode="array",
                                                          tickvals=[i*22.5 for i in range(16)], ticktext=SECTORS),
                                          radialaxis=dict(title="Frecuencia (%)")))
            st.plotly_chart(fig, use_container_width=True)
            st.caption("La rosa muestra con qué frecuencia se registra viento desde cada sector. No es una rosa de energía y utiliza los valores direccionales de WD10M.")
        with right:
            fig = go.Figure()
            fig.add_trace(go.Bar(x=SECTORS, y=freq, name="Frecuencia (%)", yaxis="y"))
            fig.add_trace(go.Scatter(x=SECTORS, y=avg_sector10, mode="lines+markers", name="Media WS10M", yaxis="y2"))
            fig.add_trace(go.Scatter(x=SECTORS, y=avg_sector50, mode="lines+markers", name="Media WS50M", yaxis="y2"))
            fig.update_layout(title="Frecuencia y velocidad media por sector", xaxis_title="Sector direccional",
                              yaxis=dict(title="Frecuencia (%)"), yaxis2=dict(title="Velocidad media (m/s)", overlaying="y", side="right"),
                              height=450, template="plotly_white", margin=dict(l=35, r=35, t=65, b=45),
                              legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0))
            st.plotly_chart(fig, use_container_width=True)
            st.caption(f"Se usaron {valid_directions:,} registros con dirección válida en el periodo filtrado. Una dirección frecuente no implica necesariamente la mayor contribución energética.")

    with tab_model:
        st.warning("Los resultados de las hojas del modelo se leen de los valores calculados que quedaron guardados en el Excel. Después de sustituir NASA POWER, abre el libro en Excel o LibreOffice, verifica que el cálculo esté en modo automático y guarda el archivo. Si una hoja no está vinculada por fórmulas a los datos nuevos, también habrá que corregir esa dependencia en el libro.")
        left, right = st.columns(2)
        with left:
            fig = _new_figure("Perfil vertical calculado en el Excel", "Altura (m)", "Velocidad (m/s)")
            if data["profile"]:
                fig.add_trace(go.Scatter(x=[p["height"] for p in data["profile"]], y=[p["power"] for p in data["profile"]], mode="lines+markers", name="Ley de potencia"))
                fig.add_trace(go.Scatter(x=[p["height"] for p in data["profile"]], y=[p["log"] for p in data["profile"]], mode="lines+markers", name="Ley logarítmica"))
            st.plotly_chart(fig, use_container_width=True)
            st.caption("Este perfil toma los valores guardados en 03_PERFIL_VERTICAL; solo representará los datos nuevos si sus fórmulas se han recalculado correctamente.")
        with right:
            bal = data["balance"]
            categories = ["AEP bruta", "Después de estelas", "AEP neta"]
            fig = _new_figure("Balance energético por configuración", "Etapa", "Energía (MWh/año)")
            for layout in ("Fila", "Escalonado"):
                b = bal[layout]
                fig.add_trace(go.Bar(x=categories, y=[b["gross"], b["after_wake"], b["net"]], name=layout))
            fig.update_layout(barmode="group")
            st.plotly_chart(fig, use_container_width=True)
            st.caption("La energía bruta, la energía tras estelas y la neta son estimaciones del modelo, condicionadas por la curva de potencia, Weibull, estelas y pérdidas asumidas.")

        metric_rows = []
        for layout, b in data["balance"].items():
            if b["gross"] is None and b["net"] is None:
                continue
            metric_rows.append({
                "Configuración": layout,
                "Potencia instalada (MW)": _fmt(b["installed_mw"], 2),
                "AEP bruta (MWh/año)": _fmt(b["gross"], 0),
                "AEP después de estelas (MWh/año)": _fmt(b["after_wake"], 0),
                "AEP neta (MWh/año)": _fmt(b["net"], 0),
                "Pérdida por estelas (%)": _fmt(b["wake_loss"] * 100 if b["wake_loss"] is not None else None, 2),
                "Factor de capacidad neto (%)": _fmt(b["capacity_factor"] * 100 if b["capacity_factor"] is not None else None, 2),
            })
        if metric_rows:
            st.subheader("Indicadores guardados en BALANCE_AEP")
            st.table(metric_rows)

        sens = [s for s in data["sensitivities"] if abs(s["change"]) > 1e-9 and s["delta_pct"] is not None]
        if sens:
            fig = _new_figure("Sensibilidad de la AEP neta frente al escenario base", "Cambio de parámetro", "Cambio relativo de AEP neta (%)")
            labels = []
            for s in sens:
                param_symbol = {"alpha": "α", "kw": "k_w", "rho": "ρ"}.get(s["parameter"].lower(), s["parameter"])
                label = f"{param_symbol} {'+' if s['change'] > 0 else '−'}{abs(s['change'])*100:.0f}%"
                labels.append((label, s))
            cats = list(dict.fromkeys(lbl for lbl, _ in labels))
            for layout in ["Fila", "Escalonado"]:
                by_cat = {}
                for label, s in labels:
                    if s["layout"].lower() == layout.lower():
                        by_cat[label] = s["delta_pct"] * 100
                fig.add_trace(go.Bar(x=cats, y=[by_cat.get(c) for c in cats], name=layout))
            fig.update_layout(barmode="group")
            st.plotly_chart(fig, use_container_width=True)
            st.caption("La sensibilidad muestra cambios paramétricos independientes de ±10 %, no una incertidumbre probabilística ni valores P50/P90.")
        else:
            st.info("No hay valores guardados suficientes en SENSIBILIDADES para dibujar la comparación.")

    with tab_quality:
        st.subheader("Control de cobertura de la serie NASA POWER")
        st.write(f"**Periodo leído:** {quality['start']:%Y-%m-%d %H:%M} UTC — {quality['end']:%Y-%m-%d %H:%M} UTC")
        st.write(f"**Registros:** {quality['count']:,} · **Marcas duplicadas:** {quality['duplicates']} · **Horas ausentes detectadas:** {quality['gap_hours']}")
        rows = []
        labels = {"WS10M": "Velocidad a 10 m", "WD10M": "Dirección a 10 m", "WS50M": "Velocidad a 50 m", "WD50M": "Dirección a 50 m", "PS": "Presión superficial", "T2M": "Temperatura a 2 m"}
        for key, q in quality["variables"].items():
            rows.append({"Variable": key, "Descripción": labels[key], "Válidos": q["valid"], "Faltantes": q["missing"], "Cobertura (%)": round(q["coverage"] * 100, 3)})
        st.table(rows)
        st.subheader("Muestra de los registros más recientes")
        sample = records[-10:]
        st.table([{"Fecha UTC": r[0].strftime("%Y-%m-%d %H:%M"), "WS10M (m/s)": r[1], "WD10M (°)": r[2], "WS50M (m/s)": r[3], "WD50M (°)": r[4], "PS (kPa)": r[5], "T2M (°C)": r[6]} for r in reversed(sample)])
        st.caption("NASA POWER es una fuente de datos de reanálisis/modelado. Para un estudio de prefactibilidad, estos resultados deberían contrastarse con una campaña de medición en el sitio.")

    st.divider()
    st.caption("Visualizador de solo lectura. No altera fórmulas, datos ni gráficos incrustados del archivo Excel.")


if __name__ == "__main__":
    main()
