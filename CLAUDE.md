# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv sync                              # install deps
uv run streamlit run app.py --server.port 8501   # run app
uv run python -c "..."               # run Python snippet
```

## Architecture

Streamlit ETL dashboard. Upload CSV/XLSX → apply rules → view/download result.

**Data flow:**
`app.py` (UI) → `rules.py` (load rules file) → `transform.py` (apply rules sequentially) → `filters.py` (custom filter funcs)

**Rule engine (`transform.py`):** `apply_rules(df, rules)` iterate rule list, dispatch on `type`. Each rule type is a pure function `df → df`. New rule types added in `apply_rule()`.

**Custom filters:** `custom_filter` rule type loads Python function from user-provided module via `_load_func()`. Functions receive `df`, return filtered `df`.

**Rules file formats:** YAML (preferred), JSON, or Python (define `RULES = [...]` list).

**Excel engine priority:** calamine → openpyxl → default. calamine required for non-standard xlsx files (common with Shopify exports).

## Key Design Decisions

- Rules applied sequentially, each sees output of previous rule. Order matters.
- `fill_from_lookup` runs before `fill_domain` in rules files — fill known values first, then infer from domain for remaining NaN.
- `fill_domain` has `free_domains` list — these use full email as group key (not domain) to avoid merging different companies sharing gmail/yahoo.
- `summarize` is typically the final rule — it changes row count and column structure.

## Gotchas

- `pd.read_excel()` with no `sheet_name` returns dict when multiple sheets exist. `_read_excel()` handles this.
- `Billing Company` (capital C) — column names are case-sensitive in rules.
- Streamlit reruns whole script on any widget change — rules and data both persist across reruns via widget state.
