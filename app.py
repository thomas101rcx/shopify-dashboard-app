"""Shopify ETL Dashboard — rev0.0.0."""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import streamlit as st

from rules import load_rules
from transform import apply_rules

st.set_page_config(page_title="Shopify ETL", layout="wide")
st.title("Shopify ETL Dashboard")

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

            c1, c2 = st.columns(2)
            c1.download_button(
                "Download CSV", csv_bytes, f"{Path(f.name).stem}_out.csv", "text/csv"
            )
            c2.download_button(
                "Download XLSX",
                buf.read(),
                f"{Path(f.name).stem}_out.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        st.divider()
else:
    st.info("Upload one or more CSV/XLSX files to begin.")
