"""
NHL Analytics Hub — Streamlit Dashboard
======================================
Phase 5 deliverable: a multi-page analytics platform over the SQLite
database built in notebooks 01-04.

Run with:  streamlit run app.py

Structure of this file
----------------------
  1. Config, path resolution and design tokens
  2. Theme  (single organised CSS block)
  3. UI primitives  (hero, KPI cards, section headers, cards, tables)
  4. Chart layer  (shared Plotly theme + graceful fallback)
  5. Data layer  (SQLite connection, cached query runner)
  6. SQL query library
  7. Sidebar (navigation + contextual filter panel)
  8. Pages: Dashboard / Teams / Players / Games / Insights / SQL Lab

Only the presentation layer was redesigned — every SQL statement, KPI
calculation and filter behaviour from the original app is preserved.
"""

import base64
import html as _html
import re
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

# =========================================================
# 1. CONFIG & PATH RESOLUTION
# =========================================================
CURRENT_SEASON_LABEL = "2025–26"
APP_VERSION = "2.0"

# Anchor every path to this file's own location, not the current working
# directory. This matters because `streamlit run app.py` behaves
# differently depending on *where* it's launched from — a relative path
# like "data/nhl.db" only resolves correctly if you happen to be in the
# project root. If launched from anywhere else, sqlite3.connect() would
# NOT raise an error — it silently creates a new, empty database file at
# the wrong location instead, which looks like "no data" or "not
# connected" with no obvious error message anywhere.
BASE_DIR = Path(__file__).resolve().parent


def _find_db_path() -> Path:
    """Look for data/nhl.db next to this script AND one level up.

    Handles two common project layouts:
      NHL_Analytics_Hub/app.py + NHL_Analytics_Hub/data/nhl.db   (script at root)
      NHL_Analytics_Hub/app/app.py + NHL_Analytics_Hub/data/nhl.db  (script in app/)
    Returns the first one that actually exists; if neither exists yet,
    defaults to the root-sibling path so the error message points
    somewhere sensible.
    """
    candidates = [
        BASE_DIR / "data" / "nhl.db",
        BASE_DIR.parent / "data" / "nhl.db",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


ASSETS_DIR = BASE_DIR / "assets"
DB_PATH = _find_db_path()

st.set_page_config(
    page_title="NHL Analytics Hub",
    page_icon="🏒",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---- Streamlit version shim -----------------------------------------
# Streamlit 1.49 replaced `use_container_width=True` with `width="stretch"`
# on st.dataframe / st.plotly_chart. Detect once and build the right
# kwargs so the app runs clean (no deprecation spam) on old *and* new
# versions without pinning anyone to a specific Streamlit release.
def _st_version_tuple() -> tuple:
    parts = []
    for chunk in str(getattr(st, "__version__", "0.0")).split(".")[:2]:
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    while len(parts) < 2:
        parts.append(0)
    return tuple(parts)


_STREAMLIT_VERSION = _st_version_tuple()
_STRETCH = (
    {"width": "stretch"} if _STREAMLIT_VERSION >= (1, 49) else {"use_container_width": True}
)

# =========================================================
# DESIGN TOKENS — "NHL Ice Arena · Data Intelligence"
# Deep navy base, ice-blue / cyan highlights, white type, cool-gray
# secondary text. Red is reserved strictly as an accent (negative
# differentials, alerts, selected/critical states) and never dominates.
# =========================================================
NAVY_950 = "#040B16"   # deepest backdrop
NAVY_900 = "#071525"   # app background
NAVY_800 = "#0B1F33"   # panels
NAVY_700 = "#122B42"   # raised surfaces
ICE_BLUE = "#5CC8FF"   # primary highlight
CYAN = "#32D6FF"       # secondary highlight / live states
TEAL = "#7BE8D4"       # positive series
VIOLET = "#9B8CFF"     # tertiary series
WHITE = "#F5F9FC"
COOL_GRAY = "#9FB0C0"
DIM_GRAY = "#6C7F92"
ACCENT_RED = "#E2384F"  # accent only
AMBER = "#F5B942"       # rank-1 badge only
BLACK = "#000000"

GRID = "rgba(146,180,214,0.13)"
BORDER = "rgba(146,180,214,0.16)"
BORDER_HI = "rgba(92,200,255,0.38)"

# Ordered categorical series palette for all charts (ice-blue family
# first so the theme reads as one system; red kept out of the rotation).
SERIES = [ICE_BLUE, TEAL, VIOLET, CYAN, "#4E7FB8", "#C8D8E6"]


def _bg_image_data_uri() -> str | None:
    """Safe optional background image loader.

    Looks for assets/hockey_background.jpg. If it doesn't exist (the
    default — no images are bundled with this project), returns None and
    every caller falls back to a pure-CSS rink motif. Never raises,
    never leaves a broken image path in the DOM.
    """
    img_path = ASSETS_DIR / "hockey_background.jpg"
    if not img_path.exists():
        return None
    try:
        b64 = base64.b64encode(img_path.read_bytes()).decode()
        return f"data:image/jpeg;base64,{b64}"
    except Exception:
        return None


_BG_URI = _bg_image_data_uri()
_HERO_BG_LAYER = f"url('{_BG_URI}')" if _BG_URI else "none"
_HERO_BG_OPACITY = "0.20" if _BG_URI else "0"


# =========================================================
# 2. THEME
# One CSS block, grouped by concern. Streamlit re-runs top-to-bottom on
# every interaction, so this is injected once per run and nothing else
# in the app emits inline <style> tags.
# =========================================================
st.markdown(
    f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@500;600;700;800&family=Inter:wght@400;500;600;700&display=swap');

    :root {{
        --navy-950: {NAVY_950};
        --navy-900: {NAVY_900};
        --navy-800: {NAVY_800};
        --navy-700: {NAVY_700};
        --ice: {ICE_BLUE};
        --cyan: {CYAN};
        --teal: {TEAL};
        --white: {WHITE};
        --gray: {COOL_GRAY};
        --dim: {DIM_GRAY};
        --red: {ACCENT_RED};
        --amber: {AMBER};
        --border: {BORDER};
        --border-hi: {BORDER_HI};
        --r-lg: 20px;
        --r-md: 14px;
        --r-sm: 10px;
    }}

    /* ================= APP SHELL ================= */
    .stApp {{
        background:
            radial-gradient(ellipse 80% 50% at 12% -5%, rgba(50,214,255,0.13), transparent 60%),
            radial-gradient(ellipse 70% 45% at 88% 4%, rgba(92,200,255,0.10), transparent 60%),
            linear-gradient(180deg, {NAVY_900} 0%, {NAVY_950} 100%);
        background-attachment: fixed;
        color: {WHITE};
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }}

    /* Rink texture: blue/red lines + faceoff circles, drawn in pure CSS
       at very low opacity. No external asset, no readability cost. */
    .stApp::before {{
        content: "";
        position: fixed; inset: 0;
        pointer-events: none; z-index: 0;
        background-image:
            radial-gradient(circle at 20% 78%, transparent 88px, rgba(92,200,255,0.055) 90px, rgba(92,200,255,0.055) 92px, transparent 94px),
            radial-gradient(circle at 80% 26%, transparent 120px, rgba(50,214,255,0.045) 122px, rgba(50,214,255,0.045) 124px, transparent 126px),
            linear-gradient(90deg, transparent 33.2%, rgba(92,200,255,0.05) 33.3%, rgba(92,200,255,0.05) 33.45%, transparent 33.55%),
            linear-gradient(90deg, transparent 66.4%, rgba(226,56,79,0.045) 66.5%, rgba(226,56,79,0.045) 66.65%, transparent 66.75%);
        background-repeat: no-repeat;
    }}
    .stApp > * {{ position: relative; z-index: 1; }}

    /* Streamlit chrome */
    header[data-testid="stHeader"] {{ background: transparent; height: 0; }}
    #MainMenu, footer, [data-testid="stStatusWidget"] {{ visibility: hidden; }}
    [data-testid="stDecoration"] {{
        background: linear-gradient(90deg, {ICE_BLUE}, {CYAN}, {ACCENT_RED}) !important;
        height: 2px;
    }}
    [data-testid="stToolbar"], [data-testid="stAppDeployButton"] {{ display: none !important; }}

    /* Content width: fluid, capped so ultra-wide screens don't sprawl.
       No fixed px width anywhere -> no horizontal scrollbar. */
    .block-container {{
        max-width: 1680px;
        padding: 1.4rem 2.2rem 3rem 2.2rem;
    }}
    @media (max-width: 1500px) {{ .block-container {{ padding: 1.2rem 1.4rem 2.4rem 1.4rem; }} }}
    @media (max-width: 1100px) {{ .block-container {{ padding: 1rem 0.9rem 2rem 0.9rem; }} }}
    .stApp, .block-container {{ overflow-x: hidden; }}

    /* ================= TYPOGRAPHY ================= */
    h1, h2, h3, h4,
    .hero-title, .kpi-value, .sec-title, .page-title, .stat-big {{
        font-family: 'Manrope', 'Inter', sans-serif;
        letter-spacing: -0.015em;
    }}
    h1, h2, h3, h4, h5, h6 {{ color: {WHITE} !important; }}
    p, span, div, label, li {{ color: {WHITE}; }}
    .stCaption, [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {{
        color: {COOL_GRAY} !important; font-size: 12.5px !important;
    }}
    .muted {{ color: {COOL_GRAY}; }}
    .mono {{ font-variant-numeric: tabular-nums; font-feature-settings: "tnum"; }}

    /* ================= SIDEBAR ================= */
    section[data-testid="stSidebar"] {{
        background: linear-gradient(180deg, {NAVY_800} 0%, {NAVY_950} 100%);
        border-right: 1px solid {BORDER};
    }}
    section[data-testid="stSidebar"] > div {{ padding-top: 1.1rem; }}
    section[data-testid="stSidebar"] .stMarkdown,
    section[data-testid="stSidebar"] label {{ color: {WHITE}; }}

    .sb-brand {{
        display: flex; align-items: center; gap: 11px;
        padding: 2px 4px 16px 4px;
        border-bottom: 1px solid {BORDER}; margin-bottom: 14px;
    }}
    .sb-puck {{
        width: 38px; height: 38px; border-radius: 12px; flex: 0 0 38px;
        display: flex; align-items: center; justify-content: center;
        font-size: 19px;
        background: linear-gradient(135deg, rgba(92,200,255,0.22), rgba(50,214,255,0.10));
        border: 1px solid {BORDER_HI};
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.12);
    }}
    .sb-brand-name {{
        font-family: 'Manrope', sans-serif; font-size: 15px; font-weight: 800;
        color: {WHITE}; line-height: 1.15; letter-spacing: 0.01em;
    }}
    .sb-brand-sub {{
        font-size: 9.5px; font-weight: 700; letter-spacing: 0.16em;
        color: {ICE_BLUE}; text-transform: uppercase; margin-top: 2px;
    }}
    .sb-label {{
        font-size: 10px; font-weight: 700; letter-spacing: 0.15em;
        color: {DIM_GRAY}; text-transform: uppercase;
        margin: 18px 4px 8px 4px;
    }}
    .sb-panel {{
        background: rgba(255,255,255,0.035);
        border: 1px solid {BORDER};
        border-radius: var(--r-md);
        padding: 10px 12px 4px 12px;
        margin-bottom: 6px;
    }}

    /* Sidebar nav buttons — native Streamlit buttons, fully restyled, so
       no iframed component can leak a white box into the dark sidebar. */
    section[data-testid="stSidebar"] .stButton button {{
        background: transparent !important;
        color: {COOL_GRAY} !important;
        font-family: 'Inter', sans-serif !important;
        font-size: 13.5px !important;
        font-weight: 500 !important;
        text-align: left !important;
        justify-content: flex-start !important;
        border: 1px solid transparent !important;
        border-radius: var(--r-sm) !important;
        box-shadow: none !important;
        padding: 0.42rem 0.7rem !important;
        margin: 1px 0 !important;
        display: flex !important;
        transition: background 0.18s ease, color 0.18s ease, border-color 0.18s ease;
    }}
    /* keep the label flush-left regardless of Streamlit's inner wrappers */
    section[data-testid="stSidebar"] .stButton button > div,
    section[data-testid="stSidebar"] .stButton button > div > span,
    section[data-testid="stSidebar"] .stButton button [data-testid="stMarkdownContainer"] {{
        width: 100% !important; text-align: left !important;
        justify-content: flex-start !important;
    }}
    section[data-testid="stSidebar"] .stButton button p {{
        text-align: left !important; font-size: 13.5px !important; margin: 0 !important;
    }}
    section[data-testid="stSidebar"] .stButton button:hover {{
        background: rgba(92,200,255,0.10) !important;
        color: {WHITE} !important;
        border-color: {BORDER} !important;
        transform: none !important;
    }}
    section[data-testid="stSidebar"] .stButton button[kind="primary"] {{
        background: linear-gradient(90deg, rgba(50,214,255,0.20), rgba(92,200,255,0.07)) !important;
        color: {WHITE} !important;
        font-weight: 700 !important;
        border: 1px solid {BORDER_HI} !important;
        box-shadow: inset 2px 0 0 {CYAN} !important;
    }}
    section[data-testid="stSidebar"] .stButton button[kind="primary"]:hover {{
        background: linear-gradient(90deg, rgba(50,214,255,0.26), rgba(92,200,255,0.10)) !important;
    }}

    /* ================= CARDS ================= */
    .card {{
        background: linear-gradient(160deg, rgba(255,255,255,0.058), rgba(255,255,255,0.022));
        backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
        border: 1px solid {BORDER};
        border-radius: var(--r-lg);
        padding: 18px 20px;
        transition: transform 0.24s ease, border-color 0.24s ease, box-shadow 0.24s ease;
    }}
    .card:hover {{
        transform: translateY(-2px);
        border-color: {BORDER_HI};
        box-shadow: 0 10px 30px rgba(4,11,22,0.55);
    }}

    /* KPI card */
    .kpi {{
        position: relative; overflow: hidden;
        background: linear-gradient(160deg, rgba(255,255,255,0.062), rgba(255,255,255,0.02));
        backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
        border: 1px solid {BORDER};
        border-radius: var(--r-lg);
        padding: 16px 18px 15px 18px;
        height: 100%;
        animation: rise 0.45s ease both;
        transition: transform 0.24s ease, border-color 0.24s ease, box-shadow 0.24s ease;
    }}
    .kpi::after {{
        content: ""; position: absolute; top: 0; left: 0; right: 0; height: 2px;
        background: linear-gradient(90deg, {ICE_BLUE}, rgba(50,214,255,0.05));
        opacity: 0.85;
    }}
    .kpi.is-accent::after {{ background: linear-gradient(90deg, {ACCENT_RED}, rgba(226,56,79,0.05)); }}
    .kpi:hover {{
        transform: translateY(-3px);
        border-color: {BORDER_HI};
        box-shadow: 0 12px 32px rgba(50,214,255,0.10);
    }}
    .kpi-top {{ display: flex; align-items: center; justify-content: space-between; gap: 8px; }}
    .kpi-icon {{
        width: 30px; height: 30px; border-radius: 9px; flex: 0 0 30px;
        display: flex; align-items: center; justify-content: center; font-size: 15px;
        background: rgba(92,200,255,0.12); border: 1px solid rgba(92,200,255,0.20);
    }}
    .kpi.is-accent .kpi-icon {{ background: rgba(226,56,79,0.14); border-color: rgba(226,56,79,0.28); }}
    .kpi-trend {{
        font-size: 10.5px; font-weight: 700; letter-spacing: 0.04em;
        padding: 3px 8px; border-radius: 999px; white-space: nowrap;
        background: rgba(123,232,212,0.12); color: {TEAL};
        border: 1px solid rgba(123,232,212,0.22);
    }}
    .kpi-trend.down {{ background: rgba(226,56,79,0.12); color: {ACCENT_RED}; border-color: rgba(226,56,79,0.26); }}
    .kpi-trend.flat {{ background: rgba(159,176,192,0.10); color: {COOL_GRAY}; border-color: {BORDER}; }}
    .kpi-label {{
        font-size: 10.5px; font-weight: 700; letter-spacing: 0.13em;
        text-transform: uppercase; color: {COOL_GRAY};
        margin: 12px 0 3px 0;
    }}
    .kpi-value {{
        font-size: 29px; font-weight: 800; line-height: 1.12; color: {WHITE};
        font-variant-numeric: tabular-nums;
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }}
    .kpi-value.sm {{ font-size: 21px; letter-spacing: -0.01em; }}
    .kpi-sub {{ font-size: 11.5px; color: {COOL_GRAY}; margin-top: 5px; line-height: 1.4; }}
    .kpi-sub b {{ color: {ICE_BLUE}; font-weight: 600; }}
    @keyframes rise {{
        from {{ opacity: 0; transform: translateY(10px); }}
        to   {{ opacity: 1; transform: translateY(0); }}
    }}

    /* Spotlight card (top scorer / best goalie) */
    .spot {{
        display: flex; align-items: center; gap: 16px;
        background: linear-gradient(120deg, rgba(92,200,255,0.10), rgba(255,255,255,0.02) 60%);
        border: 1px solid {BORDER}; border-radius: var(--r-lg);
        padding: 16px 18px; height: 100%;
        transition: transform 0.24s ease, border-color 0.24s ease;
    }}
    .spot:hover {{ transform: translateY(-2px); border-color: {BORDER_HI}; }}
    .spot-badge {{
        width: 52px; height: 52px; flex: 0 0 52px; border-radius: 16px;
        display: flex; align-items: center; justify-content: center; font-size: 24px;
        background: linear-gradient(135deg, rgba(50,214,255,0.22), rgba(92,200,255,0.06));
        border: 1px solid {BORDER_HI};
    }}
    .spot-eyebrow {{
        font-size: 10px; font-weight: 700; letter-spacing: 0.14em;
        text-transform: uppercase; color: {CYAN};
    }}
    .spot-name {{
        font-family: 'Manrope', sans-serif; font-size: 21px; font-weight: 800;
        color: {WHITE}; margin-top: 3px; line-height: 1.15;
    }}
    .spot-meta {{ font-size: 12.5px; color: {COOL_GRAY}; margin-top: 4px; }}
    .spot-meta b {{ color: {ICE_BLUE}; font-weight: 700; }}

    /* Insight card */
    .insight {{
        border-left: 2px solid {ICE_BLUE};
        background: linear-gradient(90deg, rgba(92,200,255,0.075), rgba(255,255,255,0.018));
        border-radius: 0 var(--r-md) var(--r-md) 0;
        padding: 13px 16px; margin-bottom: 10px;
        transition: transform 0.2s ease, background 0.2s ease;
    }}
    .insight:hover {{ transform: translateX(3px); background: linear-gradient(90deg, rgba(92,200,255,0.12), rgba(255,255,255,0.02)); }}
    .insight.warn {{ border-left-color: {ACCENT_RED}; background: linear-gradient(90deg, rgba(226,56,79,0.08), rgba(255,255,255,0.018)); }}
    .insight-title {{ font-size: 12.5px; font-weight: 700; color: {WHITE}; letter-spacing: 0.01em; }}
    .insight-body {{ font-size: 12.5px; color: {COOL_GRAY}; margin-top: 3px; line-height: 1.5; }}
    .insight-body b {{ color: {ICE_BLUE}; font-weight: 700; }}
    .insight.warn .insight-body b {{ color: {ACCENT_RED}; }}

    /* ================= HERO ================= */
    .hero {{
        position: relative; overflow: hidden;
        border-radius: 24px; padding: 30px 32px 22px 32px; margin-bottom: 22px;
        border: 1px solid rgba(92,200,255,0.20);
        background:
            linear-gradient(115deg, rgba(11,31,51,0.94) 0%, rgba(7,21,37,0.97) 55%, rgba(4,11,22,0.98) 100%);
        box-shadow: 0 18px 44px rgba(4,11,22,0.5);
    }}
    .hero-photo {{
        position: absolute; inset: 0; z-index: 0;
        background-image: {_HERO_BG_LAYER};
        background-size: cover; background-position: center;
        opacity: {_HERO_BG_OPACITY};
    }}
    .hero::before {{
        /* rink motif: centre line, faceoff circle, goal crease arc */
        content: ""; position: absolute; inset: 0; z-index: 0; pointer-events: none;
        background-image:
            linear-gradient(90deg, transparent 49.6%, rgba(226,56,79,0.16) 49.8%, rgba(226,56,79,0.16) 50.2%, transparent 50.4%),
            radial-gradient(circle at 50% 50%, transparent 44px, rgba(92,200,255,0.16) 46px, rgba(92,200,255,0.16) 47px, transparent 49px),
            radial-gradient(circle at 96% 50%, transparent 108px, rgba(50,214,255,0.13) 110px, rgba(50,214,255,0.13) 111px, transparent 113px);
    }}
    .hero::after {{
        content: ""; position: absolute; z-index: 0;
        width: 340px; height: 340px; right: -90px; top: -140px; border-radius: 50%;
        background: radial-gradient(circle, rgba(50,214,255,0.20), transparent 68%);
        animation: drift 9s ease-in-out infinite alternate;
    }}
    @keyframes drift {{
        from {{ transform: translate(0, 0) scale(1); opacity: 0.75; }}
        to   {{ transform: translate(-26px, 22px) scale(1.1); opacity: 1; }}
    }}
    .hero > * {{ position: relative; z-index: 1; }}
    .hero-eyebrow {{
        display: inline-flex; align-items: center; gap: 8px;
        font-size: 10.5px; font-weight: 700; letter-spacing: 0.16em;
        color: {CYAN}; text-transform: uppercase; margin-bottom: 12px;
        padding: 4px 11px 4px 9px; border-radius: 999px;
        background: rgba(50,214,255,0.09); border: 1px solid rgba(50,214,255,0.24);
    }}
    .live-dot {{
        width: 7px; height: 7px; border-radius: 50%; background: {CYAN};
        box-shadow: 0 0 0 0 rgba(50,214,255,0.6); animation: pulse 2.2s infinite;
    }}
    @keyframes pulse {{
        0%   {{ box-shadow: 0 0 0 0 rgba(50,214,255,0.55); }}
        70%  {{ box-shadow: 0 0 0 9px rgba(50,214,255,0); }}
        100% {{ box-shadow: 0 0 0 0 rgba(50,214,255,0); }}
    }}
    .hero-title {{
        font-size: clamp(28px, 3.1vw, 44px); font-weight: 800; margin: 0;
        line-height: 1.05; color: {WHITE};
    }}
    .hero-title .accent {{
        background: linear-gradient(92deg, {ICE_BLUE}, {CYAN});
        -webkit-background-clip: text; background-clip: text;
        -webkit-text-fill-color: transparent;
    }}
    .hero-subtitle {{
        font-size: 13.5px; color: {COOL_GRAY}; margin-top: 8px; letter-spacing: 0.03em;
    }}
    .hero-meta {{
        display: flex; flex-wrap: wrap; gap: 10px 22px;
        justify-content: space-between; align-items: center;
        margin-top: 20px; padding-top: 14px;
        border-top: 1px solid rgba(255,255,255,0.09);
        font-size: 12px; color: {DIM_GRAY};
    }}
    .hero-pipeline {{ display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }}
    .pipe-step {{
        padding: 3px 10px; border-radius: 999px; font-size: 11px; font-weight: 600;
        background: rgba(255,255,255,0.045); border: 1px solid {BORDER}; color: {COOL_GRAY};
    }}
    .pipe-arrow {{ color: {ICE_BLUE}; font-size: 11px; opacity: 0.7; }}
    .hero-season {{
        color: {WHITE}; font-weight: 700; font-size: 12.5px;
        padding: 5px 13px; border-radius: 999px;
        background: rgba(92,200,255,0.11); border: 1px solid {BORDER_HI};
        white-space: nowrap;
    }}

    /* ================= HEADERS ================= */
    .page-head {{
        display: flex; align-items: center; gap: 15px;
        padding: 16px 22px; margin-bottom: 18px; border-radius: var(--r-lg);
        background: linear-gradient(100deg, rgba(92,200,255,0.09), rgba(255,255,255,0.022) 65%);
        border: 1px solid {BORDER};
    }}
    .page-head-icon {{
        width: 44px; height: 44px; flex: 0 0 44px; border-radius: 13px;
        display: flex; align-items: center; justify-content: center; font-size: 21px;
        background: rgba(92,200,255,0.13); border: 1px solid {BORDER_HI};
    }}
    .page-title {{ font-size: 23px; font-weight: 800; color: {WHITE}; line-height: 1.2; }}
    .page-sub {{ font-size: 12.5px; color: {COOL_GRAY}; margin-top: 2px; }}

    .sec {{
        display: flex; align-items: center; gap: 10px;
        margin: 4px 0 13px 0; padding-bottom: 9px;
        border-bottom: 1px solid {BORDER};
    }}
    .sec-bar {{
        width: 3px; height: 17px; border-radius: 2px;
        background: linear-gradient(180deg, {CYAN}, {ICE_BLUE});
    }}
    .sec-icon {{ font-size: 15px; }}
    .sec-title {{ font-size: 15.5px; font-weight: 700; color: {WHITE}; letter-spacing: 0.01em; }}
    .sec-note {{ font-size: 11.5px; color: {DIM_GRAY}; margin-left: auto; text-align: right; }}

    /* ================= TABLES (HTML stat tables) ================= */
    .tbl-wrap {{
        border: 1px solid {BORDER}; border-radius: var(--r-md);
        overflow: hidden; background: rgba(255,255,255,0.022);
    }}
    .tbl-scroll {{ overflow-x: auto; }}
    table.stat {{
        width: 100%; border-collapse: collapse;
        font-family: 'Inter', sans-serif; font-size: 12.5px;
    }}
    table.stat thead th {{
        background: rgba(92,200,255,0.075);
        color: {COOL_GRAY};
        font-size: 10px; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase;
        padding: 11px 12px; text-align: left; white-space: nowrap;
        border-bottom: 1px solid {BORDER};
        position: sticky; top: 0; z-index: 2;
        backdrop-filter: blur(6px);
    }}
    table.stat tbody td {{
        padding: 9px 12px; color: {WHITE};
        border-bottom: 1px solid rgba(146,180,214,0.07);
        white-space: nowrap; font-variant-numeric: tabular-nums;
    }}
    table.stat tbody tr {{ transition: background 0.15s ease; }}
    table.stat tbody tr:hover {{ background: rgba(92,200,255,0.075); }}
    table.stat tbody tr:last-child td {{ border-bottom: none; }}
    table.stat .num {{ text-align: right; }}
    table.stat .ctr {{ text-align: center; }}
    table.stat .dim {{ color: {COOL_GRAY}; }}
    table.stat .strong {{ font-weight: 700; }}
    table.stat .pos {{ color: {TEAL}; font-weight: 600; }}
    table.stat .neg {{ color: {ACCENT_RED}; font-weight: 600; }}
    table.stat tr.top-row {{ background: rgba(92,200,255,0.05); }}
    .rank-pill {{
        display: inline-flex; align-items: center; justify-content: center;
        min-width: 24px; height: 22px; padding: 0 6px; border-radius: 7px;
        font-size: 11px; font-weight: 700; font-variant-numeric: tabular-nums;
        background: rgba(255,255,255,0.05); border: 1px solid {BORDER}; color: {COOL_GRAY};
    }}
    .rank-pill.r1 {{ background: rgba(245,185,66,0.16); border-color: rgba(245,185,66,0.45); color: {AMBER}; }}
    .rank-pill.r2 {{ background: rgba(92,200,255,0.15); border-color: {BORDER_HI}; color: {ICE_BLUE}; }}
    .rank-pill.r3 {{ background: rgba(123,232,212,0.13); border-color: rgba(123,232,212,0.34); color: {TEAL}; }}
    .cell-bar {{
        position: relative; display: block; min-width: 46px;
        padding: 2px 0; border-radius: 4px;
    }}
    .cell-bar::before {{
        content: ""; position: absolute; left: 0; top: 2px; bottom: 2px;
        width: var(--w, 0%); border-radius: 3px;
        background: linear-gradient(90deg, rgba(50,214,255,0.34), rgba(92,200,255,0.12));
    }}
    .cell-bar span {{ position: relative; padding-left: 6px; }}
    .chip {{
        display: inline-block; padding: 2px 8px; border-radius: 999px;
        font-size: 10.5px; font-weight: 700; letter-spacing: 0.04em;
        background: rgba(255,255,255,0.055); border: 1px solid {BORDER}; color: {COOL_GRAY};
    }}
    .chip.ice {{ background: rgba(92,200,255,0.13); border-color: {BORDER_HI}; color: {ICE_BLUE}; }}
    .chip.red {{ background: rgba(226,56,79,0.13); border-color: rgba(226,56,79,0.32); color: {ACCENT_RED}; }}
    .chip.teal {{ background: rgba(123,232,212,0.12); border-color: rgba(123,232,212,0.3); color: {TEAL}; }}

    /* ================= EMPTY / STATUS STATES ================= */
    .empty {{
        display: flex; align-items: center; gap: 13px;
        padding: 20px 22px; border-radius: var(--r-md);
        background: rgba(255,255,255,0.028);
        border: 1px dashed {BORDER};
    }}
    .empty-icon {{ font-size: 21px; opacity: 0.75; }}
    .empty-title {{ font-size: 13.5px; font-weight: 700; color: {WHITE}; }}
    .empty-body {{ font-size: 12px; color: {COOL_GRAY}; margin-top: 2px; }}
    .banner {{
        display: flex; gap: 12px; align-items: flex-start;
        padding: 15px 18px; border-radius: var(--r-md); margin-bottom: 16px;
        background: rgba(226,56,79,0.09); border: 1px solid rgba(226,56,79,0.34);
    }}
    .banner-title {{ font-size: 13.5px; font-weight: 700; color: {WHITE}; }}
    .banner-body {{ font-size: 12px; color: {COOL_GRAY}; margin-top: 3px; line-height: 1.5; }}
    .banner-body code {{
        background: rgba(255,255,255,0.07); padding: 1px 6px; border-radius: 5px;
        color: {ICE_BLUE}; font-size: 11.5px;
    }}

    /* ================= WIDGETS ================= */
    /* Selects / inputs: dark surface, light text, ice-blue focus ring. */
    div[data-baseweb="select"] > div {{
        background: rgba(255,255,255,0.055) !important;
        border: 1px solid {BORDER} !important;
        border-radius: var(--r-sm) !important;
        color: {WHITE} !important;
        min-height: 38px;
        transition: border-color 0.18s ease, box-shadow 0.18s ease;
    }}
    div[data-baseweb="select"] > div:hover {{ border-color: {BORDER_HI} !important; }}
    div[data-baseweb="select"] > div:focus-within {{
        border-color: {ICE_BLUE} !important;
        box-shadow: 0 0 0 3px rgba(92,200,255,0.16) !important;
    }}
    div[data-baseweb="select"] div, div[data-baseweb="select"] span,
    div[data-baseweb="select"] input {{ color: {WHITE} !important; }}
    div[data-baseweb="select"] svg {{ fill: {ICE_BLUE} !important; }}
    /* dropdown popover (rendered in a portal, so target globally) */
    div[data-baseweb="popover"] div[data-baseweb="menu"],
    ul[data-baseweb="menu"] {{
        background: {NAVY_800} !important;
        border: 1px solid {BORDER_HI} !important;
        border-radius: var(--r-sm) !important;
        box-shadow: 0 16px 40px rgba(4,11,22,0.65) !important;
    }}
    ul[data-baseweb="menu"] li {{ color: {WHITE} !important; font-size: 13px !important; }}
    ul[data-baseweb="menu"] li:hover,
    ul[data-baseweb="menu"] li[aria-selected="true"] {{
        background: rgba(92,200,255,0.16) !important; color: {WHITE} !important;
    }}
    .stTextInput input, .stDateInput input, .stTextArea textarea,
    .stNumberInput input {{
        background: rgba(255,255,255,0.055) !important;
        border: 1px solid {BORDER} !important;
        border-radius: var(--r-sm) !important;
        color: {WHITE} !important;
        caret-color: {CYAN};
    }}
    .stTextInput input::placeholder, .stTextArea textarea::placeholder {{ color: {DIM_GRAY} !important; }}
    .stTextInput input:focus, .stTextArea textarea:focus, .stDateInput input:focus {{
        border-color: {ICE_BLUE} !important; box-shadow: 0 0 0 3px rgba(92,200,255,0.16) !important;
    }}
    div[data-baseweb="input"], div[data-baseweb="base-input"], div[data-baseweb="textarea"] {{
        background: transparent !important; border-radius: var(--r-sm) !important;
    }}
    /* date picker calendar */
    div[data-baseweb="calendar"] {{ background: {NAVY_800} !important; }}
    div[data-baseweb="calendar"] * {{ color: {WHITE} !important; }}
    div[data-baseweb="calendar"] div[aria-selected="true"] {{ background: {ICE_BLUE} !important; color: {NAVY_900} !important; }}

    /* ---- Current Streamlit widget DOM (react-aria) ----
       Recent releases replaced the BaseWeb inputs above with react-aria
       components exposed through data-testid hooks. Their default surface
       is white, which would punch holes in the dark shell, so the same
       treatment is re-applied here. Both selector families are kept so the
       theme survives a Streamlit upgrade or downgrade. */
    [data-testid="stSelectbox"] div[role="group"],
    [data-testid="stMultiSelect"] div[role="group"],
    [data-testid="stDateInputField"],
    [data-testid="stTextInputRootElement"],
    [data-testid="stTextAreaRootElement"],
    [data-testid="stNumberInputContainer"] {{
        background: rgba(255,255,255,0.055) !important;
        border: 1px solid {BORDER} !important;
        border-radius: var(--r-sm) !important;
        box-shadow: none !important;
        transition: border-color 0.18s ease, box-shadow 0.18s ease;
    }}
    [data-testid="stSelectbox"] div[role="group"]:hover,
    [data-testid="stDateInputField"]:hover,
    [data-testid="stTextInputRootElement"]:hover {{
        border-color: {BORDER_HI} !important;
    }}
    [data-testid="stSelectbox"] div[role="group"]:focus-within,
    [data-testid="stMultiSelect"] div[role="group"]:focus-within,
    [data-testid="stDateInputField"]:focus-within,
    [data-testid="stTextInputRootElement"]:focus-within,
    [data-testid="stTextAreaRootElement"]:focus-within {{
        border-color: {ICE_BLUE} !important;
        box-shadow: 0 0 0 3px rgba(92,200,255,0.16) !important;
    }}
    /* inner text: transparent surface, light type */
    [data-testid="stTextInputField"],
    [data-testid="stSelectbox"] input,
    [data-testid="stDateInputField"] input,
    [data-testid="stTextAreaRootElement"] textarea,
    [data-testid="stNumberInputContainer"] input {{
        background: transparent !important;
        border: none !important;
        color: {WHITE} !important;
        caret-color: {CYAN};
    }}
    [data-testid="stDateInputField"] div,
    [data-testid="stSelectbox"] div[role="group"] span {{ color: {WHITE} !important; }}
    [data-testid="stTextInputField"]::placeholder,
    [data-testid="stTextAreaRootElement"] textarea::placeholder,
    [data-testid="stSelectbox"] input::placeholder {{ color: {DIM_GRAY} !important; }}
    [data-testid="stSelectbox"] svg, [data-testid="stDateInputField"] svg,
    [data-testid="stMultiSelect"] svg {{ color: {ICE_BLUE} !important; fill: {ICE_BLUE} !important; }}

    /* dropdown / listbox popovers (rendered in a portal) */
    [role="listbox"], [data-testid="stSelectboxVirtualDropdown"],
    .react-aria-Popover, .react-aria-ListBox {{
        background: {NAVY_800} !important;
        border: 1px solid {BORDER_HI} !important;
        border-radius: var(--r-sm) !important;
        box-shadow: 0 18px 44px rgba(4,11,22,0.7) !important;
    }}
    [role="option"], .react-aria-ListBoxItem {{
        color: {WHITE} !important; font-size: 13px !important;
    }}
    [role="option"]:hover, [role="option"][aria-selected="true"],
    [role="option"][data-focused="true"], [role="option"][data-selected="true"] {{
        background: rgba(92,200,255,0.16) !important; color: {WHITE} !important;
    }}
    /* react-aria calendar */
    .react-aria-Calendar, [data-testid="stDateInputCalendar"] {{
        background: {NAVY_800} !important; color: {WHITE} !important;
    }}
    .react-aria-CalendarCell[data-selected] {{
        background: {ICE_BLUE} !important; color: {NAVY_900} !important;
    }}

    /* Main-area buttons */
    div[data-testid="stMainBlockContainer"] .stButton button,
    .stForm .stButton button {{
        background: linear-gradient(92deg, {ICE_BLUE}, {CYAN}) !important;
        color: {NAVY_900} !important;
        font-weight: 700 !important; font-size: 13px !important;
        border: none !important; border-radius: var(--r-sm) !important;
        padding: 0.45rem 1.1rem !important;
        transition: transform 0.18s ease, box-shadow 0.18s ease, filter 0.18s ease;
    }}
    div[data-testid="stMainBlockContainer"] .stButton button:hover {{
        transform: translateY(-2px);
        box-shadow: 0 8px 22px rgba(50,214,255,0.30);
        filter: brightness(1.06);
    }}
    .stDownloadButton button {{
        background: rgba(255,255,255,0.055) !important;
        color: {ICE_BLUE} !important; font-weight: 600 !important;
        border: 1px solid {BORDER_HI} !important; border-radius: var(--r-sm) !important;
    }}
    .stDownloadButton button:hover {{ background: rgba(92,200,255,0.13) !important; }}

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 4px; background: rgba(255,255,255,0.03);
        padding: 5px; border-radius: var(--r-md);
        border: 1px solid {BORDER}; margin-bottom: 14px;
    }}
    .stTabs [data-baseweb="tab"] {{
        background: transparent; border-radius: var(--r-sm);
        color: {COOL_GRAY}; font-size: 13px; font-weight: 600;
        padding: 7px 16px; height: auto;
        transition: background 0.18s ease, color 0.18s ease;
    }}
    .stTabs [data-baseweb="tab"]:hover {{ background: rgba(92,200,255,0.08); color: {WHITE}; }}
    .stTabs [aria-selected="true"] {{
        background: linear-gradient(92deg, rgba(50,214,255,0.20), rgba(92,200,255,0.09)) !important;
        color: {WHITE} !important;
        border: 1px solid {BORDER_HI} !important;
    }}
    /* Streamlit's default active-tab underline is red, which is reserved
       here as an accent — recolour it to the ice-blue highlight. */
    .stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {{
        background-color: transparent !important; height: 0 !important;
    }}
    /* Newer Streamlit releases render tabs as [data-testid="stTab"] with a
       react-aria selection indicator instead of the BaseWeb DOM above.
       Both selector families are kept so the theme holds across versions. */
    div[role="tablist"] {{ gap: 4px; }}
    [data-testid="stTab"] {{
        border-radius: var(--r-sm) !important;
        padding: 6px 15px !important;
        border: 1px solid transparent !important;
        transition: background 0.18s ease, border-color 0.18s ease;
    }}
    [data-testid="stTab"] p {{
        color: {COOL_GRAY} !important; font-size: 13px !important; font-weight: 600 !important;
    }}
    [data-testid="stTab"]:hover {{ background: rgba(92,200,255,0.08) !important; }}
    [data-testid="stTab"]:hover p {{ color: {WHITE} !important; }}
    [data-testid="stTab"][aria-selected="true"] {{
        background: linear-gradient(92deg, rgba(50,214,255,0.20), rgba(92,200,255,0.09)) !important;
        border-color: {BORDER_HI} !important;
    }}
    [data-testid="stTab"][aria-selected="true"] p {{ color: {WHITE} !important; font-weight: 700 !important; }}
    .react-aria-SelectionIndicator {{
        background: linear-gradient(90deg, {CYAN}, {ICE_BLUE}) !important;
        height: 2px !important; border-radius: 2px !important;
    }}

    /* Radio + checkbox: default accent is red, which is reserved here. */
    div[role="radiogroup"] {{ gap: 6px; }}
    div[role="radiogroup"] label {{
        background: rgba(255,255,255,0.04); border: 1px solid {BORDER};
        border-radius: var(--r-sm); padding: 5px 12px 5px 8px;
        transition: border-color 0.18s ease, background 0.18s ease;
    }}
    div[role="radiogroup"] label:hover {{ border-color: {BORDER_HI}; background: rgba(92,200,255,0.07); }}
    div[role="radiogroup"] label span:first-child {{ border-color: {ICE_BLUE} !important; }}
    div[role="radiogroup"] label span:first-child > div {{ background-color: {ICE_BLUE} !important; }}
    /* Newer Streamlit renders each option as label[data-testid="stRadioOption"]
       with the dot as a plain nested div; the default fill is red. */
    [data-testid="stRadioOption"]:has(input:checked) {{
        background: rgba(92,200,255,0.12) !important;
        border-color: {BORDER_HI} !important;
    }}
    [data-testid="stRadioOption"]:has(input:checked) > div > div > div:first-child {{
        background-color: {ICE_BLUE} !important;
    }}
    [data-testid="stRadioOption"] p {{ font-size: 12.5px !important; }}

    /* Sliders — Streamlit paints the filled track with an inline
       linear-gradient whose stop position tracks the current value, so it
       can't be replaced with a static colour without losing the fill
       indicator. Rotating the hue red -> ice-blue keeps the behaviour and
       only shifts the colour (the gray remainder is unsaturated, so it is
       left visually untouched). */
    [data-testid="stSlider"] [role="group"] > div > div:first-child {{
        filter: hue-rotate(196deg) saturate(1.12) !important;
    }}
    /* the draggable thumb sits in the next sibling and is red by default */
    [data-testid="stSlider"] [role="group"] > div > div:nth-child(2) {{
        background: {ICE_BLUE} !important;
    }}
    [data-testid="stSlider"] [data-testid="stSliderThumbValue"],
    [data-testid="stSlider"] [data-testid="stSliderThumbValue"] p {{
        color: {ICE_BLUE} !important; font-weight: 700 !important; font-size: 12px !important;
    }}
    [data-testid="stSlider"] [data-testid="stSliderTickBar"] p {{
        color: {DIM_GRAY} !important; font-size: 11px !important;
    }}
    [data-testid="stSlider"] input {{ box-shadow: 0 0 0 3px rgba(92,200,255,0.22) !important; }}
    [data-testid="stCheckbox"] label span:first-child {{ background-color: rgba(255,255,255,0.06) !important; border-color: {BORDER} !important; }}
    [data-baseweb="checkbox"] [data-checked="true"] {{ background-color: {ICE_BLUE} !important; }}

    /* Widget labels */
    .stSelectbox label p, .stTextInput label p, .stDateInput label p,
    .stRadio label p, .stMultiSelect label p, .stTextArea label p,
    [data-testid="stWidgetLabel"] p {{
        font-size: 10.5px !important; font-weight: 700 !important;
        letter-spacing: 0.11em !important; text-transform: uppercase !important;
        color: {COOL_GRAY} !important;
    }}

    /* Dataframes (used where sortable/exploratory grids beat static tables) */
    div[data-testid="stDataFrame"], div[data-testid="stDataFrameResizable"] {{
        border: 1px solid {BORDER} !important;
        border-radius: var(--r-md) !important;
        overflow: hidden;
    }}

    /* Expanders */
    details, [data-testid="stExpander"] {{
        background: rgba(255,255,255,0.03) !important;
        border: 1px solid {BORDER} !important;
        border-radius: var(--r-md) !important;
    }}
    [data-testid="stExpander"] summary {{ font-size: 13px; font-weight: 600; color: {WHITE}; }}
    [data-testid="stExpander"] summary:hover {{ color: {ICE_BLUE}; }}

    /* Code blocks: Streamlit's highlighter theme is light by default, which
       renders some tokens invisible against this navy shell. Force the
       whole block dark with guaranteed-readable text rather than fighting
       Pygments token classes one by one. */
    div[data-testid="stCode"], div[data-testid="stCodeBlock"], .stCode {{
        background: rgba(4,11,22,0.55) !important;
        border: 1px solid {BORDER} !important;
        border-radius: var(--r-md) !important;
    }}
    div[data-testid="stCode"] pre, div[data-testid="stCodeBlock"] pre,
    div[data-testid="stCode"] code, div[data-testid="stCodeBlock"] code {{
        background: transparent !important;
    }}
    div[data-testid="stCode"] *, div[data-testid="stCodeBlock"] * {{
        color: #CFEBFF !important; font-size: 12.5px !important;
    }}

    /* Alerts */
    div[data-testid="stAlert"] {{ border-radius: var(--r-md); border: 1px solid {BORDER}; }}

    /* Plotly container */
    .js-plotly-plot, .plot-container {{ border-radius: var(--r-md); }}
    div[data-testid="stPlotlyChart"] {{ overflow: hidden; }}

    /* Images (team logos / headshots) */
    div[data-testid="stImage"] img {{
        border-radius: var(--r-md);
        background: rgba(255,255,255,0.05);
        border: 1px solid {BORDER};
        padding: 6px;
    }}

    hr, div[data-testid="stDivider"] {{ border-color: {BORDER} !important; }}

    /* Inline code inside markdown/help text — light by default */
    code, [data-testid="stMarkdownContainer"] code {{
        background: rgba(92,200,255,0.10) !important;
        color: {ICE_BLUE} !important;
        border: 1px solid {BORDER} !important;
        border-radius: 6px !important;
        padding: 1px 6px !important;
        font-size: 0.9em !important;
    }}
    div[data-testid="stCode"] code, div[data-testid="stCodeBlock"] code {{
        background: transparent !important; border: none !important; padding: 0 !important;
    }}

    /* ================= FOOTER ================= */
    .foot {{
        display: flex; flex-wrap: wrap; gap: 8px 18px;
        justify-content: space-between; align-items: center;
        margin-top: 34px; padding: 16px 20px; border-radius: var(--r-md);
        background: rgba(255,255,255,0.022); border: 1px solid {BORDER};
        font-size: 11.5px; color: {DIM_GRAY};
    }}
    .foot b {{ color: {COOL_GRAY}; font-weight: 600; }}
    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# 3. UI PRIMITIVES
# Small, composable helpers that return HTML strings (or write directly
# to the page). Every piece of chrome in the app is built from these —
# no duplicated markup anywhere.
# =========================================================
def _esc(value) -> str:
    """HTML-escape any value for safe interpolation into markup."""
    return _html.escape("" if value is None else str(value))


def _fmt_int(value) -> str:
    """1312 -> '1,312'. Non-numeric / missing values render as an em dash."""
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return "—"
        return f"{int(round(float(value))):,}"
    except (TypeError, ValueError):
        return _esc(value)


def _fmt_float(value, places: int = 2) -> str:
    try:
        if value is None or pd.isna(value):
            return "—"
        return f"{float(value):.{places}f}"
    except (TypeError, ValueError):
        return _esc(value)


def _season_label(code) -> str:
    """'20252026' -> '2025–26'. Anything unexpected passes straight through."""
    if code is None or code == "All seasons":
        return "All seasons"
    s = str(code)
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}–{s[6:]}"
    return s


def _fmt_signed(value) -> str:
    try:
        n = int(round(float(value)))
        return f"+{n:,}" if n > 0 else f"{n:,}"
    except (TypeError, ValueError):
        return "—"


_WS_RE = re.compile(r"\s*\n\s*")


def write(html: str) -> None:
    """Render an HTML fragment produced by the helpers below.

    Newlines are collapsed first. This matters: Streamlit runs markup
    through a markdown parser, and a blank line inside an HTML block
    terminates that block — the rest of the tags then leak onto the page
    as literal text. Emitting each fragment as a single line makes the
    helpers safe to compose with optional (possibly empty) sub-fragments.
    """
    st.markdown(_WS_RE.sub(" ", html).strip(), unsafe_allow_html=True)


def spacer(px: int = 22) -> None:
    write(f"<div style='height:{px}px'></div>")


def render_hero(db_ok: bool, teams: int | None = None, games: int | None = None) -> None:
    """Dashboard hero banner. Season + pipeline provenance are real values."""
    status_txt = "LIVE DATA" if db_ok else "DATA OFFLINE"
    dot = '<span class="live-dot"></span>' if db_ok else ""
    scale_bits = []
    if teams:
        scale_bits.append(f"{_fmt_int(teams)} teams")
    if games:
        scale_bits.append(f"{_fmt_int(games)} games")
    scale = " · ".join(scale_bits)
    write(
        f"""
        <div class="hero">
            <div class="hero-photo"></div>
            <div class="hero-eyebrow">{dot}{status_txt}</div>
            <div class="hero-title">🏒 NHL <span class="accent">ANALYTICS HUB</span></div>
            <div class="hero-subtitle">
                Professional Hockey Performance &amp; Analytics Platform
                &nbsp;·&nbsp; Game Intelligence • Team Performance • Player Metrics
            </div>
            <div class="hero-meta">
                <div class="hero-pipeline">
                    <span class="pipe-step">NHL API</span><span class="pipe-arrow">→</span>
                    <span class="pipe-step">SQLite</span><span class="pipe-arrow">→</span>
                    <span class="pipe-step">SQL Analysis</span><span class="pipe-arrow">→</span>
                    <span class="pipe-step">Dashboard</span>
                    {f'<span class="pipe-arrow">·</span><span class="pipe-step">{_esc(scale)}</span>' if scale else ''}
                </div>
                <span class="hero-season">Season Analytics · {_esc(CURRENT_SEASON_LABEL)}</span>
            </div>
        </div>
        """
    )


def kpi_card(
    icon: str,
    label: str,
    value,
    sub: str | None = None,
    trend: str | None = None,
    trend_dir: str = "up",
    accent: bool = False,
    small_value: bool = False,
) -> str:
    """One KPI card. `value` is always passed in from a real query."""
    trend_html = (
        f'<div class="kpi-trend {_esc(trend_dir)}">{_esc(trend)}</div>' if trend else ""
    )
    sub_html = f'<div class="kpi-sub">{sub}</div>' if sub else ""
    return f"""
    <div class="kpi{' is-accent' if accent else ''}">
        <div class="kpi-top">
            <div class="kpi-icon">{icon}</div>
            {trend_html}
        </div>
        <div class="kpi-label">{_esc(label)}</div>
        <div class="kpi-value{' sm' if small_value else ''}">{value}</div>
        {sub_html}
    </div>
    """


def render_kpi_row(cards: list[str]) -> None:
    """Lay KPI cards out in an evenly-spaced, responsive row."""
    if not cards:
        return
    for col, card in zip(st.columns(len(cards)), cards):
        with col:
            write(card)


def spotlight_card(eyebrow: str, name: str, meta: str, badge: str = "🏅") -> str:
    return f"""
    <div class="spot">
        <div class="spot-badge">{badge}</div>
        <div>
            <div class="spot-eyebrow">{_esc(eyebrow)}</div>
            <div class="spot-name">{_esc(name)}</div>
            <div class="spot-meta">{meta}</div>
        </div>
    </div>
    """


def section_header(icon: str, title: str, note: str = "") -> None:
    note_html = f'<div class="sec-note">{_esc(note)}</div>' if note else ""
    write(
        f"""
        <div class="sec">
            <div class="sec-bar"></div>
            <span class="sec-icon">{icon}</span>
            <span class="sec-title">{_esc(title)}</span>
            {note_html}
        </div>
        """
    )


def page_header(icon: str, title: str, subtitle: str = "") -> None:
    sub_html = f'<div class="page-sub">{_esc(subtitle)}</div>' if subtitle else ""
    write(
        f"""
        <div class="page-head">
            <div class="page-head-icon">{icon}</div>
            <div>
                <div class="page-title">{_esc(title)}</div>
                {sub_html}
            </div>
        </div>
        """
    )


def insight_card(title: str, body: str, warn: bool = False) -> str:
    return f"""
    <div class="insight{' warn' if warn else ''}">
        <div class="insight-title">{_esc(title)}</div>
        <div class="insight-body">{body}</div>
    </div>
    """


def empty_state(
    title: str = "No data available",
    body: str = "No rows matched the selected filters.",
    icon: str = "📭",
) -> None:
    """Friendly, styled replacement for a bare st.info() / stack trace."""
    write(
        f"""
        <div class="empty">
            <div class="empty-icon">{icon}</div>
            <div>
                <div class="empty-title">{_esc(title)}</div>
                <div class="empty-body">{_esc(body)}</div>
            </div>
        </div>
        """
    )


def error_state(message: str, hint: str = "") -> None:
    """User-facing failure notice — never a raw traceback."""
    hint_html = f"<div class='banner-body'>{hint}</div>" if hint else ""
    write(
        f"""
        <div class="banner">
            <div style="font-size:19px;">⚠️</div>
            <div>
                <div class="banner-title">{_esc(message)}</div>
                {hint_html}
            </div>
        </div>
        """
    )


def render_footer(row_note: str = "") -> None:
    write(
        f"""
        <div class="foot">
            <div>🏒 <b>NHL Analytics Hub</b> v{APP_VERSION} &nbsp;·&nbsp;
                 Season {_esc(CURRENT_SEASON_LABEL)} &nbsp;·&nbsp;
                 NHL API → SQLite → SQL → Streamlit</div>
            <div>{_esc(row_note) if row_note else 'All figures queried live from the project database.'}</div>
        </div>
        """
    )


# ---------- Professional stat tables (HTML) ----------
def stat_table(
    df: pd.DataFrame,
    columns: list[tuple],
    rank: bool = True,
    rank_label: str = "#",
    bar_col: str | None = None,
    highlight_top: int = 3,
    max_height: int | None = 460,
) -> None:
    """Render a DataFrame as a styled sports-analytics table.

    `columns` is a list of (dataframe_column, header, kind) where kind is
    one of: 'text', 'strong', 'dim', 'int', 'float2', 'float3', 'signed',
    'chip'. Formatting and alignment follow from the kind, so number
    columns are right-aligned and tabular everywhere in the app.
    Data is never modified — this is display only.
    """
    if df is None or len(df) == 0:
        empty_state()
        return

    max_bar = None
    if bar_col and bar_col in df.columns:
        try:
            max_bar = float(pd.to_numeric(df[bar_col], errors="coerce").max())
        except Exception:
            max_bar = None

    head = ""
    if rank:
        head += f'<th style="width:56px">{_esc(rank_label)}</th>'
    for _, header, kind in columns:
        cls = "num" if kind in ("int", "float2", "float3", "signed") else ""
        head += f'<th class="{cls}">{_esc(header)}</th>'

    body = ""
    for i, (_, row) in enumerate(df.iterrows(), start=1):
        tr_cls = " class='top-row'" if rank and i <= highlight_top else ""
        body += f"<tr{tr_cls}>"
        if rank:
            pill = f"rank-pill r{i}" if i <= 3 else "rank-pill"
            body += f'<td><span class="{pill}">{i}</span></td>'
        for col, _, kind in columns:
            raw = row.get(col) if hasattr(row, "get") else None
            if kind == "int":
                txt, cls = _fmt_int(raw), "num"
            elif kind == "float2":
                txt, cls = _fmt_float(raw, 2), "num"
            elif kind == "float3":
                txt, cls = _fmt_float(raw, 3), "num"
            elif kind == "signed":
                txt = _fmt_signed(raw)
                pol = "pos" if txt.startswith("+") else ("neg" if txt.startswith("-") else "dim")
                cls = f"num {pol}"
            elif kind == "strong":
                txt, cls = _esc(raw) if raw is not None else "—", "strong"
            elif kind == "dim":
                txt, cls = _esc(raw) if raw is not None else "—", "dim"
            elif kind == "chip":
                txt, cls = f'<span class="chip ice">{_esc(raw)}</span>', "ctr"
            else:
                txt, cls = _esc(raw) if raw is not None else "—", ""

            if bar_col and col == bar_col and max_bar and max_bar > 0:
                try:
                    pct = max(0.0, min(100.0, float(raw) / max_bar * 100.0))
                except (TypeError, ValueError):
                    pct = 0.0
                txt = f'<span class="cell-bar" style="--w:{pct:.1f}%"><span>{txt}</span></span>'
            body += f'<td class="{cls}">{txt}</td>'
        body += "</tr>"

    style = f"max-height:{max_height}px; overflow-y:auto;" if max_height else ""
    write(
        f"""
        <div class="tbl-wrap">
          <div class="tbl-scroll" style="{style}">
            <table class="stat">
              <thead><tr>{head}</tr></thead>
              <tbody>{body}</tbody>
            </table>
          </div>
        </div>
        """
    )


def auto_table(df: pd.DataFrame, max_rows: int = 300, max_height: int = 470) -> None:
    """Render an arbitrary result set with the styled table treatment.

    Column kinds are inferred from dtypes so ad-hoc SQL output still gets
    right-aligned, tabular numbers instead of raw repr strings.
    """
    if df is None or len(df) == 0:
        empty_state()
        return
    columns, first_text_used = [], False
    for col in df.columns:
        series = df[col]
        if pd.api.types.is_bool_dtype(series):
            kind = "text"
        elif pd.api.types.is_integer_dtype(series):
            kind = "int"
        elif pd.api.types.is_float_dtype(series):
            clean = series.dropna()
            # save_pct-style ratios read better at three decimals
            kind = "float3" if len(clean) and clean.abs().le(1.5).all() else "float2"
        elif not first_text_used:
            kind, first_text_used = "strong", True
        else:
            kind = "text"
        columns.append((col, str(col).replace("_", " ").upper(), kind))
    stat_table(df.head(max_rows), columns, rank=False, max_height=max_height)
    if len(df) > max_rows:
        st.caption(f"Showing the first {max_rows:,} of {len(df):,} rows.")


def show_df(df: pd.DataFrame, **kwargs) -> None:
    """st.dataframe with the container-width shim + shared defaults.
    Used where sortable/searchable exploration beats a static table.
    """
    kwargs.setdefault("hide_index", True)
    st.dataframe(df, **_STRETCH, **kwargs)


# =========================================================
# 4. CHART LAYER
# A single Plotly theme applied through style_fig() so every chart in
# the app shares one visual language. If plotly isn't installed the app
# degrades to Streamlit's built-in charts instead of crashing.
# =========================================================
try:
    import plotly.express as px
    import plotly.graph_objects as go

    HAS_PLOTLY = True
except Exception:  # pragma: no cover - dependency-optional by design
    px = None
    go = None
    HAS_PLOTLY = False

PLOTLY_CONFIG = {"displayModeBar": False, "responsive": True}
CHART_FONT = "Inter, -apple-system, sans-serif"


def style_fig(fig, height: int = 330, title: str | None = None, legend: bool = False):
    """Apply the shared NHL chart theme: transparent surface, cool grid,
    tabular hover labels, no chart junk."""
    if fig is None:
        return None
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=CHART_FONT, color=WHITE, size=12),
        height=height,
        margin=dict(l=6, r=14, t=42 if title else 12, b=8),
        showlegend=legend,
        hoverlabel=dict(
            bgcolor=NAVY_800,
            bordercolor=ICE_BLUE,
            font=dict(family=CHART_FONT, color=WHITE, size=12),
        ),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0,
            bgcolor="rgba(0,0,0,0)", font=dict(color=COOL_GRAY, size=11), title_text="",
            traceorder="normal",
        ),
        title=dict(
            text=title or "",
            font=dict(family="Manrope, sans-serif", size=14, color=WHITE),
            x=0, xanchor="left", y=0.97, yanchor="top",
        ),
        colorway=SERIES,
        bargap=0.28,
    )
    axis = dict(
        gridcolor=GRID,
        zerolinecolor=GRID,
        linecolor=GRID,
        tickfont=dict(color=COOL_GRAY, size=11),
        title_font=dict(color=DIM_GRAY, size=11),
        automargin=True,
    )
    fig.update_xaxes(**axis)
    fig.update_yaxes(**axis)
    return fig


def show_fig(fig) -> None:
    if fig is None:
        empty_state("Chart unavailable", "Not enough data to draw this visual.", "📉")
        return
    st.plotly_chart(fig, config=PLOTLY_CONFIG, **_STRETCH)


def chart_card_open(icon: str, title: str, note: str = "") -> None:
    """Section header used above every chart, so charts always arrive with
    a professional title + context line rather than floating bare."""
    section_header(icon, title, note)


def fallback_bar(df: pd.DataFrame, x: str, y: str) -> None:
    """Used only when plotly is missing — keeps the page functional."""
    try:
        st.bar_chart(df.set_index(x)[[y]], color=CYAN)
    except Exception:
        auto_table(df)


# =========================================================
# 5. DATA LAYER  (unchanged logic — connection, health check, queries)
# =========================================================
@st.cache_resource
def get_conn():
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Database not found at {DB_PATH}. Run notebooks 01-04 first "
            f"to create and populate data/nhl.db, and make sure this app "
            f"is run from the project root (or just use `streamlit run "
            f"app.py` from inside the project folder — the path is now "
            f"anchored to this file's location either way)."
        )
    return sqlite3.connect(str(DB_PATH), check_same_thread=False)


@st.cache_data(ttl=300, show_spinner=False)
def _cached_query(query: str, params: tuple) -> tuple:
    """Cached SELECT execution. Keyed on (query, params) so repeated
    reads across pages and reruns don't re-hit SQLite."""
    try:
        conn = get_conn()
        df = pd.read_sql(query, conn, params=params)
        return df, None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def run_query(query: str, params: tuple = ()) -> tuple:
    """Run a SELECT query safely. Returns (dataframe, error_message)."""
    return _cached_query(query, tuple(params))


def scalar(query: str, params: tuple = (), default=None):
    """Convenience for single-value queries used by the insight cards."""
    df, err = run_query(query, params)
    if err or df is None or len(df) == 0 or len(df.columns) == 0:
        return default
    value = df.iloc[0, 0]
    return default if pd.isna(value) else value


@st.cache_data(ttl=300, show_spinner=False)
def db_health() -> tuple:
    """Real connection health check — actually queries the database rather
    than assuming it's fine. Returns (is_connected, status_message)."""
    if not DB_PATH.exists():
        return False, "Database file not found"
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM teams")
        count = cur.fetchone()[0]
        if count == 0:
            return False, "Database empty (0 teams)"
        return True, f"Connected · {count} teams loaded"
    except Exception as e:
        return False, f"Connection error: {type(e).__name__}"


def db_is_connected() -> tuple:
    """Kept as the public name used elsewhere in the project."""
    return db_health()


@st.cache_data(ttl=300, show_spinner=False)
def division_colors() -> dict:
    """Stable division -> colour map so a division keeps the same hue in
    every chart across the app (donut, bars, scatter legends)."""
    df, _ = run_query(
        "SELECT DISTINCT division_name FROM teams "
        "WHERE division_name IS NOT NULL ORDER BY division_name"
    )
    if df is None or len(df) == 0:
        return {}
    return {n: SERIES[i % len(SERIES)] for i, n in enumerate(df.division_name.tolist())}


def colors_for(labels) -> list:
    """Resolve a label sequence to the shared division palette."""
    cmap = division_colors()
    return [cmap.get(str(v), SERIES[i % len(SERIES)]) for i, v in enumerate(labels)]


GAME_STATE_LABELS = {
    "OFF": "Final",
    "FUT": "Upcoming",
    "LIVE": "In Progress",
    "PRE": "Pre-Game",
}

POSITION_LABELS = {
    "C": "Centre", "L": "Left Wing", "LW": "Left Wing",
    "R": "Right Wing", "RW": "Right Wing", "D": "Defence", "G": "Goaltender",
}

FORWARD_CODES = ["C", "L", "R", "LW", "RW"]


# =========================================================
# 6. SQL QUERY LIBRARY  (mirrors sql/queries.sql — unchanged)
# =========================================================
QUERY_LIBRARY = {
    "1. Most total goals this season": """
        SELECT t.team_name, t.team_abbrev, s.goals_for AS total_goals
        FROM teams t
        JOIN standings s ON t.team_id = s.team_id
        ORDER BY s.goals_for DESC
        LIMIT 1;
    """,
    "2. Top 5 point scorers league-wide": """
        SELECT p.first_name, p.last_name, t.team_abbrev,
               ss.goals, ss.assists, ss.points
        FROM skater_season_stats ss
        JOIN players p ON ss.player_id = p.player_id
        JOIN teams t ON ss.team_id = t.team_id
        ORDER BY ss.points DESC
        LIMIT 5;
    """,
    "3. Players with 20+ goals AND 30+ assists": """
        SELECT p.first_name, p.last_name, t.team_abbrev,
               ss.goals, ss.assists, ss.points
        FROM skater_season_stats ss
        JOIN players p ON ss.player_id = p.player_id
        JOIN teams t ON ss.team_id = t.team_id
        WHERE ss.goals > 20 AND ss.assists > 30
        ORDER BY ss.points DESC;
    """,
    "4. Teams above league-average points": """
        SELECT t.team_name, t.team_abbrev, s.points
        FROM teams t
        JOIN standings s ON t.team_id = s.team_id
        WHERE s.points > (SELECT AVG(points) FROM standings)
        ORDER BY s.points DESC;
    """,
    "5. Divisions averaging 90+ points": """
        SELECT t.division_name,
               ROUND(AVG(s.points), 1) AS avg_division_points,
               COUNT(*) AS num_teams
        FROM teams t
        JOIN standings s ON t.team_id = s.team_id
        GROUP BY t.division_name
        HAVING AVG(s.points) > 90
        ORDER BY avg_division_points DESC;
    """,
    "6. Best save % goalies (min 20 GP)": """
        SELECT p.first_name, p.last_name, t.team_abbrev,
               gs.games_played, gs.save_pct, gs.goals_against_avg, gs.shutouts
        FROM goalie_season_stats gs
        JOIN players p ON gs.player_id = p.player_id
        JOIN teams t ON gs.team_id = t.team_id
        WHERE gs.games_played >= 20
        ORDER BY gs.save_pct DESC
        LIMIT 10;
    """,
    "7. Most wins by team": """
        SELECT t.team_name, t.conference_name, t.division_name,
               s.wins, s.losses, s.ot_losses
        FROM teams t
        JOIN standings s ON t.team_id = s.team_id
        ORDER BY s.wins DESC
        LIMIT 10;
    """,
    "8. Leading scorer per team": """
        SELECT team_abbrev, first_name, last_name, goals, assists, points
        FROM (
            SELECT t.team_abbrev, p.first_name, p.last_name,
                   ss.goals, ss.assists, ss.points,
                   ROW_NUMBER() OVER (
                       PARTITION BY ss.team_id ORDER BY ss.points DESC
                   ) AS team_rank
            FROM skater_season_stats ss
            JOIN players p ON ss.player_id = p.player_id
            JOIN teams t ON ss.team_id = t.team_id
        ) ranked
        WHERE team_rank = 1
        ORDER BY points DESC;
    """,
    "9. Best goal differential": """
        SELECT t.team_name, t.team_abbrev, s.goals_for, s.goals_against,
               (s.goals_for - s.goals_against) AS goal_differential
        FROM teams t
        JOIN standings s ON t.team_id = s.team_id
        ORDER BY goal_differential DESC
        LIMIT 10;
    """,
    "10. Most penalty minutes vs. points": """
        SELECT p.first_name, p.last_name, t.team_abbrev,
               ss.penalty_min, ss.points, ss.games_played
        FROM skater_season_stats ss
        JOIN players p ON ss.player_id = p.player_id
        JOIN teams t ON ss.team_id = t.team_id
        ORDER BY ss.penalty_min DESC
        LIMIT 10;
    """,
    "11. Home vs. away win gap": """
        SELECT t.team_name, s.home_wins, s.away_wins,
               (s.home_wins - s.away_wins) AS home_ice_advantage
        FROM teams t
        JOIN standings s ON t.team_id = s.team_id
        ORDER BY home_ice_advantage DESC
        LIMIT 10;
    """,
}


# =========================================================
# 7. SIDEBAR — navigation + analytics control panel
# Pages are regrouped into six sections; every original page is still
# reachable (Standings + Team Info live under Teams, Player Search +
# Leaderboards under Players). Filters are contextual: the sidebar only
# offers the controls that actually apply to the page you're on, and each
# one feeds the exact same SQL predicates as before.
# =========================================================
NAV_PAGES = [
    ("Dashboard", "🏠", "Season overview"),
    ("Teams", "🏒", "Standings & profiles"),
    ("Players", "👤", "Search & leaderboards"),
    ("Games", "📊", "Schedule & results"),
    ("Insights", "🔍", "Derived observations"),
    ("SQL Lab", "💻", "Query runner"),
]
NAV_NAMES = [name for name, _, _ in NAV_PAGES]

# Filter values collected from the sidebar, consumed by the page bodies.
F: dict = {}

with st.sidebar:
    # ---- Brand ----
    write(
        """
        <div class="sb-brand">
            <div class="sb-puck">🏒</div>
            <div>
                <div class="sb-brand-name">NHL Analytics Hub</div>
                <div class="sb-brand-sub">Performance Platform</div>
            </div>
        </div>
        """
    )

    # ---- Navigation ----
    if "nav_page" not in st.session_state or st.session_state.nav_page not in NAV_NAMES:
        st.session_state.nav_page = NAV_NAMES[0]

    write('<div class="sb-label">Navigation</div>')
    for name, icon, _hint in NAV_PAGES:
        is_active = st.session_state.nav_page == name
        if st.button(
            f"{icon} {name}",
            key=f"nav_btn_{name}",
            type="primary" if is_active else "secondary",
            **_STRETCH,
        ):
            st.session_state.nav_page = name
            st.rerun()

    page = st.session_state.nav_page
    _db_ok, _db_status = db_is_connected()

    # ---- Contextual filters ----
    if _db_ok:
        seasons_df, _ = run_query(
            "SELECT DISTINCT season FROM skater_season_stats "
            "WHERE season IS NOT NULL ORDER BY season DESC"
        )
        season_values = (
            seasons_df.season.astype(str).tolist()
            if seasons_df is not None and len(seasons_df) > 0
            else []
        )

        # Only the genuinely global control lives here. Every page-specific
        # filter (player search, team picker, conference/division, schedule
        # filters) is rendered in that page's own filter bar, where it is
        # visible even with the sidebar collapsed.
        if page in ("Dashboard", "Teams", "Players", "Insights"):
            write('<div class="sb-label">Global Filter</div>')
            F["season"] = st.selectbox(
                "🗓 Season",
                ["All seasons"] + season_values,
                index=1 if len(season_values) == 1 else 0,
                format_func=_season_label,
                key="flt_season",
                help="Applies to skater and goalie season statistics on every page.",
            )

    # ---- Status panel ----
    write('<div class="sb-label">Data Source</div>')
    _status_color = ICE_BLUE if _db_ok else ACCENT_RED
    _dot = (
        f"display:inline-block; margin-right:7px; width:8px; height:8px; "
        f"border-radius:50%; background:{_status_color};"
    )
    if _db_ok:
        _dot += " box-shadow: 0 0 0 0 rgba(50,214,255,0.6); animation: pulse 2.2s infinite;"
    write(
        f"""
        <div class="sb-panel" style="padding-bottom:12px;">
            <div style="font-size:10px; font-weight:700; letter-spacing:0.13em;
                        color:{DIM_GRAY}; text-transform:uppercase;">Season</div>
            <div style="font-size:15px; font-weight:800; color:{ICE_BLUE}; margin-top:1px;">
                {_esc(CURRENT_SEASON_LABEL)}</div>
            <div style="margin-top:12px; font-size:11.5px; color:{COOL_GRAY};">
                <span style="{_dot}"></span>{_esc(_db_status)}
            </div>
            <div style="margin-top:6px; font-size:10.5px; color:{DIM_GRAY};">
                SQLite · {_esc(DB_PATH.name)}
            </div>
        </div>
        """
    )

    if not _db_ok:
        write(
            f"""
            <div style="margin-top:8px; padding:11px 13px; border-radius:12px;
                        background: rgba(226,56,79,0.11); border: 1px solid rgba(226,56,79,0.34);
                        font-size:11px; color:{COOL_GRAY}; line-height:1.5;">
                Run notebooks 01–04 to populate the database, then launch with
                <code style="color:{ICE_BLUE};">streamlit run app.py</code>
                from the project folder.
            </div>
            """
        )


# ---- Season predicate helper ------------------------------------------
def season_clause(alias: str) -> tuple:
    """Return (sql_fragment, params) for the sidebar season filter.

    Returns an empty fragment when 'All seasons' is selected, so the
    original queries run byte-identically to before.
    """
    chosen = F.get("season")
    if not chosen or chosen == "All seasons":
        return "", ()
    return f" AND {alias}.season = ?", (chosen,)


# =========================================================
# Global connection guard — shown on every page if the database isn't
# actually reachable, instead of pages silently rendering as empty.
# =========================================================
_db_connected, _db_status_msg = db_is_connected()
if not _db_connected:
    error_state(
        f"Database not connected — {_db_status_msg}",
        f"Expected the file at <code>{_esc(DB_PATH)}</code>. Run notebooks 01–04 "
        f"in order to create and populate it, then refresh this page.",
    )


# =========================================================
# 8a. DASHBOARD
# =========================================================
if page == "Dashboard":
    # ---- Hero ----
    _scale_df, _ = run_query(
        "SELECT (SELECT COUNT(*) FROM teams) AS t, (SELECT COUNT(*) FROM games) AS g"
    )
    _t = int(_scale_df.t.iloc[0]) if _scale_df is not None and len(_scale_df) else None
    _g = int(_scale_df.g.iloc[0]) if _scale_df is not None and len(_scale_df) else None
    render_hero(_db_connected, _t, _g)

    # ---- KPI row (all values from live queries) ----
    section_header("📊", "Season Overview", "Live from the project database")

    counts_df, err = run_query("""
        SELECT
            (SELECT COUNT(*) FROM teams) AS teams,
            (SELECT COUNT(*) FROM players) AS players,
            (SELECT COUNT(*) FROM games) AS games,
            (SELECT COALESCE(SUM(goals_for), 0) FROM standings) AS goals
    """)

    if err:
        error_state("Couldn't load the season KPIs", "The overview counts query failed.")
    elif counts_df is None or len(counts_df) == 0:
        empty_state("No season data yet", "Run notebooks 01–04 to populate the database.")
    else:
        row = counts_df.iloc[0]
        final_games = scalar("SELECT COUNT(*) FROM games WHERE game_state = 'OFF'", default=0)
        upcoming = scalar("SELECT COUNT(*) FROM games WHERE game_state = 'FUT'", default=0)
        avg_gpg = scalar(
            "SELECT ROUND(AVG(home_score + away_score), 2) FROM games "
            "WHERE game_state = 'OFF' AND home_score IS NOT NULL AND away_score IS NOT NULL"
        )
        skaters_n = scalar("SELECT COUNT(*) FROM skater_season_stats", default=0)
        goalies_n = scalar("SELECT COUNT(*) FROM goalie_season_stats", default=0)

        pct_played = (
            f"{final_games / int(row.games) * 100:.0f}% played"
            if row.games and int(row.games) > 0 else None
        )

        render_kpi_row([
            kpi_card("🏒", "Teams", _fmt_int(row.teams), "Franchises tracked league-wide"),
            kpi_card("👤", "Players", _fmt_int(row.players),
                     f"<b>{_fmt_int(skaters_n)}</b> skater &amp; <b>{_fmt_int(goalies_n)}</b> goalie stat lines"),
            kpi_card("🗓", "Games Tracked", _fmt_int(row.games),
                     f"<b>{_fmt_int(final_games)}</b> final · <b>{_fmt_int(upcoming)}</b> upcoming",
                     trend=pct_played, trend_dir="flat"),
            kpi_card("🔥", "Total Goals", _fmt_int(row.goals), "Season goals-for, all teams"),
            kpi_card("⚡", "Goals / Game", _fmt_float(avg_gpg, 2) if avg_gpg is not None else "—",
                     "Average across completed games", accent=True),
        ])

    spacer(24)

    # ---- Spotlight: league leaders ----
    section_header("🏅", "League Leaders", "Top performers this season")
    col_left, col_right = st.columns(2)

    with col_left:
        sc, sp = season_clause("ss")
        top_scorer_df, err = run_query(f"""
            SELECT p.first_name, p.last_name, t.team_abbrev, ss.points, ss.goals, ss.assists
            FROM skater_season_stats ss
            JOIN players p ON ss.player_id = p.player_id
            JOIN teams t ON ss.team_id = t.team_id
            WHERE 1=1{sc}
            ORDER BY ss.points DESC
            LIMIT 1
        """, sp)
        if err:
            error_state("Couldn't load the scoring leader")
        elif top_scorer_df is not None and len(top_scorer_df) > 0:
            r = top_scorer_df.iloc[0]
            write(spotlight_card(
                "Points leader",
                f"{r.first_name} {r.last_name}",
                f"<b>{_esc(r.team_abbrev)}</b> &nbsp;·&nbsp; <b>{_fmt_int(r.points)} PTS</b> "
                f"&nbsp;·&nbsp; {_fmt_int(r.goals)}G / {_fmt_int(r.assists)}A",
                "🥇",
            ))
        else:
            empty_state("No skater stats yet", "Run notebook 04 to load season statistics.", "🏒")

    with col_right:
        gc, gp_ = season_clause("gs")
        top_goalie_df, err = run_query(f"""
            SELECT p.first_name, p.last_name, t.team_abbrev, gs.save_pct, gs.wins
            FROM goalie_season_stats gs
            JOIN players p ON gs.player_id = p.player_id
            JOIN teams t ON gs.team_id = t.team_id
            WHERE gs.games_played >= 10{gc}
            ORDER BY gs.save_pct DESC
            LIMIT 1
        """, gp_)
        if err:
            error_state("Couldn't load the goaltending leader")
        elif top_goalie_df is not None and len(top_goalie_df) > 0:
            r = top_goalie_df.iloc[0]
            write(spotlight_card(
                "Best save % (min 10 GP)",
                f"{r.first_name} {r.last_name}",
                f"<b>{_esc(r.team_abbrev)}</b> &nbsp;·&nbsp; <b>{_fmt_float(r.save_pct, 3)} SV%</b> "
                f"&nbsp;·&nbsp; {_fmt_int(r.wins)} wins",
                "🧤",
            ))
        else:
            empty_state("No goalie stats yet", "Run notebook 04 to load season statistics.", "🧤")

    spacer(24)

    # ---- Analytics overview: primary + supporting chart ----
    main_col, side_col = st.columns([1.35, 1])

    with main_col:
        section_header("📈", "Scoring Race", "Top 10 point producers")
        sc, sp = season_clause("ss")
        top10_df, err = run_query(f"""
            SELECT p.first_name || ' ' || p.last_name AS player, t.team_abbrev,
                   ss.goals, ss.assists, ss.points
            FROM skater_season_stats ss
            JOIN players p ON ss.player_id = p.player_id
            JOIN teams t ON ss.team_id = t.team_id
            WHERE 1=1{sc}
            ORDER BY ss.points DESC
            LIMIT 10
        """, sp)
        if err:
            error_state("Couldn't load the scoring race")
        elif top10_df is None or len(top10_df) == 0:
            empty_state("Nothing to chart yet", "No skater season statistics available.", "📉")
        elif HAS_PLOTLY:
            d = top10_df.copy()
            d["label"] = d["player"] + "  (" + d["team_abbrev"].astype(str) + ")"
            d = d.iloc[::-1]  # highest at the top of a horizontal bar chart
            fig = go.Figure()
            fig.add_bar(
                y=d["label"], x=d["goals"], name="Goals", orientation="h",
                marker=dict(color=CYAN, line=dict(width=0)),
                hovertemplate="<b>%{y}</b><br>Goals: %{x}<extra></extra>",
            )
            fig.add_bar(
                y=d["label"], x=d["assists"], name="Assists", orientation="h",
                marker=dict(color="rgba(92,200,255,0.42)", line=dict(width=0)),
                hovertemplate="<b>%{y}</b><br>Assists: %{x}<extra></extra>",
            )
            fig.update_layout(barmode="stack")
            style_fig(fig, height=392, legend=True)
            fig.update_xaxes(title_text="Points (goals + assists)")
            fig.update_yaxes(title_text=None)
            show_fig(fig)
        else:
            fallback_bar(top10_df, "player", "points")

    with side_col:
        section_header("🎯", "Offence vs. Defence", "Goals for / against, by team")
        scatter_df, err = run_query("""
            SELECT t.team_abbrev, t.conference_name, s.goals_for, s.goals_against, s.points
            FROM teams t
            JOIN standings s ON t.team_id = s.team_id
        """)
        if err:
            error_state("Couldn't load team goal data")
        elif scatter_df is None or len(scatter_df) == 0:
            empty_state("No standings data", "Run notebook 03 to load standings.", "📉")
        elif HAS_PLOTLY:
            fig = px.scatter(
                scatter_df, x="goals_against", y="goals_for",
                color="conference_name", size="points", size_max=17,
                text="team_abbrev",
                color_discrete_sequence=[ICE_BLUE, TEAL],
                labels={
                    "goals_against": "Goals against",
                    "goals_for": "Goals for",
                    "conference_name": "Conference",
                    "points": "Points",
                },
                custom_data=["team_abbrev", "points"],
            )
            fig.update_traces(
                textposition="top center",
                textfont=dict(size=9, color=COOL_GRAY),
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>Goals for: %{y}"
                    "<br>Goals against: %{x}<br>Points: %{customdata[1]}<extra></extra>"
                ),
            )
            style_fig(fig, height=392, legend=True)
            show_fig(fig)
        else:
            auto_table(scatter_df)

    spacer(24)

    # ---- Team performance ----
    perf_left, perf_right = st.columns([1.35, 1])

    with perf_left:
        section_header("🏆", "Points Standings", "Top 12 teams by points")
        pts_df, err = run_query("""
            SELECT t.team_abbrev, t.team_name, s.points, s.wins, s.losses, s.ot_losses
            FROM teams t
            JOIN standings s ON t.team_id = s.team_id
            ORDER BY s.points DESC
            LIMIT 12
        """)
        if err or pts_df is None or len(pts_df) == 0:
            empty_state("No standings to chart", "Run notebook 03 to load standings.", "📉")
        elif HAS_PLOTLY:
            fig = px.bar(
                pts_df, x="team_abbrev", y="points",
                color="points", color_continuous_scale=[[0, "#2C5F8A"], [1, CYAN]],
                labels={"team_abbrev": "Team", "points": "Points"},
                custom_data=["team_name", "wins", "losses", "ot_losses"],
            )
            fig.update_traces(
                marker_line_width=0,
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>Points: %{y}"
                    "<br>Record: %{customdata[1]}-%{customdata[2]}-%{customdata[3]}<extra></extra>"
                ),
            )
            style_fig(fig, height=330)
            fig.update_layout(coloraxis_showscale=False)
            show_fig(fig)
        else:
            fallback_bar(pts_df, "team_abbrev", "points")

    with perf_right:
        section_header("🍩", "Goal Share by Division", "Percentage of league goals scored")
        div_df, err = run_query("""
            SELECT t.division_name, SUM(s.goals_for) AS goals_for,
                   ROUND(AVG(s.points), 1) AS avg_points
            FROM teams t
            JOIN standings s ON t.team_id = s.team_id
            GROUP BY t.division_name
            ORDER BY goals_for DESC
        """)
        if err or div_df is None or len(div_df) == 0:
            empty_state("No division data", "Run notebooks 01 and 03.", "📉")
        elif HAS_PLOTLY:
            fig = go.Figure(go.Pie(
                labels=div_df["division_name"], values=div_df["goals_for"],
                hole=0.62, sort=False,
                marker=dict(colors=colors_for(div_df["division_name"]),
                            line=dict(color=NAVY_900, width=2)),
                textinfo="percent", textfont=dict(size=11, color=WHITE),
                hovertemplate="<b>%{label}</b><br>Goals: %{value}<br>Share: %{percent}<extra></extra>",
            ))
            total_goals = int(pd.to_numeric(div_df["goals_for"], errors="coerce").fillna(0).sum())
            fig.add_annotation(
                text=f"<b>{total_goals:,}</b><br><span style='font-size:10px;color:{COOL_GRAY}'>LEAGUE GOALS</span>",
                showarrow=False, font=dict(size=17, color=WHITE, family="Manrope"),
            )
            style_fig(fig, height=330, legend=True)
            show_fig(fig)
        else:
            auto_table(div_df)

    spacer(24)

    # ---- Recent games ----
    section_header("🗓", "Recent Results", "Latest completed games")
    recent_df, err = run_query("""
        SELECT g.game_date, at.team_abbrev AS away, g.away_score,
               ht.team_abbrev AS home, g.home_score, g.venue_name
        FROM games g
        JOIN teams ht ON g.home_team_id = ht.team_id
        JOIN teams at ON g.away_team_id = at.team_id
        WHERE g.game_state = 'OFF'
          AND g.home_score IS NOT NULL AND g.away_score IS NOT NULL
        ORDER BY g.game_date DESC
        LIMIT 8
    """)
    if err:
        error_state("Couldn't load recent results")
    elif recent_df is None or len(recent_df) == 0:
        empty_state("No completed games yet", "Run notebook 03 to load the schedule.", "🗓")
    else:
        d = recent_df.copy()
        d["matchup"] = d["away"].astype(str) + "  @  " + d["home"].astype(str)
        d["score"] = d["away_score"].map(_fmt_int) + " – " + d["home_score"].map(_fmt_int)

        def _winner(r):
            try:
                if r.home_score > r.away_score:
                    return f"{r.home} win"
                if r.away_score > r.home_score:
                    return f"{r.away} win"
            except TypeError:
                pass
            return "—"

        d["result"] = d.apply(_winner, axis=1)
        stat_table(
            d,
            [("game_date", "Date", "dim"), ("matchup", "Matchup", "strong"),
             ("score", "Score", "text"), ("result", "Result", "chip"),
             ("venue_name", "Venue", "dim")],
            rank=False, max_height=None,
        )

    # ---- Insights strip ----
    spacer(24)
    section_header("💡", "Automated Insights", "Derived from the current dataset")
    ins_col1, ins_col2 = st.columns(2)

    best_diff, _ = run_query("""
        SELECT t.team_name, t.team_abbrev,
               (s.goals_for - s.goals_against) AS diff
        FROM teams t JOIN standings s ON t.team_id = s.team_id
        ORDER BY diff DESC LIMIT 1
    """)
    worst_diff, _ = run_query("""
        SELECT t.team_name, t.team_abbrev,
               (s.goals_for - s.goals_against) AS diff
        FROM teams t JOIN standings s ON t.team_id = s.team_id
        ORDER BY diff ASC LIMIT 1
    """)
    above_avg = scalar(
        "SELECT COUNT(*) FROM standings WHERE points > (SELECT AVG(points) FROM standings)"
    )
    home_edge, _ = run_query("""
        SELECT t.team_abbrev, (s.home_wins - s.away_wins) AS edge
        FROM teams t JOIN standings s ON t.team_id = s.team_id
        ORDER BY edge DESC LIMIT 1
    """)

    with ins_col1:
        if best_diff is not None and len(best_diff) > 0:
            r = best_diff.iloc[0]
            write(insight_card(
                "🥇 Best goal differential",
                f"<b>{_esc(r.team_name)}</b> lead the league at "
                f"<b>{_fmt_signed(r['diff'])}</b> goal differential.",
            ))
        if above_avg is not None:
            write(insight_card(
                "📊 Above league average",
                f"<b>{_fmt_int(above_avg)}</b> teams are sitting above the "
                f"league-average points total.",
            ))

    with ins_col2:
        if home_edge is not None and len(home_edge) > 0:
            r = home_edge.iloc[0]
            write(insight_card(
                "🏟 Strongest home-ice edge",
                f"<b>{_esc(r.team_abbrev)}</b> have <b>{_fmt_signed(r.edge)}</b> more "
                f"wins at home than on the road.",
            ))
        if worst_diff is not None and len(worst_diff) > 0:
            r = worst_diff.iloc[0]
            write(insight_card(
                "⚠️ Widest negative differential",
                f"<b>{_esc(r.team_name)}</b> are at <b>{_fmt_signed(r['diff'])}</b> "
                f"on the season.",
                warn=True,
            ))

    render_footer()


# =========================================================
# 8b. TEAMS  (original "Standings" + "Team Info" pages, regrouped)
# =========================================================
elif page == "Teams":
    page_header("🏒", "Teams", "League standings, division races and full team profiles")
    tab_standings, tab_profile = st.tabs(["📋 Standings", "🛡️ Team Profile"])

    # ---------- Standings ----------
    with tab_standings:
        # Filter bar — rendered inline (not in the sidebar) so the controls
        # are always visible next to the data they affect.
        section_header("🎛", "Filters", "Narrow the table by conference or division")
        fcol1, fcol2, fcol3 = st.columns([1, 1, 2])
        conf_df, _ = run_query(
            "SELECT DISTINCT conference_name FROM teams "
            "WHERE conference_name IS NOT NULL ORDER BY conference_name"
        )
        div_df, _ = run_query(
            "SELECT DISTINCT division_name FROM teams "
            "WHERE division_name IS NOT NULL ORDER BY division_name"
        )
        with fcol1:
            conference = st.selectbox(
                "🌐 Conference",
                ["All"] + (conf_df.conference_name.dropna().tolist() if conf_df is not None else []),
                key="flt_conference",
            )
        with fcol2:
            division = st.selectbox(
                "🧭 Division",
                ["All"] + (div_df.division_name.dropna().tolist() if div_df is not None else []),
                key="flt_division",
            )
        spacer(10)

        query = """
            SELECT t.team_name, t.team_abbrev, t.conference_name, t.division_name,
                   s.games_played, s.wins, s.losses, s.ot_losses, s.points,
                   s.goals_for, s.goals_against, s.streak_type, s.streak_count
            FROM teams t
            JOIN standings s ON t.team_id = s.team_id
            WHERE 1=1
        """
        params = []
        if conference != "All":
            query += " AND t.conference_name = ?"
            params.append(conference)
        if division != "All":
            query += " AND t.division_name = ?"
            params.append(division)
        query += " ORDER BY s.points DESC"

        df, err = run_query(query, tuple(params))
        if err:
            error_state("Standings query failed", "Check that notebooks 01 and 03 have been run.")
        elif df is None or len(df) == 0:
            empty_state("No standings for this filter",
                        "Try widening the conference or division filter in the sidebar.")
        else:
            d = df.copy()
            d["diff"] = pd.to_numeric(d["goals_for"], errors="coerce") - pd.to_numeric(
                d["goals_against"], errors="coerce"
            )
            d["record"] = (
                d["wins"].map(_fmt_int) + "-" + d["losses"].map(_fmt_int)
                + "-" + d["ot_losses"].map(_fmt_int)
            )
            d["streak"] = d["streak_type"].fillna("").astype(str) + d["streak_count"].map(
                lambda v: _fmt_int(v) if pd.notna(v) else ""
            )
            pts = pd.to_numeric(d["points"], errors="coerce")
            gp = pd.to_numeric(d["games_played"], errors="coerce").replace(0, pd.NA)
            d["pts_pct"] = (pts / (gp * 2) * 100).round(1)

            scope = "League" if (conference == "All" and division == "All") else (
                division if division != "All" else conference
            )
            render_kpi_row([
                kpi_card("🛡️", "Teams in view", _fmt_int(len(d)), _esc(scope)),
                kpi_card("🏆", "Points leader", _esc(d.iloc[0].team_abbrev),
                         f"<b>{_fmt_int(d.iloc[0].points)} PTS</b> · {_esc(d.iloc[0].record)}",
                         small_value=True),
                kpi_card("📊", "Average points", _fmt_float(pts.mean(), 1), "Across teams in view"),
                kpi_card("🔥", "Most goals for", _fmt_int(pd.to_numeric(d["goals_for"], errors="coerce").max()),
                         f"<b>{_esc(d.loc[pd.to_numeric(d['goals_for'], errors='coerce').idxmax()].team_abbrev)}</b> leads the group"),
                kpi_card("🧱", "Best differential", _fmt_signed(d["diff"].max()),
                         f"<b>{_esc(d.loc[d['diff'].idxmax()].team_abbrev)}</b> · goals for − against",
                         accent=True),
            ])

            spacer(22)
            section_header("📋", "Standings Table",
                           f"{len(d)} teams · sorted by points")
            stat_table(
                d,
                [
                    ("team_name", "Team", "strong"),
                    ("team_abbrev", "Abbr", "chip"),
                    ("conference_name", "Conference", "dim"),
                    ("division_name", "Division", "dim"),
                    ("games_played", "GP", "int"),
                    ("record", "Record", "text"),
                    ("points", "PTS", "int"),
                    ("pts_pct", "PTS%", "float2"),
                    ("goals_for", "GF", "int"),
                    ("goals_against", "GA", "int"),
                    ("diff", "DIFF", "signed"),
                    ("streak", "Streak", "dim"),
                ],
                bar_col="points",
                max_height=520,
            )

            spacer(22)
            c1, c2 = st.columns([1.3, 1])
            with c1:
                section_header("🧱", "Goal Differential", "Goals for minus goals against")
                if HAS_PLOTLY:
                    dd = d.sort_values("diff")
                    fig = go.Figure(go.Bar(
                        x=dd["diff"], y=dd["team_abbrev"], orientation="h",
                        marker=dict(
                            color=[ACCENT_RED if v < 0 else CYAN for v in dd["diff"].fillna(0)],
                            line=dict(width=0),
                        ),
                        hovertemplate="<b>%{y}</b><br>Differential: %{x}<extra></extra>",
                    ))
                    style_fig(fig, height=max(320, 17 * len(dd)))
                    fig.update_xaxes(title_text="Goal differential")
                    fig.update_yaxes(title_text=None, tickfont=dict(size=10, color=COOL_GRAY))
                    show_fig(fig)
                else:
                    fallback_bar(d, "team_abbrev", "diff")
            with c2:
                section_header("🏟", "Home vs. Away Wins", "Where wins are being earned")
                ha_df, ha_err = run_query("""
                    SELECT t.team_abbrev, s.home_wins, s.away_wins
                    FROM teams t JOIN standings s ON t.team_id = s.team_id
                    ORDER BY (s.home_wins + s.away_wins) DESC
                    LIMIT 12
                """)
                if ha_err or ha_df is None or len(ha_df) == 0:
                    empty_state("No home/away split available", "Standings table is missing this column.")
                elif HAS_PLOTLY:
                    fig = go.Figure()
                    fig.add_bar(x=ha_df["team_abbrev"], y=ha_df["home_wins"], name="Home wins",
                                marker_color=CYAN, marker_line_width=0,
                                hovertemplate="<b>%{x}</b><br>Home wins: %{y}<extra></extra>")
                    fig.add_bar(x=ha_df["team_abbrev"], y=ha_df["away_wins"], name="Away wins",
                                marker_color="rgba(123,232,212,0.75)", marker_line_width=0,
                                hovertemplate="<b>%{x}</b><br>Away wins: %{y}<extra></extra>")
                    fig.update_layout(barmode="group")
                    style_fig(fig, height=340, legend=True)
                    fig.update_yaxes(title_text="Wins")
                    show_fig(fig)
                else:
                    auto_table(ha_df)

    # ---------- Team profile ----------
    with tab_profile:
        teams_df, err = run_query(
            "SELECT team_id, team_name, team_abbrev, logo_url FROM teams ORDER BY team_name"
        )
        if err or teams_df is None or len(teams_df) == 0:
            error_state("Couldn't load the team list", "Has notebook 01 been run?")
        else:
            # Team picker sits at the top of the tab, as in the original app.
            pick_col, _pad = st.columns([2, 3])
            with pick_col:
                chosen_name = st.selectbox(
                    "🛡️ Choose a team",
                    teams_df.team_name.tolist(),
                    key="flt_team_name",
                )
            match = teams_df[teams_df.team_name == chosen_name]
            team_row = match.iloc[0] if len(match) else teams_df.iloc[0]
            team_id = int(team_row.team_id)

            col_logo, col_info = st.columns([1, 4])
            with col_logo:
                shown = False
                if isinstance(team_row.logo_url, str) and team_row.logo_url.strip():
                    try:
                        st.image(team_row.logo_url, width=118)
                        shown = True
                    except Exception:
                        shown = False
                if not shown:
                    write(
                        f"""
                        <div style="width:118px;height:118px;border-radius:20px;display:flex;
                                    align-items:center;justify-content:center;font-size:42px;
                                    background:rgba(92,200,255,0.10);border:1px solid {BORDER_HI};">🛡️</div>
                        """
                    )
            with col_info:
                detail_df, _ = run_query("""
                    SELECT t.conference_name, t.division_name, s.wins, s.losses,
                           s.ot_losses, s.points, s.games_played, s.goals_for, s.goals_against
                    FROM teams t
                    JOIN standings s ON t.team_id = s.team_id
                    WHERE t.team_id = ?
                """, (team_id,))
                write(
                    f"""
                    <div style="padding-top:6px;">
                        <div class="page-title" style="font-size:27px;">{_esc(team_row.team_name)}</div>
                        <div class="page-sub"><span class="chip ice">{_esc(team_row.team_abbrev)}</span></div>
                    </div>
                    """
                )
                if detail_df is not None and len(detail_df) > 0:
                    dd = detail_df.iloc[0]
                    rank = scalar(
                        "SELECT COUNT(*) + 1 FROM standings WHERE points > "
                        "(SELECT points FROM standings WHERE team_id = ?)", (team_id,)
                    )
                    write(
                        f"""
                        <div style="display:flex;flex-wrap:wrap;gap:8px 10px;margin-top:12px;">
                            <span class="chip">🌐 {_esc(dd.conference_name)}</span>
                            <span class="chip">🧭 {_esc(dd.division_name)}</span>
                            <span class="chip teal">📈 Record {_fmt_int(dd.wins)}-{_fmt_int(dd.losses)}-{_fmt_int(dd.ot_losses)}</span>
                            <span class="chip ice">🏆 {_fmt_int(dd.points)} points</span>
                            {f'<span class="chip">#{_fmt_int(rank)} in league</span>' if rank is not None else ''}
                        </div>
                        """
                    )
                else:
                    empty_state("No standings row for this team yet",
                                "Run notebook 03 to load standings.", "🛡️")

            spacer(20)

            if detail_df is not None and len(detail_df) > 0:
                dd = detail_df.iloc[0]
                gf = pd.to_numeric(pd.Series([dd.goals_for]), errors="coerce").iloc[0]
                ga = pd.to_numeric(pd.Series([dd.goals_against]), errors="coerce").iloc[0]
                gp_val = pd.to_numeric(pd.Series([dd.games_played]), errors="coerce").iloc[0]
                render_kpi_row([
                    kpi_card("🗓", "Games played", _fmt_int(dd.games_played), "This season"),
                    kpi_card("🏆", "Points", _fmt_int(dd.points),
                             f"<b>{_fmt_int(dd.wins)}</b> wins · <b>{_fmt_int(dd.ot_losses)}</b> OTL"),
                    kpi_card("🔥", "Goals for", _fmt_int(gf),
                             f"{_fmt_float(gf / gp_val, 2) if gp_val else '—'} per game"),
                    kpi_card("🥅", "Goals against", _fmt_int(ga),
                             f"{_fmt_float(ga / gp_val, 2) if gp_val else '—'} per game"),
                    kpi_card("🧱", "Differential", _fmt_signed(gf - ga if pd.notna(gf) and pd.notna(ga) else None),
                             "Goals for − goals against", accent=True),
                ])
                spacer(22)

            # Roster + team scoring
            ros_left, ros_right = st.columns([1.5, 1])

            with ros_left:
                section_header("👥", "Roster", "Grouped by position")
                roster_df, err = run_query("""
                    SELECT first_name, last_name, position, jersey_number,
                           shoots_catches, height_cm, weight_kg
                    FROM players
                    WHERE team_id = ?
                    ORDER BY position, last_name
                """, (team_id,))
                if err:
                    error_state("Couldn't load the roster")
                elif roster_df is None or len(roster_df) == 0:
                    empty_state("No roster data for this team yet",
                                "Run notebook 02 to load rosters.", "👥")
                else:
                    r = roster_df.copy()
                    r["player"] = r["first_name"].astype(str) + " " + r["last_name"].astype(str)
                    r["pos_label"] = r["position"].map(POSITION_LABELS).fillna(r["position"])
                    groups = {
                        "Forwards": r[r.position.isin(FORWARD_CODES)],
                        "Defence": r[r.position == "D"],
                        "Goalies": r[r.position == "G"],
                    }
                    tabs = st.tabs([f"{k} ({len(v)})" for k, v in groups.items()])
                    for tab, (label, group_df) in zip(tabs, groups.items()):
                        with tab:
                            if len(group_df) == 0:
                                empty_state(f"No {label.lower()} on file",
                                            "This position group is empty for the selected team.", "👤")
                            else:
                                stat_table(
                                    group_df.sort_values("last_name"),
                                    [("jersey_number", "#", "int"),
                                     ("player", "Player", "strong"),
                                     ("pos_label", "Position", "dim"),
                                     ("shoots_catches", "S/C", "ctr"),
                                     ("height_cm", "Height (cm)", "int"),
                                     ("weight_kg", "Weight (kg)", "int")],
                                    rank=False, max_height=380,
                                )

            with ros_right:
                section_header("📈", "Scoring Leaders", "Team points leaders")
                sc, sp = season_clause("ss")
                team_scorers, err = run_query(f"""
                    SELECT p.first_name || ' ' || p.last_name AS player,
                           ss.goals, ss.assists, ss.points
                    FROM skater_season_stats ss
                    JOIN players p ON ss.player_id = p.player_id
                    WHERE ss.team_id = ?{sc}
                    ORDER BY ss.points DESC
                    LIMIT 10
                """, (team_id,) + sp)
                if err or team_scorers is None or len(team_scorers) == 0:
                    empty_state("No skater stats for this team",
                                "Run notebook 04 to load season statistics.", "📉")
                elif HAS_PLOTLY:
                    ts = team_scorers.iloc[::-1]
                    fig = go.Figure(go.Bar(
                        x=ts["points"], y=ts["player"], orientation="h",
                        marker=dict(color=CYAN, line=dict(width=0)),
                        customdata=ts[["goals", "assists"]].values,
                        hovertemplate=("<b>%{y}</b><br>Points: %{x}"
                                       "<br>%{customdata[0]}G / %{customdata[1]}A<extra></extra>"),
                    ))
                    style_fig(fig, height=352)
                    fig.update_xaxes(title_text="Points")
                    fig.update_yaxes(title_text=None, tickfont=dict(size=10, color=COOL_GRAY))
                    show_fig(fig)
                else:
                    fallback_bar(team_scorers, "player", "points")

                if roster_df is not None and len(roster_df) > 0 and HAS_PLOTLY:
                    section_header("🥍", "Roster Composition", "Players by position group")
                    comp = (
                        roster_df.assign(
                            grp=roster_df.position.map(
                                lambda p: "Forwards" if p in FORWARD_CODES
                                else ("Defence" if p == "D" else ("Goalies" if p == "G" else "Other"))
                            )
                        )
                        .groupby("grp", as_index=False)
                        .size()
                        .rename(columns={"size": "players"})
                    )
                    fig = go.Figure(go.Pie(
                        labels=comp["grp"], values=comp["players"], hole=0.6, sort=False,
                        marker=dict(colors=SERIES, line=dict(color=NAVY_900, width=2)),
                        textinfo="value", textfont=dict(size=11, color=WHITE),
                        hovertemplate="<b>%{label}</b><br>%{value} players<extra></extra>",
                    ))
                    fig.add_annotation(
                        text=f"<b>{len(roster_df)}</b><br><span style='font-size:10px;color:{COOL_GRAY}'>PLAYERS</span>",
                        showarrow=False, font=dict(size=17, color=WHITE, family="Manrope"),
                    )
                    style_fig(fig, height=270, legend=True)
                    show_fig(fig)

    render_footer()


# =========================================================
# 8c. PLAYERS  (original "Player Search" + "Leaderboards", regrouped)
# =========================================================
elif page == "Players":
    page_header("👤", "Players", "Search any player, or browse league-wide leaderboards")
    tab_search, tab_leaders = st.tabs(["🔍 Player Search", "🏆 Leaderboards"])

    POS_SQL = {
        "Forwards": (" AND p.position IN ('C','L','R','LW','RW')", ()),
        "Defence": (" AND p.position = 'D'", ()),
        "Goaltenders": (" AND p.position = 'G'", ()),
    }

    # ---------- Player search ----------
    with tab_search:
        # Search controls live in the page body so they're impossible to miss.
        s_col, p_col, _pad = st.columns([2, 1, 1])
        with s_col:
            search_term = st.text_input(
                "🔍 Search by player name",
                placeholder="e.g. McDavid",
                key="flt_player_search",
            )
        with p_col:
            pos_group = st.selectbox(
                "🥍 Position group",
                ["All", "Forwards", "Defence", "Goaltenders"],
                key="flt_pos_group",
            )
        pos_sql, _ = POS_SQL.get(pos_group, ("", ()))
        spacer(6)

        if not search_term:
            empty_state(
                "Search for a player",
                "Type a name into the search box above to look up any player "
                "in the league.",
                "🔍",
            )
        else:
            query = f"""
                SELECT p.player_id, p.first_name, p.last_name, p.position,
                       p.headshot_url, p.jersey_number, p.height_cm, p.weight_kg,
                       p.shoots_catches, t.team_abbrev, t.team_name, t.team_id
                FROM players p
                JOIN teams t ON p.team_id = t.team_id
                WHERE (p.first_name || ' ' || p.last_name) LIKE ?{pos_sql}
                ORDER BY p.last_name
            """
            matches_df, err = run_query(query, (f"%{search_term}%",))

            if err:
                error_state("Player search failed", "Check that notebook 02 has been run.")
            elif matches_df is None or len(matches_df) == 0:
                empty_state("No players matched",
                            f"Nothing found for “{search_term}” in the {pos_group.lower()} group.",
                            "🔍")
            else:
                match_labels = [
                    f"{r.first_name} {r.last_name} ({r.team_abbrev}) · {POSITION_LABELS.get(r.position, r.position)}"
                    for r in matches_df.itertuples()
                ]
                st.caption(f"{len(match_labels)} player(s) matched “{search_term}”")
                chosen_label = st.selectbox("Select a player", match_labels, key="player_pick")
                chosen_row = matches_df.iloc[match_labels.index(chosen_label)]
                player_id = int(chosen_row.player_id)
                is_goalie = chosen_row.position == "G"

                col_photo, col_meta = st.columns([1, 4])
                with col_photo:
                    shown = False
                    if isinstance(chosen_row.headshot_url, str) and chosen_row.headshot_url.strip():
                        try:
                            st.image(chosen_row.headshot_url, width=132)
                            shown = True
                        except Exception:
                            shown = False
                    if not shown:
                        write(
                            f"""
                            <div style="width:132px;height:132px;border-radius:20px;display:flex;
                                        align-items:center;justify-content:center;font-size:46px;
                                        background:rgba(92,200,255,0.10);border:1px solid {BORDER_HI};">
                                {'🧤' if is_goalie else '🏒'}</div>
                            """
                        )
                with col_meta:
                    write(
                        f"""
                        <div style="padding-top:8px;">
                            <div class="page-title" style="font-size:27px;">
                                {_esc(chosen_row.first_name)} {_esc(chosen_row.last_name)}</div>
                            <div style="display:flex;flex-wrap:wrap;gap:8px 10px;margin-top:12px;">
                                <span class="chip ice">{_esc(chosen_row.team_abbrev)}</span>
                                <span class="chip">{_esc(POSITION_LABELS.get(chosen_row.position, chosen_row.position))}</span>
                                {f'<span class="chip">#{_fmt_int(chosen_row.jersey_number)}</span>' if pd.notna(chosen_row.jersey_number) else ''}
                                {f'<span class="chip">{_fmt_int(chosen_row.height_cm)} cm</span>' if pd.notna(chosen_row.height_cm) else ''}
                                {f'<span class="chip">{_fmt_int(chosen_row.weight_kg)} kg</span>' if pd.notna(chosen_row.weight_kg) else ''}
                                {f'<span class="chip">{"Catches" if is_goalie else "Shoots"} {_esc(chosen_row.shoots_catches)}</span>' if isinstance(chosen_row.shoots_catches, str) and chosen_row.shoots_catches else ''}
                            </div>
                            <div class="page-sub" style="margin-top:10px;">{_esc(chosen_row.team_name)}</div>
                        </div>
                        """
                    )

                spacer(20)

                if is_goalie:
                    sc, sp = season_clause("goalie_season_stats")
                    stats_df, err = run_query(f"""
                        SELECT season, games_played, wins, losses, ot_losses,
                               save_pct, goals_against_avg, shutouts, saves
                        FROM goalie_season_stats
                        WHERE player_id = ?{sc}
                        ORDER BY season DESC
                    """, (player_id,) + sp)
                else:
                    sc, sp = season_clause("skater_season_stats")
                    stats_df, err = run_query(f"""
                        SELECT season, games_played, goals, assists, points,
                               plus_minus, penalty_min, shots, avg_toi
                        FROM skater_season_stats
                        WHERE player_id = ?{sc}
                        ORDER BY season DESC
                    """, (player_id,) + sp)

                if err:
                    error_state("Couldn't load season statistics")
                elif stats_df is None or len(stats_df) == 0:
                    empty_state("No season stats on file for this player",
                                "Run notebook 04 to load season statistics.", "📉")
                else:
                    row = stats_df.iloc[0]
                    # display copy with the season code shown as '2025-26'
                    stats_view = stats_df.copy()
                    if "season" in stats_view.columns:
                        stats_view["season"] = stats_view["season"].map(_season_label)
                    section_header(
                        "📊", "Season Statistics",
                        f"Season {_season_label(row.season)}" if "season" in stats_df.columns else "",
                    )
                    if is_goalie:
                        gp_v = pd.to_numeric(pd.Series([row.games_played]), errors="coerce").iloc[0]
                        render_kpi_row([
                            kpi_card("🗓", "Games played", _fmt_int(row.games_played), "This season"),
                            kpi_card("🏒", "Wins", _fmt_int(row.wins),
                                     f"{_fmt_int(row.losses)}L · {_fmt_int(row.ot_losses)}OTL"),
                            kpi_card("🧤", "Save %", _fmt_float(row.save_pct, 3), "Shots saved / shots faced"),
                            kpi_card("🥅", "GAA", _fmt_float(row.goals_against_avg, 2), "Goals against average"),
                            kpi_card("🛡️", "Shutouts", _fmt_int(row.shutouts),
                                     f"<b>{_fmt_int(row.saves)}</b> total saves", accent=True),
                        ])
                        spacer(22)
                        c1, c2 = st.columns([1, 1])
                        with c1:
                            section_header("📈", "Workload Split", "Decisions this season")
                            if HAS_PLOTLY:
                                labels = ["Wins", "Losses", "OT losses"]
                                values = [
                                    pd.to_numeric(pd.Series([row.wins]), errors="coerce").fillna(0).iloc[0],
                                    pd.to_numeric(pd.Series([row.losses]), errors="coerce").fillna(0).iloc[0],
                                    pd.to_numeric(pd.Series([row.ot_losses]), errors="coerce").fillna(0).iloc[0],
                                ]
                                fig = go.Figure(go.Pie(
                                    labels=labels, values=values, hole=0.6, sort=False,
                                    marker=dict(colors=[CYAN, "#3F6488", VIOLET],
                                                line=dict(color=NAVY_900, width=2)),
                                    textinfo="value", textfont=dict(size=11, color=WHITE),
                                    hovertemplate="<b>%{label}</b><br>%{value} (%{percent})<extra></extra>",
                                ))
                                fig.add_annotation(
                                    text=f"<b>{_fmt_int(gp_v)}</b><br><span style='font-size:10px;color:{COOL_GRAY}'>GP</span>",
                                    showarrow=False, font=dict(size=17, color=WHITE, family="Manrope"))
                                style_fig(fig, height=270, legend=True)
                                show_fig(fig)
                        with c2:
                            section_header("📋", "Season Log", "All rows on file")
                            stat_table(
                                stats_view,
                                [("season", "Season", "dim"), ("games_played", "GP", "int"),
                                 ("wins", "W", "int"), ("losses", "L", "int"),
                                 ("ot_losses", "OTL", "int"), ("save_pct", "SV%", "float3"),
                                 ("goals_against_avg", "GAA", "float2"),
                                 ("shutouts", "SO", "int"), ("saves", "SV", "int")],
                                rank=False, max_height=300,
                            )
                    else:
                        gp_v = pd.to_numeric(pd.Series([row.games_played]), errors="coerce").iloc[0]
                        pts_v = pd.to_numeric(pd.Series([row.points]), errors="coerce").iloc[0]
                        ppg = (pts_v / gp_v) if (pd.notna(gp_v) and gp_v) else None
                        render_kpi_row([
                            kpi_card("🔥", "Goals", _fmt_int(row.goals), "Season total"),
                            kpi_card("🎯", "Assists", _fmt_int(row.assists), "Season total"),
                            kpi_card("⚡", "Points", _fmt_int(row.points),
                                     f"<b>{_fmt_float(ppg, 2) if ppg is not None else '—'}</b> per game"),
                            kpi_card("📊", "Plus / minus", _fmt_signed(row.plus_minus),
                                     "On-ice goal differential"),
                            kpi_card("🥊", "Penalty minutes", _fmt_int(row.penalty_min),
                                     f"<b>{_fmt_int(row.shots)}</b> shots · TOI {_esc(row.avg_toi)}",
                                     accent=True),
                        ])
                        spacer(22)
                        c1, c2 = st.columns([1, 1])
                        with c1:
                            section_header("📈", "Production Split", "Goals vs. assists")
                            if HAS_PLOTLY:
                                g_v = pd.to_numeric(pd.Series([row.goals]), errors="coerce").fillna(0).iloc[0]
                                a_v = pd.to_numeric(pd.Series([row.assists]), errors="coerce").fillna(0).iloc[0]
                                fig = go.Figure(go.Bar(
                                    x=["Goals", "Assists"], y=[g_v, a_v],
                                    marker=dict(color=[CYAN, ICE_BLUE], line=dict(width=0)),
                                    text=[_fmt_int(g_v), _fmt_int(a_v)], textposition="outside",
                                    textfont=dict(color=WHITE, size=12),
                                    hovertemplate="<b>%{x}</b>: %{y}<extra></extra>",
                                ))
                                style_fig(fig, height=300)
                                fig.update_yaxes(title_text="Count")
                                show_fig(fig)
                            else:
                                fallback_bar(
                                    pd.DataFrame({"Stat": ["Goals", "Assists"],
                                                  "Count": [row.goals, row.assists]}),
                                    "Stat", "Count",
                                )
                        with c2:
                            section_header("📋", "Season Log", "All rows on file")
                            stat_table(
                                stats_view,
                                [("season", "Season", "dim"), ("games_played", "GP", "int"),
                                 ("goals", "G", "int"), ("assists", "A", "int"),
                                 ("points", "PTS", "int"), ("plus_minus", "+/−", "signed"),
                                 ("penalty_min", "PIM", "int"), ("shots", "SOG", "int"),
                                 ("avg_toi", "TOI", "dim")],
                                rank=False, max_height=300,
                            )

    # ---------- Leaderboards ----------
    with tab_leaders:
        n_col, _pad = st.columns([1, 3])
        with n_col:
            top_n = int(st.slider("📏 Leaderboard size", 5, 30, 15, 5, key="flt_top_n"))
        sc, sp = season_clause("ss")
        gc, gp_ = season_clause("gs")

        lb_points, lb_goals, lb_pim, lb_save, lb_wins = st.tabs(
            ["⚡ Top Scorers", "🔥 Goal Scorers", "🥊 Penalty Minutes",
             "🧤 Best Save %", "🏒 Most Wins"]
        )

        with lb_points:
            df, err = run_query(f"""
                SELECT p.first_name, p.last_name, t.team_abbrev,
                       ss.games_played, ss.goals, ss.assists, ss.points, ss.plus_minus
                FROM skater_season_stats ss
                JOIN players p ON ss.player_id = p.player_id
                JOIN teams t ON ss.team_id = t.team_id
                WHERE 1=1{sc}
                ORDER BY ss.points DESC
                LIMIT ?
            """, sp + (top_n,))
            if err:
                error_state("Leaderboard query failed")
            elif df is None or len(df) == 0:
                empty_state("No skater statistics available", "Run notebook 04 first.")
            else:
                d = df.copy()
                d["player"] = d["first_name"].astype(str) + " " + d["last_name"].astype(str)
                gpn = pd.to_numeric(d["games_played"], errors="coerce").replace(0, pd.NA)
                d["ppg"] = (pd.to_numeric(d["points"], errors="coerce") / gpn).round(2)
                section_header("⚡", "Points Leaders", f"Top {len(d)} skaters league-wide")
                stat_table(
                    d,
                    [("player", "Player", "strong"), ("team_abbrev", "Team", "chip"),
                     ("games_played", "GP", "int"), ("goals", "G", "int"),
                     ("assists", "A", "int"), ("points", "PTS", "int"),
                     ("ppg", "PTS/GP", "float2"), ("plus_minus", "+/−", "signed")],
                    bar_col="points", max_height=560,
                )

        with lb_goals:
            df, err = run_query(f"""
                SELECT p.first_name, p.last_name, t.team_abbrev,
                       ss.games_played, ss.goals, ss.shots
                FROM skater_season_stats ss
                JOIN players p ON ss.player_id = p.player_id
                JOIN teams t ON ss.team_id = t.team_id
                WHERE 1=1{sc}
                ORDER BY ss.goals DESC
                LIMIT ?
            """, sp + (top_n,))
            if err:
                error_state("Leaderboard query failed")
            elif df is None or len(df) == 0:
                empty_state("No skater statistics available", "Run notebook 04 first.")
            else:
                d = df.copy()
                d["player"] = d["first_name"].astype(str) + " " + d["last_name"].astype(str)
                shots = pd.to_numeric(d["shots"], errors="coerce").replace(0, pd.NA)
                d["shot_pct"] = (pd.to_numeric(d["goals"], errors="coerce") / shots * 100).round(1)
                section_header("🔥", "Goal Scoring Leaders", f"Top {len(d)} by goals, with shooting %")
                stat_table(
                    d,
                    [("player", "Player", "strong"), ("team_abbrev", "Team", "chip"),
                     ("games_played", "GP", "int"), ("goals", "G", "int"),
                     ("shots", "SOG", "int"), ("shot_pct", "S%", "float2")],
                    bar_col="goals", max_height=560,
                )

        with lb_pim:
            df, err = run_query(f"""
                SELECT p.first_name, p.last_name, t.team_abbrev,
                       ss.games_played, ss.penalty_min, ss.points
                FROM skater_season_stats ss
                JOIN players p ON ss.player_id = p.player_id
                JOIN teams t ON ss.team_id = t.team_id
                WHERE 1=1{sc}
                ORDER BY ss.penalty_min DESC
                LIMIT ?
            """, sp + (top_n,))
            if err:
                error_state("Leaderboard query failed")
            elif df is None or len(df) == 0:
                empty_state("No skater statistics available", "Run notebook 04 first.")
            else:
                d = df.copy()
                d["player"] = d["first_name"].astype(str) + " " + d["last_name"].astype(str)
                section_header("🥊", "Penalty Minutes", f"Top {len(d)} — discipline vs. production")
                stat_table(
                    d,
                    [("player", "Player", "strong"), ("team_abbrev", "Team", "chip"),
                     ("games_played", "GP", "int"), ("penalty_min", "PIM", "int"),
                     ("points", "PTS", "int")],
                    bar_col="penalty_min", max_height=460,
                )
                if HAS_PLOTLY:
                    spacer(16)
                    section_header("📉", "Penalties vs. Points", "Does time in the box cost production?")
                    fig = px.scatter(
                        d, x="penalty_min", y="points", text="team_abbrev",
                        labels={"penalty_min": "Penalty minutes", "points": "Points"},
                        custom_data=["player", "team_abbrev"],
                        color_discrete_sequence=[CYAN],
                    )
                    fig.update_traces(
                        marker=dict(size=11, opacity=0.85,
                                    line=dict(width=1, color="rgba(255,255,255,0.35)")),
                        textposition="top center", textfont=dict(size=9, color=DIM_GRAY),
                        hovertemplate=("<b>%{customdata[0]}</b> (%{customdata[1]})"
                                       "<br>PIM: %{x}<br>Points: %{y}<extra></extra>"),
                    )
                    style_fig(fig, height=330)
                    show_fig(fig)

        with lb_save:
            df, err = run_query(f"""
                SELECT p.first_name, p.last_name, t.team_abbrev,
                       gs.games_played, gs.save_pct, gs.goals_against_avg,
                       gs.shutouts, gs.wins
                FROM goalie_season_stats gs
                JOIN players p ON gs.player_id = p.player_id
                JOIN teams t ON gs.team_id = t.team_id
                WHERE gs.games_played >= 10{gc}
                ORDER BY gs.save_pct DESC
                LIMIT ?
            """, gp_ + (top_n,))
            if err:
                error_state("Leaderboard query failed")
            elif df is None or len(df) == 0:
                empty_state("No goalie statistics available",
                            "Run notebook 04, or lower the games-played threshold.")
            else:
                d = df.copy()
                d["player"] = d["first_name"].astype(str) + " " + d["last_name"].astype(str)
                section_header("🧤", "Save Percentage", f"Top {len(d)} goaltenders (min 10 GP)")
                stat_table(
                    d,
                    [("player", "Player", "strong"), ("team_abbrev", "Team", "chip"),
                     ("games_played", "GP", "int"), ("save_pct", "SV%", "float3"),
                     ("goals_against_avg", "GAA", "float2"),
                     ("shutouts", "SO", "int"), ("wins", "W", "int")],
                    bar_col="save_pct", max_height=460,
                )
                if HAS_PLOTLY:
                    spacer(16)
                    section_header("🎯", "Save % vs. GAA", "Upper-left is elite goaltending")
                    fig = px.scatter(
                        d, x="goals_against_avg", y="save_pct",
                        size="games_played", size_max=18, text="team_abbrev",
                        labels={"goals_against_avg": "Goals against average",
                                "save_pct": "Save percentage"},
                        custom_data=["player", "games_played"],
                        color_discrete_sequence=[TEAL],
                    )
                    fig.update_traces(
                        textposition="top center", textfont=dict(size=9, color=DIM_GRAY),
                        hovertemplate=("<b>%{customdata[0]}</b><br>SV%: %{y:.3f}"
                                       "<br>GAA: %{x:.2f}<br>GP: %{customdata[1]}<extra></extra>"),
                    )
                    style_fig(fig, height=330)
                    show_fig(fig)

        with lb_wins:
            df, err = run_query(f"""
                SELECT p.first_name, p.last_name, t.team_abbrev,
                       gs.games_played, gs.wins, gs.losses, gs.ot_losses, gs.save_pct
                FROM goalie_season_stats gs
                JOIN players p ON gs.player_id = p.player_id
                JOIN teams t ON gs.team_id = t.team_id
                WHERE 1=1{gc}
                ORDER BY gs.wins DESC
                LIMIT ?
            """, gp_ + (top_n,))
            if err:
                error_state("Leaderboard query failed")
            elif df is None or len(df) == 0:
                empty_state("No goalie statistics available", "Run notebook 04 first.")
            else:
                d = df.copy()
                d["player"] = d["first_name"].astype(str) + " " + d["last_name"].astype(str)
                section_header("🏒", "Goaltender Wins", f"Top {len(d)} by wins")
                stat_table(
                    d,
                    [("player", "Player", "strong"), ("team_abbrev", "Team", "chip"),
                     ("games_played", "GP", "int"), ("wins", "W", "int"),
                     ("losses", "L", "int"), ("ot_losses", "OTL", "int"),
                     ("save_pct", "SV%", "float3")],
                    bar_col="wins", max_height=460,
                )

    render_footer()


# =========================================================
# 8d. GAMES  (original "Game Results" page)
# =========================================================
elif page == "Games":
    page_header("📊", "Game Analytics", "Browse the schedule and results by team, date or state")

    # Schedule filter bar — inline, mirroring the original layout.
    section_header("🎛", "Filters", "Filter the schedule by team, state or date")
    g1, g2, g3, g4 = st.columns([1, 1.4, 1, 1])
    teams_abbrev_df, _ = run_query("SELECT team_abbrev FROM teams ORDER BY team_abbrev")
    with g1:
        team_filter = st.selectbox(
            "🛡️ Team",
            ["All"] + (teams_abbrev_df.team_abbrev.dropna().tolist()
                       if teams_abbrev_df is not None else []),
            key="flt_game_team",
        )
    with g2:
        state_filter = st.radio(
            "🚦 Game state", ["All", "Final", "Upcoming"],
            horizontal=True, key="flt_game_state",
        )
    with g3:
        date_filter = st.date_input("📅 On or after", value=None, key="flt_game_date")
    with g4:
        row_limit = int(st.slider("📏 Max rows", 50, 500, 200, 50, key="flt_game_limit"))
    spacer(10)

    query = """
        SELECT g.game_date, ht.team_abbrev AS home, g.home_score,
               at.team_abbrev AS away, g.away_score, g.game_state, g.venue_name
        FROM games g
        JOIN teams ht ON g.home_team_id = ht.team_id
        JOIN teams at ON g.away_team_id = at.team_id
        WHERE 1=1
    """
    params = []

    if team_filter != "All":
        query += " AND (ht.team_abbrev = ? OR at.team_abbrev = ?)"
        params.extend([team_filter, team_filter])

    if state_filter == "Final":
        query += " AND g.game_state = 'OFF'"
    elif state_filter == "Upcoming":
        query += " AND g.game_state = 'FUT'"

    if date_filter:
        query += " AND g.game_date >= ?"
        params.append(date_filter.strftime("%Y-%m-%d"))

    query += " ORDER BY g.game_date DESC LIMIT ?"
    params.append(row_limit)

    df, err = run_query(query, tuple(params))

    if err:
        error_state("Schedule query failed", "Check that notebook 03 has been run.")
    elif df is None or len(df) == 0:
        empty_state("No games matched those filters",
                    "Try clearing the team, date or game-state filter in the sidebar.", "🗓")
    else:
        d = df.copy()
        d["state_label"] = d["game_state"].map(GAME_STATE_LABELS).fillna(d["game_state"])
        hs = pd.to_numeric(d["home_score"], errors="coerce")
        as_ = pd.to_numeric(d["away_score"], errors="coerce")
        d["total_goals"] = hs + as_
        played = d[d["game_state"] == "OFF"]

        render_kpi_row([
            kpi_card("🗓", "Games in view", _fmt_int(len(d)),
                     f"Limit {_fmt_int(row_limit)} rows · {_esc(team_filter)} · {_esc(state_filter)}"),
            kpi_card("✅", "Completed", _fmt_int(len(played)), "Final results in this selection"),
            kpi_card("⏳", "Upcoming", _fmt_int(int((d["game_state"] == "FUT").sum())),
                     "Scheduled, not yet played"),
            kpi_card("⚡", "Goals / game", _fmt_float(d["total_goals"].mean(), 2),
                     "Average across completed games in view"),
            kpi_card("🔥", "Highest scoring", _fmt_int(d["total_goals"].max()),
                     "Most combined goals in one game", accent=True),
        ])

        spacer(22)
        section_header("🗓", "Results & Schedule", f"{len(d)} games")
        d["matchup"] = d["away"].astype(str) + "  @  " + d["home"].astype(str)
        d["score"] = [
            f"{_fmt_int(a)} – {_fmt_int(h)}" if pd.notna(a) and pd.notna(h) else "—"
            for a, h in zip(as_, hs)
        ]
        stat_table(
            d,
            [("game_date", "Date", "dim"), ("matchup", "Matchup", "strong"),
             ("score", "Away – Home", "text"), ("state_label", "State", "chip"),
             ("total_goals", "Total G", "int"), ("venue_name", "Venue", "dim")],
            rank=False, max_height=520,
        )

        spacer(22)
        gcol1, gcol2 = st.columns([1.3, 1])

        with gcol1:
            section_header("📈", "Games by Month", "Schedule density over the season")
            month_df, m_err = run_query("""
                SELECT substr(game_date, 1, 7) AS month,
                       SUM(CASE WHEN game_state = 'OFF' THEN 1 ELSE 0 END) AS completed,
                       SUM(CASE WHEN game_state = 'FUT' THEN 1 ELSE 0 END) AS upcoming
                FROM games
                WHERE game_date IS NOT NULL
                GROUP BY month
                ORDER BY month
            """)
            if m_err or month_df is None or len(month_df) == 0:
                empty_state("No dated games available", "Run notebook 03 to load the schedule.", "📉")
            elif HAS_PLOTLY:
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=month_df["month"], y=month_df["completed"],
                    name="Completed", mode="lines+markers", fill="tozeroy",
                    line=dict(color=CYAN, width=2.4),
                    fillcolor="rgba(50,214,255,0.16)",
                    marker=dict(size=6, color=CYAN),
                    hovertemplate="<b>%{x}</b><br>Completed: %{y}<extra></extra>",
                ))
                fig.add_trace(go.Scatter(
                    x=month_df["month"], y=month_df["upcoming"],
                    name="Upcoming", mode="lines+markers", fill="tozeroy",
                    line=dict(color=VIOLET, width=2.4, dash="dot"),
                    fillcolor="rgba(155,140,255,0.12)",
                    marker=dict(size=6, color=VIOLET),
                    hovertemplate="<b>%{x}</b><br>Upcoming: %{y}<extra></extra>",
                ))
                style_fig(fig, height=340, legend=True)
                fig.update_yaxes(title_text="Games")
                fig.update_xaxes(title_text="Month")
                show_fig(fig)
            else:
                auto_table(month_df)

        with gcol2:
            section_header("🔥", "Score Heatmap", "Frequency of final scorelines")
            heat_df, h_err = run_query("""
                SELECT away_score, home_score, COUNT(*) AS games
                FROM games
                WHERE game_state = 'OFF'
                  AND home_score IS NOT NULL AND away_score IS NOT NULL
                GROUP BY away_score, home_score
            """)
            if h_err or heat_df is None or len(heat_df) == 0:
                empty_state("No completed games to map", "Final scores are required for this chart.", "📉")
            elif HAS_PLOTLY:
                pivot = heat_df.pivot_table(
                    index="away_score", columns="home_score",
                    values="games", aggfunc="sum",
                ).fillna(0)
                fig = go.Figure(go.Heatmap(
                    z=pivot.values,
                    x=[str(int(c)) for c in pivot.columns],
                    y=[str(int(i)) for i in pivot.index],
                    colorscale=[[0, "rgba(92,200,255,0.05)"], [0.5, "#2E7FB5"], [1, CYAN]],
                    hovertemplate="Home %{x} – Away %{y}<br>%{z} games<extra></extra>",
                    colorbar=dict(
                        title=dict(text="Games", font=dict(color=COOL_GRAY, size=10)),
                        tickfont=dict(color=COOL_GRAY, size=10),
                        outlinewidth=0, thickness=10,
                    ),
                ))
                style_fig(fig, height=340)
                fig.update_xaxes(title_text="Home goals")
                fig.update_yaxes(title_text="Away goals")
                show_fig(fig)
            else:
                auto_table(heat_df)

    render_footer()


# =========================================================
# 8e. INSIGHTS — observations derived from the existing dataset only
# =========================================================
elif page == "Insights":
    page_header("🔍", "Insights", "Automated observations derived from the current database")

    league_avg_pts = scalar("SELECT ROUND(AVG(points), 1) FROM standings")
    league_avg_gf = scalar("SELECT ROUND(AVG(goals_for), 1) FROM standings")
    total_goals = scalar("SELECT SUM(goals_for) FROM standings")
    completed = scalar("SELECT COUNT(*) FROM games WHERE game_state = 'OFF'", default=0)
    avg_gpg = scalar(
        "SELECT ROUND(AVG(home_score + away_score), 2) FROM games "
        "WHERE game_state = 'OFF' AND home_score IS NOT NULL AND away_score IS NOT NULL"
    )
    home_win_rate = scalar("""
        SELECT ROUND(100.0 * SUM(CASE WHEN home_score > away_score THEN 1 ELSE 0 END)
                     / NULLIF(COUNT(*), 0), 1)
        FROM games
        WHERE game_state = 'OFF' AND home_score IS NOT NULL AND away_score IS NOT NULL
    """)

    render_kpi_row([
        kpi_card("📊", "Avg team points", _fmt_float(league_avg_pts, 1), "League-wide average"),
        kpi_card("🔥", "Avg goals for", _fmt_float(league_avg_gf, 1), "Per team, season to date"),
        kpi_card("⚡", "Goals per game", _fmt_float(avg_gpg, 2),
                 f"Across <b>{_fmt_int(completed)}</b> completed games"),
        kpi_card("🏟", "Home win rate", f"{_fmt_float(home_win_rate, 1)}%",
                 "Share of completed games won at home"),
        kpi_card("🥅", "Total league goals", _fmt_int(total_goals), "Sum of goals-for", accent=True),
    ])

    spacer(24)
    section_header("💡", "Key Observations", "Every figure below is computed live from the database")

    ic1, ic2 = st.columns(2)
    cards_left, cards_right = [], []

    top_team, _ = run_query("""
        SELECT t.team_name, t.team_abbrev, s.points, s.wins, s.losses, s.ot_losses
        FROM teams t JOIN standings s ON t.team_id = s.team_id
        ORDER BY s.points DESC LIMIT 1
    """)
    if top_team is not None and len(top_team) > 0:
        r = top_team.iloc[0]
        cards_left.append(insight_card(
            "🏆 League leader",
            f"<b>{_esc(r.team_name)}</b> top the table with <b>{_fmt_int(r.points)} points</b> "
            f"on a {_fmt_int(r.wins)}-{_fmt_int(r.losses)}-{_fmt_int(r.ot_losses)} record.",
        ))

    best_off, _ = run_query("""
        SELECT t.team_name, s.goals_for FROM teams t
        JOIN standings s ON t.team_id = s.team_id
        ORDER BY s.goals_for DESC LIMIT 1
    """)
    if best_off is not None and len(best_off) > 0:
        r = best_off.iloc[0]
        cards_left.append(insight_card(
            "🔥 Most productive offence",
            f"<b>{_esc(r.team_name)}</b> have scored <b>{_fmt_int(r.goals_for)} goals</b>, "
            f"the most in the league.",
        ))

    best_def, _ = run_query("""
        SELECT t.team_name, s.goals_against FROM teams t
        JOIN standings s ON t.team_id = s.team_id
        ORDER BY s.goals_against ASC LIMIT 1
    """)
    if best_def is not None and len(best_def) > 0:
        r = best_def.iloc[0]
        cards_left.append(insight_card(
            "🧱 Stingiest defence",
            f"<b>{_esc(r.team_name)}</b> have conceded just "
            f"<b>{_fmt_int(r.goals_against)} goals</b> — fewest league-wide.",
        ))

    top_div, _ = run_query("""
        SELECT t.division_name, ROUND(AVG(s.points), 1) AS avg_points
        FROM teams t JOIN standings s ON t.team_id = s.team_id
        GROUP BY t.division_name ORDER BY avg_points DESC LIMIT 1
    """)
    if top_div is not None and len(top_div) > 0:
        r = top_div.iloc[0]
        cards_right.append(insight_card(
            "🧭 Strongest division",
            f"The <b>{_esc(r.division_name)}</b> division averages "
            f"<b>{_fmt_float(r.avg_points, 1)} points</b> per team.",
        ))

    eff, _ = run_query("""
        SELECT p.first_name || ' ' || p.last_name AS player, t.team_abbrev,
               ss.points, ss.games_played,
               ROUND(1.0 * ss.points / ss.games_played, 2) AS ppg
        FROM skater_season_stats ss
        JOIN players p ON ss.player_id = p.player_id
        JOIN teams t ON ss.team_id = t.team_id
        WHERE ss.games_played >= 20
        ORDER BY ppg DESC LIMIT 1
    """)
    if eff is not None and len(eff) > 0:
        r = eff.iloc[0]
        cards_right.append(insight_card(
            "⚡ Most efficient scorer",
            f"<b>{_esc(r.player)}</b> ({_esc(r.team_abbrev)}) is producing "
            f"<b>{_fmt_float(r.ppg, 2)} points per game</b> over "
            f"{_fmt_int(r.games_played)} games.",
        ))

    struggling, _ = run_query("""
        SELECT t.team_name, s.points, (s.goals_for - s.goals_against) AS diff
        FROM teams t JOIN standings s ON t.team_id = s.team_id
        ORDER BY s.points ASC LIMIT 1
    """)
    if struggling is not None and len(struggling) > 0:
        r = struggling.iloc[0]
        cards_right.append(insight_card(
            "⚠️ Bottom of the table",
            f"<b>{_esc(r.team_name)}</b> sit last on <b>{_fmt_int(r.points)} points</b> "
            f"with a {_fmt_signed(r['diff'])} goal differential.",
            warn=True,
        ))

    if not cards_left and not cards_right:
        empty_state("No insights available yet",
                    "Populate the database with notebooks 01–04 to generate observations.", "💡")
    with ic1:
        for c in cards_left:
            write(c)
    with ic2:
        for c in cards_right:
            write(c)

    spacer(24)
    icol1, icol2 = st.columns([1, 1])

    with icol1:
        section_header("🧭", "Division Strength", "Average points per team by division")
        dstr, e = run_query("""
            SELECT t.division_name, ROUND(AVG(s.points), 1) AS avg_points,
                   COUNT(*) AS num_teams
            FROM teams t JOIN standings s ON t.team_id = s.team_id
            GROUP BY t.division_name
            ORDER BY avg_points DESC
        """)
        if e or dstr is None or len(dstr) == 0:
            empty_state("No division data", "Run notebooks 01 and 03.", "📉")
        elif HAS_PLOTLY:
            fig = go.Figure(go.Bar(
                x=dstr["avg_points"], y=dstr["division_name"], orientation="h",
                marker=dict(color=colors_for(dstr["division_name"]), line=dict(width=0)),
                text=[_fmt_float(v, 1) for v in dstr["avg_points"]],
                textposition="outside", textfont=dict(color=WHITE, size=11),
                customdata=dstr[["num_teams"]].values,
                hovertemplate="<b>%{y}</b><br>Avg points: %{x}<br>Teams: %{customdata[0]}<extra></extra>",
            ))
            style_fig(fig, height=300)
            fig.update_xaxes(title_text="Average points")
            fig.update_yaxes(title_text=None)
            show_fig(fig)
        else:
            auto_table(dstr)

    with icol2:
        section_header("🏟", "Home-Ice Advantage", "Home wins minus away wins")
        hia, e = run_query("""
            SELECT t.team_abbrev, (s.home_wins - s.away_wins) AS edge
            FROM teams t JOIN standings s ON t.team_id = s.team_id
            ORDER BY edge DESC
            LIMIT 14
        """)
        if e or hia is None or len(hia) == 0:
            empty_state("No home/away data", "Standings are missing home_wins / away_wins.", "📉")
        elif HAS_PLOTLY:
            fig = go.Figure(go.Bar(
                x=hia["team_abbrev"], y=hia["edge"],
                marker=dict(
                    color=[ACCENT_RED if v < 0 else CYAN for v in
                           pd.to_numeric(hia["edge"], errors="coerce").fillna(0)],
                    line=dict(width=0),
                ),
                hovertemplate="<b>%{x}</b><br>Home-ice edge: %{y}<extra></extra>",
            ))
            style_fig(fig, height=300)
            fig.update_yaxes(title_text="Home wins − away wins")
            show_fig(fig)
        else:
            auto_table(hia)

    spacer(22)
    section_header("📋", "Teams Above League Average", "Points above the league mean")
    above, e = run_query("""
        SELECT t.team_name, t.team_abbrev, t.division_name, s.points,
               ROUND(s.points - (SELECT AVG(points) FROM standings), 1) AS above_avg,
               s.wins, s.losses, s.ot_losses
        FROM teams t JOIN standings s ON t.team_id = s.team_id
        WHERE s.points > (SELECT AVG(points) FROM standings)
        ORDER BY s.points DESC
    """)
    if e:
        error_state("Couldn't compute the above-average table")
    elif above is None or len(above) == 0:
        empty_state("Nothing to show", "Standings data is required for this table.")
    else:
        a = above.copy()
        a["record"] = (a["wins"].map(_fmt_int) + "-" + a["losses"].map(_fmt_int)
                       + "-" + a["ot_losses"].map(_fmt_int))
        stat_table(
            a,
            [("team_name", "Team", "strong"), ("team_abbrev", "Abbr", "chip"),
             ("division_name", "Division", "dim"), ("record", "Record", "text"),
             ("points", "PTS", "int"), ("above_avg", "vs. AVG", "signed")],
            bar_col="points", max_height=480,
        )

    render_footer()


# =========================================================
# 8f. SQL LAB  (original "SQL Query" page)
# =========================================================
elif page == "SQL Lab":
    page_header("💻", "SQL Lab",
                "Run any of the 11 saved analysis queries, or write your own SELECT")

    mode = st.radio("Mode", ["Pre-built queries", "Custom query"], horizontal=True)

    def _render_result(df: pd.DataFrame, label: str = "result") -> None:
        """Shared result renderer: row count, styled table, optional
        sortable grid, CSV export."""
        section_header("📄", "Result Set", f"{len(df)} row(s) · {len(df.columns)} column(s)")
        auto_table(df)
        # st.dataframe renders to a canvas that CSS can't reach, so it stays
        # on Streamlit's own (light) theme. It's kept behind an expander for
        # people who want column sorting without breaking the dark shell.
        with st.expander("🔎 Open as sortable grid"):
            show_df(df)
        try:
            st.download_button(
                "⬇ Download CSV",
                df.to_csv(index=False).encode("utf-8"),
                file_name=f"nhl_{label}.csv",
                mime="text/csv",
            )
        except Exception:
            pass

    if mode == "Pre-built queries":
        choice = st.selectbox("Choose a query", list(QUERY_LIBRARY.keys()))
        query_text = QUERY_LIBRARY[choice]

        section_header("📝", "Query", _esc(choice))
        st.code(query_text.strip(), language="sql")

        if st.button("▶ Run query"):
            df, err = run_query(query_text)
            if err:
                error_state("Query failed", "The saved query couldn't be executed against this database.")
            elif df is None or len(df) == 0:
                empty_state("Query ran successfully",
                            "It returned no rows — the filters may exclude everything in this dataset.",
                            "📄")
            else:
                _render_result(df, "query")

    else:
        st.caption("Read-only sandbox — only SELECT statements are permitted.")
        custom_query = st.text_area(
            "Write your SQL query",
            height=170,
            placeholder="SELECT team_name, team_abbrev FROM teams LIMIT 10;",
        )
        with st.expander("📚 Available tables"):
            write(
                f"""
                <div style="font-size:12.5px; color:{COOL_GRAY}; line-height:1.9;">
                    <span class="chip ice">teams</span>
                    <span class="chip ice">standings</span>
                    <span class="chip ice">players</span>
                    <span class="chip ice">games</span>
                    <span class="chip ice">skater_season_stats</span>
                    <span class="chip ice">goalie_season_stats</span>
                </div>
                """
            )
        if st.button("▶ Run query"):
            stripped = custom_query.strip().rstrip(";").strip()
            if not stripped:
                empty_state("Nothing to run", "Enter a SELECT statement above first.", "✍️")
            elif not stripped.lower().startswith("select"):
                error_state("Only SELECT statements are allowed on this page",
                            "This page is read-only by design, so the database can't be modified.")
            else:
                df, err = run_query(stripped)
                if err:
                    error_state("Query failed",
                                "Check table and column names — the available tables are listed above.")
                elif df is None or len(df) == 0:
                    empty_state("Query ran successfully", "It returned no rows.", "📄")
                else:
                    _render_result(df, "custom")

    render_footer()