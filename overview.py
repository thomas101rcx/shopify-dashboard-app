"""Load and compute the Shopify Pivot Table overview dashboard."""

from __future__ import annotations

import pandas as pd

PIVOT_PATH = "pivot_table.xlsx"

# Color palette extracted from original xlsx
FILL_COLORS = {
    "FFF2CEEF": "#FFF2CEEF",  # light orange (header background)
    "FFFFFF00": "#FFFF00",  # yellow (New labels)
    "FFFF0000": "#FF0000",  # red (Lost labels)
    "FF92D050": "#92D050",  # green (Reactivated)
}
FONT_COLORS = {
    "FF000000": "#000000",
    "FFFF0000": "#FF0000",
    "FF303030": "#303030",
}


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
        return FILL_COLORS.get(rgb, f"#{rgb}")
    return None


def _resolve_font_color(cell) -> str | None:
    if not cell.font or not cell.font.color:
        return None
    rgb = cell.font.color.rgb
    if rgb and rgb != "00000000" and not str(rgb).startswith("Values"):
        return FONT_COLORS.get(rgb, f"#{rgb}")
    return None


def _has_colored_label(cell) -> str | None:
    """Return label type based on cell fill color."""
    if not cell.fill or not cell.fill.fgColor:
        return None
    rgb = cell.fill.fgColor.rgb
    if str(rgb) == "FFFFFF00":
        return "new"
    if str(rgb) == "FFFF0000":
        return "lost"
    if str(rgb) == "FF92D050":
        return "reactivated"
    return None


def load_overview() -> pd.DataFrame:
    """Load Overview sheet with computed 2026 YTD and growth."""
    df = _load_raw_sheet("Overview")
    data = df.iloc[2:].copy()
    data.columns = range(13)
    data = data.rename(columns={
        0: "Account", 1: "Account Label",
        2: "Qty_2023", 3: "23-24 Growth", 4: "Qty_2024",
        5: "24-25 Growth", 6: "Qty_2025", 7: "25-26 Growth",
        8: "Qty_2026_", 9: "Qty_2026_1", 10: "Qty_2026_2",
        11: "Qty_2026_3", 12: "Qty_2026_4",
    })
    data = data.dropna(how="all").reset_index(drop=True)
    # Stop before subtotal row (row 412 = index 410)
    data = data[data["Account"].notna()].reset_index(drop=True)

    numeric_cols = ["Qty_2023", "Qty_2024", "Qty_2025",
                    "Qty_2026_1", "Qty_2026_2", "Qty_2026_3", "Qty_2026_4"]
    data = _coerce_numeric(data, numeric_cols)

    data["Qty_2026_"] = (
        data["Qty_2026_1"] + data["Qty_2026_2"] + data["Qty_2026_3"] + data["Qty_2026_4"]
    )

    data["23-24 Growth"] = data.apply(
        lambda r: _growth(r["Qty_2024"], r["Qty_2023"]) if r["Qty_2023"] > 0 else None, axis=1
    )
    data["24-25 Growth"] = data.apply(
        lambda r: _growth(r["Qty_2025"], r["Qty_2024"]) if r["Qty_2024"] > 0 else None, axis=1
    )
    data["25-26 Growth"] = data.apply(
        lambda r: _growth(r["Qty_2026_"], r["Qty_2025"]) if r["Qty_2025"] > 0 else None, axis=1
    )

    return data


def load_overview_styled() -> list[dict]:
    """Return per-cell style info for the Overview sheet."""
    df = _load_raw_sheet("Overview")
    rows = []
    for r_idx in range(3, len(df) + 1):
        row_data = {}
        for c_idx in range(1, 18):
            cell = df.cell(row=r_idx, column=c_idx)
            if cell.value is None:
                continue
            row_data[c_idx] = {
                "value": cell.value,
                "bold": cell.font.bold if cell.font else False,
                "fill": _resolve_fill(cell),
                "font_color": _resolve_font_color(cell),
                "label_type": _has_colored_label(cell),
            }
        if row_data:
            rows.append(row_data)
    # drop subtotal row
    rows = [r for r in rows if not (isinstance(r.get(9, {}).get("value"), str) and r[9]["value"].startswith("="))]
    return rows


def load_lost_accounts() -> pd.DataFrame:
    df = _load_raw_sheet("Lost Account ")
    data = df.iloc[2:].copy()
    data.columns = range(13)
    data = data.rename(columns={
        0: "Account", 1: "Account Label",
        2: "Qty_2023", 3: "23-24 Growth", 4: "Qty_2024",
        5: "24-25 Growth", 6: "Qty_2025", 7: "25-26 Growth",
        8: "Qty_2026_", 9: "Qty_2026_1", 10: "Qty_2026_2",
        11: "Qty_2026_3", 12: "Qty_2026_4",
    })
    data = data.dropna(how="all").reset_index(drop=True)
    data = data[data["Account"].notna()].reset_index(drop=True)
    data = _coerce_numeric(data, ["Qty_2023", "Qty_2024", "Qty_2025", "Qty_2026_1", "Qty_2026_2", "Qty_2026_3", "Qty_2026_4"])
    data["Qty_2026_"] = data["Qty_2026_1"] + data["Qty_2026_2"] + data["Qty_2026_3"] + data["Qty_2026_4"]
    return data


def load_count() -> pd.DataFrame:
    df = _load_raw_sheet("Count")
    data = df.iloc[1:].copy()
    data.columns = ["Label", "0413-0419", "0420-0426", "0427-0503", "0504-0510", "0511-0517", "0518-0531"]
    data = data.dropna(how="all").reset_index(drop=True)
    for c in data.columns[1:]:
        data[c] = pd.to_numeric(data[c], errors="coerce").fillna(0).astype(int)
    return data


def load_account_labels() -> pd.DataFrame:
    df = _load_raw_sheet("Account Label Definition ")
    data = df.iloc[2:].copy()
    data.columns = ["idx", "Label", "Definition", "Note"]
    data = data.dropna(subset=["Label"]).reset_index(drop=True)
    return data[["Label", "Definition", "Note"]]


def load_24y_25n() -> pd.DataFrame:
    df = _load_raw_sheet("24Y 25N")
    data = df.iloc[1:].copy()
    data.columns = range(7)
    data = data.rename(columns={0: "Company", 1: 2024, 2: 2025, 3: 2026, 4: "2025 Carecraft", 5: "email sent", 6: "Date"})
    data = data.dropna(how="all").reset_index(drop=True)
    data = _coerce_numeric(data, [2024, 2025, 2026])
    if "Date" in data.columns:
        data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
    return data


def load_duplicates() -> pd.DataFrame:
    df = _load_raw_sheet("Dupilicate Accounts ")
    data = df.copy()
    data.columns = ["Account", "Note"]
    data = data.dropna(subset=["Account"]).reset_index(drop=True)
    return data
