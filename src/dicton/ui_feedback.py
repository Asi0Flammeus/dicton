"""Cross-platform notifications for Dicton"""
import subprocess
from .platform_utils import IS_WINDOWS, IS_LINUX, IS_MACOS


def notify(title: str, message: str, timeout: int = 2):
    """Show desktop notification - cross-platform"""
    try:
        if IS_LINUX:
            _notify_linux(title, message, timeout)
        elif IS_WINDOWS:
            _notify_windows(title, message, timeout)
        elif IS_MACOS:
            _notify_macos(title, message, timeout)
        else:
            # Silent fallback - just print to console
            print(f"[{title}] {message}")
    except Exception:
        pass  # Notifications are optional


def _notify_linux(title: str, message: str, timeout: int):
    """Linux notification using notify-send"""
    try:
        subprocess.run(
            ['notify-send', '-t', str(timeout * 1000), title, message],
            timeout=2,
            capture_output=True
        )
    except FileNotFoundError:
        # notify-send not installed, try plyer
        _notify_plyer(title, message, timeout)


def _notify_windows(title: str, message: str, timeout: int):
    """Windows notification using plyer or win10toast"""
    try:
        # Try plyer first (cross-platform)
        from plyer import notification
        notification.notify(
            title=title,
            message=message,
            timeout=timeout,
            app_name="Dicton"
        )
    except ImportError:
        try:
            # Fallback to win10toast
            from win10toast import ToastNotifier
            toaster = ToastNotifier()
            toaster.show_toast(
                title,
                message,
                duration=timeout,
                threaded=True
            )
        except ImportError:
            # No notification library available
            print(f"[{title}] {message}")


def _notify_macos(title: str, message: str, timeout: int):
    """macOS notification using osascript or plyer"""
    try:
        # Try native AppleScript first
        script = f'display notification "{message}" with title "{title}"'
        subprocess.run(
            ['osascript', '-e', script],
            timeout=2,
            capture_output=True
        )
    except Exception:
        # Fallback to plyer
        _notify_plyer(title, message, timeout)


def _notify_plyer(title: str, message: str, timeout: int):
    """Cross-platform notification using plyer"""
    try:
        from plyer import notification
        notification.notify(
            title=title,
            message=message,
            timeout=timeout,
            app_name="Dicton"
        )
    except ImportError:
        # plyer not installed
        print(f"[{title}] {message}")
    except Exception:
        # Notification failed
        print(f"[{title}] {message}")
