# =============================================================
# streamlit run WCS/github/wcs-projet-3-app-immo/app.py --server.address 192.168.1.134
# =============================================================

import streamlit as st
import pandas as pd
import psycopg2
import base64
import os
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
        query = 'SELECT * FROM properties ORDER BY scraped_date DESC, id DESC'
        df = pd.read_sql_query(query, conn)
    finally:
        conn.close()
    return df

def format_price(price):
    """Formate le prix pour l'affichage"""
    if pd.notna(price):
        return f"{int(price):,} €".replace(",", " ")
    return "Prix non disponible"


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
available_dates = sorted(df['scraped_date'].unique(), reverse=True)

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

# Filtres de prix
price_min_data = df['price_numeric'].min()
price_max_data = df['price_numeric'].max()

min_price = int(price_min_data) if pd.notna(price_min_data) else 0
max_price = int(price_max_data) if pd.notna(price_max_data) else 100000000

# Valeurs par défaut depuis URL
url_price_min = st.query_params.get("price_min")
url_price_max = st.query_params.get("price_max")

default_price_min = int(url_price_min) if url_price_min else None
default_price_max = int(url_price_max) if url_price_max else None

price_min = st.sidebar.number_input(
    "💰 Prix min. (€)", 
    min_value=0, 
    max_value=max_price,
    value=default_price_min,
    step=10000,
    placeholder="Pas de minimum"
)

price_max = st.sidebar.number_input(
    "💰 Prix max. (€)", 
    min_value=0, 
    max_value=max_price,
    value=default_price_max,
    step=10000,
    placeholder="Pas de maximum"
)

st.sidebar.divider()

# Filtres de surface (m²)
m2_min_data = df['square_meters'].min()
m2_max_data = df['square_meters'].max()

min_m2 = int(m2_min_data) if pd.notna(m2_min_data) else 0
max_m2 = int(m2_max_data) if pd.notna(m2_max_data) else 1000

# Valeurs par défaut depuis URL
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

# Filtre Dates
with st.sidebar.expander('📅 Dates', expanded=True):
    default_dates = get_url_param_list('dates', available_dates)
    selected_dates = []
    
    for date in available_dates:
        is_selected = st.checkbox(
            str(date), 
            value=(date in default_dates), 
            key=f"date_{date}"
        )
        if is_selected:
            selected_dates.append(date)

st.sidebar.divider()

# Infos en bas du sidebar
st.sidebar.caption(f"Mis à jour: {df['scraped_date'].max()}")
st.sidebar.caption(f"Total: {len(df)} annonces")

# =============================================================
# MISE À JOUR URL
# =============================================================

st.query_params.update({
    "sites": ",".join(selected_sites),
    "dates": ",".join(selected_dates),
    "search": search_term,
    "price_min": str(price_min) if price_min else "",
    "price_max": str(price_max) if price_max else "",
    "m2_min": str(m2_min) if m2_min else "",
    "m2_max": str(m2_max) if m2_max else "",
    "favorites": ",".join(str(x) for x in st.session_state.favorites),
})

# =============================================================
# FILTRAGE DES DONNÉES
# =============================================================

# Vérifier qu'au moins un filtre est sélectionné
if not selected_sites or not selected_dates:
    st.warning("⚠️ Sélectionnez au moins une source et une date")
    filtered_df = pd.DataFrame()
else:
    # Commencer avec toutes les données
    filtered_df = df.copy()
    
    # Filtrer par site
    filtered_df = filtered_df[filtered_df['site'].isin(selected_sites)]
    
    # Filtrer par date
    filtered_df = filtered_df[filtered_df['scraped_date'].isin(selected_dates)]
    
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
    # Afficher un message si aucun résultat
    if selected_sites and selected_dates:
        st.info("Aucune annonce avec ces filtres")
else:
    # Afficher les cartes en 3 colonnes
    cols = st.columns(3)
    
    for idx, (_, row) in enumerate(filtered_df.iterrows()):
        # Déterminer la colonne (0, 1, ou 2)
        col = cols[idx % 3]
        
        # Préparer les données de la carte
        price_display = format_price(row['price_numeric'])
        description = row['description'] if pd.notna(row['description']) else 'Pas de description'
        is_favorited = row['id'] in st.session_state.favorites
        heart_icon = "❤️" if is_favorited else "🤍"

        with col:
            # Carte HTML
            card_html = f"""
            <div class="card-wrapper">
                <a href="{row['url']}" target="_blank" class="card-link">
                    <div class="card">
                        <img src="{row['image_url']}" class="card-image" alt="Photo">
                        <div class="card-meta">
                                <div class="card-logo-wrapper">{logo_svg_text}</div>
                                <div class="card-meta-text">{row['site']} · {row['scraped_date']}</div>
                        </div>
                        <div class="card-title">{row['title']}</div>
                        <div class="card-description">{description}</div>
                        <div class="card-price-container">
                            <span>🏷️</span>
                            <span class="card-price">{price_display}</span>
                        </div>
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