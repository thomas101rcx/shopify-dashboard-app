# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working in this repository.

## Commands

```bash
uv sync                              # install deps
uv run streamlit run app.py --server.port 8501   # run app
uv run python -c "..."               # run Python snippet
```

## Architecture

Three-page Streamlit app: **Data Prep** → **Overview** → **Merge**.

**Data Prep** (`app.py` + `transform.py` + `rules.py` + `filters.py`):
- Upload CSV/XLSX + rules file → transform → view/download result
- Rules applied sequentially, each `df → df`
- `custom_filter` rule type loads Python function via `_load_func()`
- Excel engine priority: calamine → openpyxl → default (calamine required for non-standard xlsx)
- "Send to Merge" button stores result in `st.session_state["etl_result"]`

**Overview** (`overview.py`):
- User uploads their own `pivot_table.xlsx` (not bundled)
- Reads all sheets: Overview, Lost Account, Count, 24Y 25N, Account Label Definitions, Duplicate Accounts
- Computes formula cells (growth %, SUM) as numeric values at load time
- Preserves text labels in growth columns (New_24, Lost, SOS, etc.)
- Renders HTML table with color-coded badges for label types
- `PIVOT_PATH` module-level var — Merge page overrides to point at user-uploaded file

**Merge** (`merge.py`):
- User uploads `pivot_table.xlsx` + Data Prep output
- `aggregate_etl_by_quarter(etl)`: groups Data Prep output by Billing Company + quarter from `Created at` month
- `merge_overview_with_etl()`: side-by-side view with ETL_Q1..ETL_Q4 columns
- `updated_overview_with_etl()`: Data Prep qty added to correct quarter, Qty_2026_ recomputed
- Growth labels preserved via `_restore_original_growth()` — only 25-26 recomputed when Data Prep changes Q26 from 0→>0
- `compute_count(updated)`: derives Count categories from updated Overview
- `etl_date_label(etl)`: derives 'MMDD-MMDD' label from Data Prep min/max dates
- `add_count_column(wb, label, updated)`: appends new column to Count sheet
- `generate_updated_pivot_xlsx(etl, output_path)`: copies original xlsx, rebuilds Overview sheet (data + SUM/COUNTIF formulas), appends Count column, saves

**Config** (`config.py`):
- Single source of truth for all hardcoded values
- Sheet names, column names, growth labels, color mappings, badge styles, quarter-to-column mapping, Excel engine priority

## Key Design Decisions

- Rules applied sequentially, order matters. `fill_from_lookup` before `fill_domain`.
- `fill_domain` has `free_domains` list — these use full email as group key (not domain).
- `summarize` with `list` agg uses lambda (pandas doesn't support `"list"` string).
- Overview sheet: row 1 = date, row 2 = headers, row 3+ = data, last rows = SUM/COUNTIF formulas.
- Data Prep quarter mapping: month → Qty_2026_1..4, then Qty_2026_ = SUM(Q1..Q4).
- Growth labels: preserve original text labels, only recompute 25-26 when Data Prep changes Qty_2026_ from 0→>0.
- SOS labels: not auto-assigned (manually set via red font color `FFFF0000`), preserved from original.
- Count tab: categories derived from Overview data, new column appended per merge (never overwritten).
- All config constants in `cfg.*` — no hardcoded strings in business logic.

## Gotchas

- `pd.read_excel()` without `sheet_name` returns dict for multi-sheet. `_read_excel()` handles.
- Column names are case-sensitive: `Billing Company` (capital C).
- Streamlit reruns whole script on any widget change — session_state persists across reruns.
- Non-standard xlsx (conformance="strict", missing sheet ids) requires calamine engine.
- Growth columns in Lost Account sheet have mixed types (floats + strings like "SOS", "Lost", "New_24") — format only numeric values as %.
- Count sheet: row labels in col A, not in header. Lost row = red bg, New_26 row = yellow bg (label cell only, not entire row).
- Overview may have duplicate account names — `drop_duplicates(subset=cfg.COL_ACCOUNT, keep="first")` before `set_index()`.
- `load_overview_styled()` takes a workbook object (not path) — call `load_workbook()` first.
- Sheet names have trailing spaces: `"Lost Account "`, `"Account Label Definition "`, `"Dupilicate Accounts "`.
