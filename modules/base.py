"""Base interfaces for modular Streamlit sections."""

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class AppModule:
    """Simple module contract used by the module manager."""

    key: str
    name: str
    description: str
    render: Callable[[str], None]
    requires_admin: bool = False
