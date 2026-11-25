import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication
from aurora_boot.animation import Canvas, envelope
from aurora_boot.app import Controller, Preferences, logical_geometry
from aurora_boot.config import Settings, Store
from aurora_boot.windows import Window, make_provider

APP = QApplication.instance() or QApplication([])


class FakeProvider:
    def __init__(self):
        self.window = Window('1:20', 'Claude.exe', 80, 60, 700, 500)
        self.closed = False
    def current(self):
        return self.window
    def close(self):
        self.closed = True


class Windows(unittest.TestCase):
    def test_application_matching_ignores_case_not_blank_patterns(self):
        target = Window('key', 'Org.Example.ChatGPT', -200, 50, 800, 600)
        self.assertTrue(target.matches('claude, chatgpt'))
        self.assertFalse(target.matches(' , '))
        self.assertFalse(target.matches('firefox'))
        self.assertFalse(Window('key', 'chatgpt', 0, 0, 10, 20).matches('chatgpt'))

    @unittest.skipUnless(sys.platform.startswith('linux'), 'Linux session contract')
    def test_wayland_is_explicitly_unsupported(self):
        with patch.dict(os.environ, {'XDG_SESSION_TYPE': 'wayland'}):
            with self.assertRaisesRegex(RuntimeError, 'X11'):
                make_provider()

    @unittest.skipUnless(sys.platform in ('win32', 'darwin'), 'native platform API smoke check')
    def test_native_platform_adapter(self):
        from aurora_boot.windows import Windows as Win32, MacOS
        provider = Win32() if sys.platform == 'win32' else MacOS()
        try:
            result = provider.current()
            self.assertTrue(result is None or isinstance(result, Window))
        finally:
            provider.close()

    def test_windows_monitor_scaling(self):
        class Screen:
            def name(self): return r'\\.\DISPLAY2'
            def geometry(self): return QRect(1920, -100, 1280, 720)
            def devicePixelRatio(self): return 1.5
        target = Window('key', 'app', 3000, 150, 900, 600, r'\\.\DISPLAY2', 2880, 0)
        self.assertEqual(logical_geometry(target, [Screen()]), QRect(2000, 0, 600, 400))


class Rendering(unittest.TestCase):
    def test_themes_export_distinct_nonempty_frames(self):
        fingerprints = set()
        for theme in ('aurora', 'ember', 'orbit'):
            canvas = Canvas(Settings(theme=theme), preview=True)
            canvas.fixed_time = 1.5; canvas.resize(640, 400)
            image = canvas.grab().toImage()
            self.assertFalse(image.isNull())
            colors = {image.pixelColor(x, y).name() for x in range(10, 630, 20) for y in range(10, 390, 20)}
            self.assertGreater(len(colors), 15)
            fingerprints.add(image.pixelColor(10, 10).name())
            canvas.close()
        self.assertEqual(len(fingerprints), 3)

    def test_frames_change_over_time(self):
        canvas = Canvas(Settings(), preview=True); canvas.resize(640, 400)
        canvas.fixed_time = 1
        first = canvas.grab().toImage()
        canvas.fixed_time = 4
        second = canvas.grab().toImage()
        self.assertNotEqual(first, second)
        canvas.close()

    def test_background_and_intro_envelopes(self):
        self.assertEqual(envelope(0, 3.5, .18, True), (.96, True))
        opacity, active = envelope(5, 3.5, .18, True)
        self.assertAlmostEqual(opacity, .18); self.assertTrue(active)
        self.assertEqual(envelope(5, 3.5, .18, False), (0, False))
        self.assertEqual(envelope(5, 3.5, 0, True), (0, False))

    def test_hidden_widget_stops_frame_timer(self):
        canvas = Canvas(Settings(), preview=True)
        canvas.show(); APP.processEvents()
        self.assertTrue(canvas.timer.isActive())
        canvas.hide(); APP.processEvents()
        self.assertFalse(canvas.timer.isActive())
        canvas.close()


class Lifecycle(unittest.TestCase):
    def test_focus_replay_pause_and_shutdown(self):
        with tempfile.TemporaryDirectory() as temporary:
            provider = FakeProvider()
            controller = Controller(APP, Store(Path(temporary) / 'settings.json'), Settings(), provider)
            controller.poll.stop()
            try:
                controller.refresh()
                self.assertTrue(controller.canvas.isVisible()); self.assertTrue(controller.canvas.intro)
                provider.window = Window('2', 'Firefox', 0, 0, 800, 600)
                controller.refresh(); self.assertFalse(controller.canvas.isVisible())
                provider.window = Window('1:20', 'Claude.exe', 80, 60, 700, 500)
                controller.refresh()
                self.assertTrue(controller.canvas.isVisible()); self.assertFalse(controller.canvas.intro)
                controller.pause(True); self.assertFalse(controller.canvas.isVisible())
                controller.pause(False); controller.replay(); self.assertTrue(controller.canvas.intro)
                provider.window = None; controller.refresh(); self.assertFalse(controller.canvas.isVisible())
            finally:
                controller.close()
            self.assertTrue(provider.closed)
            self.assertFalse(controller.canvas.timer.isActive())

    def test_intro_only_does_not_reappear_after_expiry(self):
        with tempfile.TemporaryDirectory() as temporary:
            controller = Controller(APP, Store(Path(temporary) / 'settings.json'), Settings(background=False), FakeProvider())
            controller.poll.stop()
            try:
                controller.refresh(); controller.canvas.started -= 10; controller.canvas.advance()
                self.assertFalse(controller.canvas.isVisible())
                controller.refresh(); self.assertFalse(controller.canvas.isVisible())
            finally:
                controller.close()

    def test_settings_dialog_roundtrip(self):
        settings = Settings(theme='orbit', match='firefox', duration=5, opacity=.4, fps=24, background=False)
        dialog = Preferences(settings)
        self.assertEqual(dialog.result_settings(), settings)
        dialog.close()
