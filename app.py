# =============================================================
# streamlit run WCS/github/wcs-projet-3-app-immo/app.py --server.address 192.168.1.35
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

PAGE_SIZE = 51  # Cards per page -- change here to test different values

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
        query = 'SELECT * FROM properties ORDER BY id DESC'
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
DEV_MODE = os.environ.get("DEV_MODE", "false").lower() == "true"

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
# Write favorites to URL immediately — tightens the PTR race window so a
# reload fired before the bottom-of-script query_params.update() still
# captures the current state.
st.query_params["favorites"] = ",".join(str(x) for x in st.session_state.favorites)

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
    # Get sort from URL, default to "Date (récent → ancien)"
    url_sort = st.query_params.get("sort", "Date (récent → ancien)")
    # Validate it's a valid sort option
    SORT_OPTIONS = {
        "Date (récent → ancien)":  (None,              None),
        "Prix (croissant)":        ("price_numeric",   True),
        "Prix (décroissant)":      ("price_numeric",   False),
        "Prix/m² (croissant)":     ("price_per_m2",    True),
        "Prix/m² (décroissant)":   ("price_per_m2",    False),
        "Surface (croissante)":    ("square_meters",   True),
        "Surface (décroissante)":  ("square_meters",   False),
    }
    if url_sort not in SORT_OPTIONS:
        url_sort = "Date (récent → ancien)"
    st.session_state.applied_sort_label = url_sort
if 'applied_selected_sites' not in st.session_state:
    st.session_state.applied_selected_sites = None  # None = not yet resolved; resolved after df loads
if 'applied_date_min' not in st.session_state:
    _d = st.query_params.get("date_min")
    st.session_state.applied_date_min = _d  # stored as ISO string or None
if 'applied_date_max' not in st.session_state:
    _d = st.query_params.get("date_max")
    st.session_state.applied_date_max = _d  # stored as ISO string or None
if 'current_page' not in st.session_state:
    _pg = st.query_params.get("page", "0")
    st.session_state.current_page = int(_pg) if _pg.isdigit() else 0

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

# ── Compute whether any filter is currently active (used to show Reset button) ──
# Evaluated once per main-body render, captured by the filter_panel closure.
# "Active" means any applied value differs from the all-data default.
_all_sites = sorted(df['site'].unique())
_applied_sites = st.session_state.get('applied_selected_sites') or _all_sites
_date_min_data = df['scraped_date_dt'].min()
_date_max_data = df['scraped_date_dt'].max()
_applied_date_min = st.session_state.get('applied_date_min')
_applied_date_max = st.session_state.get('applied_date_max')
_filters_are_active = any([
    bool(st.session_state.get('applied_search', '')),
    st.session_state.get('applied_show_favorites', False),
    bool(st.session_state.get('applied_price_min', '')),
    bool(st.session_state.get('applied_price_max', '')),
    st.session_state.get('applied_m2_min') is not None,
    st.session_state.get('applied_m2_max') is not None,
    st.session_state.get('applied_sort_label', 'Date (récent → ancien)') != 'Date (récent → ancien)',
    set(_applied_sites) != set(_all_sites),
    _applied_date_min is not None and date.fromisoformat(_applied_date_min) > _date_min_data,
    _applied_date_max is not None and date.fromisoformat(_applied_date_max) < _date_max_data,
])

# ── Filter dialog ──────────────────────────────────────────────
@st.dialog("⚙️ Filtres", width="large")
def filter_panel():
    # Reset all filters — only shown when something is active. Top of dialog
    # so it's the first thing seen when opening with filters applied.
    if _filters_are_active and st.button("🔄 Réinitialiser les filtres", use_container_width=True, key="fab_reset_filters"):
        keys_to_clear = [
            'applied_search', 'applied_show_favorites',
            'applied_price_min', 'applied_price_max',
            'applied_m2_min', 'applied_m2_max',
            'applied_sort_label', 'applied_selected_sites',
            'applied_date_min', 'applied_date_max',
            'current_page', 'sites_multiselect',
        ]
        for k in keys_to_clear:
            if k in st.session_state:
                del st.session_state[k]
        st.query_params.clear()
        st.rerun()

    st.divider()

    search_term = st.text_input(
        "🔎 Chercher par mot-clé",
        value=st.session_state.applied_search,
        placeholder="Rechercher",
        key="search_term"
    )

    st.divider()

    show_favorites = st.checkbox("⭐ Favoris seulement", value=st.session_state.applied_show_favorites, key="show_favorites")

    st.divider()

    # ------------------------------------------------------------------
    # Filtres de prix — text_input with thousand-space formatting
    # ------------------------------------------------------------------
    # Use session state values (initialized from URL on first load)
    default_price_min_str = st.session_state.applied_price_min
    default_price_max_str = st.session_state.applied_price_max

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

    # Use session state values (initialized from URL on first load)
    default_m2_min = st.session_state.applied_m2_min
    default_m2_max = st.session_state.applied_m2_max

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

    # Get current sort label from session state (which is initialized from URL on first load)
    current_sort_label = st.session_state.applied_sort_label
    # Ensure it's a valid option
    if current_sort_label not in SORT_OPTIONS:
        current_sort_label = "Date (récent → ancien)"
    
    sort_label = st.selectbox(
        "↕️ Trier par", 
        options=list(SORT_OPTIONS.keys()), 
        index=list(SORT_OPTIONS.keys()).index(current_sort_label),
        key="sort_label"
    )
    sort_col, sort_asc = SORT_OPTIONS[sort_label]

    st.divider()

    # ------------------------------------------------------------------
    # Filtre Sources
    # ------------------------------------------------------------------
    available_sites = sorted(df['site'].unique())

    # Determine default sites: use session state if set, otherwise URL params
    if st.session_state.applied_selected_sites is not None:
        default_sites = st.session_state.applied_selected_sites
    else:
        default_sites = get_url_param_list('sites', available_sites)

    st.markdown("🏢 **Sources**")
    col_all, col_none = st.columns(2)
    with col_all:
        if st.button("✓ Tout", use_container_width=True, key="sites_select_all"):
            st.session_state['sites_multiselect'] = available_sites
    with col_none:
        if st.button("× Aucun", use_container_width=True, key="sites_select_none"):
            st.session_state['sites_multiselect'] = []

    # Seed the widget key on first render so it reflects default_sites.
    # After that the widget owns its own state — only the buttons above
    # (or a Reset) should overwrite it externally.
    if 'sites_multiselect' not in st.session_state:
        st.session_state['sites_multiselect'] = default_sites

    selected_sites = st.multiselect(
        "Sources actives",
        options=available_sites,
        key='sites_multiselect',
        label_visibility='collapsed',
        placeholder="Choisir les agences",
    )

    st.divider()

    # ------------------------------------------------------------------
    # Filtre Dates
    # ------------------------------------------------------------------
    date_min_data = df['scraped_date_dt'].min()
    date_max_data = df['scraped_date_dt'].max()

    # Use session state values (initialized from URL on first load)
    try:
        default_date_min = date.fromisoformat(st.session_state.applied_date_min) if st.session_state.applied_date_min else date_min_data
        default_date_max = date.fromisoformat(st.session_state.applied_date_max) if st.session_state.applied_date_max else date_max_data
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
        st.session_state.current_page             = 0  # reset on every filter change
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

    # Fix FAB position directly via JS -- CSS right:0 is unreliable in Safari
    # when the element's static flow position is on the left. Inline style wins
    # over any stylesheet rule in all browsers.
    st.components.v1.html("""
        <script>
        (function() {
            if (window.parent.__nantimmoFABFixed) return;
            var fix = function() {
                var fab = window.parent.document.querySelector('.st-key-fab_open_filters');
                if (!fab) { setTimeout(fix, 50); return; }
                fab.style.setProperty('position', 'fixed', 'important');
                fab.style.setProperty('bottom', '5rem', 'important');
                fab.style.setProperty('right', '0', 'important');
                fab.style.setProperty('left', 'auto', 'important');
                fab.style.setProperty('width', '3.5rem', 'important');
                fab.style.setProperty('z-index', '9999', 'important');
                window.parent.__nantimmoFABFixed = true;
            };
            fix();
        })();
        </script>
    """, height=0)

    # Pull-to-refresh for standalone PWA (home screen icon).
    # Injected into the parent frame via the same pattern as the scroll-to-top
    # observer. Hidden by CSS in normal browser tabs -- only activates under
    # @media (display-mode: standalone). The overscrollBehaviorY trick suppresses
    # iOS rubber-band during the drag so the custom indicator controls the visual.
    st.components.v1.html("""
        <script>
        (function() {
            if (window.parent.__nantimmoPTR) return;
            window.parent.__nantimmoPTR = true;

            var doc = window.parent.document;

            // Spinner element -- always in DOM, visibility driven by opacity + translateY
            var spinner = doc.createElement('div');
            spinner.id = 'ptr-spinner';
            spinner.innerHTML = '&#8635;';
            doc.body.appendChild(spinner);

            var style = doc.createElement('style');
            style.textContent = `
                #ptr-spinner {
                    position: fixed;
                    top: 12px;
                    left: 50%;
                    width: 40px;
                    height: 40px;
                    border-radius: 50%;
                    background: #10B981;
                    color: white;
                    font-size: 22px;
                    display: none;
                    align-items: center;
                    justify-content: center;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.3);
                    z-index: 99999;
                    pointer-events: none;
                    opacity: 0;
                    transform: translateX(-50%) translateY(-56px);
                    /* No transition here -- we drive position on every touchmove tick */
                }
                @media all and (display-mode: standalone) {
                    #ptr-spinner { display: flex; }
                }
                #ptr-spinner.ptr-committed {
                    /* Snap to resting position and spin while reload fires */
                    opacity: 1 !important;
                    transform: translateX(-50%) translateY(0px) !important;
                    transition: transform 0.15s ease, opacity 0.15s ease;
                    animation: ptr-spin 0.5s linear infinite;
                }
                @keyframes ptr-spin {
                    from { transform: translateX(-50%) translateY(0px) rotate(0deg); }
                    to   { transform: translateX(-50%) translateY(0px) rotate(360deg); }
                }
            `;
            doc.head.appendChild(style);

            var startY = 0;
            var THRESHOLD = 72;      // drag distance before commit (px)
            var MAX_DRAG = 80;       // caps visual travel
            var pulling = false;
            var triggered = false;

            function getScrollEl() {
                return doc.querySelector('[data-testid="stMain"]');
            }

            function isDialogOpen() {
                return !!doc.querySelector('[data-baseweb="modal"]');
            }

            doc.addEventListener('touchstart', function(e) {
                if (isDialogOpen()) return;
                var el = getScrollEl();
                if (!el || el.scrollTop > 0) return;
                startY = e.touches[0].clientY;
                pulling = true;
                triggered = false;
                // Remove committed class from any previous cycle
                spinner.classList.remove('ptr-committed');
            }, { passive: true });

            doc.addEventListener('touchmove', function(e) {
                if (!pulling) return;
                if (isDialogOpen()) { pulling = false; return; }
                var el = getScrollEl();
                if (!el || el.scrollTop > 0) { pulling = false; return; }

                var dy = e.touches[0].clientY - startY;
                if (dy <= 0) {
                    spinner.style.opacity = '0';
                    spinner.style.transform = 'translateX(-50%) translateY(-56px)';
                    return;
                }

                // Suppress iOS native rubber-band so our indicator owns the visual
                el.style.overscrollBehaviorY = 'contain';

                // Resistance curve: feels like pulling against a spring
                var travel = Math.min(dy * 0.55, MAX_DRAG);
                var progress = Math.min(travel / MAX_DRAG, 1);

                // Fade in and slide down proportionally to drag distance
                spinner.style.opacity = String(progress);
                spinner.style.transform = 'translateX(-50%) translateY(' + (travel - 56) + 'px)';

                if (dy >= THRESHOLD && !triggered) {
                    triggered = true;
                }
            }, { passive: true });

            doc.addEventListener('touchend', function() {
                if (!pulling) return;
                pulling = false;

                var el = getScrollEl();
                if (el) el.style.overscrollBehaviorY = '';

                if (triggered) {
                    // Snap spinner to final position and keep it visible during reload
                    spinner.classList.add('ptr-committed');
                    spinner.style.opacity = '';
                    spinner.style.transform = '';
                    setTimeout(function() {
                        window.parent.location.reload();
                    }, 350);
                } else {
                    // Fade out and slide back up
                    spinner.style.transition = 'transform 0.2s ease, opacity 0.2s ease';
                    spinner.style.opacity = '0';
                    spinner.style.transform = 'translateX(-50%) translateY(-56px)';
                    setTimeout(function() { spinner.style.transition = ''; }, 220);
                }
            }, { passive: true });
        })();
        </script>
    """, height=0)

    # localStorage safety net for favorites.
    # Primary fix for iOS PWA: when the app is closed and reopened, iOS
    # restores it to the base URL with no query params, wiping URL-stored
    # favorites. localStorage survives PWA close/reopen on all platforms.
    #
    # Frame topology on Streamlit Cloud (confirmed by inspection):
    #   window.top  = nant-immo.streamlit.app  (outer shell, real URL + real LS)
    #   window.parent = nant-immo.streamlit.app/~/+/  (Streamlit app iframe)
    #   window (this script) = st.components srcdoc iframe
    #
    # All three are same-origin so window.top is accessible.
    # window.top.localStorage is the correct storage bucket.
    # window.top.location.search has the real query params including ?favorites=.
    #
    # DO NOT inject script tags into window.parent.document -- Streamlit's /~/+/
    # frame has a strict CSP that blocks dynamically injected inline scripts.
    # Run everything directly here using window.top references instead.
    #
    # Two separate guards:
    #   window.top.__nantimmoFavRestored -- one-shot on the outer window,
    #     prevents the location.replace restore from firing more than once.
    #   No guard on the sync write -- runs every rerun so heart taps update
    #     localStorage immediately without waiting for the next full page load.
    st.components.v1.html("""
        <script>
        (function() {
            var LS_KEY = 'nantimmo_favorites';
            var top = window.top;
            var params = new URLSearchParams(top.location.search);
            var urlFavs = params.get('favorites') || '';

            // Restore path: one-shot per page lifecycle.
            if (!top.__nantimmoFavRestored) {
                top.__nantimmoFavRestored = true;
                var storedFavs = '';
                try { storedFavs = top.localStorage.getItem(LS_KEY) || ''; } catch(e) {}
                if (!urlFavs && storedFavs) {
                    params.set('favorites', storedFavs);
                    top.location.replace(top.location.pathname + '?' + params.toString());
                    return;
                }
            }

            // Sync path: write current favorites to localStorage on every rerun.
            try { top.localStorage.setItem(LS_KEY, urlFavs); } catch(e) {}
        })();
        </script>
    """, height=0)

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
    "sort":        sort_label,
    "favorites":   ",".join(str(x) for x in st.session_state.favorites),
    "page":        str(st.session_state.current_page),
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
    # Pagination
    unique_dates = sorted(filtered_df['scraped_date_dt'].unique(), reverse=True)
    total_pages  = max(1, len(unique_dates))
    current_page = min(st.session_state.current_page, total_pages - 1)  # clamp after filter
    page_df      = filtered_df[filtered_df['scraped_date_dt'] == unique_dates[current_page]] if unique_dates else filtered_df.iloc[0:0]

    # Nav bar — pure HTML links, no st.columns needed
    def _nav_url(p):
        """Build a URL for page p preserving all current query params."""
        params = dict(st.query_params)
        params['page'] = str(p)
        return '?' + '&'.join(f'{k}={v}' for k, v in params.items())

    prev_url  = _nav_url(current_page - 1)
    next_url  = _nav_url(current_page + 1)
    first_url = _nav_url(0)
    last_url  = _nav_url(total_pages - 1)
    prev_attr  = '' if current_page > 0 else 'aria-disabled="true"'
    next_attr  = '' if current_page < total_pages - 1 else 'aria-disabled="true"'
    first_attr = '' if current_page > 0 else 'aria-disabled="true"'
    last_attr  = '' if current_page < total_pages - 1 else 'aria-disabled="true"'

    st.markdown(f"""
        <div class="page-nav">
            <a href="{first_url}" class="nav-btn nav-btn-edge" {first_attr} target="_self">&#8676;</a>
            <a href="{prev_url}" class="nav-btn" {prev_attr} target="_self">&#8592; Pr&#233;c.</a>
            <span class="nav-label">{current_page + 1} / {total_pages}</span>
            <a href="{next_url}" class="nav-btn" {next_attr} target="_self">Suiv. &#8594;</a>
            <a href="{last_url}" class="nav-btn nav-btn-edge" {last_attr} target="_self">&#8677;</a>
        </div>
    """, unsafe_allow_html=True)

    # Scroll-to-top on page/filter navigation. Not fired on st.button reruns
    # because those don't cause DOM mutations in stMain -- Streamlit does a
    # reconciled in-place update, so the observer debounce never commits.
    st.components.v1.html("""
        <script>
        if (!window.parent.__nantimmoObs) {
            var s = window.parent.document.createElement('script');
            s.textContent = `
                var el = document.querySelector('[data-testid=stMain]');
                if (el && !window.__nantimmoObs) {
                    var t = null;
                    window.__nantimmoObs = new MutationObserver(function() {
                        clearTimeout(t);
                        t = setTimeout(function() { el.scrollTop = 0; }, 150);
                    });
                    window.__nantimmoObs.observe(el, { childList: true, subtree: true });
                }
            `;
            window.parent.document.head.appendChild(s);
            window.parent.__nantimmoObs = true;
        }
        </script>
    """, height=0)


    # Inject all heart color rules in a single st.markdown call to avoid
    # per-card empty stMarkdownContainer elements that create row gaps.
    heart_styles = ''.join(
        f".st-key-fav_{row['id']} button p {{ color: {'#10B981' if row['id'] in st.session_state.favorites else 'var(--text-gray)'} !important; font-size: 1.6rem !important; }}"
        for _, row in page_df.iterrows()
    )
    st.markdown(f'<style>{heart_styles}</style>', unsafe_allow_html=True)

    # Afficher les cartes, row-by-row (3 per row) to avoid empty column gaps on last row
    for chunk_start in range(0, len(page_df), 3):
        chunk = page_df.iloc[chunk_start:chunk_start+3]
        cols = st.columns(3) if len(chunk) == 3 else st.columns(len(chunk))
        for col, (_, row) in zip(cols, chunk.iterrows()):

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
            button_key = f"fav_{row['id']}"

            # Build price bar.
            if price_m2_display:
                price_block = f'<div class="card-price-container"><span>🏷️</span><span class="card-price">{price_display}</span><span class="card-price-m2">{price_m2_display}</span></div>'
            else:
                price_block = f'<div class="card-price-container"><span>🏷️</span><span class="card-price">{price_display}</span></div>'

            with col:
                card_html = f"""
                <div class="card-wrapper">
                    <div class="card">
                        <a href="{row['url']}" target="_blank" class="card-link">
                            <img src="{row['image_url']}" class="card-image" alt="Photo">
                        </a>
                        <div class="card-meta">
                            <div class="card-logo-wrapper">{logo_svg_text}</div>
                            <div class="card-meta-text">{row['site']} · {row['scraped_date']}</div>
                        </div>
                        <a href="{row['url']}" target="_blank" class="card-link">
                            <div class="card-title">{title}</div>
                            <div class="card-description">{description}</div>
                        </a>
                        {price_block}
                    </div>
                </div>
                """
                st.markdown(card_html, unsafe_allow_html=True)

                if st.button("\u2764\uFE0E", key=button_key, help="is_fav" if is_favorited else "not_fav"):
                    if is_favorited:
                        st.session_state.favorites.remove(row['id'])
                    else:
                        st.session_state.favorites.add(row['id'])
                    st.rerun()

    # Set stColumn to position:relative so the absolutely-positioned fav
    # button anchors to its own column instead of escaping to a distant
    # static ancestor. Runs once; guard prevents re-injection on rerun.
    st.components.v1.html("""
        <script>
        (function() {
            if (window.parent.__nantimmoColFixed) return;
            window.parent.__nantimmoColFixed = true;
            function fixCols() {
                var cols = window.parent.document.querySelectorAll('[data-testid="stColumn"]');
                if (!cols.length) { setTimeout(fixCols, 100); return; }
                cols.forEach(function(c) { c.style.position = 'relative'; });
            }
            setTimeout(fixCols, 200);
        })();
        </script>
    """, height=0)

    # Nav bar (bottom)
    st.markdown(f"""
        <div class="page-nav page-nav-bottom">
            <a href="{first_url}" class="nav-btn nav-btn-edge" {first_attr} target="_self">&#8676;</a>
            <a href="{prev_url}" class="nav-btn" {prev_attr} target="_self">&#8592; Pr&#233;c.</a>
            <span class="nav-label">{current_page + 1} / {total_pages}</span>
            <a href="{next_url}" class="nav-btn" {next_attr} target="_self">Suiv. &#8594;</a>
            <a href="{last_url}" class="nav-btn nav-btn-edge" {last_attr} target="_self">&#8677;</a>
        </div>
    """, unsafe_allow_html=True)