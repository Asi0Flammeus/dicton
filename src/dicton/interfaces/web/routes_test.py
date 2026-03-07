"""Recording test and diagnostics routes."""

from __future__ import annotations

from fastapi.responses import JSONResponse


def register_test_routes(app, *, dependencies: dict) -> None:
    background_record = dependencies["background_record"]
    build_setup_status = dependencies["build_setup_status"]
    setup_state = dependencies["setup_state"]
    test_state = dependencies["test_state"]

    @app.post("/api/test/start")
    async def api_test_start():
        import threading
        import time

        from ...speech_recognition_engine import SpeechRecognizer

        if test_state["recording"]:
            test_state["recording"] = False
            if test_state["record_thread"]:
                test_state["record_thread"].join(timeout=1.0)

        test_state["recognizer"] = SpeechRecognizer()
        test_state["frames"] = []
        test_state["audio_data"] = None
        test_state["start_time"] = time.time()
        test_state["recording"] = True
        test_state["record_thread"] = threading.Thread(target=background_record)
        test_state["record_thread"].start()

        return {"status": "recording"}

    @app.post("/api/test/stop")
    async def api_test_stop():
        import time

        import numpy as np

        if not test_state["recording"]:
            return JSONResponse({"error": "Not recording"}, status_code=400)

        test_state["recording"] = False
        record_end_time = time.time()
        record_duration_ms = (record_end_time - test_state["start_time"]) * 1000

        if test_state["record_thread"]:
            test_state["record_thread"].join(timeout=2.0)

        frames = test_state["frames"]
        if not frames:
            setup_state["first_test_passed"] = False
            return JSONResponse(
                {"error": "No audio captured", "setup": build_setup_status()},
                status_code=400,
            )

        audio_data = b"".join(frames)
        audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

        recognizer = test_state["recognizer"]
        if not recognizer:
            setup_state["first_test_passed"] = False
            return JSONResponse(
                {"error": "Recognizer not available", "setup": build_setup_status()},
                status_code=500,
            )

        result = {
            "latency": {
                "recording": record_duration_ms,
                "stt": 0,
                "llm": 0,
                "total": 0,
            },
            "text": "",
            "stt_provider": "ElevenLabs" if recognizer.use_elevenlabs else "None",
        }

        try:
            stt_start = time.time()
            text = recognizer.transcribe(audio_array)
            result["latency"]["stt"] = (time.time() - stt_start) * 1000

            if not text:
                result["error"] = "No speech detected"
                setup_state["first_test_passed"] = False
                result["setup"] = build_setup_status()
                return JSONResponse(result)

            llm_start = time.time()
            try:
                from ... import llm_processor
                from ...config import config

                if config.ENABLE_REFORMULATION and llm_processor.is_available():
                    processed = llm_processor.reformulate(text)
                    if processed:
                        text = processed
                    result["llm_provider"] = config.LLM_PROVIDER.capitalize()
                else:
                    result["llm_provider"] = (
                        "Disabled" if not config.ENABLE_REFORMULATION else "Not configured"
                    )
            except ImportError:
                result["llm_provider"] = "Not available"

            result["latency"]["llm"] = (time.time() - llm_start) * 1000
            result["text"] = text
            result["latency"]["total"] = (
                result["latency"]["recording"] + result["latency"]["stt"] + result["latency"]["llm"]
            )
            setup_state["first_test_passed"] = True
            setup_state["last_test_text"] = text

        except Exception as exc:
            result["error"] = str(exc)
            setup_state["first_test_passed"] = False

        finally:
            if test_state["recognizer"]:
                test_state["recognizer"].cleanup()
                test_state["recognizer"] = None
            test_state["frames"] = []

        result["setup"] = build_setup_status()
        return JSONResponse(result)
