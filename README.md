# Shopify ETL Dashboard

Simple Streamlit ETL app for Shopify sales data. Upload CSV/XLSX files, apply transformation rules, view results, and download.

## Setup

```bash
uv sync
```

## Run

```bash
uv run streamlit run app.py --server.port 8501
```

## Usage

1. Upload a **rules file** (YAML, JSON, or Python) via the sidebar.
2. Upload one or more **data files** (CSV or XLSX).
3. View raw data and transformed result in the app.
4. Download result as CSV or XLSX.

## Rules

Rules are applied sequentially. Supported rule types:

| Type | Description |
|------|-------------|
| `keep_cols` | Keep only specified columns |
| `drop_cols` | Drop specified columns |
| `filter` | Filter rows by column value (eq, neq, gt, gte, lt, lte, contains, in, not_in) |
| `rename` | Rename columns |
| `astype` | Cast column dtype (int, float, bool, str, datetime) |
| `drop_na` | Drop rows with NA in specified columns |
| `fill_na` | Fill NA values |
| `dedup` | Drop duplicate rows |
| `sort` | Sort rows by column |
| `summarize` | Group-by aggregation (sum, mean, count, min, max) |
| `custom_filter` | Call a custom Python function from a module file |
| `fill_from_lookup` | Fill column from same-column lookup grouped by source column |
| `fill_domain` | Fill column from email domain; free email providers use full email |

See `rules_example.yaml` and `rules_shopify.yaml` for examples.

## Project Structure

- `app.py` — Streamlit entry point
- `transform.py` — Rule engine
- `rules.py` — Rules file loader (YAML / JSON / Python)
- `filters.py` — Custom filter functions
- `rules_example.yaml` — Example rules file
- `rules_shopify.yaml` — Shopify-specific rules
