"""Test confirmation route for setup wizard."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse


def register_test_routes(app, *, dependencies: dict) -> None:
    build_setup_status = dependencies["build_setup_status"]
    setup_state = dependencies["setup_state"]

    @app.post("/api/test/confirm")
    async def api_test_confirm(request: Request):
        text = "(confirmed by user)"
        try:
            body = await request.json()
            if isinstance(body, dict) and body.get("text"):
                text = body["text"]
        except Exception:
            pass
        setup_state["first_test_passed"] = True
        setup_state["last_test_text"] = text
        return JSONResponse({"status": "ok", "setup": build_setup_status()})
