"""
pages/dedup_review.py -- DEV_MODE only: cross-site duplicate pair review

Two tabs:
  1. Paires detectees  -- all rows the algorithm has linked (canonical_id IS NOT NULL)
  2. Signalements      -- manual reports filed via the flag button on listing cards

Not linked from the main UI in production -- only accessible via the dev toolbar
banner (DEV_MODE=true) or by navigating to /dedup_review directly.
"""

import os
import streamlit as st
import pandas as pd
import psycopg2

DEV_MODE = os.environ.get("DEV_MODE", "false").lower() == "true"

st.set_page_config(page_title="Dedup Review", layout="wide", page_icon="🔍")

if not DEV_MODE:
    st.error("This page is only available in DEV_MODE.")
    st.stop()

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
        return pd.read_sql_query("""
            SELECT
                p.id            AS dupe_id,
                p.site          AS dupe_site,
                p.title         AS dupe_title,
                p.price_numeric AS dupe_price,
                p.square_meters AS dupe_m2,
                p.listing_ref   AS dupe_ref,
                p.url           AS dupe_url,
                p.image_url     AS dupe_image,
                p.scraped_date  AS dupe_date,
                p.description   AS dupe_desc,
                c.id            AS canonical_id,
                c.site          AS canonical_site,
                c.title         AS canonical_title,
                c.price_numeric AS canonical_price,
                c.square_meters AS canonical_m2,
                c.listing_ref   AS canonical_ref,
                c.url           AS canonical_url,
                c.image_url     AS canonical_image,
                c.scraped_date  AS canonical_date
            FROM properties p
            JOIN properties c ON c.id = p.canonical_id
            ORDER BY p.scraped_date DESC, p.id DESC
        """, conn)
    finally:
        conn.close()


@st.cache_data(ttl=30)
def load_reports():
    conn = psycopg2.connect(DATABASE_URL, connect_timeout=10)
    conn.autocommit = True
    try:
        return pd.read_sql_query("""
            SELECT r.id, r.id_a, r.id_b, r.site_a, r.site_b,
                   r.notes, r.reported_at, r.resolved,
                   p.title      AS title_a,
                   p.url        AS url_a,
                   p.price_numeric AS price_a,
                   p.square_meters AS m2_a
            FROM dedup_reports r
            LEFT JOIN properties p ON p.id = r.id_a
            ORDER BY r.reported_at DESC
        """, conn)
    finally:
        conn.close()


def infer_match_type(desc: str) -> str:
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

st.markdown("## \U0001f50d Dedup Review")
st.caption("Read-only. To unlink: `UPDATE properties SET canonical_id = NULL WHERE id = <id>`")

tab_pairs, tab_reports = st.tabs(["Paires d\u00e9tect\u00e9es", "\U0001f6a9 Signalements en attente"])


# ── Tab 1: detected pairs ──────────────────────────────────────────────────────

with tab_pairs:
    pairs = load_pairs()

    if pairs.empty:
        st.info("No linked pairs in the database.")
    else:
        col1, col2, col3 = st.columns(3)
        col1.metric("Total pairs", len(pairs))
        tier1 = pairs['dupe_desc'].apply(lambda d: infer_match_type(d or '') == "tier 1 (ref)").sum()
        col2.metric("Tier 1 (ref)", int(tier1))
        col3.metric("Tier 2 (fingerprint)", int(len(pairs) - tier1))

        st.divider()

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

        for _, row in filtered.iterrows():
            match_type = infer_match_type(row['dupe_desc'] or '')
            badge = "\U0001f535" if "tier 1" in match_type else "\U0001f7e1"

            with st.expander(
                f"{badge} #{row['dupe_id']} {row['dupe_site']}  \u2192  #{row['canonical_id']} {row['canonical_site']}  |  {match_type}",
                expanded=False,
            ):
                c1, c2 = st.columns(2)

                with c1:
                    if row['dupe_image']:
                        st.image(row['dupe_image'], use_container_width=True)
                    st.markdown(f"**Duplicate** \u00b7 `#{row['dupe_id']}`")
                    st.markdown(f"**Site:** {row['dupe_site']}")
                    st.markdown(f"**Date:** {row['dupe_date']}")
                    _dupe_ref = row['dupe_ref'] or '\u2014'
                    st.markdown(f"**Ref:** `{_dupe_ref}`")
                    price = f"{int(row['dupe_price']):,} \u20ac".replace(",", " ") if pd.notna(row['dupe_price']) else "\u2014"
                    m2 = f"{row['dupe_m2']} m\u00b2" if pd.notna(row['dupe_m2']) else "\u2014"
                    st.markdown(f"**Prix:** {price}  |  **Surface:** {m2}")
                    _dupe_title = row['dupe_title'] or '\u2014'
                    st.markdown(f"**Titre:** {_dupe_title}")
                    st.markdown(f"[Voir l'annonce \u2192]({row['dupe_url']})")

                with c2:
                    if row['canonical_image']:
                        st.image(row['canonical_image'], use_container_width=True)
                    st.markdown(f"**Canonical** \u00b7 `#{row['canonical_id']}`")
                    st.markdown(f"**Site:** {row['canonical_site']}")
                    st.markdown(f"**Date:** {row['canonical_date']}")
                    st.markdown(f"**Ref:** `{row['canonical_ref'] or '\u2014'}`")
                    price = f"{int(row['canonical_price']):,} \u20ac".replace(",", " ") if pd.notna(row['canonical_price']) else "\u2014"
                    m2 = f"{row['canonical_m2']} m\u00b2" if pd.notna(row['canonical_m2']) else "\u2014"
                    st.markdown(f"**Prix:** {price}  |  **Surface:** {m2}")
                    st.markdown(f"**Titre:** {row['canonical_title'] or '\u2014'}")
                    st.markdown(f"[Voir l'annonce \u2192]({row['canonical_url']})")

                st.caption(f"To unlink: `UPDATE properties SET canonical_id = NULL WHERE id = {row['dupe_id']};`")


# ── Tab 2: pending reports ─────────────────────────────────────────────────────

with tab_reports:
    reports = load_reports()
    pending  = reports[~reports['resolved']]
    resolved = reports[reports['resolved']]

    st.metric("En attente", len(pending))

    if pending.empty:
        st.info("Aucun signalement en attente.")
    else:
        for _, r in pending.iterrows():
            with st.expander(
                f"\U0001f6a9 #{r['id_a']} {r['site_a'] or ''}  \u00b7  {str(r['reported_at'])[:16]}",
                expanded=True,
            ):
                title_display = r['title_a'] if pd.notna(r['title_a']) else str(r['id_a'])
                url_display   = r['url_a']   if pd.notna(r['url_a'])   else '#'
                st.markdown(f"**Annonce:** [{title_display}]({url_display})")
                price = f"{int(r['price_a']):,} \u20ac".replace(',', ' ') if pd.notna(r['price_a']) else '\u2014'
                m2    = f"{r['m2_a']} m\u00b2" if pd.notna(r['m2_a']) else '\u2014'
                st.markdown(f"**Prix:** {price}  |  **Surface:** {m2}")
                st.markdown(f"**Notes:** {r['notes'] or '*(aucune)*'}")
                st.caption(f"To resolve: `UPDATE dedup_reports SET resolved = true WHERE id = {r['id']};`")

    if not resolved.empty:
        with st.expander(f"R\u00e9solus ({len(resolved)})", expanded=False):
            for _, r in resolved.iterrows():
                st.markdown(
                    f"~~`#{r['id_a']}`~~ {r['site_a'] or ''} \u00b7 "
                    f"{str(r['reported_at'])[:16]} \u00b7 {r['notes'] or ''}"
                )
