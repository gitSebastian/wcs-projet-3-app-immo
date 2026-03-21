"""
pages/dedup_review.py -- DEV_MODE only: cross-site duplicate pair review

Shows every linked pair side-by-side so false positives can be spotted quickly.
Not linked from the main UI in production -- only accessible via the dev toolbar
banner (DEV_MODE=true) or by navigating to /dedup_review directly.

Each row shows:
  - The duplicate row (canonical_id IS NOT NULL)
  - The canonical row it points to
  - Match type inferred from the description marker
  - Both listing IDs and source sites
  - Direct links to both listings

The page is read-only. To unlink a false positive or force-link a missed pair,
note the IDs and run a SQL UPDATE directly in Supabase.
"""

import os
import streamlit as st
import pandas as pd
import psycopg2

# Guard: only accessible in DEV_MODE
DEV_MODE = os.environ.get("DEV_MODE", "false").lower() == "true"

st.set_page_config(page_title="Dedup Review", layout="wide", page_icon="🔍")

if not DEV_MODE:
    st.error("This page is only available in DEV_MODE.")
    st.stop()

# Credentials
if "DATABASE_URL" in st.secrets:
    os.environ["DATABASE_URL"] = st.secrets["DATABASE_URL"]
    DATABASE_URL = st.secrets["DATABASE_URL"]
else:
    st.error("Database secret not found!")
    st.stop()


@st.cache_data(ttl=60)
def load_pairs():
    conn = psycopg2.connect(DATABASE_URL, connect_timeout=10)
    conn.autocommit = True
    try:
        df = pd.read_sql_query("""
            SELECT
                p.id            AS dupe_id,
                p.site          AS dupe_site,
                p.title         AS dupe_title,
                p.price_numeric AS dupe_price,
                p.square_meters AS dupe_m2,
                p.listing_ref   AS dupe_ref,
                p.url           AS dupe_url,
                p.scraped_date  AS dupe_date,
                p.description   AS dupe_desc,
                c.id            AS canonical_id,
                c.site          AS canonical_site,
                c.title         AS canonical_title,
                c.price_numeric AS canonical_price,
                c.square_meters AS canonical_m2,
                c.listing_ref   AS canonical_ref,
                c.url           AS canonical_url,
                c.scraped_date  AS canonical_date
            FROM properties p
            JOIN properties c ON c.id = p.canonical_id
            ORDER BY p.scraped_date DESC, p.id DESC
        """, conn)
    finally:
        conn.close()
    return df


def infer_match_type(desc: str) -> str:
    """Infer tier from the diagnostic marker written by run_cross_site_dedup()."""
    if not desc:
        return "unknown"
    if "-- ref " in desc:
        return "tier 1 (ref)"
    if "-- fingerprint" in desc:
        return "tier 2 (fingerprint)"
    if "-- tier 1" in desc:
        return "tier 1 (ref)"
    return "unknown"


# ── Page header ────────────────────────────────────────────────────────────────

st.markdown("## 🔍 Dedup Review")
st.caption("Read-only. To unlink a false positive: `UPDATE properties SET canonical_id = NULL WHERE id = <dupe_id>`")

pairs = load_pairs()

if pairs.empty:
    st.info("No linked pairs in the database.")
    st.stop()

# ── Summary stats ──────────────────────────────────────────────────────────────

col1, col2, col3 = st.columns(3)
col1.metric("Total pairs", len(pairs))

tier1 = pairs['dupe_desc'].apply(lambda d: infer_match_type(d or '') == "tier 1 (ref)").sum()
tier2 = len(pairs) - tier1
col2.metric("Tier 1 (ref)", int(tier1))
col3.metric("Tier 2 (fingerprint)", int(tier2))

st.divider()

# ── Filter controls ────────────────────────────────────────────────────────────

col_f1, col_f2 = st.columns(2)
with col_f1:
    match_filter = st.selectbox(
        "Match type",
        ["All", "tier 1 (ref)", "tier 2 (fingerprint)", "unknown"],
    )
with col_f2:
    site_options = sorted(set(pairs['dupe_site'].tolist() + pairs['canonical_site'].tolist()))
    site_filter = st.selectbox("Filter by site (either side)", ["All"] + site_options)

filtered = pairs.copy()
if match_filter != "All":
    filtered = filtered[filtered['dupe_desc'].apply(
        lambda d: infer_match_type(d or '') == match_filter
    )]
if site_filter != "All":
    filtered = filtered[
        (filtered['dupe_site'] == site_filter) |
        (filtered['canonical_site'] == site_filter)
    ]

st.caption(f"Showing {len(filtered)} of {len(pairs)} pairs")

st.divider()

# ── Pair table ─────────────────────────────────────────────────────────────────
# Rendered as a markdown table for compactness. Each row is one duplicate pair.

for _, row in filtered.iterrows():
    match_type = infer_match_type(row['dupe_desc'] or '')
    badge = "🔵" if "tier 1" in match_type else "🟡"

    with st.expander(
        f"{badge} #{row['dupe_id']} {row['dupe_site']}  →  #{row['canonical_id']} {row['canonical_site']}  |  {match_type}",
        expanded=False,
    ):
        c1, c2 = st.columns(2)

        with c1:
            st.markdown(f"**Duplicate** · `#{row['dupe_id']}`")
            st.markdown(f"**Site:** {row['dupe_site']}")
            st.markdown(f"**Date:** {row['dupe_date']}")
            st.markdown(f"**Ref:** `{row['dupe_ref'] or '—'}`")
            price = f"{int(row['dupe_price']):,} €".replace(",", " ") if pd.notna(row['dupe_price']) else "—"
            m2 = f"{row['dupe_m2']} m²" if pd.notna(row['dupe_m2']) else "—"
            st.markdown(f"**Prix:** {price}  |  **Surface:** {m2}")
            st.markdown(f"**Titre:** {row['dupe_title'] or '—'}")
            st.markdown(f"[Voir l'annonce →]({row['dupe_url']})")

        with c2:
            st.markdown(f"**Canonical** · `#{row['canonical_id']}`")
            st.markdown(f"**Site:** {row['canonical_site']}")
            st.markdown(f"**Date:** {row['canonical_date']}")
            st.markdown(f"**Ref:** `{row['canonical_ref'] or '—'}`")
            price = f"{int(row['canonical_price']):,} €".replace(",", " ") if pd.notna(row['canonical_price']) else "—"
            m2 = f"{row['canonical_m2']} m²" if pd.notna(row['canonical_m2']) else "—"
            st.markdown(f"**Prix:** {price}  |  **Surface:** {m2}")
            st.markdown(f"**Titre:** {row['canonical_title'] or '—'}")
            st.markdown(f"[Voir l'annonce →]({row['canonical_url']})")

        st.caption(f"To unlink: `UPDATE properties SET canonical_id = NULL WHERE id = {row['dupe_id']};`")
