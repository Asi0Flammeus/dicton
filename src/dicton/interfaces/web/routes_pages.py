"""HTML page routes for the setup UI."""

from __future__ import annotations

from fastapi.responses import HTMLResponse


def register_page_routes(app, *, setup_html: str, advanced_html: str) -> None:
    @app.get("/", response_class=HTMLResponse)
    async def root():
        return setup_html

    @app.get("/advanced", response_class=HTMLResponse)
    async def advanced():
        return advanced_html
