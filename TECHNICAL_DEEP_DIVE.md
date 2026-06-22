# Technical Deep Dive — Shopify Sales Dashboard

## 1. Software Stack

| Layer | Technology | Version | Purpose |
|-------|-----------|---------|---------|
| Language | Python | >=3.12 | Core runtime |
| Web Framework | Streamlit | >=1.58.0 | Multi-page UI, file uploads, data display |
| Data Processing | pandas | (via Streamlit) | DataFrame operations, JSON serialization |
| Excel Reading | python-calamine | >=0.7.0 | Fast xlsx reading (primary engine) |
| Excel Reading | openpyxl | >=3.1.5 | Fallback xlsx reading + writing |
| Config Format | PyYAML | >=6.0.3 | Rules file parsing |
| Package Manager | uv | — | Dependency management, virtual env |
| Config | pyproject.toml | — | Single source of truth for deps + metadata |

## 2. Project Structure

```
shopify_dashboard_app/
├── app.py                    # Streamlit entry point — all 3 pages + UI logic
├── config.py                 # Every hardcoded value in one place (sheet names, columns, colors, labels)
├── transform.py              # Rule engine — applies sequential rules to DataFrames
├── rules.py                  # Rules file loader — YAML, JSON, or Python
├── filters.py                # Custom filter functions (e.g. is_valid_purchase)
├── overview.py               # Reads pivot_table.xlsx sheets via openpyxl
├── merge.py                  # Merges Data Prep output into Overview, generates updated xlsx
├── rules_example.yaml        # Example rules file
├── rules_shopify.yaml        # Production Shopify rules (ready to use)
├── pyproject.toml            # Dependencies, Python version, project metadata
├── USER_GUIDE.html           # End-user guide (open in browser)
├── TECHNICAL_DEEP_DIVE.md    # This file — architecture reference
├── CLAUDE.md                 # Developer guide for AI assistants
└── README.md                 # Project overview + setup instructions
```

## 3. Architecture Overview

The app is a **three-page Streamlit application** with a sidebar for navigation:

```
Sidebar: [Data Prep] → [Merge] → [Overview]
```

### 3.1 Page Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Data Prep  │────▶│    Merge    │────▶│  Overview   │
│             │     │             │     │             │
│ Upload:     │     │ Upload:     │     │ Upload:     │
│ - rules     │     │ - pivot xlsx│     │ - pivot xlsx│
│ - data files│     │ - data output│    │             │
│             │     │             │     │ View:       │
│ Output:     │     │ Output:     │     │ - 6 tabs    │
│ - clean DF  │     │ - updated   │     │ - styled    │
│ - CSV/XLSX  │     │   workbook  │     │   HTML table│
└─────────────┘     └─────────────┘     └─────────────┘
```

### 3.2 Session State

Data Prep → Merge handoff uses `st.session_state["etl_result"]`:
- Data Prep page stores the transformed DataFrame in `st.session_state["etl_result"]`
- Merge page checks for this key first; falls back to file upload
- Key name `etl_result` is legacy (from "ETL" rename) — keep as-is to avoid breaking changes

## 4. File-by-File Breakdown

### 4.1 `config.py` — Single Source of Truth

**Purpose:** Every string, column name, color code, and mapping in one file. No hardcoded values in business logic.

**Key sections:**

| Section | Constants | Notes |
|---------|-----------|-------|
| Sheet Names | `SHEET_OVERVIEW`, `SHEET_COUNT`, etc. | Some have **trailing spaces** — intentional, matches the actual xlsx |
| Column Structure | `COL_ACCOUNT`, `COL_QTY_2023`, etc. | 13 columns in Overview sheet |
| Column Mapping | `COL_TO_XLSX_IDX` | Maps column name → 1-based xlsx column index |
| Quarter Mapping | `QUARTER_TO_COL` | `{1: "Qty_2026_1", ...}` |
| Growth Labels | `LABEL_NEW_24`, `LABEL_LOST`, etc. | Text labels preserved from original xlsx |
| Color Mapping | `FILL_COLORS`, `FILL_TO_LABEL_TYPE` | RGB fill color → label type ("new", "lost", "reactivated") |
| Badge Styles | `BADGE_STYLES` | Label type → (bg_color, fg_color, emoji) for HTML rendering |
| Count Tab | `COUNT_ROW_LABELS`, `COUNT_COL_LABELS` | Row categories and default column labels |
| Excel Engines | `EXCEL_ENGINES` | Priority: `["calamine", "openpyxl", None]` |

**Gotcha:** Sheet names `"Lost Account "`, `"Account Label Definition "`, `"Dupilicate Accounts "` have trailing spaces. Always use `cfg.SHEET_*` constants, never type them manually.

### 4.2 `transform.py` — Rule Engine

**Purpose:** Apply a sequence of transformation rules to a DataFrame. Each rule is a dict with a `"type"` key.

**Rule types supported:**

| Type | What it does | Key params |
|------|-------------|------------|
| `keep_cols` | Keep only specified columns | `cols: list[str]` |
| `drop_cols` | Remove specified columns | `cols: list[str]` |
| `filter` | Filter rows by condition | `col`, `op`, `value` |
| `rename` | Rename columns | `mapping: {old: new}` |
| `astype` | Cast column types | `mapping: {col: dtype}` |
| `drop_na` | Drop rows with NA | `cols: list[str]` |
| `fill_na` | Fill NA values | `mapping: {col: value}` |
| `dedup` | Drop duplicate rows | `cols: list[str]` |
| `sort` | Sort rows | `col`, `asc` |
| `compute` | Create new column from binary op | `new_col`, `left_col`, `right_col`, `op` |
| `summarize` | Group-by aggregation | `group_by`, `agg: {col: func}` |
| `custom_filter` | Call a Python function | `module`, `func` |
| `fill_from_lookup` | Fill column from lookup grouped by source | `src_col`, `dst_col` |
| `fill_domain` | Fill from email domain | `src_col`, `dst_col`, `free_domains` |

**Execution model:** Rules are applied **sequentially** — order matters. `fill_from_lookup` must come before `fill_domain`.

**`summarize` with `list`:** Uses a lambda (`lambda s: list(s.dropna().unique())`) because pandas doesn't support `"list"` as a string agg function.

**`custom_filter`:** Loads a Python function from a file using `importlib.util`. The function must accept a DataFrame and return a DataFrame (or boolean Series for filter functions).

**Column renaming after `summarize`:** Aggregated columns get renamed to `"Sum of X"`, `"Mean of X"`, etc. This is why the Merge code checks for both `"Sum of Lineitem quantity"` and `"Lineitem quantity"`.

### 4.3 `rules.py` — Rules File Loader

**Purpose:** Load rules from YAML, JSON, or Python files.

**Supported formats:**
- **YAML** (`.yaml`, `.yml`): Parsed with `yaml.safe_load()`. Expects `rules:` key at top level.
- **JSON** (`.json`): Parsed with `json.loads()`. Expects `{"rules": [...]}`.
- **Python** (`.py`): Imported as module. Looks for `RULES` or `rules` variable.

**Returns:** `list[dict]` — each dict has a `"type"` key.

### 4.4 `filters.py` — Custom Filter Functions

**Purpose:** Business-specific filter logic for Shopify data.

**`is_valid_purchase(df)`** — Returns boolean Series:
1. Removes accessories/services (replacement, extended, bag, warranty, foam)
2. Removes items priced below $240
3. **Exception:** Free skimmers (price=0) are kept if the same email group has a paid skimmer (complimentary pairing)

**`filter_valid_purchases(df)`** — Applies the mask and resets index.

### 4.5 `overview.py` — Pivot Table Reader

**Purpose:** Read and parse `pivot_table.xlsx` sheets using openpyxl.

**Key design:** `PIVOT_PATH` is a **module-level variable** (`"pivot_table.xlsx"` by default). The Merge page overrides it at runtime:
```python
import overview as overview_mod
overview_mod.PIVOT_PATH = str(pivot_tmp)
```

**Functions:**

| Function | Returns | Notes |
|----------|---------|-------|
| `load_overview()` | `pd.DataFrame` | Overview sheet with computed Qty_2026_ and growth. Preserves text labels. |
| `load_overview_styled(wb)` | `list[dict]` | Per-cell style info: value, fill, font_color, label_type, is_numeric |
| `load_label_rules(wb)` | `dict` | Label name → {fill, font_color, definition, note} |
| `load_lost_accounts()` | `pd.DataFrame` | Lost Account sheet |
| `load_count()` | `pd.DataFrame` | Count sheet (uses hardcoded `COUNT_COL_LABELS` — only used by merge logic) |
| `load_account_labels()` | `pd.DataFrame` | Label definitions |
| `load_24y_25n()` | `pd.DataFrame` | 24Y 25N sheet |
| `load_duplicates()` | `pd.DataFrame` | Duplicates sheet |

**`load_overview()` growth computation:**
- For each growth column (23-24, 24-25, 25-26):
  - If original cell is a non-empty string → preserve (it's a text label like "New_24", "Lost", "SOS")
  - If original cell is numeric → preserve original value
  - Otherwise → compute `(new - old) / old`

**`load_overview_styled()`:** Takes a **workbook object** (not path). Caller must call `load_workbook()` first. Returns per-cell style for the HTML table renderer.

### 4.6 `merge.py` — Merge Engine

**Purpose:** Combine Data Prep output with the existing Overview dashboard.

**Core functions:**

**`aggregate_etl_by_quarter(etl)`:**
- Groups Data Prep output by `Billing Company` + quarter (from `Created` month)
- Returns: `Account, ETL_Q1, ETL_Q2, ETL_Q3, ETL_Q4, ETL_Total`
- Quarter mapping: Jan-Mar → Q1, Apr-Jun → Q2, Jul-Sep → Q3, Oct-Dec → Q4

**`merge_overview_with_etl(etl)`:**
- Side-by-side merge: Overview columns + ETL_Q1..ETL_Q4 + ETL_Total
- Uses `how="outer"` merge → new accounts get added
- Preserves original growth labels via `_restore_original_growth()`

**`updated_overview_with_etl(etl)`:**
- Adds ETL quantities to the correct quarter column in Overview
- Drops ETL_* columns from final output
- Recomputes `Qty_2026_` = sum of Q1..Q4

**Growth label preservation (`_restore_original_growth`):**
- For existing accounts: preserves all original text labels
- 23-24 and 24-25 growth: **always preserved** (Data Prep doesn't affect past years)
- 25-26 growth: recomputed **only if** Data Prep changed Qty_2026_ from 0 → >0
  - Has prior history → `Reactivated`
  - No prior history → `New_26`
- For new accounts (not in original Overview): all growth labels computed via `_assign_all_growth_for_new_account()`

**`compute_count(updated)`:**
- Derives Count categories from updated Overview:
  - Total Account: `len(df)`
  - Lost: count where `25-26 Growth == "Lost"`
  - New_26: count where `25-26 Growth == "New_26"`
  - No Purchase 2026 / Not Lost: `Qty_2026_ == 0` and not Lost
  - Already Purchased 2026: `Qty_2026_ > 0`

**`generate_updated_pivot_xlsx(etl, output_path)`:**
1. Copies original xlsx to output path
2. Clears old data rows (row 3+) in Overview sheet
3. Writes "Updated by MM/DD/YYYY" in row 1
4. Writes merged data with formulas:
   - `Qty_2026_` = `SUM(J{r}:M{r})` (formula, not value)
   - Subtotal row: `SUM()` formulas for each qty column
   - Count rows: `COUNTIF()` formulas
5. Appends new Count column via `add_count_column()`

### 4.7 `app.py` — Streamlit Entry Point

**Structure:**
```
Imports + config
    ↓
st.set_page_config() + st.title()
    ↓
Sidebar: page = st.sidebar.radio(["Data Prep", "Merge", "Overview"])
    ↓
if page == "Data Prep": ...
elif page == "Overview": ...
elif page == "Merge": ...
```

**Data Prep page:**
- Sidebar file uploaders for rules + data files
- Files written to `/tmp/` for processing
- Multi-sheet xlsx: radio button to pick sheet
- Shows raw data + transformed result
- Download buttons (CSV, XLSX) + "Send to Merge" button
- "Send to Merge" stores result in `st.session_state["etl_result"]`

**Overview page:**
- Single file uploader for `pivot_table.xlsx`
- Loads workbook with `load_workbook(tmp, data_only=True)`
- Six tabs: Overview, Lost Account, Count, 24Y 25N, Labels, Duplicates
- **Overview tab:** Uses `load_overview_styled()` + `load_label_rules()` → renders full HTML table with color-coded badges
- **Other tabs:** Read cells directly via `ws.cell()` → DataFrame → `st.dataframe()`
- **Count tab:** Reads headers dynamically from row 1 (not hardcoded)
- All DataFrames sanitized with `df.where(pd.notnull(df), other="")` before display

**Merge page:**
- File uploader for `pivot_table.xlsx` + optional Data Prep output
- Overrides `overview.PIVOT_PATH` to point at uploaded file
- Validates required columns: `Billing Company`, `Lineitem quantity` (or `Sum of...`), `Created at`
- Detects new accounts not in original Overview → shows warning
- **Caching:** `@st.cache_data` on `_compute_merged` and `_compute_updated`
  - Uses `io.StringIO` + `orient="table"` for JSON-safe NaN handling
  - Cache key is the JSON string of the ETL DataFrame
- Three tabs: Side-by-side Merge, Updated Overview, Updated Count
- "Generate Updated Pivot XLSX" button → `generate_updated_pivot_xlsx()` → download

## 5. Key Design Decisions

### 5.1 Why `data_only=True` for openpyxl?

The Overview sheet contains Excel formulas (SUM, COUNTIF). Using `data_only=True` reads the **computed values** instead of the formula strings. This is essential for displaying growth percentages and totals.

### 5.2 Why calamine as primary engine?

The `pivot_table.xlsx` uses non-standard xlsx format (conformance="strict", missing sheet IDs). Calamine handles this; openpyxl may fail. Calamine is also faster. Fallback chain: calamine → openpyxl → default.

### 5.3 Why `orient="table"` for JSON serialization?

Default `to_json()` writes `NaN` as literal `NaN` — not valid JSON. Streamlit's frontend JS chokes on this. `orient="table"` serializes NaN as `null` (valid JSON) and round-trips cleanly through `pd.read_json()`.

### 5.4 Why `io.StringIO` wrapper?

In newer pandas/Python 3.14, `pd.read_json(string)` treats the string as a **file path**, not inline JSON. `io.StringIO` forces it to read as data.

### 5.5 Why `st.cache_data` for merge computations?

`updated_overview_with_etl()` is called on tab2 and tab3 (same data, two tabs). Without caching, it runs twice. The cache key is the JSON string of the ETL input — deterministic for same input.

### 5.6 Why HTML table for Overview tab?

Streamlit's `st.dataframe` doesn't support per-cell styling (colors, badges). The Overview tab renders a custom HTML table with:
- Color-coded badges for growth labels (🟡 New, 🔴 Lost, 🟢 Reactivated)
- Font colors (e.g., red font for SOS labels)
- Background fills
- Right-aligned numbers, left-aligned text

### 5.7 Why `PIVOT_PATH` as module-level variable?

Streamlit reruns the entire script on every widget change. The uploaded file path changes each time. By setting `overview.PIVOT_PATH = str(pivot_tmp)` at runtime, all `overview.py` functions automatically use the correct file without needing to pass paths through every function call.

## 6. Data Flow Diagram

```
                    DATA PREP PAGE
                    ──────────────
Shopify CSV/XLSX ──▶ _read_excel() ──▶ pd.DataFrame
                                            │
rules.yaml ──▶ load_rules() ──▶ list[dict]  │
                                            ▼
                                    apply_rules(df, rules)
                                            │
                                            ▼
                                    result (pd.DataFrame)
                                            │
                              ┌─────────────┼─────────────┐
                              ▼             ▼             ▼
                         CSV download  XLSX download  session_state
                                                        │
                    MERGE PAGE                         │
                    ──────────                         │
pivot_table.xlsx ──▶ load_workbook() ──▶ wb           │
                              │                        │
                              ▼                        ▼
                    overview.PIVOT_PATH = tmp    etl_result (from session)
                              │                        │
                              ▼                        │
                    load_overview() ◀──────────────────┘
                              │
                    aggregate_etl_by_quarter(etl)
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
          merge_overview_with_etl()  updated_overview_with_etl()
                    │                   │
                    ▼                   ▼
          Side-by-side Merge    Updated Overview + Updated Count
                    │                   │
                    ▼                   ▼
          st.dataframe()        generate_updated_pivot_xlsx()
                                            │
                                            ▼
                                   updated pivot_table.xlsx
```

## 7. Common Patterns for Adding Features

### 7.1 Adding a new rule type

1. Add the rule logic in `apply_rule()` in `transform.py`
2. Add documentation to the rules table in `README.md`
3. Optionally add to `rules_example.yaml`

### 7.2 Adding a new sheet to Overview page

1. Add sheet name constant in `config.py`
2. Add load function in `overview.py` (or read inline in `app.py`)
3. Add a new `st.tab()` in the Overview page
4. Read cells via `ws.cell(row=r, column=c).value` → DataFrame → `st.dataframe()`
5. Always sanitize: `df.where(pd.notnull(df), other="")`

### 7.3 Adding a new merge output

1. Add function in `merge.py` that takes the merged/updated DataFrame
2. Add a new tab in the Merge page in `app.py`
3. Use `@st.cache_data` if the computation is expensive
4. Use `io.StringIO` + `orient="table"` for any JSON serialization

### 7.4 Adding new config values

1. Add constant in `config.py`
2. Import as `cfg.CONSTANT_NAME` in any file
3. Never hardcode the value in business logic

## 8. Gotchas & Debugging

| Issue | Cause | Fix |
|-------|-------|-----|
| `FileNotFoundError` in `pd.read_json` | Newer pandas treats string as file path | Wrap with `io.StringIO()` |
| `NaN` JSON parse error in frontend | `to_json()` writes literal `NaN` | Use `orient="table"` |
| Count tab shows W1-W6 instead of dates | Hardcoded `COUNT_COL_LABELS` | Read headers from row 1 dynamically |
| Sheet not found | Trailing spaces in sheet names | Use `cfg.SHEET_*` constants |
| `load_workbook` fails on upload | Non-standard xlsx format | calamine engine handles it; fallback chain |
| Growth labels disappear after merge | `_restore_original_growth` not called | Ensure it's called in both merge functions |
| Duplicate account names | Overview may have duplicates | `drop_duplicates(keep="first")` before `set_index()` |
| Streamlit reruns on every click | By design | Use `st.session_state` for persistence |
| `st.cache_data` returns stale data | Cache key unchanged | Change input data or clear cache |

## 9. Running the App

```bash
# Install dependencies
uv sync

# Run locally
uv run streamlit run app.py --server.port 8501

# Run Python snippet
uv run python -c "import config as cfg; print(cfg.SHEET_OVERVIEW)"
```

## 10. Deployment

Deployed on **Streamlit Cloud**. The app reads from `pyproject.toml` for dependencies. Ensure all dependencies are listed there (not just in a requirements.txt).
