"""Simple notifications for Push-to-Write"""
import subprocess


def notify(title: str, message: str, timeout: int = 2):
    """Show desktop notification"""
    try:
        subprocess.run(
            ['notify-send', '-t', str(timeout * 1000), title, message],
            timeout=2,
            capture_output=True
        )
    except Exception:
        pass  # Notifications are optional
