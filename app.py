"""Modular Streamlit app for hiking planning."""

import streamlit as st

from core.auth import authenticate_user, is_admin, register_user
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
            --hg-bg: #f4efe4;
            --hg-paper: #fbf8f1;
            --hg-forest: #2f4f3d;
            --hg-moss: #5f7d4d;
            --hg-sand: #cfb997;
            --hg-clay: #8a5b3d;
            --hg-text: #2b2a28;
        }

        .stApp {
            background: linear-gradient(180deg, #f1ebde 0%, #f7f2e8 100%);
            color: var(--hg-text);
        }

        .stApp,
        .stApp * {
            color: #161512;
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
            color: #161512 !important;
        }

        .stApp [data-baseweb="select"] *,
        .stApp [data-baseweb="input"] *,
        .stApp [data-baseweb="textarea"] *,
        .stApp [data-baseweb="radio"] *,
        .stApp [data-baseweb="checkbox"] * {
            color: #161512 !important;
        }

        .stApp [data-baseweb="select"] > div,
        .stApp [data-baseweb="input"] > div,
        .stApp [data-baseweb="textarea"] > div {
            background-color: #fffaf2 !important;
            border: 1px solid rgba(138, 91, 61, 0.28) !important;
            border-radius: 10px !important;
            box-shadow: 0 1px 2px rgba(47, 79, 61, 0.08) !important;
        }

        .stApp [data-baseweb="input"] > div:focus-within,
        .stApp [data-baseweb="textarea"] > div:focus-within,
        .stApp [data-baseweb="select"] > div:focus-within {
            border-color: #5f7d4d !important;
            box-shadow: 0 0 0 2px rgba(95, 125, 77, 0.18) !important;
        }

        [data-testid="stHeader"] {
            background: #efe6d6 !important;
        }

        [data-testid="stHeader"],
        [data-testid="stToolbar"],
        [data-testid="stDecoration"] {
            color: #161512 !important;
        }

        [data-testid="stHeader"] button,
        [data-testid="stToolbar"] button {
            color: #161512 !important;
            background: #fffaf2 !important;
            border: 1px solid #cfb997 !important;
        }

        [data-testid="stHeader"] button svg,
        [data-testid="stToolbar"] button svg,
        [data-testid="stHeader"] button svg path,
        [data-testid="stToolbar"] button svg path {
            fill: #161512 !important;
            stroke: #161512 !important;
        }

        [data-testid="stHeader"] button *,
        [data-testid="stToolbar"] button * {
            color: #161512 !important;
            fill: #161512 !important;
            stroke: #161512 !important;
        }

        [data-testid="stToolbar"] button {
            background: #fffaf2 !important;
            border: 1px solid #cfb997 !important;
            color: #161512 !important;
        }

        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #304b3d 0%, #3d5f4e 100%);
        }

        [data-testid="stSidebar"] * {
            color: #f4efe4 !important;
        }

        [data-testid="stSidebar"] [data-baseweb="select"] *,
        [data-testid="stSidebar"] [data-baseweb="input"] *,
        [data-testid="stSidebar"] [data-baseweb="textarea"] * {
            color: #f4efe4 !important;
        }

        [data-testid="stSidebar"] [data-baseweb="input"] input,
        [data-testid="stSidebar"] [data-baseweb="input"] textarea,
        [data-testid="stSidebar"] [data-baseweb="textarea"] textarea {
            color: #161512 !important;
            -webkit-text-fill-color: #161512 !important;
            caret-color: #161512 !important;
        }

        [data-testid="stSidebar"] [data-baseweb="input"] input::placeholder,
        [data-testid="stSidebar"] [data-baseweb="textarea"] textarea::placeholder {
            color: #5a574f !important;
            opacity: 1;
        }

        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 14px;
            border: 1px solid rgba(138, 91, 61, 0.35);
            background: rgba(251, 248, 241, 0.92);
            box-shadow: 0 6px 18px rgba(47, 79, 61, 0.09);
            padding: 0.35rem 0.5rem;
        }

        .hg-auth-shell {
            max-width: 760px;
            margin: 0.5rem auto 0.9rem auto;
            padding: 0.4rem;
            border-radius: 16px;
            background: linear-gradient(180deg, rgba(255, 250, 242, 0.86) 0%, rgba(251, 248, 241, 0.95) 100%);
            border: 1px solid rgba(138, 91, 61, 0.32);
            box-shadow: 0 8px 20px rgba(47, 79, 61, 0.12);
        }

        .hg-auth-shell h3 {
            margin: 0.2rem 0 0.15rem 0;
        }

        .hg-auth-shell p {
            margin: 0;
            color: #3a3834 !important;
        }

        .hg-hero {
            background: linear-gradient(135deg, #2f4f3d 0%, #5f7d4d 50%, #8a5b3d 100%);
            color: #f9f5ea;
            border-radius: 16px;
            padding: 1.1rem 1.2rem;
            margin-bottom: 1rem;
            box-shadow: 0 8px 20px rgba(47, 79, 61, 0.22);
        }

        .hg-hero p {
            margin: 0.25rem 0 0 0;
            opacity: 0.92;
        }

        .stButton > button,
        .stFormSubmitButton > button {
            border-radius: 10px;
            border: 1px solid #5f7d4d;
            background: #5f7d4d;
            color: #f8f3e8;
            font-weight: 600;
            box-shadow: 0 2px 8px rgba(47, 79, 61, 0.18);
        }

        .stButton > button:hover,
        .stFormSubmitButton > button:hover {
            border-color: #2f4f3d;
            background: #2f4f3d;
            color: #fffaf0;
        }

        .stTabs [data-baseweb="tab-list"] {
            gap: 0.35rem;
        }

        .stTabs [data-baseweb="tab"] {
            background: #f6efe1;
            border: 1px solid rgba(138, 91, 61, 0.32);
            border-radius: 10px;
            padding: 0.35rem 0.85rem;
        }

        .stTabs [aria-selected="true"] {
            background: #e5d3b8 !important;
            border-color: #8a5b3d !important;
        }

        /* Separate expander styling (independent from card wrappers). */
        .stExpander {
            border: 1px solid rgba(138, 91, 61, 0.36) !important;
            border-radius: 12px !important;
            background: rgba(255, 250, 242, 0.88) !important;
            box-shadow: 0 4px 12px rgba(47, 79, 61, 0.08) !important;
            overflow: hidden;
        }

        .stExpander details {
            border: none !important;
            border-radius: 12px !important;
            background: transparent !important;
        }

        .stExpander summary {
            background: linear-gradient(180deg, #f8f1e3 0%, #f3e8d5 100%) !important;
            border-bottom: 1px solid rgba(138, 91, 61, 0.28) !important;
            padding: 0.55rem 0.8rem !important;
            font-weight: 600 !important;
        }

        .stExpander details[open] > summary {
            background: linear-gradient(180deg, #efe1c9 0%, #ead8ba 100%) !important;
        }

        .stExpander summary:hover {
            background: linear-gradient(180deg, #f1e3cb 0%, #ecdabf 100%) !important;
        }

        .stExpander [data-testid="stExpanderDetails"] {
            background: #fffaf2 !important;
            padding: 0.55rem 0.75rem 0.7rem 0.75rem !important;
        }

        /* Separate divider styling for better contrast. */
        .stApp hr,
        .stApp [data-testid="stDivider"],
        .stApp [role="separator"] {
            border: none !important;
            border-top: 2px solid rgba(90, 64, 44, 0.6) !important;
            opacity: 1 !important;
            margin-top: 0.75rem !important;
            margin-bottom: 0.75rem !important;
        }

        .stButton > button[kind="primary"],
        .stFormSubmitButton > button[kind="primary"] {
            background: #b53a2d !important;
            border-color: #8e261c !important;
            color: #fff6f3 !important;
        }

        .stButton > button[kind="primary"]:hover,
        .stFormSubmitButton > button[kind="primary"]:hover {
            background: #942c22 !important;
            border-color: #741e17 !important;
            color: #fff6f3 !important;
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
                font-size: 1.35rem !important;
                line-height: 1.25 !important;
            }

            .hg-hero p {
                font-size: 0.92rem !important;
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
                width: 100% !important;
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


def get_disabled_module_keys() -> set[str]:
    """Return module keys disabled by admin settings."""
    settings = get_collection("app_settings")
    doc = settings.find_one({"_id": "modules"}, {"disabled_keys": 1})
    if not doc:
        return set()
    disabled = {str(key) for key in doc.get("disabled_keys", [])}
    disabled.discard("admin")
    return disabled


def render_user_sidebar() -> None:
    """Render account controls in sidebar once authenticated."""
    st.sidebar.title("Konto")
    st.sidebar.success(f"Inloggad: {st.session_state.current_user}")
    if is_admin(st.session_state.current_user):
        st.sidebar.caption("Roll: Admin")
    if st.sidebar.button("Logga ut"):
        st.session_state.current_user = None
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
                    st.session_state.current_user = username.strip().lower()
                    st.success("Inloggad.")
                    st.rerun()
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
                            st.success(result.message)
                        else:
                            st.error(result.message)
    else:
        st.info("Registrering är för närvarande avstängd av administratör.")


def render_sidebar_pages(modules: list) -> str:
    """Render sidebar page navigation and return selected module key."""
    st.sidebar.title("Sidor")
    options = [(module.key, module.name) for module in modules]
    selected_key = st.session_state.get("page_nav_key")
    valid_keys = {module_key for module_key, _ in options}
    if selected_key not in valid_keys:
        selected_key = options[0][0]

    st.sidebar.caption("Gå till")
    for module_key, module_name in options:
        is_selected = module_key == selected_key
        if st.sidebar.button(
            module_name,
            key=f"page_btn_{module_key}",
            type="primary" if is_selected else "secondary",
            use_container_width=True,
        ):
            selected_key = module_key

    st.session_state.page_nav_key = selected_key
    return selected_key


def main() -> None:
    """App entry point."""
    st.set_page_config(page_title="HikingGear Hub", layout="wide")
    apply_theme()
    init_session_state()

    st.markdown(
        """
        <div class="hg-hero">
            <h1 style="margin:0;">HikingGear Hub</h1>
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
    current_user_is_admin = is_admin(st.session_state.current_user)
    modules = [module for module in modules if not module.requires_admin or current_user_is_admin]
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
    with st.container(border=True):
        st.subheader(module.name)
        st.caption(module.description)
        module.render(st.session_state.current_user)


if __name__ == "__main__":
    main()
