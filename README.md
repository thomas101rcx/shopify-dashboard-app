# Shopify Dashboard

Streamlit app for Shopify sales data prep + account overview dashboard. Upload CSV/XLSX sales data, transform via rules, merge into pivot-table-style overview, download updated workbook.

## Setup

```bash
uv sync
```

## Run

```bash
uv run streamlit run app.py --server.port 8501
```

## Pages

### Data Prep
- Upload rules file (YAML/JSON/Python) + data files (CSV/XLSX)
- View raw data and transformed result
- Download result as CSV/XLSX
- Click **"Send to Merge"** to pass result to Merge page

### Overview
- Upload your current `pivot_table.xlsx`
- View all sheets: Overview, Lost Account, Count, 24Y 25N, Account Label Definitions, Duplicate Accounts
- Formulas (growth %, SUM) computed and displayed as values
- Color-coded badges for growth labels (New, Lost, Reactivated)
- Label definitions shown in expander

### Merge
- Upload your `pivot_table.xlsx` + Data Prep output (or use "Send to Merge" from Data Prep page)
- **Side-by-side Merge**: Overview columns + Data Prep quarterly columns (ETL_Q1..ETL_Q4) + ETL_Total
- **Updated Overview**: Data Prep qty added to correct quarter column (by order date), Qty_2026_ recomputed, growth labels preserved
- **Updated Count**: New counts computed from updated Overview, delta vs previous Count column shown
- **Generate Updated Pivot XLSX**: downloads full workbook with:
  - Overview sheet rebuilt (merged data, SUM/COUNTIF formulas, preserved growth labels)
  - Count sheet updated (new snapshot column appended)
  - All other sheets copied as-is

## Merge Logic

### Quarter Mapping
Data Prep orders are grouped by `Created at` month:
- Jan-Mar → Qty_2026_1 (Q1)
- Apr-Jun → Qty_2026_2 (Q2)
- Jul-Sep → Qty_2026_3 (Q3)
- Oct-Dec → Qty_2026_4 (Q4)

Qty_2026_ = sum of all quarter columns (recomputed after merge).

### Growth Labels
Labels preserved from original xlsx. Only recomputed when Data Prep changes Qty_2026_ from 0 → >0:
- **New_26**: old Qty_2026_ = 0, new > 0, no prior history (2023-2025 all 0)
- **Reactivated**: old Qty_2026_ = 0, new > 0, has prior history
- **Lost**: Qty_2026_ = 0, has prior history (preserved from original)
- **SOS**: preserved from original (manually assigned, not auto-computed)
- **"/"**: Qty_2026_ = 0, no prior history (preserved from original)
- **23-24 Growth, 24-25 Growth**: always preserved (Data Prep doesn't affect past years)

### Count Tab
Categories derived from updated Overview:
- Total Account
- Lost
- New_26
- No Purchase 2026 / Not Lost
- Already Purchased 2026

New column appended each time (label = Data Prep date range, e.g. `0601-0618`).

## Rules

Rules are applied sequentially. Supported types:

| Type | Description |
|------|-------------|
| `keep_cols` / `drop_cols` | Column selection |
| `filter` | Row filter (eq, neq, gt, gte, lt, lte, contains, in, not_in) |
| `rename` | Rename columns |
| `astype` | Cast dtype (int, float, bool, str, datetime) |
| `drop_na` / `fill_na` | Null handling |
| `dedup` | Drop duplicates |
| `sort` | Sort rows |
| `summarize` | Group-by aggregation (sum, mean, count, min, max, list) |
| `custom_filter` | Call custom Python function |
| `fill_from_lookup` | Fill column from lookup grouped by source |
| `fill_domain` | Fill from email domain; free providers use full email |

See `rules_example.yaml` and `rules_shopify.yaml`.

## Project Structure

- `app.py` — Streamlit entry, three pages (Data Prep, Overview, Merge)
- `config.py` — All configuration constants (sheet names, column names, colors, labels, etc.)
- `transform.py` — Rule engine
- `rules.py` — Rules file loader (YAML/JSON/Python)
- `filters.py` — Custom filter functions
- `overview.py` — Load and parse pivot_table.xlsx sheets
- `merge.py` — Merge Data Prep output into Overview, generate updated xlsx
- `rules_example.yaml` — Example rules
- `rules_shopify.yaml` — Shopify-specific rules
