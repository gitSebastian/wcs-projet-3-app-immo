# =============================================================
# streamlit run WCS/github/wcs-projet-3-app-immo/app.py --server.address 192.168.1.22
# =============================================================

import streamlit as st
import pandas as pd
import psycopg2
import base64
import os
import re
from datetime import date, timedelta
from pathlib import Path
from streamlit_float import *

# =============================================================
# CONFIG
# =============================================================

# 1. Grab the secret from Streamlit's storage
if "DATABASE_URL" in st.secrets:
    # 2. MANUALLY set it as an environment variable
    # This makes psycopg2 think it's reading from a .env file again
    os.environ["DATABASE_URL"] = st.secrets["DATABASE_URL"]
    DATABASE_URL = st.secrets["DATABASE_URL"]
else:
    st.error("Database secret not found!")
    st.stop()

st.set_page_config(
    page_title="Nant'Immo", 
    layout="wide",
    initial_sidebar_state="collapsed",
    page_icon="🏠"
)

# Chemins
CURRENT_FOLDER = Path(__file__).parent
IMAGES_FOLDER = CURRENT_FOLDER / "img"
CSS_PATH = CURRENT_FOLDER / "styles.css"
LOGO_PATH = IMAGES_FOLDER / "logo-nant-immo.svg"

# =============================================================
# FONCTIONS UTILITAIRES
# =============================================================

def load_css(file_path):
    """Charge un fichier CSS externe"""
    with open(file_path) as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

def image_to_base64(image_path):
    """Convertit une image en base64 pour l'afficher en HTML"""
    with open(image_path, "rb") as file:
        image_bytes = file.read()
    return base64.b64encode(image_bytes).decode()

def load_svg_as_text(svg_path):
    """Charge un SVG en tant que texte pour l'insérer inline"""
    with open(svg_path, "r", encoding="utf-8") as file:
        return file.read()

def load_data_from_db():
    # Adding 'connect_timeout' helps identify if it's a network vs. protocol issue
    conn = psycopg2.connect(DATABASE_URL, connect_timeout=10)
    conn.autocommit = True
    try:
        query = 'SELECT * FROM properties ORDER BY scraped_date::date DESC, id ASC'
        df = pd.read_sql_query(query, conn)
    finally:
        conn.close()
    return df

def format_price(price):
    """Formate le prix pour l'affichage"""
    if pd.notna(price):
        return f"{int(price):,} €".replace(",", " ")
    return "Prix non disponible"

def format_price_per_m2(price_per_m2):
    """Formate le prix au m² pour l'affichage sur les cartes"""
    if pd.notna(price_per_m2) and price_per_m2 > 0:
        return f"({int(round(price_per_m2)):,} €/m²)".replace(",", " ")
    return None

def parse_price_input(raw: str) -> int | None:
    """
    Parse a price text input that may contain spaces as thousand separators.
    Accepts: "400 000", "400000", "400.000", "400,000" → 400000
    Returns None if the string is empty or unparseable.
    """
    if not raw or not raw.strip():
        return None
    # Strip all non-digit characters (spaces, dots, commas)
    digits = re.sub(r'[^\d]', '', raw.strip())
    return int(digits) if digits else None

def format_price_input(value: int | None) -> str:
    """
    Format an integer back to a spaced string for display in text_input.
    400000 → "400 000"
    """
    if value is None:
        return ""
    return f"{value:,}".replace(",", " ")

def get_url_param_list(param_name, available_values):  # param_name kept for call-site compatibility, logic now uses sites+known_sites directly
    """Récupère une liste depuis les paramètres URL.

    Uses two URL params to distinguish user-deselected sources from new ones:
      - `sites`       : comma-separated list of currently selected sources
      - `known_sites` : comma-separated list of ALL sources known at last write

    A source in available_values that is absent from `known_sites` is brand
    new (added since the URL was last written) and is force-selected regardless
    of what `sites` says. A source in `known_sites` but absent from `sites`
    was deliberately deselected by the user and stays deselected.

    Falls back to selecting everything when no URL params are present.
    """
    selected_param = st.query_params.get("sites", "")
    known_param    = st.query_params.get("known_sites", "")

    if not selected_param and not known_param:
        return list(available_values)  # First ever load — select all

    selected_in_url = set(selected_param.split(",")) if selected_param else set()
    known_in_url    = set(known_param.split(","))    if known_param    else set()

    result = []
    for v in available_values:
        if v not in known_in_url:
            result.append(v)          # New source — always select
        elif v in selected_in_url:
            result.append(v)          # Was selected — keep selected
        # else: was known and deselected — leave out
    return result


def load_favorites_from_url():
    """Charge les favoris depuis l'URL"""
    fav_param = st.query_params.get("favorites", "")
    if fav_param:
        return set(int(x) for x in fav_param.split(",") if x)
    return set()


def clean_ouestfrance_title(title):
    """
    Strips boilerplate from OuestFrance titles.
    e.g. "Vente appartement 5 pièces - Nantes Zola 44 - 73 m²"
      -> "5 pièces - Nantes Zola - 73 m²"

    The scraper appends m² at the end, so the department code (e.g. "44")
    is no longer the last token. We strip it wherever it appears as a
    standalone 2-digit number preceded by a space, bounded by " - " or end.
    """
    # Remove leading "Vente appartement " (case-insensitive)
    title = re.sub(r'^Vente\s+appartement\s+', '', title, flags=re.IGNORECASE)
    # Remove department code: 2-digit number as a standalone word,
    # optionally followed by " - " or end of string
    title = re.sub(r'\s+\d{2}(?=\s*(?:-|$))', '', title)
    return title.strip()


# =============================================================
# CHARGEMENT DES RESSOURCES
# =============================================================

# CSS
load_css(CSS_PATH)

# Logo en base64
logo_base64 = image_to_base64(LOGO_PATH)

# For card logos (inline SVG)
logo_svg_text = load_svg_as_text(LOGO_PATH)

# Données (cache de 10 minutes)
DEV_MODE = True  # ← False en production

if DEV_MODE:
    # Pas de cache pendant le dev
    def get_data():
        return load_data_from_db()
else:
    # Cache en production
    @st.cache_data(ttl=600)
    def get_data():
        return load_data_from_db()

df = get_data()

# Compute price per m² as a derived column (never stored in DB — pure derivative)
df['price_per_m2'] = df.apply(
    lambda r: round(r['price_numeric'] / r['square_meters'], 2)
    if pd.notna(r['price_numeric']) and pd.notna(r['square_meters']) and r['square_meters'] > 0
    else None,
    axis=1
)

# Cast scraped_date to actual dates for range filtering
df['scraped_date_dt'] = pd.to_datetime(df['scraped_date'], errors='coerce').dt.date

# Favoris (session state)
if 'favorites' not in st.session_state:
    st.session_state.favorites = load_favorites_from_url()

# Applied filter state — persists across dialog open/close cycles.
# Initialised from URL params so bookmarked links still work on first load.
if 'applied_search' not in st.session_state:
    st.session_state.applied_search = st.query_params.get("search", "")
if 'applied_show_favorites' not in st.session_state:
    st.session_state.applied_show_favorites = False
if 'applied_price_min' not in st.session_state:
    _p = st.query_params.get("price_min")
    st.session_state.applied_price_min = format_price_input(int(_p) if _p else None)
if 'applied_price_max' not in st.session_state:
    _p = st.query_params.get("price_max")
    st.session_state.applied_price_max = format_price_input(int(_p) if _p else None)
if 'applied_m2_min' not in st.session_state:
    _v = st.query_params.get("m2_min")
    st.session_state.applied_m2_min = int(_v) if _v else None
if 'applied_m2_max' not in st.session_state:
    _v = st.query_params.get("m2_max")
    st.session_state.applied_m2_max = int(_v) if _v else None
if 'applied_sort_label' not in st.session_state:
    st.session_state.applied_sort_label = "Date (récent → ancien)"
if 'applied_selected_sites' not in st.session_state:
    st.session_state.applied_selected_sites = None  # None = not yet resolved; resolved after df loads
if 'applied_date_min' not in st.session_state:
    _d = st.query_params.get("date_min")
    st.session_state.applied_date_min = _d  # stored as ISO string or None
if 'applied_date_max' not in st.session_state:
    _d = st.query_params.get("date_max")
    st.session_state.applied_date_max = _d  # stored as ISO string or None

# =============================================================
# HEADER - Logo
# =============================================================

st.markdown(f"""
    <div class="header-container">
        <img src="data:image/svg+xml;base64,{logo_base64}" alt="Logo" class="header-logo">
        <p class="logo-text">Nant'Immo</p>
    </div>
""", unsafe_allow_html=True)

# =============================================================
# FLOAT FILTERS
# =============================================================

float_init()  # required once at app startup

# ── Filter dialog ──────────────────────────────────────────────
@st.dialog("⚙️ Filtres", width="large")
def filter_panel():
    search_term = st.text_input(
        "🔎 Chercher par mot-clé",
        value=st.query_params.get("search", ""),
        placeholder="Rechercher",
        key="search_term"
    )

    st.divider()

    show_favorites = st.checkbox("⭐ Favoris seulement", value=False, key="show_favorites")

    st.divider()

    # ------------------------------------------------------------------
    # Filtres de prix — text_input with thousand-space formatting
    # ------------------------------------------------------------------
    url_price_min = st.query_params.get("price_min")
    url_price_max = st.query_params.get("price_max")

    default_price_min_str = format_price_input(int(url_price_min) if url_price_min else None)
    default_price_max_str = format_price_input(int(url_price_max) if url_price_max else None)

    col1, col2 = st.columns(2)
    with col1:
        raw_price_min = st.text_input(
        "💰 Prix min. (€)", value=default_price_min_str, placeholder="ex: 150 000", key="raw_price_min"
        )
    with col2:
        raw_price_max = st.text_input(
        "💰 Prix max. (€)", value=default_price_max_str, placeholder="ex: 400 000", key="raw_price_max"
        )

    price_min = parse_price_input(raw_price_min)
    price_max = parse_price_input(raw_price_max)

    if raw_price_min.strip() and price_min is None:
        st.caption("⚠️ Prix min. invalide")
    if raw_price_max.strip() and price_max is None:
        st.caption("⚠️ Prix max. invalide")

    st.divider()

    # ------------------------------------------------------------------
    # Filtres de surface (m²)
    # ------------------------------------------------------------------
    m2_min_data = df['square_meters'].min()
    m2_max_data = df['square_meters'].max()

    min_m2 = int(m2_min_data) if pd.notna(m2_min_data) else 0
    max_m2 = int(m2_max_data) if pd.notna(m2_max_data) else 1000

    url_m2_min = st.query_params.get("m2_min")
    url_m2_max = st.query_params.get("m2_max")

    default_m2_min = int(url_m2_min) if url_m2_min else None
    default_m2_max = int(url_m2_max) if url_m2_max else None

    col1, col2 = st.columns(2)
    with col1:
        m2_min = st.number_input(
        "📏 Surface min. (m²)", min_value=0, max_value=max_m2, value=default_m2_min, step=5,
        placeholder="Pas de minimum", key="m2_min"
        )
    with col2:
        m2_max = st.number_input(
        "📏 Surface max. (m²)", min_value=0, max_value=max_m2, value=default_m2_max, step=5,
        placeholder="Pas de maximum", key="m2_max"
        )
    
    st.divider()

    # ------------------------------------------------------------------
    # Tri
    # ------------------------------------------------------------------
    SORT_OPTIONS = {
        "Date (récent → ancien)":  (None,              None),
        "Prix (croissant)":        ("price_numeric",   True),
        "Prix (décroissant)":      ("price_numeric",   False),
        "Prix/m² (croissant)":     ("price_per_m2",    True),
        "Prix/m² (décroissant)":   ("price_per_m2",    False),
        "Surface (croissante)":    ("square_meters",   True),
        "Surface (décroissante)":  ("square_meters",   False),
    }

    sort_label = st.selectbox(
        "↕️ Trier par", options=list(SORT_OPTIONS.keys()), index=0, key="sort_label"
    )
    sort_col, sort_asc = SORT_OPTIONS[sort_label]

    st.divider()

    # ------------------------------------------------------------------
    # Filtre Sources
    # ------------------------------------------------------------------
    st.markdown("### 🏢 Sources")
    with st.expander('Sources', expanded=False):
        available_sites = sorted(df['site'].unique())
        default_sites = get_url_param_list('sites', available_sites)
        
        selected_sites = []
        for site in available_sites:
            is_selected = st.checkbox(
                site, 
                value=(site in default_sites), 
                key=f"site_{site}"
            )
            if is_selected:
                selected_sites.append(site)

    st.divider()

    # ------------------------------------------------------------------
    # Filtre Dates
    # ------------------------------------------------------------------
    date_min_data = df['scraped_date_dt'].min()
    date_max_data = df['scraped_date_dt'].max()

    url_date_min = st.query_params.get("date_min")
    url_date_max = st.query_params.get("date_max")

    try:
        default_date_min = date.fromisoformat(url_date_min) if url_date_min else date_min_data
        default_date_max = date.fromisoformat(url_date_max) if url_date_max else date_max_data
    except (ValueError, TypeError):
        default_date_min = date_min_data
        default_date_max = date_max_data

    default_date_min = max(default_date_min, date_min_data)
    default_date_max = min(default_date_max, date_max_data)

    date_range = st.date_input(
        "📅 Période", value=(default_date_min, default_date_max),
        min_value=date_min_data, max_value=date_max_data, format="DD/MM/YYYY", key="date_range"
    )

    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        selected_date_min, selected_date_max = date_range
    elif isinstance(date_range, (list, tuple)) and len(date_range) == 1:
        selected_date_min = date_range[0]
        selected_date_max = date_max_data
    else:
        selected_date_min = date_range
        selected_date_max = date_max_data

    st.divider()

    # Apply button — copies all local widget values into persistent session
    # state keys, then reruns. The main body reads exclusively from those keys.
    if st.button("Appliquer", use_container_width=True, type="primary", key="fab_apply_filters"):
        st.session_state.applied_search           = search_term
        st.session_state.applied_show_favorites   = show_favorites
        st.session_state.applied_price_min        = raw_price_min
        st.session_state.applied_price_max        = raw_price_max
        st.session_state.applied_m2_min           = m2_min
        st.session_state.applied_m2_max           = m2_max
        st.session_state.applied_sort_label       = sort_label
        st.session_state.applied_selected_sites   = selected_sites
        st.session_state.applied_date_min         = selected_date_min.isoformat()
        st.session_state.applied_date_max         = selected_date_max.isoformat()
        st.rerun()

    st.divider()

    # Infos en bas
    st.caption(f"Mis à jour: {df['scraped_date'].max()}")
    st.caption(f"Total: {len(df)} annonces")

# ── FAB button ─────────────────────────────────────────────────
fab = st.container()
with fab:
    # Style the button as a round FAB
    st.markdown("""
    <div class="fab-anchor"/>
    """, unsafe_allow_html=True)

    if st.button("⚙\uFE0E", key="fab_open_filters"):
        filter_panel()

# =============================================================
# RESOLVE APPLIED FILTER VALUES
# (reads from session state written by the dialog's Apply button)
# =============================================================

available_sites  = sorted(df['site'].unique())
date_min_data    = df['scraped_date_dt'].min()
date_max_data    = df['scraped_date_dt'].max()

# Sites: first Apply hasn't happened yet → fall back to URL params / select-all
if st.session_state.applied_selected_sites is None:
    selected_sites = get_url_param_list('sites', available_sites)
else:
    selected_sites = st.session_state.applied_selected_sites

# Search
search_term    = st.session_state.applied_search
show_favorites = st.session_state.applied_show_favorites

# Price
raw_price_min  = st.session_state.applied_price_min
raw_price_max  = st.session_state.applied_price_max
price_min      = parse_price_input(raw_price_min)
price_max      = parse_price_input(raw_price_max)

# Surface
m2_min = st.session_state.applied_m2_min
m2_max = st.session_state.applied_m2_max

# Sort
SORT_OPTIONS = {
    "Date (récent → ancien)":  (None,            None),
    "Prix (croissant)":        ("price_numeric",  True),
    "Prix (décroissant)":      ("price_numeric",  False),
    "Prix/m² (croissant)":     ("price_per_m2",   True),
    "Prix/m² (décroissant)":   ("price_per_m2",   False),
    "Surface (croissante)":    ("square_meters",  True),
    "Surface (décroissante)":  ("square_meters",  False),
}
sort_label = st.session_state.applied_sort_label
sort_col, sort_asc = SORT_OPTIONS[sort_label]

# Dates
try:
    selected_date_min = date.fromisoformat(st.session_state.applied_date_min) if st.session_state.applied_date_min else date_min_data
    selected_date_max = date.fromisoformat(st.session_state.applied_date_max) if st.session_state.applied_date_max else date_max_data
except (ValueError, TypeError):
    selected_date_min = date_min_data
    selected_date_max = date_max_data

# Clamp to actual data bounds (guards against stale session values)
selected_date_min = max(selected_date_min, date_min_data)
selected_date_max = min(selected_date_max, date_max_data)

# =============================================================
# MISE À JOUR URL
# =============================================================

st.query_params.update({
    "sites":       ",".join(selected_sites),
    "known_sites": ",".join(available_sites),
    "date_min":    selected_date_min.isoformat(),
    "date_max":    selected_date_max.isoformat(),
    "search":      search_term,
    "price_min":   str(price_min) if price_min is not None else "",
    "price_max":   str(price_max) if price_max is not None else "",
    "m2_min":      str(m2_min) if m2_min else "",
    "m2_max":      str(m2_max) if m2_max else "",
    "favorites":   ",".join(str(x) for x in st.session_state.favorites),
})

# =============================================================
# FILTRAGE DES DONNÉES
# =============================================================

if not selected_sites:
    st.warning("⚠️ Sélectionnez au moins une source")
    filtered_df = pd.DataFrame()
else:
    filtered_df = df.copy()

    # Filtrer par site
    filtered_df = filtered_df[filtered_df['site'].isin(selected_sites)]

    # Filtrer par plage de dates
    filtered_df = filtered_df[
        (filtered_df['scraped_date_dt'] >= selected_date_min) &
        (filtered_df['scraped_date_dt'] <= selected_date_max)
    ]

    # Filtrer par recherche
    if search_term:
        search_mask = (
            filtered_df['title'].str.contains(search_term, case=False, na=False) |
            filtered_df['description'].str.contains(search_term, case=False, na=False)
        )
        filtered_df = filtered_df[search_mask]

    # Filtrer par prix min
    if price_min is not None:
        filtered_df = filtered_df[filtered_df['price_numeric'] >= price_min]

    # Filtrer par prix max
    if price_max is not None:
        filtered_df = filtered_df[filtered_df['price_numeric'] <= price_max]

    # Filtrer par surface min
    if m2_min is not None:
        filtered_df = filtered_df[
            (filtered_df['square_meters'] >= m2_min) |
            (filtered_df['square_meters'].isna())  # Garde les annonces sans m² renseignés
        ]

    # Filtrer par surface max
    if m2_max is not None:
        filtered_df = filtered_df[
            (filtered_df['square_meters'] <= m2_max) |
            (filtered_df['square_meters'].isna())  # Garde les annonces sans m² renseignés
        ]

    # Filtrer par favoris
    if show_favorites:
        filtered_df = filtered_df[filtered_df['id'].isin(st.session_state.favorites)]

    # Trier
    if sort_col is None:
        # Default: preserve DB order (created_at DESC, scrape_order ASC)
        # The DataFrame already arrives in this order from the query — no-op.
        pass
    elif sort_col in ('price_per_m2', 'price_numeric', 'square_meters'):
        # Listings with no value sink to the bottom regardless of direction
        filtered_df = filtered_df.sort_values(
            by=sort_col,
            ascending=sort_asc,
            na_position='last'
        )
    else:
        filtered_df = filtered_df.sort_values(
            by=sort_col,
            ascending=sort_asc
        )

# =============================================================
# UI - STATISTIQUES ON TOP
# =============================================================

st.markdown(f"""
    <div class="stats-container">
        <div class="stat-item">
            <p class="stat-label">Annonces:</p>
            <p class="stat-value">{len(filtered_df)} / {len(df)}</p>
        </div>
        <div class="stat-item">
            <p class="stat-label">Agences:</p>
            <p class="stat-value">{filtered_df['site'].nunique()} / {df['site'].nunique()}</p>
        </div>
        <div class="stat-item">
            <p class="stat-label">Mis à jour:</p>
            <p class="stat-value">{df['scraped_date'].max()}</p>
        </div>
    </div>
""", unsafe_allow_html=True)

st.divider()

# =============================================================
# UI - LISTE DES ANNONCES
# =============================================================

if len(filtered_df) == 0:
    if not selected_sites:
        pass  # Warning already shown above
    else:
        st.info("Aucune annonce avec ces filtres")
else:
    # Afficher les cartes en 3 colonnes
    cols = st.columns(3)
    
    for idx, (_, row) in enumerate(filtered_df.iterrows()):
        col = cols[idx % 3]

        # Prix principal
        price_display = format_price(row['price_numeric'])

        # Prix au m² (shown only when both values are available)
        price_m2_display = format_price_per_m2(row['price_per_m2'])

        # Titre : nettoyer le préfixe/suffixe pour OuestFrance
        raw_title = row['title'] if pd.notna(row['title']) else ''
        if row['site'] == 'Ouest France Immo':
            title = clean_ouestfrance_title(raw_title)
        else:
            title = raw_title

        # Description : tronquer à 100 caractères
        raw_desc = row['description'] if pd.notna(row['description']) else ''
        description = (raw_desc[:100] + '…') if len(raw_desc) > 100 else (raw_desc or 'Pas de description')

        is_favorited = row['id'] in st.session_state.favorites
        heart_icon = "❤\uFE0E"
        button_key = f"fav_{row['id']}"
        heart_color = "#10B981" if is_favorited else "var(--text-gray)"
        st.markdown(
            f"<style>.st-key-fav_{row['id']} button p {{ color: {heart_color} !important; font-size: 1.6rem !important; }}</style>",
            unsafe_allow_html=True
        )

        # Build price bar. Constructed as a single-line f-string (no triple
        # quotes, no intermediate variable passed into another f-string) to
        # avoid any whitespace/newline artefacts that can confuse Streamlit's
        # markdown-to-HTML pipeline.
        if price_m2_display:
            price_block = f'<div class="card-price-container"><span>🏷️</span><span class="card-price">{price_display}</span><span class="card-price-m2">{price_m2_display}</span></div>'
        else:
            price_block = f'<div class="card-price-container"><span>🏷️</span><span class="card-price">{price_display}</span></div>'

        with col:
            card_html = f"""
            <div class="card-wrapper">
                <a href="{row['url']}" target="_blank" class="card-link">
                    <div class="card">
                        <img src="{row['image_url']}" class="card-image" alt="Photo">
                        <div class="card-meta">
                                <div class="card-logo-wrapper">{logo_svg_text}</div>
                                <div class="card-meta-text">{row['site']} · {row['scraped_date']}</div>
                        </div>
                        <div class="card-title">{title}</div>
                        <div class="card-description">{description}</div>
                        {price_block}
                    </div>
                </a>
            </div>
            """
            st.markdown(card_html, unsafe_allow_html=True)
            
            # Bouton favori
            if st.button(heart_icon, key=button_key, help="is_fav" if is_favorited else "not_fav"):
                if is_favorited:
                    st.session_state.favorites.remove(row['id'])
                else:
                    st.session_state.favorites.add(row['id'])
                st.rerun()