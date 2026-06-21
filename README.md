# Shopify Dashboard

Streamlit app for Shopify sales ETL + account overview dashboard. Upload CSV/XLSX sales data, transform via rules, merge into pivot-table-style overview, download updated workbook.

## Setup

```bash
uv sync
```

## Run

```bash
uv run streamlit run app.py --server.port 8501
```

## Pages

### ETL
- Upload rules file (YAML/JSON/Python) + data files (CSV/XLSX)
- View raw data and transformed result
- Download result as CSV/XLSX
- Click **"Send to Merge"** to pass result to Merge page

### Overview
- Upload your current `pivot_table.xlsx`
- View all sheets: Overview, Lost Account, Count, 24Y 25N, Account Label Definitions, Duplicate Accounts
- Formulas (growth %, SUM) computed and displayed as values

### Merge
- Upload your `pivot_table.xlsx` + ETL output
- **Side-by-side Merge**: Overview columns + ETL biweekly columns + Variance
- **Updated Overview**: Qty_2026_2 and Qty_2026_ updated with ETL data
- **Generate Updated Pivot XLSX**: downloads full workbook with merged Overview sheet (other sheets unchanged)

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

- `app.py` — Streamlit entry, three pages (ETL, Overview, Merge)
- `transform.py` — Rule engine
- `rules.py` — Rules file loader (YAML/JSON/Python)
- `filters.py` — Custom filter functions
- `overview.py` — Load and parse pivot_table.xlsx sheets
- `merge.py` — Merge ETL data into Overview, generate updated xlsx
- `rules_example.yaml` — Example rules
- `rules_shopify.yaml` — Shopify-specific rules
