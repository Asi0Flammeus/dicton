"""FastAPI application assembly for the config UI."""

from __future__ import annotations


def create_web_app(
    *,
    setup_html: str,
    advanced_html: str,
    config_model,
    autostart_model,
    dependencies: dict,
):
    from fastapi import FastAPI

    from .routes_config import register_config_routes
    from .routes_pages import register_page_routes
    from .routes_test import register_test_routes

    app = FastAPI(title="Dicton Setup")
    register_page_routes(app, setup_html=setup_html, advanced_html=advanced_html)
    register_config_routes(
        app,
        config_model=config_model,
        autostart_model=autostart_model,
        dependencies=dependencies,
    )
    register_test_routes(app, dependencies=dependencies)
    return app
