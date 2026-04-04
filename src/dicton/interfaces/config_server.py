"""Configuration web UI server for Dicton.

This module is the public entry-point.  The heavy lifting now lives in
dedicated submodules under ``dicton.interfaces.web``:

* ``env_io``       – .env file reading / writing
* ``config_logic`` – field maps, status checks, dictionary helpers
* ``templates``    – HTML / asset loading

Everything is re-exported here so that existing callers (CLI, tests) that do
``from dicton.interfaces.config_server import X`` keep working.
"""

from __future__ import annotations

import webbrowser
from threading import Timer

from ..shared.config import Config as Config  # noqa: F401

# -- re-exports used by tests for monkeypatching -----------------------------
from ..shared.platform_utils import get_platform_info as get_platform_info  # noqa: F401
from ..shared.startup import (  # noqa: F401
    get_autostart_state as get_autostart_state,
)
from ..shared.startup import (
    has_display_session as has_display_session,
)
from ..shared.startup import (
    launch_background as launch_background,
)
from ..shared.startup import (
    set_autostart as set_autostart,
)

# -- re-exports: config logic -------------------------------------------------
from .web.config_logic import (  # noqa: F401
    CONFIG_BOOL_FIELDS,
    CONFIG_FIELD_MAP,
    CONFIG_STRING_FIELDS,
    _get_env_bool,
    _get_env_string,
    _hotkey_status,
    _llm_status,
    _mask_api_key,
    _setup_state,
    _stt_status,
    _text_output_status,
    add_similarity_word,
    build_setup_status,
    get_current_config,
    get_dictionary,
    remove_similarity_word,
    save_config,
    save_dictionary,
)

# -- re-exports: env I/O -----------------------------------------------------
from .web.env_io import (  # noqa: F401
    _find_env_file,
    get_env_path,
    read_env_file,
    write_env_file,
)

# -- re-exports: templates ----------------------------------------------------
from .web.templates import (  # noqa: F401
    ADVANCED_HTML_TEMPLATE,
    LOGO_BASE64,
    SETUP_HTML_TEMPLATE,
    _load_html_template,
    _load_logo_base64,
)


def create_app():
    """Create FastAPI application."""
    try:
        from pydantic import create_model
    except ImportError as e:
        raise ImportError(
            "FastAPI not installed. Install with: pip install dicton[configui]"
        ) from e

    config_fields = dict.fromkeys(CONFIG_STRING_FIELDS, (str | None, None))
    config_fields.update(dict.fromkeys(CONFIG_BOOL_FIELDS, (bool | None, None)))
    ConfigData = create_model("ConfigData", **config_fields)
    AutostartData = create_model("AutostartData", enabled=(bool, ...))
    from .web.app import create_web_app

    return create_web_app(
        setup_html=SETUP_HTML_TEMPLATE,
        advanced_html=ADVANCED_HTML_TEMPLATE,
        config_model=ConfigData,
        autostart_model=AutostartData,
        dependencies={
            "get_current_config": get_current_config,
            "save_config": save_config,
            "build_setup_status": build_setup_status,
            "set_autostart": set_autostart,
            "launch_background": launch_background,
            "get_dictionary": get_dictionary,
            "add_similarity_word": add_similarity_word,
            "remove_similarity_word": remove_similarity_word,
            "setup_state": _setup_state,
        },
    )


def find_available_port(start_port: int = 6873, max_attempts: int = 10) -> int:
    """Find an available port starting from start_port."""
    import socket

    for offset in range(max_attempts):
        port = start_port + offset
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue

    raise RuntimeError(
        f"Could not find available port in range {start_port}-{start_port + max_attempts}"
    )


def run_config_server(port: int = 6873, open_browser: bool = True) -> None:
    """Run the configuration server."""
    try:
        import uvicorn
    except ImportError:
        print("Error: FastAPI/uvicorn not installed.")
        print("Install with: pip install dicton[configui]")
        return

    # Find available port if requested port is in use
    try:
        actual_port = find_available_port(port)
        if actual_port != port:
            print(f"Port {port} in use, using {actual_port}")
    except RuntimeError as e:
        print(f"Error: {e}")
        return

    app = create_app()

    print(f"\n{'=' * 50}")
    print("Dicton Setup")
    print(f"{'=' * 50}")
    print(f"Open: http://localhost:{actual_port}")
    print("Press Ctrl+C to stop")
    print(f"{'=' * 50}\n")

    if open_browser:
        Timer(1.0, lambda: webbrowser.open(f"http://localhost:{actual_port}")).start()

    uvicorn.run(app, host="127.0.0.1", port=actual_port, log_level="warning")
