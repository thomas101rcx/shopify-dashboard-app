"""Custom filter functions for Shopify Data Prep rules."""

from __future__ import annotations

import pandas as pd

ACCESSORY_KEYWORDS = ("replacement", "extended", "bag", "warranty", "foam")
SKIMMER_KEYWORD = "skimmer"
PRICE_THRESHOLD = 240


def is_valid_purchase(df: pd.DataFrame) -> pd.Series:
    """Return boolean Series marking genuine line-item purchases.

    Rules:
    1. Accessory/service items (replacement, extended, bag, warranty, foam) → invalid.
    2. Price below threshold → likely invalid.
    3. Price == 0 AND name contains "skimmer" AND same email group has a skimmer
       with price > threshold → valid (complimentary skimmer paired with paid one).
    4. Everything else → valid.
    """
    name_col = "Lineitem name"
    price_col = "Lineitem price"
    email_col = "Email"

    if name_col not in df.columns or price_col not in df.columns:
        return pd.Series(True, index=df.index)

    names = df[name_col].fillna("").astype(str).str.lower()
    prices = pd.to_numeric(df[price_col], errors="coerce").fillna(0)

    is_accessory = names.str.contains("|".join(ACCESSORY_KEYWORDS), regex=True)
    below_threshold = prices < PRICE_THRESHOLD
    is_skimmer = names.str.contains(SKIMMER_KEYWORD)

    # Per email: does this group contain a paid skimmer (price > threshold)?
    has_paid_skimmer: dict[str, bool] = {}
    if email_col in df.columns:
        for email, group in df.groupby(email_col):
            grp_prices = pd.to_numeric(group[price_col], errors="coerce").fillna(0)
            grp_names = group[name_col].fillna("").astype(str).str.lower()
            paid_skimmer = ((grp_prices > PRICE_THRESHOLD) & grp_names.str.contains(SKIMMER_KEYWORD)).any()
            has_paid_skimmer[str(email)] = bool(paid_skimmer)

    is_free_skimmer = (prices == 0) & is_skimmer
    if email_col in df.columns:
        is_free_skimmer &= df[email_col].astype(str).map(has_paid_skimmer).fillna(False)

    invalid = is_accessory & ~is_free_skimmer
    invalid |= below_threshold & ~is_free_skimmer
    invalid &= ~is_free_skimmer

    return ~invalid


def filter_valid_purchases(df: pd.DataFrame) -> pd.DataFrame:
    mask = is_valid_purchase(df)
    return df[mask].reset_index(drop=True)
