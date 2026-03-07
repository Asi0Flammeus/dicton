"""Configuration and setup routes."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse


def register_config_routes(app, *, config_model, autostart_model, dependencies: dict) -> None:
    get_current_config = dependencies["get_current_config"]
    save_config = dependencies["save_config"]
    build_setup_status = dependencies["build_setup_status"]
    set_autostart = dependencies["set_autostart"]
    launch_background = dependencies["launch_background"]
    get_dictionary = dependencies["get_dictionary"]
    add_similarity_word = dependencies["add_similarity_word"]
    remove_similarity_word = dependencies["remove_similarity_word"]
    setup_state = dependencies["setup_state"]

    @app.get("/api/config")
    async def api_get_config():
        return JSONResponse(get_current_config())

    @app.post("/api/config")
    async def api_save_config(request: Request):
        try:
            payload = await request.json()
            data = config_model.model_validate(payload)
            config_dict = data.model_dump(exclude_none=True)
            save_config(config_dict)
            setup_state["first_test_passed"] = False
            setup_state["last_test_text"] = ""
            return {"status": "ok", "setup": build_setup_status()}
        except Exception as exc:
            import traceback

            print(f"[ERROR] Save config failed: {exc}")
            traceback.print_exc()
            return JSONResponse({"status": "error", "message": str(exc)}, status_code=500)

    @app.get("/api/setup/status")
    async def api_setup_status():
        return JSONResponse(build_setup_status())

    @app.post("/api/setup/save")
    async def api_setup_save(request: Request):
        return await api_save_config(request)

    @app.post("/api/setup/autostart")
    async def api_setup_autostart(request: Request):
        payload = await request.json()
        data = autostart_model.model_validate(payload)
        result = set_autostart(data.enabled)
        payload = {"status": "ok" if result.get("ok") else "error", **result}
        payload["setup"] = build_setup_status()
        status_code = 200 if result.get("ok") else 400
        return JSONResponse(payload, status_code=status_code)

    @app.post("/api/setup/launch")
    async def api_setup_launch():
        result = launch_background()
        payload = {"status": "ok" if result.get("ok") else "error", **result}
        payload["setup"] = build_setup_status()
        status_code = 200 if result.get("ok") else 400
        return JSONResponse(payload, status_code=status_code)

    @app.get("/api/dictionary")
    async def api_get_dictionary():
        return JSONResponse(get_dictionary())

    @app.post("/api/dictionary")
    async def api_add_similarity_word(data: dict):
        word = data.get("word", "")
        if word:
            add_similarity_word(word)
            return {"status": "ok"}
        return JSONResponse({"error": "Missing word"}, status_code=400)

    @app.delete("/api/dictionary")
    async def api_remove_similarity_word(data: dict):
        word = data.get("word", "")
        if word:
            remove_similarity_word(word)
            return {"status": "ok"}
        return JSONResponse({"error": "Missing word"}, status_code=400)
