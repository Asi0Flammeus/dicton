"""OS-dependent layer.

Every `sys.platform` branch, OS binary invocation, kernel API, registry,
plist, evdev, fcntl, ctypes Win32, AppleScript, systemctl, playerctl call
lives under this package. The rest of dicton (`pipeline.py`, `cli.py`,
`wizard.py`, `runtime.py`, …) calls a neutral API without ever inspecting
`sys.platform` itself.

The single exemption is `src/dicton/visualizer.py` — explicit desktop GUI
coupling that is intentionally kept in one file.
"""
