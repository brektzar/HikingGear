"""Basic stats and controls module."""

import streamlit as st

from .base import AppModule


def render(current_user: str) -> None:
    """Render a generic interactive module."""
    st.header("Snabbstatistik")
    st.caption(f"Användare: {current_user}")
    value = st.slider("Välj ett värde", min_value=0, max_value=100, value=25)
    st.metric("Valt värde", value)
    st.progress(value / 100)


def get_module() -> AppModule:
    """Return module metadata and render callable."""
    return AppModule(
        key="stats",
        name="Snabbstatistik",
        description="Liten interaktiv exempelmodul.",
        render=render,
    )
