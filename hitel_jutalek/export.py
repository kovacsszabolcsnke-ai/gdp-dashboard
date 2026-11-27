"""Excel export a számfejtés eredményéből."""
from __future__ import annotations

from io import BytesIO

import pandas as pd

from .szamitas import Eredmeny, TIPUS_STORNO


def _iras(writer, df: pd.DataFrame, lap: str) -> None:
    df.to_excel(writer, sheet_name=lap, index=False)
    ws = writer.sheets[lap]
    for i, oszlop in enumerate(df.columns, start=1):
        hossz = max([len(str(oszlop))] + [len(str(v)) for v in df[oszlop].head(200)])
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = min(hossz + 2, 45)
        if pd.api.types.is_numeric_dtype(df[oszlop]) and "%" not in oszlop:
            for c in ws.iter_rows(min_row=2, min_col=i, max_col=i):
                c[0].number_format = "#,##0"
    ws.freeze_panes = "A2"


def excel(e: Eredmeny, idoszak: str) -> bytes:
    buf = BytesIO()
    ceg = pd.DataFrame([{"Tétel": k, "Összeg (Ft)": v} for k, v in e.ceg.items()])
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        _iras(w, e.osszesito, "Összesítő")
        _iras(w, ceg, "Cég")
        _iras(w, e.tetelek, "Tételek")
        _iras(w, e.tetelek[e.tetelek["Típus"] == TIPUS_STORNO], "Storno")
        _iras(w, e.hibak, "Hibák")
        w.book.properties.title = f"Hitel jutalék számfejtés {idoszak}"
    return buf.getvalue()


def kozvetito_elszamolo(e: Eredmeny, nev: str, idoszak: str) -> bytes:
    buf = BytesIO()
    osszesito = e.osszesito[e.osszesito["Közvetítő"] == nev].T.reset_index()
    osszesito.columns = ["Megnevezés", "Érték"]
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        _iras(w, osszesito, "Elszámoló")
        _iras(w, e.tetelek[e.tetelek["Kedvezményezett"] == nev], "Tételek")
        w.book.properties.title = f"Jutalék elszámoló {nev} {idoszak}"
    return buf.getvalue()
