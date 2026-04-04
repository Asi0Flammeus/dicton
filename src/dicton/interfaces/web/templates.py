"""HTML template and asset loading for the configuration UI."""

from __future__ import annotations

import base64
from pathlib import Path


def _load_logo_base64() -> str:
    """Load logo from package assets folder and convert to base64."""
    logo_path = Path(__file__).parent.parent.parent / "assets" / "logo.png"
    if logo_path.exists():
        return base64.b64encode(logo_path.read_bytes()).decode("utf-8")
    return ""


LOGO_BASE64 = _load_logo_base64()


def _load_html_template(template_name: str) -> str:
    """Load HTML template for the configuration UI."""
    template_path = Path(__file__).parent.parent.parent / "assets" / template_name
    if template_path.exists():
        html = template_path.read_text(encoding="utf-8")
        return html.replace("{{LOGO_BASE64}}", LOGO_BASE64)
    return "<html><body>Config UI template missing.</body></html>"


SETUP_HTML_TEMPLATE = _load_html_template("setup_ui.html")
ADVANCED_HTML_TEMPLATE = _load_html_template("config_ui.html")
