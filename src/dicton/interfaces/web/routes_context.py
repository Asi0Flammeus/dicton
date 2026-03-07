"""Context profile routes."""

from __future__ import annotations

import json

from fastapi import Request
from fastapi.responses import JSONResponse

from ...app_paths import get_user_contexts_path


def register_context_routes(app) -> None:
    @app.get("/api/context/profiles")
    async def api_get_context_profiles():
        try:
            from ...context_profiles import get_profile_manager

            manager = get_profile_manager()
            manager.load()
            return list(manager.list_profiles())
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    @app.get("/api/context/current")
    async def api_get_current_context():
        try:
            from ...context_detector import get_context_detector
            from ...context_profiles import get_profile_manager

            detector = get_context_detector()
            if not detector:
                return {
                    "app_name": "N/A",
                    "window_title": "Context detection not available",
                    "wm_class": "",
                    "matched_profile": "default",
                    "typing_speed": "normal",
                }

            context = detector.get_context()
            manager = get_profile_manager()
            profile = manager.match_context(context)

            return {
                "app_name": context.app_name if context else "",
                "window_title": context.window.title if context and context.window else "",
                "wm_class": context.window.wm_class if context and context.window else "",
                "matched_profile": profile.name if profile else "default",
                "typing_speed": profile.typing_speed if profile else "normal",
            }
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    @app.get("/api/context/profiles/{profile_name}")
    async def api_get_profile(profile_name: str):
        try:
            from ...context_profiles import get_profile_manager

            manager = get_profile_manager()
            manager.load()
            profile = manager.get_profile(profile_name)

            if not profile:
                return JSONResponse(
                    {"error": f"Profile '{profile_name}' not found"}, status_code=404
                )

            return {
                "name": profile.name,
                "match": {
                    "wm_class": profile.match.wm_class,
                    "window_title_contains": profile.match.window_title_contains,
                    "file_extension": profile.match.file_extension,
                    "widget_role": profile.match.widget_role,
                    "url_contains": profile.match.url_contains,
                },
                "llm_preamble": profile.llm_preamble,
                "typing_speed": profile.typing_speed,
                "formatting": profile.formatting,
                "extends": profile.extends,
                "priority": profile.priority,
            }
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    @app.put("/api/context/profiles/{profile_name}")
    async def api_update_profile(profile_name: str, request: Request):
        try:
            data = await request.json()
            user_config_path = get_user_contexts_path()

            if user_config_path.exists():
                with open(user_config_path, encoding="utf-8") as f:
                    user_config = json.load(f)
            else:
                user_config = {"profiles": {}, "typing_speeds": {}}

            user_config["profiles"][profile_name] = {
                "match": data.get("match", {}),
                "llm_preamble": data.get("llm_preamble", ""),
                "typing_speed": data.get("typing_speed", "normal"),
                "formatting": data.get("formatting", "auto"),
                "priority": data.get("priority", 0),
            }

            if data.get("extends"):
                user_config["profiles"][profile_name]["extends"] = data["extends"]

            user_config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(user_config_path, "w", encoding="utf-8") as f:
                json.dump(user_config, f, indent=2)

            from ...context_profiles import get_profile_manager

            manager = get_profile_manager()
            manager.reload()

            return {"status": "ok", "profile": profile_name}
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    @app.delete("/api/context/profiles/{profile_name}")
    async def api_delete_profile(profile_name: str):
        try:
            if profile_name == "default":
                return JSONResponse({"error": "Cannot delete the default profile"}, status_code=400)

            user_config_path = get_user_contexts_path()
            if not user_config_path.exists():
                return JSONResponse(
                    {
                        "error": f"Profile '{profile_name}' is a bundled default and cannot be deleted"
                    },
                    status_code=400,
                )

            with open(user_config_path, encoding="utf-8") as f:
                user_config = json.load(f)

            if profile_name not in user_config.get("profiles", {}):
                return JSONResponse(
                    {
                        "error": f"Profile '{profile_name}' is a bundled default and cannot be deleted"
                    },
                    status_code=400,
                )

            del user_config["profiles"][profile_name]

            with open(user_config_path, "w", encoding="utf-8") as f:
                json.dump(user_config, f, indent=2)

            from ...context_profiles import get_profile_manager

            manager = get_profile_manager()
            manager.reload()

            return {"status": "ok", "deleted": profile_name}
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)
