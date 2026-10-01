from __future__ import annotations

import re

import pandas as pd


OP_TYPE_COL = "TYPE"
OP_FINGER_COL = "FINGER"
OP_DIMENSION_COL = "DIMENSION"
OP_MARKER_1_COL = "MARKER 1"
OP_MARKER_2_COL = "MARKER 2"

OP_COLUMNS = [
    OP_TYPE_COL,
    OP_FINGER_COL,
    OP_DIMENSION_COL,
    OP_MARKER_1_COL,
    OP_MARKER_2_COL,
]

OP_COLUMN_ALIASES = {
    OP_TYPE_COL: ("TYPE", "TIPO"),
    OP_FINGER_COL: ("FINGER",),
    OP_DIMENSION_COL: ("DIMENSION",),
    OP_MARKER_1_COL: ("MARKER 1", "MARCADOR 1"),
    OP_MARKER_2_COL: ("MARKER 2", "MARCADOR 2"),
}


def normalize_ops_columns(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Return a copy whose operations columns use the current English names.

    Legacy Spanish headers are accepted so older selected/custom CSV files remain
    loadable.
    """
    original_by_normalized = {
        str(col).strip().upper(): col
        for col in df.columns
    }

    rename_map = {}
    missing: list[str] = []
    for canonical, aliases in OP_COLUMN_ALIASES.items():
        source = None
        for alias in aliases:
            source = original_by_normalized.get(alias.upper())
            if source is not None:
                break
        if source is None:
            missing.append(canonical)
        else:
            rename_map[source] = canonical

    if missing:
        return df.copy(), missing

    return df.rename(columns=rename_map).copy(), []


def is_invalid_ops_marker(value: object) -> bool:
    if value is None or pd.isna(value):
        return True

    marker = str(value).strip()
    if not marker:
        return True

    low = marker.casefold()
    if "linea" in low or "línea" in low or "l�nea" in low:
        return True

    return bool(re.search(r"\s-\s", marker))


def drop_invalid_marker_ops(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    invalid = (
        df[OP_MARKER_1_COL].apply(is_invalid_ops_marker)
        | df[OP_MARKER_2_COL].apply(is_invalid_ops_marker)
    )
    return df.loc[~invalid].copy(), int(invalid.sum())
