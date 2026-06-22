"""Dashboard configuration constants."""

# ── Sheet Names ──────────────────────────────────────────────
SHEET_OVERVIEW = "Overview"
SHEET_COUNT = "Count"
SHEET_LOST_ACCOUNT = "Lost Account "
SHEET_LABEL_DEFINITION = "Account Label Definition "  # trailing space intentional
SHEET_24Y_25N = "24Y 25N"
SHEET_DUPLICATES = "Dupilicate Accounts "  # trailing space intentional

# ── Column Structure ─────────────────────────────────────────
# Overview sheet: 13 columns (1-based xlsx indices)
COL_ACCOUNT = "Account"
COL_ACCOUNT_LABEL = "Account Label"
COL_QTY_2023 = "Qty_2023"
COL_GROWTH_23_24 = "23-24 Growth"
COL_QTY_2024 = "Qty_2024"
COL_GROWTH_24_25 = "24-25 Growth"
COL_QTY_2025 = "Qty_2025"
COL_GROWTH_25_26 = "25-26 Growth"
COL_QTY_2026_TOTAL = "Qty_2026_"
COL_QTY_2026_Q1 = "Qty_2026_1"
COL_QTY_2026_Q2 = "Qty_2026_2"
COL_QTY_2026_Q3 = "Qty_2026_3"
COL_QTY_2026_Q4 = "Qty_2026_4"

OVERVIEW_COLS = [
    COL_ACCOUNT, COL_ACCOUNT_LABEL,
    COL_QTY_2023, COL_GROWTH_23_24,
    COL_QTY_2024, COL_GROWTH_24_25,
    COL_QTY_2025, COL_GROWTH_25_26,
    COL_QTY_2026_TOTAL, COL_QTY_2026_Q1, COL_QTY_2026_Q2, COL_QTY_2026_Q3, COL_QTY_2026_Q4,
]

GROWTH_COLS = [COL_GROWTH_23_24, COL_GROWTH_24_25, COL_GROWTH_25_26]

# xlsx 1-based column index for each Overview column
COL_TO_XLSX_IDX = {name: i + 1 for i, name in enumerate(OVERVIEW_COLS)}

# Quarter number → Qty_2026_N column
QUARTER_TO_COL = {1: COL_QTY_2026_Q1, 2: COL_QTY_2026_Q2, 3: COL_QTY_2026_Q3, 4: COL_QTY_2026_Q4}

# All qty columns that need numeric coercion
QTY_COLS = [
    COL_QTY_2023, COL_QTY_2024, COL_QTY_2025,
    COL_QTY_2026_Q1, COL_QTY_2026_Q2, COL_QTY_2026_Q3, COL_QTY_2026_Q4,
]

# Number of data columns in Overview sheet (for range(1, N+1))
OVERVIEW_NUM_COLS = len(OVERVIEW_COLS)  # 13

# ── Growth Labels ────────────────────────────────────────────
LABEL_NEW_24 = "New_24"
LABEL_NEW_25 = "New_25"
LABEL_NEW_26 = "New_26"
LABEL_SOS = "SOS"
LABEL_LOST = "Lost"
LABEL_REACTIVATED = "Reactivated"
LABEL_SLASH = "/"

ALL_LABELS = [
    LABEL_NEW_24, LABEL_NEW_25, LABEL_NEW_26,
    LABEL_SOS, LABEL_LOST, LABEL_REACTIVATED, LABEL_SLASH,
]

# ── Color Mapping (fill color → label type) ──────────────────
FILL_COLORS = {
    "FFF2CEEF": "#FFF2CEEF",   # light orange (header background)
    "FFFFFF00": "#FFFF00",     # yellow (New labels)
    "FFFF0000": "#FF0000",     # red (Lost labels)
    "FF92D050": "#92D050",     # green (Reactivated)
}
FILL_TO_LABEL_TYPE = {
    "FFFFFF00": "new",
    "FFFF0000": "lost",
    "FF92D050": "reactivated",
}

FONT_COLORS = {
    "FF000000": "#000000",
    "FFFF0000": "#FF0000",
    "FF303030": "#303030",
}

# ── Badge Styles (label type → (bg_color, fg_color, icon)) ──
BADGE_STYLES = {
    "new": ("#FFF9C4", "#F57F17", "🟡"),
    "lost": ("#FFCDD2", "#C62828", "🔴"),
    "reactivated": ("#C8E6C9", "#2E7D32", "🟢"),
}

# ── Count Tab ────────────────────────────────────────────────
COUNT_ROW_LABELS = [
    "Total Account",
    LABEL_LOST,
    LABEL_NEW_26,
    "No Purchase 2026 / Not Lost",
    "Already Purchased 2026",
]

COUNT_COL_LABELS = ["Label", "W1", "W2", "W3", "W4", "W5", "W6"]

# ── 24Y 25N Tab ───────────────────────────────────────────────
COL_24Y_25N_COMPANY = "Company"
COL_24Y_25N_2024 = 2024
COL_24Y_25N_2025 = 2025
COL_24Y_25N_2026 = 2026
COL_24Y_25N_CARECRAFT = "2025 Carecraft"
COL_24Y_25N_EMAIL_SENT = "email sent"
COL_24Y_25N_DATE = "Date"

# ── Label Definition Tab ───────────────────────────────────────
COL_LABEL_DEF_IDX = "idx"
COL_LABEL_DEF_LABEL = "Label"
COL_LABEL_DEF_DEFINITION = "Definition"
COL_LABEL_DEF_NOTE = "Note"

# ── Duplicates Tab ─────────────────────────────────────────────
COL_DUPLICATES_ACCOUNT = "Account"
COL_DUPLICATES_NOTE = "Note"

# ── Excel Engine Priority ────────────────────────────────────
EXCEL_ENGINES = ["calamine", "openpyxl", None]
