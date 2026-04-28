"""Basic welcome module."""

import streamlit as st

from .base import AppModule


def render(current_user: str) -> None:
    """Render the welcome section."""
    st.header("Välkommen")
    st.write("Detta är din arbetsyta för vandringsplanering.")
    st.success(f"Inloggad som: {current_user}")
    st.info("Använd sidonavigeringen i menyn för att hoppa mellan moduler.")


def get_module() -> AppModule:
    """Return module metadata and render callable."""
    return AppModule(
        key="welcome",
        name="Välkommen",
        description="Enkel startsida för appen.",
        render=render,
    )
