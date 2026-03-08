"""Test confirmation route for setup wizard."""

from __future__ import annotations

from fastapi.responses import JSONResponse


def register_test_routes(app, *, dependencies: dict) -> None:
    build_setup_status = dependencies["build_setup_status"]
    setup_state = dependencies["setup_state"]

    @app.post("/api/test/confirm")
    async def api_test_confirm():
        setup_state["first_test_passed"] = True
        setup_state["last_test_text"] = "(confirmed by user)"
        return JSONResponse({"status": "ok", "setup": build_setup_status()})
