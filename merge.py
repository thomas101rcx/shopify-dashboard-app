"""Merge ETL output into Overview dashboard."""

from __future__ import annotations

import pandas as pd

from overview import load_overview

# Biweekly buckets for June 2026 (ETL period: 0601-0618)
BIWEEKLY_BUCKETS = [
    ("Qty_2026_1", "0601-0607", "2026-06-01", "2026-06-07"),
    ("Qty_2026_2", "0608-0614", "2026-06-08", "2026-06-14"),
    ("Qty_2026_3", "0615-0621", "2026-06-15", "2026-06-21"),
    ("Qty_2026_4", "0622-0628", "2026-06-22", "2026-06-28"),
]


def _empty_weekly_df(accounts: list[str]) -> pd.DataFrame:
    return pd.DataFrame({
        "Account": accounts,
        "ETL_0601-0607": 0,
        "ETL_0608-0614": 0,
        "ETL_0615-0621": 0,
        "ETL_0622-0628": 0,
        "ETL_Total": 0,
    })


def aggregate_etl_by_biweekly(etl: pd.DataFrame) -> pd.DataFrame:
    """Aggregate ETL result by Billing Company + biweekly bucket.

    Returns DataFrame with columns:
      Account, ETL_0601-0607, ETL_0608-0614, ETL_0615-0621, ETL_0622-0628, ETL_Total
    """
    if etl.empty:
        return _empty_weekly_df([])

    df = etl.copy()
    df["Created at"] = pd.to_datetime(df["Created at"])

    def _bucket(dt):
        day = dt.day
        if day <= 7:
            return "ETL_0601-0607"
        if day <= 14:
            return "ETL_0608-0614"
        if day <= 21:
            return "ETL_0615-0621"
        return "ETL_0622-0628"

    df["bucket"] = df["Created at"].apply(_bucket)
    pivot = df.pivot_table(
        index="Billing Company",
        columns="bucket",
        values="Lineitem quantity",
        aggfunc="sum",
        fill_value=0,
    ).reset_index()

    # Ensure all bucket columns exist
    for col in ["ETL_0601-0607", "ETL_0608-0614", "ETL_0615-0621", "ETL_0622-0628"]:
        if col not in pivot.columns:
            pivot[col] = 0

    pivot["ETL_Total"] = (
        pivot["ETL_0601-0607"] + pivot["ETL_0608-0614"]
        + pivot["ETL_0615-0621"] + pivot["ETL_0622-0628"]
    )
    pivot = pivot.rename(columns={"Billing Company": "Account"})
    return pivot[
        ["Account", "ETL_0601-0607", "ETL_0608-0614", "ETL_0615-0621", "ETL_0622-0628", "ETL_Total"]
    ]


def merge_overview_with_etl(etl: pd.DataFrame) -> pd.DataFrame:
    """Merge Overview with ETL biweekly data.

    Returns merged DataFrame with:
      Overview columns + ETL biweekly columns + Variance
    """
    overview = load_overview()
    etl_agg = aggregate_etl_by_biweekly(etl)

    merged = overview.merge(etl_agg, on="Account", how="left")

    # Fill NaN ETL columns with 0
    for col in ["ETL_0601-0607", "ETL_0608-0614", "ETL_0615-0621", "ETL_0622-0628", "ETL_Total"]:
        if col in merged.columns:
            merged[col] = merged[col].fillna(0).astype(int)

    # Variance: ETL_Total - Qty_2026_ (existing)
    merged["Variance"] = merged["ETL_Total"] - merged["Qty_2026_"]

    return merged


def updated_overview_with_etl(etl: pd.DataFrame) -> pd.DataFrame:
    """Return Overview with ETL data added to Qty_2026_2 and Qty_2026_.

    Qty_2026_2 = existing Qty_2026_2 + ETL biweekly totals (0601-0618 falls in Q2).
    Qty_2026_ = Qty_2026_1 + Qty_2026_2 + Qty_2026_3 + Qty_2026_4.
    """
    overview = load_overview()
    etl_agg = aggregate_etl_by_biweekly(etl)

    # ETL 0601-0618 maps to Q2 (Qty_2026_2)
    etl_for_q2 = etl_agg[["Account", "ETL_Total"]].rename(columns={"ETL_Total": "ETL_Q2"})

    updated = overview.merge(etl_for_q2, on="Account", how="left")
    updated["ETL_Q2"] = updated["ETL_Q2"].fillna(0).astype(int)
    updated["Qty_2026_2"] = updated["Qty_2026_2"] + updated["ETL_Q2"]
    updated["Qty_2026_"] = (
        updated["Qty_2026_1"] + updated["Qty_2026_2"]
        + updated["Qty_2026_3"] + updated["Qty_2026_4"]
    )
    updated = updated.drop(columns=["ETL_Q2"])

    return updated


def generate_updated_pivot_xlsx(etl: pd.DataFrame, output_path: str) -> None:
    """Generate a full pivot_table.xlsx with Overview sheet updated from ETL data.

    Other sheets are copied as-is. Overview sheet is rebuilt with:
      - Row 1: Updated by date
      - Row 2: Headers
      - Row 3+: Account data with formulas preserved
      - Subtotal row: SUM / COUNTIF formulas
    """
    import shutil
    from copy import copy
    from datetime import date
    from openpyxl import load_workbook
    from openpyxl.utils import get_column_letter

    src = "pivot_table.xlsx"
    shutil.copy(src, output_path)

    wb = load_workbook(output_path)
    ws = wb["Overview"]

    # Clear old data rows (3 onwards) — keep rows 1-2 (title + header)
    for r in range(3, ws.max_row + 1):
        for c in range(1, 14):
            ws.cell(row=r, column=c).value = None

    # Row 1: updated date
    ws.cell(row=1, column=1).value = f"Updated by {date.today().strftime('%m/%d/%Y')}"

    # Build updated overview
    updated = updated_overview_with_etl(etl)

    # Write data rows
    for idx, row in updated.iterrows():
        r = idx + 3
        ws.cell(row=r, column=1, value=row["Account"])
        ws.cell(row=r, column=2, value=row["Account Label"] if pd.notna(row["Account Label"]) else None)
        ws.cell(row=r, column=3, value=int(row["Qty_2023"]))

        # 23-24 Growth: formula or label
        g_23_24 = row["23-24 Growth"]
        if pd.isna(g_23_24):
            ws.cell(row=r, column=4, value=None)
        elif isinstance(g_23_24, (int, float)):
            ws.cell(row=r, column=4, value=g_23_24)
        else:
            ws.cell(row=r, column=4, value=g_23_24)

        ws.cell(row=r, column=5, value=int(row["Qty_2024"]))

        g_24_25 = row["24-25 Growth"]
        if pd.isna(g_24_25):
            ws.cell(row=r, column=6, value=None)
        elif isinstance(g_24_25, (int, float)):
            ws.cell(row=r, column=6, value=g_24_25)
        else:
            ws.cell(row=r, column=6, value=g_24_25)

        ws.cell(row=r, column=7, value=int(row["Qty_2025"]))

        # 25-26 Growth
        g_25_26 = row["25-26 Growth"]
        if pd.isna(g_25_26):
            ws.cell(row=r, column=8, value=None)
        elif isinstance(g_25_26, (int, float)):
            ws.cell(row=r, column=8, value=g_25_26)
        else:
            ws.cell(row=r, column=8, value=g_25_26)

        # Qty_2026_ = SUM of week columns (formula)
        ws.cell(row=r, column=9, value=f"=SUM(J{r}:M{r})")
        ws.cell(row=r, column=10, value=int(row["Qty_2026_1"]))
        ws.cell(row=r, column=11, value=int(row["Qty_2026_2"]))
        ws.cell(row=r, column=12, value=int(row["Qty_2026_3"]))
        ws.cell(row=r, column=13, value=int(row["Qty_2026_4"]))

    # Subtotal row
    last_data_row = len(updated) + 2  # +2 because data starts at row 3
    sub_row = last_data_row + 1
    ws.cell(row=sub_row, column=5, value=f"=SUM(E3:E{last_data_row})")
    ws.cell(row=sub_row, column=7, value=f"=SUM(G3:G{last_data_row})")
    ws.cell(row=sub_row, column=9, value=f"=SUM(I3:I{last_data_row})")
    ws.cell(row=sub_row, column=10, value=f"=SUM(J3:J{last_data_row})")
    ws.cell(row=sub_row, column=11, value=f"=SUM(K3:K{last_data_row})")

    # Count rows
    ws.cell(row=sub_row + 1, column=9, value=f"=COUNTIF(I3:I{last_data_row},0)")
    ws.cell(row=sub_row + 2, column=9, value=f"=COUNTIF(I3:I{last_data_row}, \"<>0\")")

    wb.save(output_path)
