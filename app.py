"""Modular Streamlit app for hiking planning."""

import streamlit as st

from core.auth import authenticate_user, is_admin, register_user
from core.activity_log import log_activity
from core.db import ensure_indexes, get_collection, ping_database
from modules.registry import load_modules

try:
    from core.auth import is_registration_enabled
except ImportError:
    # Backward compatibility for environments with older core/auth.py.
    def is_registration_enabled() -> bool:
        return True


def get_external_ip() -> str:
    """Return host external IP for database allowlist troubleshooting."""
    # Try multiple providers + stdlib fallback to reduce false "Unknown" results.
    services = [
        ("https://api64.ipify.org?format=json", "json", "ip"),
        ("https://ipinfo.io/json", "json", "ip"),
        ("https://checkip.amazonaws.com", "text", ""),
        ("https://ifconfig.me/ip", "text", ""),
    ]
    try:
        import requests

        for url, mode, field in services:
            try:
                response = requests.get(url, timeout=5)
                if response.status_code != 200:
                    continue
                if mode == "json":
                    data = response.json()
                    ip_value = str(data.get(field, "")).strip()
                else:
                    ip_value = str(response.text).strip()
                if ip_value:
                    return ip_value
            except Exception:
                continue
    except Exception:
        # requests unavailable or failed; continue with stdlib fallback.
        pass

    try:
        import json
        from urllib.request import urlopen

        with urlopen("https://api64.ipify.org?format=json", timeout=5) as response:
            payload = response.read().decode("utf-8").strip()
            data = json.loads(payload)
            ip_value = str(data.get("ip", "")).strip()
            if ip_value:
                return ip_value
    except Exception:
        pass

    return "Unknown"


def apply_theme() -> None:
    """Apply a hiking-inspired earth-tone visual theme."""
    st.markdown(
        """
        <style>
        :root {
            --hg-sandstrand: #E8DCC3;
            --hg-ljus-beige: #D9C6A3;
            --hg-solblekt-halm: #E2C77A;
            --hg-olivgron: #7A8A5A;
            --hg-mossig-skog: #5E6E4A;
            --hg-djup-skog: #3E4D34;
            --hg-jordig-brun: #8B6E4F;
            --hg-trabark: #6B3F2A;
            --hg-mork-jord: #3A2A1F;
            --hg-gyllene-gul: #D4A72C;
            --hg-senapsgul: #C9B24D;
            --hg-rostad-lera: #C8693D;
            --hg-tegelrod: #A44432;
            --hg-naturrod: #7F2E2E;
            --hg-dov-ros: #B47A6F;
            --hg-varm-beige: #CBB9A0;
            --hg-sten: #8E8D83;
            --hg-skiffergra: #5A5A5A;

            --hg-bg: var(--hg-sandstrand);
            --hg-paper: var(--hg-mork-jord);
            --hg-forest: var(--hg-djup-skog);
            --hg-moss: var(--hg-mossig-skog);
            --hg-sand: var(--hg-solblekt-halm);
            --hg-clay: var(--hg-rostad-lera);
            --hg-text: var(--hg-mork-jord);

            --hg-overlay-forest: rgba(62, 77, 52, 0.10);
            --hg-overlay-moss: rgba(94, 110, 74, 0.18);
            --hg-overlay-bark: var(--hg-mork-jord);
            --hg-overlay-earth: rgba(58, 42, 31, 0.16);
            --hg-overlay-paper: var(--hg-mork-jord);
        }

        .stApp {
            background: linear-gradient(180deg, var(--hg-sandstrand) 0%, var(--hg-ljus-beige) 100%);
            color: var(--hg-text);
        }



        .stApp p,
        .stApp li,
        .stApp label,
        .stApp span,
        .stApp .stMarkdown,
        .stApp .stText,
        .stApp .stCaption,
        .stApp h1,
        .stApp h2,
        .stApp h3,
        .stApp h4,
        .stApp h5,
        .stApp h6 {
            color: var(--hg-djup-skog);
        }

        .stApp [data-baseweb="select"] *,
        .stApp [data-baseweb="input"] *,
        .stApp [data-baseweb="textarea"] *,
        .stApp [data-baseweb="radio"] *,
        .stApp [data-baseweb="checkbox"] * {
            color: var(--hg-djup-skog);
        }

        .stApp [data-baseweb="select"] > div,
        .stApp [data-baseweb="input"] > div,
        .stApp [data-baseweb="textarea"] > div {
            background-color: var(--hg-sandstrand);
            border: 1px solid var(--hg-mork-jord);
            border-radius: 10px;
            box-shadow: 0 1px 2px var(--hg-overlay-forest);
        }

        .stApp [data-baseweb="input"] > div:focus-within,
        .stApp [data-baseweb="textarea"] > div:focus-within,
        .stApp [data-baseweb="select"] > div:focus-within {
            border-color: var(--hg-mossig-skog);
            box-shadow: 0 0 0 2px var(--hg-overlay-moss);
        }

        .stApp [data-baseweb="input"] input::placeholder,
        .stApp [data-baseweb="textarea"] textarea::placeholder {
            color: var(--hg-jordig-brun);
            opacity: 1;
        }

        [data-testid="stHeader"] {
            background: var(--hg-ljus-beige);
        }

        [data-testid="stHeader"],
        [data-testid="stToolbar"],
        [data-testid="stDecoration"] {
            color: var(--hg-text);
        }

        [data-testid="stHeader"] button,
        [data-testid="stToolbar"] button {
            color: var(--hg-text) ;
            background: var(--hg-sandstrand) ;
            border: 1px solid var(--hg-mork-jord);
        }

        /*[data-testid="stHeader"] button svg,
        [data-testid="stToolbar"] button svg,
        [data-testid="stHeader"] button svg path,
        [data-testid="stToolbar"] button svg path {
            fill: var(--hg-text) ;
            stroke: var(--hg-text) ;
        }

        [data-testid="stHeader"] button *,
        [data-testid="stToolbar"] button * {
            color: var(--hg-text) ;
            fill: var(--hg-text) ;
            stroke: var(--hg-text) ;
        }

        [data-testid="stToolbar"] button {
            background: var(--hg-sandstrand) ;
            border: 1px solid var(--hg-mork-jord);
            color: var(--hg-text) ;
        }*/

        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, var(--hg-djup-skog) 0%, var(--hg-mossig-skog) 100%);
        }

        [data-testid="stSidebar"] * {
            color: var(--hg-sandstrand) ;
        }

        [data-testid="stSidebar"] .stButton > button,
        [data-testid="stSidebar"] .stFormSubmitButton > button {
            color: var(--hg-sandstrand);
        }

        [data-testid="stSidebar"] [data-baseweb="select"] *,
        [data-testid="stSidebar"] [data-baseweb="input"] *,
        [data-testid="stSidebar"] [data-baseweb="textarea"] * {
            color: var(--hg-sandstrand) ;
        }

        [data-testid="stSidebar"] [data-baseweb="input"] input,
        [data-testid="stSidebar"] [data-baseweb="input"] textarea,
        [data-testid="stSidebar"] [data-baseweb="textarea"] textarea {
            color: var(--hg-text) ;
            -webkit-text-fill-color: var(--hg-text) ;
            caret-color: var(--hg-djup-skog) ;
        }

        [data-testid="stSidebar"] [data-baseweb="input"] input::placeholder,
        [data-testid="stSidebar"] [data-baseweb="textarea"] textarea::placeholder {
            color: var(--hg-sten) ;
            opacity: 1;
        }

        .hg-sidebar-heading {
            text-align: center;
            font-size: 2.0rem;
            font-weight: 800;
            line-height: 1.25;
            color: var(--hg-mork-jord);
            margin: 0.25rem 0 0.7rem 0;
        }

        .hg-sidebar-note {
            color: var(--hg-sandstrand);
            font-weight: 700;
            margin: 0.15rem 0 0.35rem 0;
        }

        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 14px;
            border: 1px solid var(--hg-mork-jord) !important;
            border-color: var(--hg-mork-jord) !important;
            background: var(--hg-overlay-paper);
            box-shadow: 0 6px 18px var(--hg-overlay-forest);
            padding: 0.35rem 0.5rem;
        }

        /* Outermost module block inside main container */
        .stMainBlockContainer > div[data-testid="stVerticalBlock"] > div[data-testid="stVerticalBlock"] {
            border: 2px solid var(--hg-mork-jord) !important;
            border-color: var(--hg-mork-jord) !important;
        }

        .stMainBlockContainer .stForm {
            border: 2px solid var(--hg-mork-jord) !important;
            border-color: var(--hg-mork-jord) !important;
        }

        .hg-auth-shell {
            max-width: 760px;
            margin: 0.5rem auto 0.9rem auto;
            padding: 0.4rem;
            border-radius: 16px;
            background: linear-gradient(130deg, var(--hg-djup-skog) 0%, var(--hg-jordig-brun) 100%);
            border: 1px solid var(--hg-mork-jord);
            box-shadow: 0 8px 20px var(--hg-overlay-forest);
        }

        .hg-auth-shell h3 {
            margin: 0.2rem 0 0.15rem 0;
        }

        .hg-auth-shell p {
            margin: 0;
        }

        .hg-auth-shell h1,
        .hg-auth-shell h2,
        .hg-auth-shell h3,
        .hg-auth-shell h4,
        .hg-auth-shell h5,
        .hg-auth-shell h6,
        .hg-auth-shell p,
        .hg-auth-shell span,
        .hg-auth-shell a,
        .hg-auth-shell button,
        .hg-auth-shell textarea,
        .hg-auth-shell select,
        .hg-auth-shell option,
        .hg-auth-shell label {
            color: var(--hg-sandstrand);
        }

        .hg-auth-shell input {
            color: var(--hg-djup-skog);
        }

        .hg-hero {
            background: linear-gradient(135deg, var(--hg-djup-skog) 0%, var(--hg-rostad-lera) 80%, var(--hg-gyllene-gul) 100%);
            color: var(--hg-sandstrand);
            border-radius: 16px;
            border: 5px solid var(--hg-mork-jord);
            border-image: linear-gradient(135deg, var(--hg-jordig-brun) 0%, var(--hg-mossig-skog) 50%, var(--hg-djup-skog) 100%) 1;
            padding: 1.1rem 1.2rem;
            margin-bottom: 1rem;
            box-shadow: 0 8px 20px rgba(62, 77, 52, 0.22);
        }


        .hg-hero h1,
        .hg-hero p,
        .hg-hero h3,
        .hg-hero h4,
        .hg-hero h5,
        .hg-hero h6,
        .hg-hero span,
        .hg-hero a,
        .hg-hero button,
        .hg-hero input,
        .hg-hero textarea,
        .hg-hero select,
        .hg-hero option,
        .hg-hero label {
            color: var(--hg-sandstrand);
        }

        .hg-hero p {
            margin: 0.25rem 0 0 0;
            opacity: 0.92;
        }

        .stButton > button,
        .stFormSubmitButton > button {
            border-radius: 10px;
            border: 1px solid var(--hg-olivgron);
            background: var(--hg-mossig-skog);
            color: var(--hg-solblekt-halm);
            font-weight: 600;
            box-shadow: 0 2px 8px var(--hg-overlay-moss);
        }

        .stButton > button:hover,
        .stFormSubmitButton > button:hover {
            border-color: var(--hg-olivgron);
            background: var(--hg-djup-skog);
            color: var(--hg-solblekt-halm);
        }

        .stTabs [data-baseweb="tab-list"] {
            gap: 0.35rem;
        }

        .stTabs [data-baseweb="tab"] {
            background: var(--hg-ljus-beige);
            border: 1px solid var(--hg-mork-jord);
            border-radius: 10px;
            padding: 0.35rem 0.85rem;
        }

        .stTabs [aria-selected="true"] {
            background: var(--hg-solblekt-halm) ;
            border-color: var(--hg-jordig-brun) ;
        }

        /* Separate expander styling (independent from card wrappers). */
        .stExpander {
            border: 1px solid var(--hg-mork-jord);
            border-radius: 12px ;
            background: var(--hg-overlay-paper) ;
            box-shadow: 0 4px 12px var(--hg-overlay-forest) ;
            overflow: hidden;
        }

        .stExpander details {
            border: 1px solid var(--hg-mork-jord);
            border-radius: 12px ;
            background: transparent ;
        }

        .stExpander summary {
            background: linear-gradient(90deg, var(--hg-olivgron) 0%, var(--hg-rostad-lera) 30%, var(--hg-senapsgul) 70%) ;
            border-bottom: 2px solid var(--hg-overlay-bark) ;
            padding: 0.55rem 0.8rem ;
            font-weight: 600 ;
        }

        .stExpander details[open] > summary {
            background: linear-gradient(90deg, var(--hg-olivgron) 0%, var(--hg-rostad-lera) 70%, var(--hg-senapsgul) 100%) ;
        }

        .stExpander summary:hover {
            background: linear-gradient(90deg, var(--hg-olivgron) 0%, var(--hg-rostad-lera) 50%, var(--hg-senapsgul) 100%) ;
        }

        .stExpander [data-testid="stExpanderDetails"] {
            background: var(--hg-ljus-beige) ;
            padding: 0.55rem 0.75rem 0.7rem 0.75rem ;
        }

        /* Reusable gear/checklist cards */
        .gear-card {
            border: 1px solid var(--hg-mork-jord);
            border-radius: 10px !important;
            padding: 0.6rem 0.7rem !important;
            margin-bottom: 0.65rem !important;
            box-shadow: 0 2px 8px var(--hg-overlay-forest) !important;
            background: var(--hg-overlay-paper) !important;
        }

        .gear-card--missing {
            background: var(--hg-sandstrand) !important;
            border-color: var(--hg-naturrod) !important;
        }

        .gear-card--started {
            background: var(--hg-sandstrand) !important;
            border-color: var(--hg-gyllene-gul) !important;
        }

        .gear-card--complete {
            background: var(--hg-sandstrand) !important;
            border-color: var(--hg-olivgron) !important;
        }

        div[class*="st-key-gear_card_"] {
            border: 2px solid var(--hg-overlay-bark) !important;
            border-radius: 10px !important;
            padding: 0.6rem 0.7rem !important;
            margin-bottom: 0.65rem !important;
            box-shadow: 0 2px 8px var(--hg-overlay-forest) !important;
        }

        div[class*="st-key-gear_card_missing_"] {
            background: var(--hg-sandstrand) !important;
            border-color: var(--hg-naturrod) !important;
        }

        div[class*="st-key-gear_card_started_"] {
            background: var(--hg-sandstrand) !important;
            border-color: var(--hg-gyllene-gul) !important;
        }

        div[class*="st-key-gear_card_complete_"] {
            background: var(--hg-sandstrand) !important;
            border-color: var(--hg-olivgron) !important;
        }

        /* Separate divider styling for better contrast. */
        .stApp hr,
        .stApp [data-testid="stDivider"],
        .stApp [role="separator"] {
            border: var(--hg-mork-jord);
            border-top: 2px solid rgba(58, 42, 31, 0.6) ;
            opacity: 1 ;
            margin-top: 0.75rem ;
            margin-bottom: 0.75rem ;
        }

        .stButton > button[kind="primary"],
        .stFormSubmitButton > button[kind="primary"] {
            background: var(--hg-tegelrod) ;
            border-color: var(--hg-naturrod) ;
            color: var(--hg-sandstrand) ;
        }

        .stButton > button[kind="primary"]:hover,
        .stFormSubmitButton > button[kind="primary"]:hover {
            background: var(--hg-naturrod) ;
            border-color: var(--hg-mork-jord) ;
            color: var(--hg-sandstrand) ;
        }

        /* Force sidebar button text color */
        [data-testid="stSidebar"] .stButton > button,
        [data-testid="stSidebar"] .stFormSubmitButton > button,
        [data-testid="stSidebar"] .stButton > button *,
        [data-testid="stSidebar"] .stFormSubmitButton > button * {
            color: var(--hg-sandstrand) !important;
            fill: var(--hg-sandstrand) !important;
            stroke: var(--hg-sandstrand) !important;
            -webkit-text-fill-color: var(--hg-sandstrand) !important;
        }

        /* Force main-area green button text color (exclude sidebar) */
        [data-testid="stMain"] .stButton > button,
        [data-testid="stMain"] .stFormSubmitButton > button,
        [data-testid="stMain"] .stButton > button *,
        [data-testid="stMain"] .stFormSubmitButton > button * {
            color: var(--hg-solblekt-halm) !important;
            fill: var(--hg-solblekt-halm) !important;
            stroke: var(--hg-solblekt-halm) !important;
            -webkit-text-fill-color: var(--hg-solblekt-halm) !important;
        }

        @media (max-width: 900px) {
            .block-container {
                padding-top: 0.75rem;
                padding-left: 0.75rem;
                padding-right: 0.75rem;
            }

            .hg-hero {
                padding: 0.85rem 0.9rem;
                border-radius: 12px;
            }

            .hg-hero h1 {
                font-size: 1.35rem ;
                line-height: 1.25 ;
            }

            .hg-hero p {
                font-size: 0.92rem ;
            }

            div[data-testid="stVerticalBlockBorderWrapper"] {
                border-radius: 12px;
                padding: 0.3rem 0.4rem;
            }

            [data-testid="stSidebar"] .stButton > button,
            [data-testid="stSidebar"] .stFormSubmitButton > button,
            [data-testid="stSidebar"] [data-baseweb="input"],
            [data-testid="stSidebar"] [data-baseweb="select"],
            [data-testid="stSidebar"] [data-baseweb="textarea"] {
                width: 100% ;
            }

            .hg-auth-shell {
                margin-top: 0.2rem;
                padding: 0.3rem;
                border-radius: 12px;
            }
        }

        @media (max-width: 640px) {
            .block-container {
                padding-top: 0.55rem;
                padding-left: 0.55rem;
                padding-right: 0.55rem;
            }

            [data-testid="stHeader"] {
                min-height: 2.6rem;
            }

            [data-testid="stToolbar"] button {
                min-height: 2.1rem;
                min-width: 2.1rem;
            }

            .stButton > button,
            .stFormSubmitButton > button {
                min-height: 2.6rem;
            }

            .stTabs [data-baseweb="tab"] {
                flex: 1 1 auto;
                justify-content: center;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def init_session_state() -> None:
    """Initialize state keys used across reruns."""
    st.session_state.setdefault("current_user", None)
    st.session_state.setdefault("db_ready", False)
    st.session_state.setdefault("last_module_key", None)
    st.session_state.setdefault("last_logged_page_key", None)


def get_disabled_module_keys() -> set[str]:
    """Return module keys disabled by admin settings."""
    settings = get_collection("app_settings")
    doc = settings.find_one({"_id": "modules"}, {"disabled_keys": 1})
    if not doc:
        return set()
    disabled = {str(key) for key in doc.get("disabled_keys", [])}
    disabled.discard("admin")
    return disabled


def get_admin_required_module_keys() -> set[str]:
    """Return module keys explicitly configured to require admin rights."""
    settings = get_collection("app_settings")
    doc = settings.find_one({"_id": "modules"}, {"admin_required_keys": 1})
    if not doc:
        return set()
    admin_required = {str(key) for key in doc.get("admin_required_keys", [])}
    admin_required.add("admin")
    return admin_required


def get_module_order_keys() -> list[str]:
    """Return module order configured by admin settings."""
    settings = get_collection("app_settings")
    doc = settings.find_one({"_id": "modules"}, {"module_order_keys": 1})
    if not doc:
        return []
    return [str(key) for key in doc.get("module_order_keys", []) if str(key).strip()]


def apply_module_order(modules: list, ordered_keys: list[str]) -> list:
    """Return modules sorted by configured order, with unknown keys last."""
    if not ordered_keys:
        return modules
    module_by_key = {module.key: module for module in modules}
    ordered_modules = [module_by_key[key] for key in ordered_keys if key in module_by_key]
    remaining = [module for module in modules if module.key not in set(ordered_keys)]
    return ordered_modules + remaining


def render_user_sidebar() -> None:
    """Render account controls in sidebar once authenticated."""
    st.sidebar.markdown('<div class="hg-sidebar-heading">Konto</div>', unsafe_allow_html=True)
    st.sidebar.success(f"Inloggad: {st.session_state.current_user}")
    if is_admin(st.session_state.current_user):
        st.sidebar.markdown('<div class="hg-sidebar-note">Roll: Admin</div>', unsafe_allow_html=True)
    if st.sidebar.button("Logga ut"):
        log_activity(st.session_state.current_user, "logout", module="auth")
        st.session_state.current_user = None
        st.session_state.last_logged_page_key = None
        st.rerun()


def render_auth_main(registration_enabled: bool) -> None:
    """Render a mobile-friendly authentication card in the main content area."""
    st.markdown(
        """
        <div class="hg-auth-shell">
            <h3>Välkommen</h3>
            <p>Logga in för att fortsätta, eller skapa ett nytt konto.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if registration_enabled:
        login_tab, register_tab = st.tabs(["Logga in", "Registrera"])
    else:
        login_tab = st.container()
        register_tab = None

    with login_tab:
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("Användarnamn", key="main_username_login")
            password = st.text_input("Lösenord", type="password", key="main_password_login")
            submitted = st.form_submit_button("Logga in")
            if submitted:
                result = authenticate_user(username, password)
                if result.ok:
                    normalized_username = username.strip().lower()
                    st.session_state.current_user = normalized_username
                    log_activity(normalized_username, "login_success", module="auth")
                    st.success("Inloggad.")
                    st.rerun()
                log_activity(username.strip().lower(), "login_failed", module="auth")
                st.error(result.message)

    if register_tab is not None:
        with register_tab:
            with st.form("register_form", clear_on_submit=False):
                username = st.text_input("Användarnamn", key="main_username_register")
                password = st.text_input("Lösenord", type="password", key="main_password_register")
                confirm = st.text_input("Bekräfta lösenord", type="password", key="main_confirm_register")
                submitted = st.form_submit_button("Skapa konto")
                if submitted:
                    if password != confirm:
                        st.error("Lösenorden matchar inte.")
                    else:
                        result = register_user(username, password)
                        if result.ok:
                            log_activity(username.strip().lower(), "register_success", module="auth")
                            st.success(result.message)
                        else:
                            log_activity(
                                username.strip().lower(),
                                "register_failed",
                                module="auth",
                                details={"reason": result.message},
                            )
                            st.error(result.message)
    else:
        st.info("Registrering är för närvarande avstängd av administratör.")


def render_sidebar_pages(modules: list) -> str:
    """Render sidebar page navigation and return selected module key."""
    st.sidebar.markdown('<div class="hg-sidebar-heading">Sidor</div>', unsafe_allow_html=True)
    options = [(module.key, module.name) for module in modules]
    selected_key = st.session_state.get("page_nav_key")
    valid_keys = {module_key for module_key, _ in options}
    if selected_key not in valid_keys:
        selected_key = options[0][0]

    st.sidebar.markdown('<div class="hg-sidebar-note">Gå till</div>', unsafe_allow_html=True)
    for module_key, module_name in options:
        is_selected = module_key == selected_key
        if st.sidebar.button(
            module_name,
            key=f"page_btn_{module_key}",
            type="primary" if is_selected else "secondary",
            use_container_width=True,
        ):
            if module_key != selected_key:
                st.session_state.page_nav_key = module_key
                st.rerun()
            selected_key = module_key

    st.session_state.page_nav_key = selected_key
    return selected_key


def main() -> None:
    """App entry point."""
    st.set_page_config(page_title="Vandringsplanerare V.0.2", layout="wide")
    apply_theme()
    init_session_state()

    st.markdown(
        """
        <div class="hg-hero">
            <h1 style="margin:0;">Vandringsplanerare V.0.2</h1>
            <p>Planera vandringar, hantera utrustning och samordna äventyr med gruppen.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not st.session_state.db_ready:
        connected, message = ping_database()
        if not connected:
            st.error(message)
            host_ip = get_external_ip()
            st.warning(f"Extern IP (för grönlistning i databasen): {host_ip}")
            st.info("Skapa `.streamlit/secrets.toml` med Mongo-inställningar och kör igen.")
            return
        ensure_indexes()
        st.session_state.db_ready = True

    if st.session_state.current_user:
        render_user_sidebar()

    if not st.session_state.current_user:
        render_auth_main(is_registration_enabled())
        return

    modules = load_modules()
    modules = apply_module_order(modules, get_module_order_keys())
    current_user_is_admin = is_admin(st.session_state.current_user)
    admin_required_module_keys = get_admin_required_module_keys()
    modules = [
        module
        for module in modules
        if not (module.requires_admin or module.key in admin_required_module_keys) or current_user_is_admin
    ]
    disabled_module_keys = get_disabled_module_keys()
    available_modules = [module for module in modules if module.key not in disabled_module_keys]

    last_module_key = st.session_state.get("last_module_key")
    all_accessible_keys = {module.key for module in modules}
    module_name_by_key = {module.key: module.name for module in modules}
    if last_module_key in all_accessible_keys and last_module_key in disabled_module_keys:
        module_name = module_name_by_key.get(last_module_key, "Den valda modulen")
        st.warning(f"Modulen '{module_name}' är avstängd av administratören.")

    if not available_modules:
        st.warning("Alla moduler är avstängda av administratören.")
        return

    key_to_module = {module.key: module for module in available_modules}
    selected_key = render_sidebar_pages(available_modules)
    module = key_to_module.get(selected_key)
    if module is None:
        st.error("Den här modulen är avstängd av administratören.")
        return
    st.session_state.last_module_key = selected_key
    if st.session_state.get("last_logged_page_key") != selected_key:
        log_activity(
            st.session_state.current_user,
            "view_module",
            module=selected_key,
            target=module.name if module else selected_key,
        )
        st.session_state.last_logged_page_key = selected_key
    with st.container(border=True):
        if module.description:
            st.caption(module.description)
        module.render(st.session_state.current_user)

    st.divider()
    bug_module_available = "bug_tracker" in key_to_module
    if st.button("Rapportera Buggar", use_container_width=True, key="global_report_bug_button"):
        if bug_module_available:
            st.session_state.page_nav_key = "bug_tracker"
            st.rerun()
        else:
            st.warning("Bugtracker-modulen är för närvarande avstängd av administratören.")


if __name__ == "__main__":
    main()
