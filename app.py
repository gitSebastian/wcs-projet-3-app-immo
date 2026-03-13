# =============================================================
# streamlit run WCS/github/wcs-projet-3-app-immo/app.py --server.address 192.168.1.134
# =============================================================

import streamlit as st
import pandas as pd
import psycopg2
import base64
import os
import re
from datetime import date, timedelta
from pathlib import Path

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
        query = 'SELECT * FROM properties ORDER BY scraped_date DESC, scrape_order ASC NULLS LAST, id DESC'
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
        return f"{int(round(price_per_m2)):,} €/m²".replace(",", " ")
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

def get_url_param_list(param_name, available_values):
    """Récupère une liste depuis les paramètres URL"""
    param_value = st.query_params.get(param_name, "")
    if param_value:
        selected = param_value.split(",")
        return [v for v in selected if v in available_values]
    return list(available_values)  # Par défaut: tout sélectionné


def load_favorites_from_url():
    """Charge les favoris depuis l'URL"""
    fav_param = st.query_params.get("favorites", "")
    if fav_param:
        return set(int(x) for x in fav_param.split(",") if x)
    return set()


def clean_ouestfrance_title(title):
    """
    Strips boilerplate from OuestFrance titles.
    e.g. "Vente appartement 5 pièces - Nantes Procé - Monselet 44"
      -> "5 pièces - Nantes Procé - Monselet"
    """
    # Remove leading "Vente appartement " (case-insensitive)
    title = re.sub(r'^Vente\s+appartement\s+', '', title, flags=re.IGNORECASE)
    # Remove trailing department code: 1–5 digits at end of string
    title = re.sub(r'\s+\d{2,5}\s*$', '', title)
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
# SIDEBAR - Filtres
# =============================================================

# Valeurs disponibles
available_sites = sorted(df['site'].unique())

# Date bounds from data
date_min_data = df['scraped_date_dt'].min()
date_max_data = df['scraped_date_dt'].max()

# Recherche
search_term = st.sidebar.text_input(
    "🔎  Chercher",
    value=st.query_params.get("search", ""),
    placeholder="Rechercher"
)

st.sidebar.divider()

# Favoris seulement
show_favorites = st.sidebar.checkbox("⭐ Favoris seulement", value=False)

st.sidebar.divider()

# ------------------------------------------------------------------
# Filtres de prix — text_input with thousand-space formatting
# ------------------------------------------------------------------
url_price_min = st.query_params.get("price_min")
url_price_max = st.query_params.get("price_max")

default_price_min_str = format_price_input(int(url_price_min) if url_price_min else None)
default_price_max_str = format_price_input(int(url_price_max) if url_price_max else None)

raw_price_min = st.sidebar.text_input(
    "💰 Prix min. (€)",
    value=default_price_min_str,
    placeholder="ex: 150 000"
)
raw_price_max = st.sidebar.text_input(
    "💰 Prix max. (€)",
    value=default_price_max_str,
    placeholder="ex: 400 000"
)

price_min = parse_price_input(raw_price_min)
price_max = parse_price_input(raw_price_max)

# Show a validation hint if the user typed something unparseable
if raw_price_min.strip() and price_min is None:
    st.sidebar.caption("⚠️ Prix min. invalide")
if raw_price_max.strip() and price_max is None:
    st.sidebar.caption("⚠️ Prix max. invalide")

st.sidebar.divider()

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

m2_min = st.sidebar.number_input(
    "📏 Surface min. (m²)", 
    min_value=0, 
    max_value=max_m2,
    value=default_m2_min,
    step=5,
    placeholder="Pas de minimum"
)

m2_max = st.sidebar.number_input(
    "📏 Surface max. (m²)", 
    min_value=0, 
    max_value=max_m2,
    value=default_m2_max,
    step=5,
    placeholder="Pas de maximum"
)

st.sidebar.divider()

# ------------------------------------------------------------------
# Tri
# ------------------------------------------------------------------
SORT_OPTIONS = {
    "Date (récent → ancien)": ("scraped_date_dt", False),
    "Prix (croissant)":        ("price_numeric",   True),
    "Prix (décroissant)":      ("price_numeric",   False),
    "Prix/m² (croissant)":     ("price_per_m2",    True),
    "Prix/m² (décroissant)":   ("price_per_m2",    False),
    "Surface (croissante)":    ("square_meters",   True),
    "Surface (décroissante)":  ("square_meters",   False),
}

sort_label = st.sidebar.selectbox(
    "↕️ Trier par",
    options=list(SORT_OPTIONS.keys()),
    index=0
)
sort_col, sort_asc = SORT_OPTIONS[sort_label]

st.sidebar.divider()

# Filtre Sources
with st.sidebar.expander('🏢 Sources', expanded=True):
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

st.sidebar.divider()

# ------------------------------------------------------------------
# Filtre Dates — date_input range (replaces checkbox list)
# ------------------------------------------------------------------
# Restore range from URL params if present
url_date_min = st.query_params.get("date_min")
url_date_max = st.query_params.get("date_max")

try:
    default_date_min = date.fromisoformat(url_date_min) if url_date_min else date_min_data
    default_date_max = date.fromisoformat(url_date_max) if url_date_max else date_max_data
except (ValueError, TypeError):
    default_date_min = date_min_data
    default_date_max = date_max_data

# Clamp defaults to actual data bounds (guards against stale URL params)
default_date_min = max(default_date_min, date_min_data)
default_date_max = min(default_date_max, date_max_data)

date_range = st.sidebar.date_input(
    "📅 Période",
    value=(default_date_min, default_date_max),
    min_value=date_min_data,
    max_value=date_max_data,
    format="DD/MM/YYYY",
)

# date_input returns a tuple of 1 or 2 dates depending on user interaction
if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
    selected_date_min, selected_date_max = date_range
elif isinstance(date_range, (list, tuple)) and len(date_range) == 1:
    # User has only picked the start date — keep max open
    selected_date_min = date_range[0]
    selected_date_max = date_max_data
else:
    # Single date object (shouldn't happen with range mode, but be safe)
    selected_date_min = date_range
    selected_date_max = date_max_data

st.sidebar.divider()

# Infos en bas du sidebar
st.sidebar.caption(f"Mis à jour: {df['scraped_date'].max()}")
st.sidebar.caption(f"Total: {len(df)} annonces")

# =============================================================
# MISE À JOUR URL
# =============================================================

st.query_params.update({
    "sites":     ",".join(selected_sites),
    "date_min":  selected_date_min.isoformat(),
    "date_max":  selected_date_max.isoformat(),
    "search":    search_term,
    "price_min": str(price_min) if price_min is not None else "",
    "price_max": str(price_max) if price_max is not None else "",
    "m2_min":    str(m2_min) if m2_min else "",
    "m2_max":    str(m2_max) if m2_max else "",
    "favorites": ",".join(str(x) for x in st.session_state.favorites),
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
    # For price_per_m2 and price_numeric sorts, listings with no value sink to the bottom
    # regardless of sort direction, so real listings always surface first.
    if sort_col in ('price_per_m2', 'price_numeric', 'square_meters'):
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
        heart_icon = "❤️" if is_favorited else "🤍"

        # Build the price block: show €/m² badge only when available
        if price_m2_display:
            price_block = f"""
                        <div class="card-price-container">
                            <span>🏷️</span>
                            <span class="card-price">{price_display}</span>
                            <span class="card-price-m2">{price_m2_display}</span>
                        </div>
            """
        else:
            price_block = f"""
                        <div class="card-price-container">
                            <span>🏷️</span>
                            <span class="card-price">{price_display}</span>
                        </div>
            """

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
            if st.button(heart_icon, key=f"fav_{row['id']}"):
                if is_favorited:
                    st.session_state.favorites.remove(row['id'])
                else:
                    st.session_state.favorites.add(row['id'])
                st.rerun()
