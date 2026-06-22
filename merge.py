"""Merge Data Prep output into Overview dashboard."""

from __future__ import annotations

import pandas as pd

import config as cfg
import overview
from overview import load_overview


def _assign_growth_label(new_qty: int, old_qty: int, prior_qty_1: int, prior_qty_2: int,
                          new_label: str = cfg.LABEL_NEW_26) -> str | float | None:
    """Assign a growth label or compute numeric growth based on qty pattern.

    Rules (derived from original xlsx labeling logic):
      - New label: old=0, new>0, no prior history → new_label
      - Reactivated: old=0, new>0, has prior history → Reactivated
      - Lost: old=0, new=0, has prior history → Lost
      - "/": old=0, new=0, no prior history → "/"
      - Numeric: old>0 → (new - old) / old
    """
    has_prior = (prior_qty_1 > 0) or (prior_qty_2 > 0)

    if old_qty == 0 and new_qty > 0:
        if has_prior:
            return cfg.LABEL_REACTIVATED
        return new_label

    if old_qty == 0 and new_qty == 0:
        if has_prior:
            return cfg.LABEL_LOST
        return cfg.LABEL_SLASH

    if old_qty > 0:
        return (new_qty - old_qty) / old_qty

    return None


def _restore_original_growth(merged: pd.DataFrame, original: pd.DataFrame) -> pd.DataFrame:
    """Restore original growth labels for existing accounts after merge.

    For accounts that existed in the Overview, preserve their original text labels
    (New_24, New_25, New_26, Lost, SOS, Reactivated, /) and only recompute
    25-26 Growth when Data Prep changed Qty_2026_ from 0 to >0.
    """
    # Build lookup of original growth labels by account (use first if duplicates)
    orig_labels = original.drop_duplicates(subset=cfg.COL_ACCOUNT, keep="first").set_index(cfg.COL_ACCOUNT)[cfg.GROWTH_COLS].to_dict("index")

    for i, row in merged.iterrows():
        acct = row[cfg.COL_ACCOUNT]
        if acct not in orig_labels:
            _assign_all_growth_for_new_account(merged, i, row)
            continue

        orig = orig_labels[acct]

        # 23-24 and 24-25 Growth: always preserve (Data Prep doesn't affect past years)
        merged.at[i, cfg.COL_GROWTH_23_24] = orig[cfg.COL_GROWTH_23_24]
        merged.at[i, cfg.COL_GROWTH_24_25] = orig[cfg.COL_GROWTH_24_25]

        # 25-26 Growth: preserve unless Data Prep changed Qty_2026_ from 0 to >0
        orig_25_26 = orig[cfg.COL_GROWTH_25_26]
        orig_q26 = row.get("_orig_Qty_2026_", row[cfg.COL_QTY_2026_TOTAL])
        new_q26 = row[cfg.COL_QTY_2026_TOTAL]

        if orig_q26 == 0 and new_q26 > 0:
            has_prior = (row[cfg.COL_QTY_2023] > 0) or (row[cfg.COL_QTY_2024] > 0) or (row[cfg.COL_QTY_2025] > 0)
            if has_prior:
                merged.at[i, cfg.COL_GROWTH_25_26] = cfg.LABEL_REACTIVATED
            else:
                merged.at[i, cfg.COL_GROWTH_25_26] = cfg.LABEL_NEW_26
        else:
            merged.at[i, cfg.COL_GROWTH_25_26] = orig_25_26

    return merged


def _assign_all_growth_for_new_account(merged: pd.DataFrame, i, row) -> None:
    """Assign growth labels for a new Data Prep-only account (not in original Overview)."""
    q23 = int(row[cfg.COL_QTY_2023])
    q24 = int(row[cfg.COL_QTY_2024])
    q25 = int(row[cfg.COL_QTY_2025])
    q26 = int(row[cfg.COL_QTY_2026_TOTAL])

    merged.at[i, cfg.COL_GROWTH_23_24] = _assign_growth_label(q24, q23, 0, 0, new_label=cfg.LABEL_NEW_24)
    merged.at[i, cfg.COL_GROWTH_24_25] = _assign_growth_label(q25, q24, q23, 0, new_label=cfg.LABEL_NEW_25)
    merged.at[i, cfg.COL_GROWTH_25_26] = _assign_growth_label(q26, q25, q24, q23, new_label=cfg.LABEL_NEW_26)


def _month_to_quarter(month: int) -> int:
    """Map month (1-12) to quarter (1-4)."""
    return (month - 1) // 3 + 1


def _quarter_col(month: int) -> str:
    """Return the Qty_2026_N column name for a given month."""
    return cfg.QUARTER_TO_COL[_month_to_quarter(month)]


def aggregate_etl_by_quarter(etl: pd.DataFrame) -> pd.DataFrame:
    """Aggregate Data Prep result by Billing Company + quarter.

    Returns DataFrame with columns:
      Account, ETL_Q1, ETL_Q2, ETL_Q3, ETL_Q4, ETL_Total
    Only quarters present in the Data Prep data will have non-zero values.
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
    """Merge Overview with Data Prep quarterly data.

    Returns merged DataFrame with:
      Overview columns + ETL_Q1..ETL_Q4 + ETL_Total

    New accounts in Data Prep (not in Overview) are appended as rows with
    Overview columns filled with 0/empty. Original growth labels are preserved.
    """
    ov = load_overview()
    etl_agg = aggregate_etl_by_quarter(etl)

    ov = ov.copy()
    ov["_orig_Qty_2026_"] = ov[cfg.COL_QTY_2026_TOTAL]

    merged = ov.merge(etl_agg, on=cfg.COL_ACCOUNT, how="outer")

    for col in ["ETL_Q1", "ETL_Q2", "ETL_Q3", "ETL_Q4", "ETL_Total"]:
        if col in merged.columns:
            merged[col] = merged[col].fillna(0).astype(int)

    for col in cfg.QTY_COLS + [cfg.COL_QTY_2026_TOTAL]:
        if col in merged.columns:
            merged[col] = merged[col].fillna(0).astype(int)

    merged[cfg.COL_ACCOUNT_LABEL] = merged[cfg.COL_ACCOUNT_LABEL].fillna("")

    merged["_orig_Qty_2026_"] = merged["_orig_Qty_2026_"].fillna(0).astype(int)

    for q_num in range(1, 5):
        etl_q = f"ETL_Q{q_num}"
        pivot_q = cfg.QUARTER_TO_COL[q_num]
        merged[pivot_q] = merged[pivot_q] + merged[etl_q]

    merged[cfg.COL_QTY_2026_TOTAL] = sum(merged[cfg.QUARTER_TO_COL[q]] for q in range(1, 5))

    merged = _restore_original_growth(merged, ov)

    return merged.drop(columns=["_orig_Qty_2026_"], errors="ignore")


def updated_overview_with_etl(etl: pd.DataFrame) -> pd.DataFrame:
    """Return Overview with Data Prep data added to the correct quarter column.

    Orders are grouped by quarter (Jan-Mar → Q1, Apr-Jun → Q2, Jul-Sep → Q3, Oct-Dec → Q4).
    Qty_2026_ = sum of all quarter columns (recomputed).
    Original growth labels are preserved.
    """
    ov = load_overview()
    etl_agg = aggregate_etl_by_quarter(etl)

    ov = ov.copy()
    ov["_orig_Qty_2026_"] = ov[cfg.COL_QTY_2026_TOTAL]

    updated = ov.merge(etl_agg, on=cfg.COL_ACCOUNT, how="outer")

    for q in ["ETL_Q1", "ETL_Q2", "ETL_Q3", "ETL_Q4"]:
        updated[q] = updated[q].fillna(0).astype(int)

    for col in cfg.QTY_COLS + [cfg.COL_QTY_2026_TOTAL]:
        if col in updated.columns:
            updated[col] = updated[col].fillna(0).astype(int)

    updated[cfg.COL_ACCOUNT_LABEL] = updated[cfg.COL_ACCOUNT_LABEL].fillna("")
    updated["_orig_Qty_2026_"] = updated["_orig_Qty_2026_"].fillna(0).astype(int)

    for q_num in range(1, 5):
        updated[cfg.QUARTER_TO_COL[q_num]] += updated[f"ETL_Q{q_num}"]

    updated[cfg.COL_QTY_2026_TOTAL] = sum(updated[cfg.QUARTER_TO_COL[q]] for q in range(1, 5))

    updated = updated.drop(columns=["ETL_Q1", "ETL_Q2", "ETL_Q3", "ETL_Q4", "ETL_Total"], errors="ignore")
    updated = _restore_original_growth(updated, ov)

    return updated.drop(columns=["_orig_Qty_2026_"], errors="ignore")


def compute_count(updated: pd.DataFrame) -> dict:
    """Compute Count tab row values from an updated Overview DataFrame."""
    total = len(df := updated)
    lost = int((df[cfg.COL_GROWTH_25_26] == cfg.LABEL_LOST).sum())
    new_26 = int((df[cfg.COL_GROWTH_25_26] == cfg.LABEL_NEW_26).sum())
    no_purchase = int(((df[cfg.COL_QTY_2026_TOTAL] == 0) & (df[cfg.COL_GROWTH_25_26] != cfg.LABEL_LOST)).sum())
    already = int((df[cfg.COL_QTY_2026_TOTAL] > 0).sum())
    return {
        cfg.COUNT_ROW_LABELS[0]: total,
        cfg.COUNT_ROW_LABELS[1]: lost,
        cfg.COUNT_ROW_LABELS[2]: new_26,
        cfg.COUNT_ROW_LABELS[3]: no_purchase,
        cfg.COUNT_ROW_LABELS[4]: already,
    }


def etl_date_label(etl: pd.DataFrame) -> str:
    """Derive a date range label from Data Prep's Created at column.

    Returns string like '0601-0618' from min/max dates.
    """
    dates = pd.to_datetime(etl["Created at"])
    lo = dates.min()
    hi = dates.max()
    return f"{lo.strftime('%m%d')}-{hi.strftime('%m%d')}"


def add_count_column(wb, label: str, updated: pd.DataFrame) -> None:
    """Append a new column to the Count sheet with updated counts."""
    ws = wb[cfg.SHEET_COUNT]
    new_col = ws.max_column + 1

    ws.cell(row=1, column=new_col, value=label)

    counts = compute_count(updated)
    for i, lbl in enumerate(cfg.COUNT_ROW_LABELS, start=2):
        ws.cell(row=i, column=new_col, value=counts[lbl])


def generate_updated_pivot_xlsx(etl: pd.DataFrame, output_path: str) -> None:
    """Generate a full pivot_table.xlsx with Overview sheet updated from Data Prep data.

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
    ws = wb[cfg.SHEET_OVERVIEW]
    ncols = cfg.OVERVIEW_NUM_COLS

    # Clear old data rows (3 onwards) — keep rows 1-2 (title + header)
    for r in range(3, ws.max_row + 1):
        for c in range(1, ncols + 1):
            ws.cell(row=r, column=c).value = None

    ws.cell(row=1, column=1, value=f"Updated by {date.today().strftime('%m/%d/%Y')}")

    updated = updated_overview_with_etl(etl)

    # Map column names to xlsx positions
    c = cfg.COL_TO_XLSX_IDX

    for idx, row in updated.iterrows():
        r = idx + 3
        ws.cell(row=r, column=c[cfg.COL_ACCOUNT], value=row[cfg.COL_ACCOUNT])
        ws.cell(row=r, column=c[cfg.COL_ACCOUNT_LABEL], value=row[cfg.COL_ACCOUNT_LABEL] if pd.notna(row[cfg.COL_ACCOUNT_LABEL]) else None)
        ws.cell(row=r, column=c[cfg.COL_QTY_2023], value=int(row[cfg.COL_QTY_2023]))

        for gcol in cfg.GROWTH_COLS:
            val = row[gcol]
            if pd.isna(val):
                ws.cell(row=r, column=c[gcol], value=None)
            else:
                ws.cell(row=r, column=c[gcol], value=val)

        ws.cell(row=r, column=c[cfg.COL_QTY_2024], value=int(row[cfg.COL_QTY_2024]))
        ws.cell(row=r, column=c[cfg.COL_QTY_2025], value=int(row[cfg.COL_QTY_2025]))

        # Qty_2026_ = SUM formula
        ws.cell(row=r, column=c[cfg.COL_QTY_2026_TOTAL], value=f"=SUM(J{r}:M{r})")
        ws.cell(row=r, column=c[cfg.COL_QTY_2026_Q1], value=int(row[cfg.COL_QTY_2026_Q1]))
        ws.cell(row=r, column=c[cfg.COL_QTY_2026_Q2], value=int(row[cfg.COL_QTY_2026_Q2]))
        ws.cell(row=r, column=c[cfg.COL_QTY_2026_Q3], value=int(row[cfg.COL_QTY_2026_Q3]))
        ws.cell(row=r, column=c[cfg.COL_QTY_2026_Q4], value=int(row[cfg.COL_QTY_2026_Q4]))

    # Subtotal row
    last_data_row = len(updated) + 2
    sub_row = last_data_row + 1
    ws.cell(row=sub_row, column=c[cfg.COL_QTY_2024], value=f"=SUM(E3:E{last_data_row})")
    ws.cell(row=sub_row, column=c[cfg.COL_QTY_2025], value=f"=SUM(G3:G{last_data_row})")
    ws.cell(row=sub_row, column=c[cfg.COL_QTY_2026_TOTAL], value=f"=SUM(I3:I{last_data_row})")
    ws.cell(row=sub_row, column=c[cfg.COL_QTY_2026_Q1], value=f"=SUM(J3:J{last_data_row})")
    ws.cell(row=sub_row, column=c[cfg.COL_QTY_2026_Q2], value=f"=SUM(K3:K{last_data_row})")

    # Count rows
    ws.cell(row=sub_row + 1, column=c[cfg.COL_QTY_2026_TOTAL], value=f"=COUNTIF(I3:I{last_data_row},0)")
    ws.cell(row=sub_row + 2, column=c[cfg.COL_QTY_2026_TOTAL], value=f"=COUNTIF(I3:I{last_data_row}, \"<>0\")")

    add_count_column(wb, etl_date_label(etl), updated)

    wb.save(output_path)
