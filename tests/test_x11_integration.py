"""Run only on a disposable X server: this test owns the root active-window property."""
import os
import unittest


@unittest.skipUnless(os.environ.get('AURORA_X11_INTEGRATION') == '1', 'requires a disposable Xvfb display')
class X11Integration(unittest.TestCase):
    def test_native_geometry_focus_and_click_through(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication, QWidget
        from Xlib import X, display
        from Xlib.ext import xtest
        from aurora_boot.animation import Canvas
        from aurora_boot.config import Settings
        from aurora_boot.windows import X11
        app = QApplication.instance() or QApplication([])
        class Target(QWidget):
            def __init__(self):
                super().__init__(); self.clicks = 0
            def mousePressEvent(self, event):
                self.clicks += 1
        target = Target(); target.setGeometry(100, 120, 700, 500); target.show()
        QTest.qWait(100)
        connection = display.Display(); root = connection.screen().root
        active = connection.intern_atom('_NET_ACTIVE_WINDOW')
        native = connection.create_resource_object('window', int(target.winId()))
        native.set_wm_class('aurora-fixture', 'AuroraFixture')
        root.change_property(active, connection.intern_atom('WINDOW'), 32, [native.id])
        connection.sync()
        provider = X11()
        canvas = Canvas(Settings())
        try:
            window = provider.current()
            self.assertIsNotNone(window)
            self.assertTrue(window.matches('aurorafixture'))
            self.assertEqual((window.x, window.y, window.width, window.height), (100, 120, 700, 500))
            canvas.setGeometry(100, 120, 700, 500); canvas.show()
            QTest.qWait(150)
            xtest.fake_input(connection, X.MotionNotify, x=350, y=350)
            xtest.fake_input(connection, X.ButtonPress, detail=1)
            xtest.fake_input(connection, X.ButtonRelease, detail=1)
            connection.sync(); QTest.qWait(100)
            self.assertEqual(target.clicks, 1, 'The native overlay intercepted a click')
            target.hide(); QTest.qWait(50)
            self.assertIsNone(provider.current())
        finally:
            canvas.close(); target.close(); provider.close()
            root.delete_property(active); connection.sync(); connection.close()


if __name__ == '__main__':
    unittest.main()
