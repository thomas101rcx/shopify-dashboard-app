"""Load and compute the Shopify Pivot Table overview dashboard."""

from __future__ import annotations

import pandas as pd

import config as cfg

PIVOT_PATH = "pivot_table.xlsx"


def _load_raw_sheet(name: str) -> pd.DataFrame:
    return pd.read_excel(PIVOT_PATH, sheet_name=name, header=None)


def _coerce_numeric(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
    return df


def _growth(new, old):
    if old == 0:
        return None
    return (new - old) / old


def _resolve_fill(cell) -> str | None:
    if not cell.fill or not cell.fill.fgColor:
        return None
    rgb = cell.fill.fgColor.rgb
    if rgb and rgb != "00000000" and not str(rgb).startswith("Values"):
        return cfg.FILL_COLORS.get(rgb, f"#{rgb}")
    return None


def _resolve_font_color(cell) -> str | None:
    if not cell.font or not cell.font.color:
        return None
    rgb = cell.font.color.rgb
    if rgb and rgb != "00000000" and not str(rgb).startswith("Values"):
        return cfg.FONT_COLORS.get(rgb, f"#{rgb}")
    return None


def _has_colored_label(cell) -> str | None:
    """Return label type based on cell fill color."""
    if not cell.fill or not cell.fill.fgColor:
        return None
    rgb = str(cell.fill.fgColor.rgb)
    return cfg.FILL_TO_LABEL_TYPE.get(rgb)


def load_overview() -> pd.DataFrame:
    """Load Overview sheet with computed 2026 YTD and growth.

    Preserves text labels in growth columns (New_24, Lost, SOS, etc.).
    Only computes % for cells that are originally numeric.
    """
    from openpyxl import load_workbook as _lw
    wb = _lw(PIVOT_PATH, data_only=True)
    ws = wb[cfg.SHEET_OVERVIEW]

    cols = cfg.OVERVIEW_COLS
    ncols = cfg.OVERVIEW_NUM_COLS

    data_rows = []
    for r in range(3, ws.max_row + 1):
        row_vals = [ws.cell(row=r, column=c).value for c in range(1, ncols + 1)]
        if all(v is None for v in row_vals):
            continue
        if not row_vals[0]:
            break
        data_rows.append(row_vals)

    df = pd.DataFrame(data_rows, columns=cols)

    for c in cfg.QTY_COLS:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)

    df[cfg.COL_QTY_2026_TOTAL] = (
        df[cfg.COL_QTY_2026_Q1] + df[cfg.COL_QTY_2026_Q2]
        + df[cfg.COL_QTY_2026_Q3] + df[cfg.COL_QTY_2026_Q4]
    )

    growth_defs = [
        (cfg.COL_GROWTH_23_24, cfg.COL_QTY_2024, cfg.COL_QTY_2023),
        (cfg.COL_GROWTH_24_25, cfg.COL_QTY_2025, cfg.COL_QTY_2024),
        (cfg.COL_GROWTH_25_26, cfg.COL_QTY_2026_TOTAL, cfg.COL_QTY_2025),
    ]
    for gcol, new_col, old_col in growth_defs:
        computed = df.apply(lambda r: _growth(r[new_col], r[old_col]), axis=1)
        for i in range(len(df)):
            original = df.at[i, gcol]
            if isinstance(original, str) and original.strip():
                continue
            elif isinstance(original, (int, float)):
                pass
            else:
                df.at[i, gcol] = computed.iloc[i]

    return df


def load_overview_styled(wb) -> list[dict]:
    """Return per-cell style info for the Overview sheet using openpyxl workbook.

    Returns list of dicts keyed by column index (1-based):
      {col_idx: {"value": ..., "fill": str|None, "font_color": str|None, "label_type": str|None, "is_numeric": bool}}
    """
    ws = wb[cfg.SHEET_OVERVIEW]
    rows = []
    for r in range(3, ws.max_row + 1):
        if not ws.cell(row=r, column=1).value:
            break
        row_data = {}
        for c in range(1, cfg.OVERVIEW_NUM_COLS + 1):
            cell = ws.cell(row=r, column=c)
            if cell.value is None:
                continue
            is_numeric = isinstance(cell.value, (int, float)) and not isinstance(cell.value, bool)
            row_data[c] = {
                "value": cell.value,
                "fill": _resolve_fill(cell),
                "font_color": _resolve_font_color(cell),
                "label_type": _has_colored_label(cell),
                "is_numeric": is_numeric,
            }
        if row_data:
            rows.append(row_data)
    return rows


def load_label_rules(wb) -> dict:
    """Read Account Label Definition sheet and return label rules.

    Returns dict mapping label name -> {fill, font_color, definition, note}
    """
    ws = wb[cfg.SHEET_LABEL_DEFINITION]
    rules = {}
    for r in range(3, ws.max_row + 1):
        label_cell = ws.cell(row=r, column=2)
        def_cell = ws.cell(row=r, column=3)
        note_cell = ws.cell(row=r, column=4)
        if not label_cell.value:
            continue
        rules[str(label_cell.value).strip()] = {
            "fill": _resolve_fill(label_cell),
            "font_color": _resolve_font_color(label_cell),
            "definition": def_cell.value,
            "note": note_cell.value,
        }
    return rules


def load_lost_accounts() -> pd.DataFrame:
    df = _load_raw_sheet(cfg.SHEET_LOST_ACCOUNT)
    data = df.iloc[2:].copy()
    data.columns = range(cfg.OVERVIEW_NUM_COLS)
    data = data.rename(columns={
        0: cfg.COL_ACCOUNT, 1: cfg.COL_ACCOUNT_LABEL,
        2: cfg.COL_QTY_2023, 3: cfg.COL_GROWTH_23_24, 4: cfg.COL_QTY_2024,
        5: cfg.COL_GROWTH_24_25, 6: cfg.COL_QTY_2025, 7: cfg.COL_GROWTH_25_26,
        8: cfg.COL_QTY_2026_TOTAL, 9: cfg.COL_QTY_2026_Q1, 10: cfg.COL_QTY_2026_Q2,
        11: cfg.COL_QTY_2026_Q3, 12: cfg.COL_QTY_2026_Q4,
    })
    data = data.dropna(how="all").reset_index(drop=True)
    data = data[data[cfg.COL_ACCOUNT].notna()].reset_index(drop=True)
    data = _coerce_numeric(data, cfg.QTY_COLS)
    data[cfg.COL_QTY_2026_TOTAL] = (
        data[cfg.COL_QTY_2026_Q1] + data[cfg.COL_QTY_2026_Q2]
        + data[cfg.COL_QTY_2026_Q3] + data[cfg.COL_QTY_2026_Q4]
    )
    return data


def load_count() -> pd.DataFrame:
    df = _load_raw_sheet(cfg.SHEET_COUNT)
    data = df.iloc[1:].copy()
    data.columns = ["Label", "0413-0419", "0420-0426", "0427-0503", "0504-0510", "0511-0517", "0518-0531"]
    data = data.dropna(how="all").reset_index(drop=True)
    for c in data.columns[1:]:
        data[c] = pd.to_numeric(data[c], errors="coerce").fillna(0).astype(int)
    return data


def load_account_labels() -> pd.DataFrame:
    df = _load_raw_sheet(cfg.SHEET_LABEL_DEFINITION)
    data = df.iloc[2:].copy()
    data.columns = ["idx", "Label", "Definition", "Note"]
    data = data.dropna(subset=["Label"]).reset_index(drop=True)
    return data[["Label", "Definition", "Note"]]


def load_24y_25n() -> pd.DataFrame:
    df = _load_raw_sheet(cfg.SHEET_24Y_25N)
    data = df.iloc[1:].copy()
    data.columns = range(7)
    data = data.rename(columns={0: "Company", 1: 2024, 2: 2025, 3: 2026, 4: "2025 Carecraft", 5: "email sent", 6: "Date"})
    data = data.dropna(how="all").reset_index(drop=True)
    data = _coerce_numeric(data, [2024, 2025, 2026])
    if "Date" in data.columns:
        data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
    return data


def load_duplicates() -> pd.DataFrame:
    df = _load_raw_sheet(cfg.SHEET_DUPLICATES)
    data = df.copy()
    data.columns = ["Account", "Note"]
    data = data.dropna(subset=["Account"]).reset_index(drop=True)
    return data
