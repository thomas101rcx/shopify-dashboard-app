"""Merge ETL output into Overview dashboard."""

from __future__ import annotations

import pandas as pd

import overview
from overview import load_overview

# Quarter -> column mapping
QUARTER_COL = {1: "Qty_2026_1", 2: "Qty_2026_2", 3: "Qty_2026_3", 4: "Qty_2026_4"}

GROWTH_COLS = ["23-24 Growth", "24-25 Growth", "25-26 Growth"]


def _assign_growth_label(new_qty: int, old_qty: int, prior_qty_1: int, prior_qty_2: int,
                          new_label: str = "New_26") -> str | float | None:
    """Assign a growth label or compute numeric growth based on qty pattern.

    Rules (derived from original xlsx labeling logic):
      - New label: old=0, new>0, no prior history → new_label (e.g. "New_24", "New_25", "New_26")
      - Reactivated: old=0, new>0, has prior history → "Reactivated"
      - Lost: old=0, new=0, has prior history → "Lost"
      - "/": old=0, new=0, no prior history → "/"
      - Numeric: old>0 → (new - old) / old

    For 23-24 Growth: prior_qty_1 and prior_qty_2 are unused (no earlier years).
    For 24-25 Growth: prior_qty_1 = Qty_2023, prior_qty_2 unused.
    For 25-26 Growth: prior_qty_1 = Qty_2024, prior_qty_2 = Qty_2023.
    """
    has_prior = (prior_qty_1 > 0) or (prior_qty_2 > 0)

    if old_qty == 0 and new_qty > 0:
        if has_prior:
            return "Reactivated"
        return new_label

    if old_qty == 0 and new_qty == 0:
        if has_prior:
            return "Lost"
        return "/"

    if old_qty > 0:
        return (new_qty - old_qty) / old_qty

    return None


def _restore_original_growth(merged: pd.DataFrame, original: pd.DataFrame) -> pd.DataFrame:
    """Restore original growth labels for existing accounts after merge.

    For accounts that existed in the Overview, preserve their original text labels
    (New_24, New_25, New_26, Lost, SOS, Reactivated, /) and only recompute
    25-26 Growth when ETL changed Qty_2026_ from 0 to >0.
    """
    # Build lookup of original growth labels by account (use first if duplicates)
    orig_labels = original.drop_duplicates(subset="Account", keep="first").set_index("Account")[GROWTH_COLS].to_dict("index")

    for i, row in merged.iterrows():
        acct = row["Account"]
        if acct not in orig_labels:
            # New ETL-only account — assign labels from scratch
            _assign_all_growth_for_new_account(merged, i, row)
            continue

        orig = orig_labels[acct]

        # 23-24 and 24-25 Growth: always preserve (ETL doesn't affect past years)
        merged.at[i, "23-24 Growth"] = orig["23-24 Growth"]
        merged.at[i, "24-25 Growth"] = orig["24-25 Growth"]

        # 25-26 Growth: preserve unless ETL changed Qty_2026_ from 0 to >0
        orig_25_26 = orig["25-26 Growth"]
        orig_q26 = row.get("_orig_Qty_2026_", row["Qty_2026_"])  # original Q26 before merge
        new_q26 = row["Qty_2026_"]

        if orig_q26 == 0 and new_q26 > 0:
            # ETL added purchases where there were none — recompute label
            has_prior = (row["Qty_2023"] > 0) or (row["Qty_2024"] > 0) or (row["Qty_2025"] > 0)
            if has_prior:
                merged.at[i, "25-26 Growth"] = "Reactivated"
            else:
                merged.at[i, "25-26 Growth"] = "New_26"
        else:
            # Preserve original label (Lost, SOS, numeric, etc.)
            merged.at[i, "25-26 Growth"] = orig_25_26

    return merged


def _assign_all_growth_for_new_account(merged: pd.DataFrame, i, row) -> None:
    """Assign growth labels for a new ETL-only account (not in original Overview)."""
    q23, q24, q25, q26 = int(row["Qty_2023"]), int(row["Qty_2024"]), int(row["Qty_2025"]), int(row["Qty_2026_"])

    # 23-24 Growth
    merged.at[i, "23-24 Growth"] = _assign_growth_label(q24, q23, 0, 0, new_label="New_24")
    # 24-25 Growth
    merged.at[i, "24-25 Growth"] = _assign_growth_label(q25, q24, q23, 0, new_label="New_25")
    # 25-26 Growth
    merged.at[i, "25-26 Growth"] = _assign_growth_label(q26, q25, q24, q23, new_label="New_26")


def _month_to_quarter(month: int) -> int:
    """Map month (1-12) to quarter (1-4)."""
    return (month - 1) // 3 + 1


def _quarter_col(month: int) -> str:
    """Return the Qty_2026_N column name for a given month."""
    return QUARTER_COL[_month_to_quarter(month)]


def aggregate_etl_by_quarter(etl: pd.DataFrame) -> pd.DataFrame:
    """Aggregate ETL result by Billing Company + quarter.

    Returns DataFrame with columns:
      Account, ETL_Q1, ETL_Q2, ETL_Q3, ETL_Q4, ETL_Total
    Only quarters present in the ETL data will have non-zero values.
    """
    if etl.empty:
        return pd.DataFrame(columns=["Account", "ETL_Q1", "ETL_Q2", "ETL_Q3", "ETL_Q4", "ETL_Total"])

    df = etl.copy()
    df["Created at"] = pd.to_datetime(df["Created at"])
    df["quarter"] = df["Created at"].dt.month.apply(lambda m: f"ETL_Q{_month_to_quarter(m)}")

    qty_col = "Sum of Lineitem quantity" if "Sum of Lineitem quantity" in df.columns else "Lineitem quantity"
    pivot = df.pivot_table(
        index="Billing Company",
        columns="quarter",
        values=qty_col,
        aggfunc="sum",
        fill_value=0,
    ).reset_index()

    # Ensure all quarter columns exist
    for q in ["ETL_Q1", "ETL_Q2", "ETL_Q3", "ETL_Q4"]:
        if q not in pivot.columns:
            pivot[q] = 0

    pivot["ETL_Total"] = pivot["ETL_Q1"] + pivot["ETL_Q2"] + pivot["ETL_Q3"] + pivot["ETL_Q4"]
    pivot = pivot.rename(columns={"Billing Company": "Account"})
    return pivot[["Account", "ETL_Q1", "ETL_Q2", "ETL_Q3", "ETL_Q4", "ETL_Total"]]


def merge_overview_with_etl(etl: pd.DataFrame) -> pd.DataFrame:
    """Merge Overview with ETL quarterly data.

    Returns merged DataFrame with:
      Overview columns + ETL_Q1..ETL_Q4 + ETL_Total

    New accounts in ETL (not in Overview) are appended as rows with
    Overview columns filled with 0/empty. Original growth labels are preserved.
    """
    ov = load_overview()
    etl_agg = aggregate_etl_by_quarter(etl)

    # Store original Qty_2026_ before merge for label logic
    ov = ov.copy()
    ov["_orig_Qty_2026_"] = ov["Qty_2026_"]

    merged = ov.merge(etl_agg, on="Account", how="outer")

    # Fill NaN ETL columns with 0
    for col in ["ETL_Q1", "ETL_Q2", "ETL_Q3", "ETL_Q4", "ETL_Total"]:
        if col in merged.columns:
            merged[col] = merged[col].fillna(0).astype(int)

    # Fill NaN Overview numeric columns with 0 (new ETL-only accounts)
    for col in ["Qty_2023", "Qty_2024", "Qty_2025", "Qty_2026_",
                "Qty_2026_1", "Qty_2026_2", "Qty_2026_3", "Qty_2026_4"]:
        if col in merged.columns:
            merged[col] = merged[col].fillna(0).astype(int)

    # Fill NaN text columns
    for col in ["Account Label"]:
        if col in merged.columns:
            merged[col] = merged[col].fillna("")

    merged["_orig_Qty_2026_"] = merged["_orig_Qty_2026_"].fillna(0).astype(int)

    # Add ETL qty to correct quarter columns
    for q_num in range(1, 5):
        etl_q = f"ETL_Q{q_num}"
        pivot_q = f"Qty_2026_{q_num}"
        merged[pivot_q] = merged[pivot_q] + merged[etl_q]

    merged["Qty_2026_"] = (
        merged["Qty_2026_1"] + merged["Qty_2026_2"]
        + merged["Qty_2026_3"] + merged["Qty_2026_4"]
    )

    # Restore growth labels (preserve original, recompute only when needed)
    merged = _restore_original_growth(merged, ov)

    # Drop helper columns
    merged = merged.drop(columns=["_orig_Qty_2026_"], errors="ignore")

    return merged


def updated_overview_with_etl(etl: pd.DataFrame) -> pd.DataFrame:
    """Return Overview with ETL data added to the correct quarter column.

    ETL orders are grouped by quarter (Jan-Mar -> Qty_2026_1, Apr-Jun -> Qty_2026_2,
    Jul-Sep -> Qty_2026_3, Oct-Dec -> Qty_2026_4).
    Qty_2026_ = Qty_2026_1 + Qty_2026_2 + Qty_2026_3 + Qty_2026_4 (recomputed).

    New accounts in ETL (not in Overview) are appended with ETL qty in the
    correct quarter column. Original growth labels are preserved.
    """
    ov = load_overview()
    etl_agg = aggregate_etl_by_quarter(etl)

    # Store original Qty_2026_ before merge for label logic
    ov = ov.copy()
    ov["_orig_Qty_2026_"] = ov["Qty_2026_"]

    updated = ov.merge(etl_agg, on="Account", how="outer")

    # Fill NaN ETL quarter columns with 0
    for q in ["ETL_Q1", "ETL_Q2", "ETL_Q3", "ETL_Q4"]:
        updated[q] = updated[q].fillna(0).astype(int)

    # Fill NaN Overview numeric columns with 0 (new ETL-only accounts)
    for col in ["Qty_2023", "Qty_2024", "Qty_2025", "Qty_2026_",
                "Qty_2026_1", "Qty_2026_2", "Qty_2026_3", "Qty_2026_4"]:
        if col in updated.columns:
            updated[col] = updated[col].fillna(0).astype(int)

    # Fill NaN text columns
    for col in ["Account Label"]:
        if col in updated.columns:
            updated[col] = updated[col].fillna("")

    updated["_orig_Qty_2026_"] = updated["_orig_Qty_2026_"].fillna(0).astype(int)

    # Add ETL qty to the correct quarter column
    for q_num in range(1, 5):
        etl_q = f"ETL_Q{q_num}"
        pivot_q = f"Qty_2026_{q_num}"
        updated[pivot_q] = updated[pivot_q] + updated[etl_q]

    # Recompute Qty_2026_ = sum of all quarter columns
    updated["Qty_2026_"] = (
        updated["Qty_2026_1"] + updated["Qty_2026_2"]
        + updated["Qty_2026_3"] + updated["Qty_2026_4"]
    )

    # Drop helper ETL columns
    updated = updated.drop(columns=["ETL_Q1", "ETL_Q2", "ETL_Q3", "ETL_Q4", "ETL_Total"], errors="ignore")

    # Restore growth labels (preserve original, recompute only when needed)
    updated = _restore_original_growth(updated, ov)

    # Drop helper columns
    updated = updated.drop(columns=["_orig_Qty_2026_"], errors="ignore")

    return updated


def compute_count(updated: pd.DataFrame) -> dict:
    """Compute Count tab row values from an updated Overview DataFrame.

    Returns dict:
      {"Total Account": int, "Lost": int, "New_26": int,
       "No Purchase 2026 / Not Lost": int, "Already Purchased 2026": int}
    """
    total = len(df := updated)
    lost = int((df["25-26 Growth"] == "Lost").sum())
    new_26 = int((df["25-26 Growth"] == "New_26").sum())
    no_purchase = int(((df["Qty_2026_"] == 0) & (df["25-26 Growth"] != "Lost")).sum())
    already = int((df["Qty_2026_"] > 0).sum())
    return {
        "Total Account": total,
        "Lost": lost,
        "New_26": new_26,
        "No Purchase 2026 / Not Lost": no_purchase,
        "Already Purchased 2026": already,
    }


def etl_date_label(etl: pd.DataFrame) -> str:
    """Derive a date range label from ETL's Created at column.

    Returns string like '0601-0618' from min/max dates.
    """
    dates = pd.to_datetime(etl["Created at"])
    lo = dates.min()
    hi = dates.max()
    return f"{lo.strftime('%m%d')}-{hi.strftime('%m%d')}"


def add_count_column(wb, label: str, updated: pd.DataFrame) -> None:
    """Append a new column to the Count sheet with updated counts.

    wb: openpyxl workbook (already loaded)
    label: date range string for the column header (e.g. '0601-0618')
    updated: post-merge Overview DataFrame
    """
    ws = wb["Count"]
    new_col = ws.max_column + 1

    # Header
    ws.cell(row=1, column=new_col, value=label)

    # Data rows
    counts = compute_count(updated)
    row_labels = ["Total Account", "Lost", "New_26",
                  "No Purchase 2026 / Not Lost", "Already Purchased 2026"]
    for i, lbl in enumerate(row_labels, start=2):
        ws.cell(row=i, column=new_col, value=counts[lbl])


def generate_updated_pivot_xlsx(etl: pd.DataFrame, output_path: str) -> None:
    """Generate a full pivot_table.xlsx with Overview sheet updated from ETL data.

    Other sheets are copied as-is. Overview sheet is rebuilt with:
      - Row 1: Updated by date
      - Row 2: Headers
      - Row 3+: Account data with formulas preserved
      - Subtotal row: SUM / COUNTIF formulas
    """
    import shutil
    from datetime import date
    from openpyxl import load_workbook

    src = overview.PIVOT_PATH
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

    # Append new column to Count tab
    add_count_column(wb, etl_date_label(etl), updated)

    wb.save(output_path)
