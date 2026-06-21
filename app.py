"""Shopify Dashboard — ETL + Overview."""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import streamlit as st

from merge import generate_updated_pivot_xlsx, merge_overview_with_etl, updated_overview_with_etl
from overview import (
    load_24y_25n,
    load_account_labels,
    load_count,
    load_duplicates,
    load_lost_accounts,
    load_overview,
)
from rules import load_rules
from transform import apply_rules

st.set_page_config(page_title="Shopify Dashboard", layout="wide")
st.title("Shopify Dashboard")

page = st.sidebar.radio("Page", ["ETL", "Overview", "Merge"], index=0)


def _read_excel(path: str, sheet: str | None = None) -> pd.DataFrame:
    engines = ["calamine", "openpyxl", None]
    last_err = None
    for engine in engines:
        try:
            result = pd.read_excel(path, sheet_name=sheet, engine=engine)
            if isinstance(result, dict):
                if sheet and sheet in result:
                    return result[sheet]
                return next(iter(result.values()))
            return result
        except Exception as e:
            last_err = e
    raise last_err  # type: ignore[misc]


def _list_sheets(path: str) -> list[str]:
    try:
        import python_calamine as pc

        return pc.CalamineWorkbook.open_path(path).sheet_names  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        import openpyxl

        return openpyxl.load_workbook(path, read_only=True).sheetnames
    except Exception:
        return []


if page == "ETL":
    rules_file = st.sidebar.file_uploader(
        "Rules file (yaml / json / py)", type=["yaml", "yml", "json", "py"]
    )
    data_files = st.sidebar.file_uploader(
        "Data files (csv / xlsx)", type=["csv", "xlsx"], accept_multiple_files=True
    )

    rules = []
    if rules_file is not None:
        suffix = Path(rules_file.name).suffix.lower()
        tmp = Path(f"/tmp/rules_{rules_file.file_id}{suffix}")
        tmp.write_bytes(rules_file.getvalue())
        try:
            rules = load_rules(str(tmp))
            st.sidebar.success(f"Loaded {len(rules)} rule(s)")
        except Exception as e:
            st.sidebar.error(f"Rules error: {e}")

    if data_files:
        for f in data_files:
            suffix = Path(f.name).suffix.lower()
            tmp = Path(f"/tmp/{f.file_id}_{f.name}")
            tmp.write_bytes(f.getvalue())

            try:
                if suffix == ".csv":
                    df = pd.read_csv(tmp)
                else:
                    sheets = _list_sheets(str(tmp))
                    if len(sheets) > 1:
                        sheet = st.radio(
                            f"Sheet — {f.name}",
                            sheets,
                            horizontal=True,
                            key=f"sheet_{f.file_id}",
                        )
                    elif sheets:
                        sheet = sheets[0]
                    else:
                        sheet = None
                    df = _read_excel(str(tmp), sheet=sheet)
            except Exception as e:
                st.error(f"Failed to read {f.name}: {e}")
                continue

            st.subheader(f.name)
            st.caption(f"Raw shape: {df.shape[0]} rows × {df.shape[1]} cols")
            st.dataframe(df.head(50), use_container_width=True)

            if rules:
                try:
                    result = apply_rules(df.copy(), rules)
                except Exception as e:
                    st.error(f"Transform error: {e}")
                    continue
                st.caption(f"Result shape: {result.shape[0]} rows × {result.shape[1]} cols")
                st.dataframe(result, use_container_width=True)

                csv_bytes = result.to_csv(index=False).encode()
                buf = io.BytesIO()
                result.to_excel(buf, index=False)
                buf.seek(0)

                c1, c2, c3 = st.columns(3)
                c1.download_button(
                    "Download CSV", csv_bytes, f"{Path(f.name).stem}_out.csv", "text/csv"
                )
                c2.download_button(
                    "Download XLSX",
                    buf.read(),
                    f"{Path(f.name).stem}_out.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
                if c3.button("Send to Merge", key=f"send_{f.file_id}"):
                    st.session_state["etl_result"] = result
                    st.success("Sent to Merge tab — switch to Merge tab to view")
            st.divider()
    else:
        st.info("Upload one or more CSV/XLSX files to begin.")

elif page == "Overview":
    st.subheader("Account Overview")
    st.markdown("Upload your current `pivot_table.xlsx` to view the dashboard.")

    pivot_file = st.file_uploader(
        "Pivot table file (xlsx)", type=["xlsx"], key="overview"
    )

    if pivot_file is None:
        st.info("Upload a pivot_table.xlsx file to view the dashboard.")
        st.stop()

    import tempfile
    suffix = Path(pivot_file.name).suffix.lower()
    tmp = Path(f"/tmp/overview_{pivot_file.file_id}{suffix}")
    tmp.write_bytes(pivot_file.getvalue())

    try:
        from openpyxl import load_workbook
        wb = load_workbook(tmp)
        sheets = wb.sheetnames
    except Exception as e:
        st.error(f"Failed to read file: {e}")
        st.stop()

    tab_overview, tab_lost, tab_count, tab_24y, tab_labels, tab_dupes = st.tabs(
        ["Overview", "Lost Account", "Count", "24Y 25N", "Labels", "Duplicates"]
    )

    with tab_overview:
        try:
            ws = wb["Overview"]
            rows = []
            for r in range(3, ws.max_row + 1):
                row_vals = [ws.cell(row=r, column=c).value for c in range(1, 14)]
                if all(v is None for v in row_vals):
                    continue
                rows.append(row_vals)
            # Data rows = those without SUM formula in col E
            data_rows = [r for r in rows if not (isinstance(r[4], str) and r[4].startswith("="))]
            subtotal_rows = [r for r in rows if isinstance(r[4], str) and r[4].startswith("=")]

            cols = ["Account", "Account Label", "Qty_2023", "23-24 Growth", "Qty_2024",
                    "24-25 Growth", "Qty_2025", "25-26 Growth", "Qty_2026_",
                    "Qty_2026_1", "Qty_2026_2", "Qty_2026_3", "Qty_2026_4"]
            df = pd.DataFrame(data_rows, columns=cols)

            # Ensure all numeric columns are numeric (None → 0)
            for c in ["Qty_2023", "Qty_2024", "Qty_2025", "Qty_2026_1", "Qty_2026_2", "Qty_2026_3", "Qty_2026_4"]:
                df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)

            # Compute Qty_2026_ = sum of week columns
            df["Qty_2026_"] = df["Qty_2026_1"] + df["Qty_2026_2"] + df["Qty_2026_3"] + df["Qty_2026_4"]

            # Compute growth columns
            def _growth(new, old):
                if old == 0:
                    return None
                return (new - old) / old

            df["23-24 Growth"] = df.apply(lambda r: _growth(r["Qty_2024"], r["Qty_2023"]), axis=1)
            df["24-25 Growth"] = df.apply(lambda r: _growth(r["Qty_2025"], r["Qty_2024"]), axis=1)
            df["25-26 Growth"] = df.apply(lambda r: _growth(r["Qty_2026_"], r["Qty_2025"]), axis=1)

            def _fmt_growth(v):
                if pd.isna(v) or v is None:
                    return ""
                if isinstance(v, (int, float)):
                    return f"{v:.1%}"
                return str(v)

            for c in ["23-24 Growth", "24-25 Growth", "25-26 Growth"]:
                df[c] = df[c].apply(_fmt_growth)

            st.metric("Total accounts", len(df))
            st.dataframe(df, use_container_width=True, height=600)

            if subtotal_rows:
                st.caption(f"Subtotal row present ({len(subtotal_rows)} formula rows)")
        except Exception as e:
            st.error(f"Failed to load Overview: {e}")

    with tab_lost:
        try:
            ws = wb["Lost Account "]
            rows = []
            for r in range(3, ws.max_row + 1):
                row_vals = [ws.cell(row=r, column=c).value for c in range(1, 14)]
                if all(v is None for v in row_vals):
                    continue
                rows.append(row_vals)
            cols = ["Account", "Account Label", "Qty_2023", "23-24 Growth", "Qty_2024",
                    "24-25 Growth", "Qty_2025", "25-26 Growth", "Qty_2026_",
                    "Qty_2026_1", "Qty_2026_2", "Qty_2026_3", "Qty_2026_4"]
            if rows:
                df = pd.DataFrame(rows, columns=cols)
                st.dataframe(df, use_container_width=True, height=400)
        except Exception as e:
            st.error(f"Failed to load Lost Account: {e}")

    with tab_count:
        try:
            ws = wb["Count"]
            rows = []
            for r in range(2, ws.max_row + 1):
                row_vals = [ws.cell(row=r, column=c).value for c in range(1, 8)]
                if all(v is None for v in row_vals):
                    continue
                rows.append(row_vals)
            if rows:
                df = pd.DataFrame(rows, columns=["Label", "W1", "W2", "W3", "W4", "W5", "W6"])
                st.dataframe(df, use_container_width=True)
        except Exception as e:
            st.error(f"Failed to load Count: {e}")

    with tab_24y:
        try:
            ws = wb["24Y 25N"]
            rows = []
            for r in range(2, ws.max_row + 1):
                row_vals = [ws.cell(row=r, column=c).value for c in range(1, 8)]
                if all(v is None for v in row_vals):
                    continue
                rows.append(row_vals)
            if rows:
                df = pd.DataFrame(rows, columns=["Company", "2024", "2025", "2026", "2025 Carecraft", "email sent", "Date"])
                st.dataframe(df, use_container_width=True, height=400)
        except Exception as e:
            st.error(f"Failed to load 24Y/25N: {e}")

    with tab_labels:
        try:
            ws = wb["Account Label Definition "]
            rows = []
            for r in range(3, ws.max_row + 1):
                row_vals = [ws.cell(row=r, column=c).value for c in range(1, 5)]
                if all(v is None for v in row_vals):
                    continue
                rows.append(row_vals)
            if rows:
                df = pd.DataFrame(rows, columns=["idx", "Label", "Definition", "Note"])
                df = df.drop(columns=["idx"], errors="ignore")
                st.dataframe(df, use_container_width=True, hide_index=True)
        except Exception as e:
            st.error(f"Failed to load Labels: {e}")

    with tab_dupes:
        try:
            ws = wb["Dupilicate Accounts "]
            rows = []
            for r in range(1, ws.max_row + 1):
                row_vals = [ws.cell(row=r, column=c).value for c in range(1, 3)]
                if all(v is None for v in row_vals):
                    continue
                rows.append(row_vals)
            if rows:
                df = pd.DataFrame(rows, columns=["Account", "Note"])
                st.dataframe(df, use_container_width=True, hide_index=True)
        except Exception as e:
            st.error(f"Failed to load Duplicates: {e}")

elif page == "Merge":
    st.subheader("Merge ETL → Overview")
    st.markdown(
        "Upload your current `pivot_table.xlsx` + ETL output (CSV/XLSX) to merge. "
        "ETL biweekly quantities (0601-0618) will be added to Qty_2026_2 and Qty_2026_."
    )

    pivot_file = st.file_uploader(
        "Pivot table file (xlsx)", type=["xlsx"], key="merge_pivot"
    )
    if pivot_file is None:
        st.info("Upload your pivot_table.xlsx first.")
        st.stop()

    import tempfile
    suffix = Path(pivot_file.name).suffix.lower()
    pivot_tmp = Path(f"/tmp/merge_pivot_{pivot_file.file_id}{suffix}")
    pivot_tmp.write_bytes(pivot_file.getvalue())

    # Point overview + merge modules at uploaded file
    import overview as overview_mod
    import merge as merge_mod
    overview_mod.PIVOT_PATH = str(pivot_tmp)
    merge_mod.PIVOT_PATH = str(pivot_tmp)

    if "etl_result" in st.session_state:
        st.info("Using ETL result from current session (sent from ETL tab).")
        etl = st.session_state["etl_result"]
        st.caption(f"ETL rows: {len(etl)}")
    else:
        merge_file = st.file_uploader(
            "ETL output file (csv / xlsx)", type=["csv", "xlsx"], key="merge_etl"
        )
        if merge_file is None:
            st.info("Send data from ETL tab via 'Send to Merge' button, or upload a file here.")
            st.stop()

        suffix = Path(merge_file.name).suffix.lower()
        tmp = Path(f"/tmp/merge_etl_{merge_file.file_id}{suffix}")
        tmp.write_bytes(merge_file.getvalue())

        try:
            if suffix == ".csv":
                etl = pd.read_csv(tmp)
            else:
                try:
                    etl = pd.read_excel(tmp, engine="calamine")
                except Exception:
                    etl = pd.read_excel(tmp, engine="openpyxl")
        except Exception as e:
            st.error(f"Failed to read file: {e}")
            st.stop()

    # ETL output may have renamed columns (e.g. "Sum of Lineitem quantity")
    if "Sum of Lineitem quantity" in etl.columns:
        qty_col = "Sum of Lineitem quantity"
    elif "Lineitem quantity" in etl.columns:
        qty_col = "Lineitem quantity"
    else:
        st.error("Missing column: Lineitem quantity")
        st.stop()
    required = {"Billing Company", qty_col, "Created at"}
    missing = required - set(etl.columns)
    if missing:
        st.error(f"Missing columns: {missing}")
        st.stop()

    # Detect new accounts in ETL not in Overview
    import overview as overview_mod
    existing_accounts = set(overview_mod.load_overview()["Account"])
    etl_accounts = set(etl["Billing Company"].dropna().unique())
    new_accounts = etl_accounts - existing_accounts
    if new_accounts:
        st.warning(f"**{len(new_accounts)} new account(s)** in ETL not in Overview: {', '.join(sorted(new_accounts)[:10])}{'...' if len(new_accounts) > 10 else ''}")

    tab1, tab2 = st.tabs(["Side-by-side Merge", "Updated Overview"])

    with tab1:
        merged = merge_overview_with_etl(etl)
        new_count = merged["Qty_2023"].eq(0) & merged["Qty_2024"].eq(0) & merged["Qty_2025"].eq(0) & merged["ETL_Total"].gt(0)
        st.caption(f"Rows: {len(merged)} ({new_count.sum()} new)")
        st.dataframe(merged, use_container_width=True, height=600)

        csv_bytes = merged.to_csv(index=False).encode()
        st.download_button(
            "Download merged CSV", csv_bytes, "merged_overview.csv", "text/csv"
        )

    with tab2:
        updated = updated_overview_with_etl(etl)
        new_count = updated["Qty_2023"].eq(0) & updated["Qty_2024"].eq(0) & updated["Qty_2025"].eq(0) & updated["Qty_2026_"].gt(0)
        st.caption(f"Rows: {len(updated)} ({new_count.sum()} new) — Qty_2026_2 and Qty_2026_ updated with ETL data")
        st.dataframe(updated, use_container_width=True, height=600)

        csv_bytes = updated.to_csv(index=False).encode()
        st.download_button(
            "Download updated CSV", csv_bytes, "updated_overview.csv", "text/csv"
        )

        if st.button("Generate Updated Pivot XLSX"):
            import tempfile

            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                out_path = tmp.name
            try:
                merge_mod.generate_updated_pivot_xlsx(etl, out_path)
                with open(out_path, "rb") as f:
                    xlsx_bytes = f.read()
                st.download_button(
                    "Download Updated Pivot XLSX",
                    xlsx_bytes,
                    "Shopify_Pivot_Table_updated.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
                st.success("Generated — click download above")
            except Exception as e:
                st.error(f"Failed to generate: {e}")
