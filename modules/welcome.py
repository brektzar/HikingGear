"""Basic welcome module."""

import base64

import streamlit as st

from core.db import get_collection
from .base import AppModule


def render(current_user: str) -> None:
    """Render the welcome section."""
    settings = get_collection("app_settings")
    doc = settings.find_one(
        {"_id": "welcome_content"},
        {"title": 1, "body": 1, "image_b64": 1, "image_mime": 1},
    ) or {}

    title = str(doc.get("title", "Välkommen"))
    body = str(doc.get("body", "Detta är din arbetsyta för vandringsplanering."))
    image_b64 = str(doc.get("image_b64", "") or "")
    image_mime = str(doc.get("image_mime", "") or "")

    st.header(title)
    st.write(body)
    if image_b64:
        try:
            image_bytes = base64.b64decode(image_b64)
            st.image(image_bytes, use_container_width=True)
            if image_mime:
                st.caption(f"Bildformat: {image_mime}")
        except Exception:
            st.warning("Bilden kunde inte läsas.")

    st.success(f"Inloggad som: {current_user}")
    st.info("Använd sidonavigeringen i menyn för att hoppa mellan moduler.")


def get_module() -> AppModule:
    """Return module metadata and render callable."""
    return AppModule(
        key="welcome",
        name="**Välkommen!**",
        description="",
        render=render,
    )
