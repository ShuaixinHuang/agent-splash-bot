"""Small platform adapters returning only active-window geometry and application identity."""
from dataclasses import dataclass
from pathlib import Path
import os
import sys


@dataclass(frozen=True)
class Window:
    key: str
    application: str
    x: int
    y: int
    width: int
    height: int
    monitor: str = ''
    monitor_x: int = 0
    monitor_y: int = 0

    def matches(self, patterns):
        terms = [term.strip().casefold() for term in patterns.split(',') if term.strip()]
        return self.width >= 160 and self.height >= 100 and any(term in self.application.casefold() for term in terms)


class X11:
    def __init__(self):
        from Xlib import display
        self.display = display.Display()
        self.root = self.display.screen().root
        self.active = self.display.intern_atom('_NET_ACTIVE_WINDOW')
        self.pid = self.display.intern_atom('_NET_WM_PID')
        self.closed = False

    def current(self):
        from Xlib import X, error
        try:
            prop = self.root.get_full_property(self.active, X.AnyPropertyType)
            if prop is None or not len(prop.value) or not prop.value[0]:
                return None
            window = self.display.create_resource_object('window', int(prop.value[0]))
            if window.get_attributes().map_state != X.IsViewable:
                return None
            geometry = window.get_geometry()
            position = self.root.translate_coords(window, 0, 0)
            identity = '.'.join(window.get_wm_class() or ())
            pid = window.get_full_property(self.pid, X.AnyPropertyType)
            process = str(pid.value[0]) if pid is not None and len(pid.value) else 'unknown'
            return Window(f'{window.id}:{process}', identity, position.x, position.y, geometry.width, geometry.height)
        except error.XError:
            return None

    def close(self):
        if not self.closed:
            self.display.close()
            self.closed = True


class Windows:
    def __init__(self):
        import ctypes as c
        from ctypes import wintypes as w
        self.c, self.w = c, w
        self.user = c.WinDLL('user32', use_last_error=True)
        self.kernel = c.WinDLL('kernel32', use_last_error=True)
        self.user.GetForegroundWindow.restype = w.HWND
        self.user.IsIconic.argtypes = [w.HWND]
        self.user.GetClientRect.argtypes = [w.HWND, c.POINTER(w.RECT)]
        self.user.ClientToScreen.argtypes = [w.HWND, c.POINTER(w.POINT)]
        self.user.GetWindowThreadProcessId.argtypes = [w.HWND, c.POINTER(w.DWORD)]
        self.kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
        self.kernel.OpenProcess.restype = w.HANDLE
        self.kernel.CloseHandle.argtypes = [w.HANDLE]
        self.kernel.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, c.POINTER(w.DWORD)]
        self.user.MonitorFromWindow.argtypes = [w.HWND, w.DWORD]
        self.user.MonitorFromWindow.restype = w.HANDLE
        class MonitorInfo(c.Structure):
            _fields_ = [('cbSize', w.DWORD), ('rcMonitor', w.RECT), ('rcWork', w.RECT), ('dwFlags', w.DWORD), ('szDevice', w.WCHAR * 32)]
        self.MonitorInfo = MonitorInfo
        self.user.GetMonitorInfoW.argtypes = [w.HANDLE, c.POINTER(MonitorInfo)]

    def current(self):
        c, w = self.c, self.w
        handle = self.user.GetForegroundWindow()
        if not handle or self.user.IsIconic(handle):
            return None
        pid = w.DWORD()
        self.user.GetWindowThreadProcessId(handle, c.byref(pid))
        process = self.kernel.OpenProcess(0x1000, False, pid.value)
        if not process:
            return None
        try:
            name = c.create_unicode_buffer(32768)
            length = w.DWORD(len(name))
            if not self.kernel.QueryFullProcessImageNameW(process, 0, name, c.byref(length)):
                return None
            application = Path(name.value).name
        finally:
            self.kernel.CloseHandle(process)
        rect, point = w.RECT(), w.POINT(0, 0)
        if not self.user.GetClientRect(handle, c.byref(rect)) or not self.user.ClientToScreen(handle, c.byref(point)):
            return None
        info = self.MonitorInfo()
        info.cbSize = c.sizeof(info)
        monitor = self.user.MonitorFromWindow(handle, 2)
        if not self.user.GetMonitorInfoW(monitor, c.byref(info)):
            return None
        return Window(f'{handle}:{pid.value}', application, point.x, point.y, rect.right, rect.bottom,
                      info.szDevice, info.rcMonitor.left, info.rcMonitor.top)

    def close(self):
        pass


class MacOS:
    def __init__(self):
        import Quartz
        from AppKit import NSWorkspace
        self.quartz, self.workspace = Quartz, NSWorkspace.sharedWorkspace()

    def current(self):
        q = self.quartz
        app = self.workspace.frontmostApplication()
        if app is None:
            return None
        pid = app.processIdentifier()
        identity = (app.bundleIdentifier() or '') + ' ' + (app.localizedName() or '')
        windows = q.CGWindowListCopyWindowInfo(q.kCGWindowListOptionOnScreenOnly | q.kCGWindowListExcludeDesktopElements, q.kCGNullWindowID)
        for item in windows or []:
            if item.get(q.kCGWindowOwnerPID) != pid or item.get(q.kCGWindowLayer) != 0:
                continue
            if item.get(q.kCGWindowAlpha, 1) <= 0:
                continue
            rect = item[q.kCGWindowBounds]
            if rect['Width'] < 160 or rect['Height'] < 100:
                continue
            return Window(f'{item[q.kCGWindowNumber]}:{pid}', identity, int(rect['X']), int(rect['Y']), int(rect['Width']), int(rect['Height']))
        return None

    def close(self):
        pass


def make_provider():
    if sys.platform == 'win32':
        return Windows()
    if sys.platform == 'darwin':
        return MacOS()
    if sys.platform.startswith('linux'):
        if os.environ.get('XDG_SESSION_TYPE') == 'wayland' or os.environ.get('WAYLAND_DISPLAY'):
            raise RuntimeError('Window following requires an X11 session. On Wayland use --demo, or sign into an X11 desktop session.')
        if not os.environ.get('DISPLAY'):
            raise RuntimeError('No X11 display is available. Run on a desktop, or use --render for an offline frame.')
        return X11()
    raise RuntimeError('This platform has no active-window adapter.')
