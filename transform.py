"""Transform engine: apply rules to dataframe."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


def _parse_value(raw: str, dtype: str):
    """Parse string value into target dtype."""
    if dtype == "int":
        return int(raw)
    if dtype == "float":
        return float(raw)
    if dtype == "bool":
        return raw.lower() in ("1", "true", "yes", "y")
    return raw


def apply_rule(df: pd.DataFrame, rule: dict) -> pd.DataFrame:
    """Apply one rule dict to dataframe.

    Supported rule types:
      - keep_cols: list[str] — keep only these columns
      - drop_cols: list[str] — drop these columns
      - filter: {col, op, value} — filter rows
        ops: eq, neq, gt, gte, lt, lte, contains, not_contains, in, not_in
      - rename: {old: new} — rename columns
      - astype: {col: dtype} — cast column dtype (int/float/bool/str)
      - drop_na: list[str] — drop rows with NA in these cols
      - fill_na: {col: value} — fill NA
      - dedup: list[str] — drop duplicate rows
      - sort: {col, asc} — sort rows
      - summarize: {group_by, agg} — group-by aggregation
        agg: {col: func}  func in sum/mean/count/min/max/first/last
    """
    t = rule.get("type")
    if t == "keep_cols":
        cols = [c for c in rule["cols"] if c in df.columns]
        return df[cols]

    if t == "drop_cols":
        return df.drop(columns=[c for c in rule["cols"] if c in df.columns])

    if t == "filter":
        col = rule["col"]
        op = rule["op"]
        raw_val = rule["value"]
        if col not in df.columns:
            return df
        series = df[col]
        if op == "in":
            vals = [str(v) for v in raw_val]
            return df[series.astype(str).isin(vals)]
        if op == "not_in":
            vals = [str(v) for v in raw_val]
            return df[~series.astype(str).isin(vals)]
        if op == "contains":
            return df[series.astype(str).str.contains(str(raw_val), case=False, na=False)]
        if op == "not_contains":
            return df[~series.astype(str).str.contains(str(raw_val), case=False, na=False)]
        dtype = rule.get("dtype", "str")
        val = _parse_value(str(raw_val), dtype)
        ops = {
            "eq": series == val,
            "neq": series != val,
            "gt": series > val,
            "gte": series >= val,
            "lt": series < val,
            "lte": series <= val,
        }
        mask = ops.get(op)
        if mask is None:
            return df
        return df[mask]

    if t == "rename":
        return df.rename(columns={k: v for k, v in rule["mapping"].items() if k in df.columns})

    if t == "astype":
        for col, dtype in rule["mapping"].items():
            if col not in df.columns:
                continue
            try:
                if dtype == "int":
                    df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
                elif dtype == "float":
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                elif dtype == "bool":
                    df[col] = df[col].astype(str).str.lower().isin(("1", "true", "yes", "y"))
                elif dtype == "datetime":
                    df[col] = pd.to_datetime(df[col], errors="coerce")
                else:
                    df[col] = df[col].astype(str)
            except Exception:
                pass
        return df

    if t == "drop_na":
        return df.dropna(subset=[c for c in rule["cols"] if c in df.columns])

    if t == "fill_na":
        for col, val in rule["mapping"].items():
            if col in df.columns:
                df[col] = df[col].fillna(val)
        return df

    if t == "dedup":
        subset = [c for c in rule["cols"] if c in df.columns]
        if not subset:
            subset = None
        return df.drop_duplicates(subset=subset)

    if t == "sort":
        by = rule["col"] if isinstance(rule["col"], list) else [rule["col"]]
        by = [c for c in by if c in df.columns]
        if not by:
            return df
        return df.sort_values(by=by, ascending=rule.get("asc", True))

    if t == "summarize":
        group_cols = [c for c in rule["group_by"] if c in df.columns]
        agg_map = {}
        for col, func in rule["agg"].items():
            if col not in df.columns:
                continue
            if func == "list":
                agg_map[col] = lambda s: list(s.dropna().unique())
            else:
                agg_map[col] = func
        if not group_cols or not agg_map:
            return df
        return df.groupby(group_cols, as_index=False).agg(agg_map)

    if t == "custom_filter":
        func = _load_func(rule["module"], rule["func"])
        return func(df)

    if t == "fill_from_lookup":
        src = rule["src_col"]
        dst = rule["dst_col"]
        if src not in df.columns or dst not in df.columns:
            return df
        email_to_company: dict[str, str] = {}
        for _, row in df.iterrows():
            email = str(row[src]).strip() if pd.notna(row[src]) else ""
            company = row[dst]
            if pd.isna(company) or str(company).strip() == "":
                if email in email_to_company:
                    row[dst] = email_to_company[email]
            else:
                if email and email_to_company.get(email, str(company)) != str(company):
                    email_to_company[email] = str(company)
        for _, row in df.iterrows():
            email = str(row[src]).strip() if pd.notna(row[src]) else ""
            company = row[dst]
            if pd.isna(company) or str(company).strip() == "":
                if email in email_to_company:
                    df.loc[_, dst] = email_to_company[email]
            elif email:
                domain = email.split("@")[1] if "@" in email else email
                if email_to_company.get(email) is None:
                    email_to_company[email] = str(company)
        return df

    if t == "fill_domain":
        src = rule["src_col"]
        dst = rule["dst_col"]
        free_domains = set(rule.get("free_domains", []))
        use_full_email = rule.get("use_full_email_for_free", True)
        if src not in df.columns or dst not in df.columns:
            return df
        for _, row in df.iterrows():
            company = row[dst]
            if pd.notna(company) and str(company).strip():
                continue
            email = str(row[src]).strip() if pd.notna(row[src]) else ""
            if "@" in email:
                domain = email.split("@")[1]
                if domain in free_domains and use_full_email:
                    df.loc[_, dst] = email
                else:
                    df.loc[_, dst] = domain
        return df

    return df


def _load_func(module_path: str, func_name: str):
    p = Path(module_path)
    if not p.exists():
        raise FileNotFoundError(f"Module not found: {module_path}")
    spec = importlib.util.spec_from_file_location("custom_filter_mod", p)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return getattr(mod, func_name)


def apply_rules(df: pd.DataFrame, rules: list[dict]) -> pd.DataFrame:
    for rule in rules:
        df = apply_rule(df, rule)
    return df
