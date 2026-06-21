# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv sync                              # install deps
uv run streamlit run app.py --server.port 8501   # run app
uv run python -c "..."               # run Python snippet
```

## Architecture

Three-page Streamlit app: **ETL** → **Overview** → **Merge**.

**ETL** (`app.py` + `transform.py` + `rules.py` + `filters.py`):
- Upload CSV/XLSX + rules file → transform → view/download result
- Rules applied sequentially, each `df → df`
- `custom_filter` rule type loads Python function via `_load_func()`
- Excel engine priority: calamine → openpyxl → default (calamine required for non-standard xlsx)
- "Send to Merge" button stores result in `st.session_state["etl_result"]`

**Overview** (`overview.py`):
- User uploads their own `pivot_table.xlsx` (not bundled)
- Reads all sheets: Overview, Lost Account, Count, 24Y 25N, Account Label Definitions, Duplicate Accounts
- Computes formula cells (growth %, SUM) as numeric values at load time
- `PIVOT_PATH` module-level var — Merge page overrides to point at user-uploaded file

**Merge** (`merge.py`):
- User uploads `pivot_table.xlsx` + ETL output
- `merge_overview_with_etl()`: side-by-side view with ETL biweekly columns + Variance
- `updated_overview_with_etl()`: Qty_2026_2 += ETL total, Qty_2026_ recomputed
- `generate_updated_pivot_xlsx()`: full xlsx with updated Overview sheet, other sheets copied as-is

## Key Design Decisions

- Rules applied sequentially, order matters. `fill_from_lookup` before `fill_domain`.
- `fill_domain` has `free_domains` list — these use full email as group key (not domain).
- `summarize` with `list` agg uses lambda (pandas doesn't support `"list"` string).
- Overview sheet: row 1 = date, row 2 = headers, row 3+ = data, last rows = SUM/COUNTIF formulas.
- ETL biweekly data (0601-0618) maps to Qty_2026_2 (Q2 column) in the Overview.

## Gotchas

- `pd.read_excel()` without `sheet_name` returns dict for multi-sheet. `_read_excel()` handles.
- Column names are case-sensitive: `Billing Company` (capital C).
- Streamlit reruns whole script on any widget change — session_state persists across reruns.
- Non-standard xlsx (conformance="strict", missing sheet ids) requires calamine engine.
- Growth columns in Lost Account sheet have mixed types (floats + strings like "SOS", "Lost", "New_24") — format only numeric values as %.
- Count sheet: row labels in col A, not in header. Lost row = red bg, New_26 row = yellow bg (label cell only, not entire row).
