"""Tray application and command-line entry points."""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys
from PySide6.QtCore import QRect, QTimer, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                             QDoubleSpinBox, QFormLayout, QLabel, QLineEdit, QMenu, QMessageBox,
                             QSpinBox, QSystemTrayIcon)
from . import __version__
from .animation import Canvas
from .config import Settings, Store, THEMES
from .windows import make_provider


def icon():
    image = QPixmap(64, 64); image.fill(QColor('#06131e'))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QColor('#65efce'))
    painter.drawEllipse(9, 21, 46, 22)
    painter.drawEllipse(21, 9, 22, 46)
    painter.setBrush(QColor('#c6fff3')); painter.drawEllipse(28, 28, 8, 8)
    painter.end()
    return QIcon(image)


def logical_geometry(window, screens):
    # Win32 returns physical client coordinates; map relative to its named monitor.
    if window.monitor:
        for screen in screens:
            if screen.name().casefold() == window.monitor.casefold():
                ratio = screen.devicePixelRatio()
                origin = screen.geometry()
                return QRect(round(origin.x() + (window.x - window.monitor_x) / ratio),
                             round(origin.y() + (window.y - window.monitor_y) / ratio),
                             round(window.width / ratio), round(window.height / ratio))
    # Quartz is already in points. X11 uses root coordinates at the normal scale.
    if sys.platform.startswith('linux') and screens:
        ratio = screens[0].devicePixelRatio()
        return QRect(round(window.x / ratio), round(window.y / ratio), round(window.width / ratio), round(window.height / ratio))
    return QRect(window.x, window.y, window.width, window.height)


class Preferences(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Aurora Boot · 设置')
        self.setMinimumWidth(410)
        form = QFormLayout(self)
        self.match = QLineEdit(settings.match)
        self.match.setPlaceholderText('claude,chatgpt,codex,antigravity')
        form.addRow('应用名称包含（逗号分隔）', self.match)
        self.theme = QComboBox(); self.theme.addItems(THEMES); self.theme.setCurrentText(settings.theme)
        form.addRow('主题', self.theme)
        self.duration = QDoubleSpinBox(); self.duration.setRange(.5, 20); self.duration.setSingleStep(.5); self.duration.setValue(settings.duration)
        form.addRow('开屏时长（秒）', self.duration)
        self.opacity = QDoubleSpinBox(); self.opacity.setRange(0, .6); self.opacity.setSingleStep(.02); self.opacity.setValue(settings.opacity)
        form.addRow('背景不透明度', self.opacity)
        self.fps = QSpinBox(); self.fps.setRange(10, 60); self.fps.setValue(settings.fps)
        form.addRow('帧率上限', self.fps)
        self.background = QCheckBox('开屏后保留动态背景'); self.background.setChecked(settings.background)
        form.addRow(self.background)
        help_text = QLabel('仅在匹配的应用位于前台时显示。\n预览窗口按 Esc 关闭；主程序通过托盘菜单退出。')
        help_text.setWordWrap(True); form.addRow(help_text)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); form.addRow(buttons)

    def result_settings(self):
        return Settings.from_dict(dict(match=self.match.text(), theme=self.theme.currentText(), duration=self.duration.value(),
                                       opacity=self.opacity.value(), fps=self.fps.value(), background=self.background.isChecked()))


class Controller:
    def __init__(self, app, store, settings, provider):
        self.app, self.store, self.settings, self.provider = app, store, settings, provider
        self.canvas = Canvas(settings)
        self.previews = []
        self.seen = {}  # bounded insertion-ordered set of windows shown in this session
        self.active = None
        self.paused = False
        self.dialog = None
        self.tray = QSystemTrayIcon(icon(), app)
        self.tray.setToolTip('Aurora Boot')
        self.menu = QMenu()
        for label, callback in [('预览动画', self.preview), ('重播当前窗口', self.replay), ('设置…', self.preferences)]:
            action = self.menu.addAction(label); action.triggered.connect(callback)
        self.pause_action = QAction('暂停', self.menu); self.pause_action.setCheckable(True)
        self.pause_action.toggled.connect(self.pause)
        self.menu.addAction(self.pause_action)
        self.menu.addSeparator()
        self.menu.addAction('退出', app.quit)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self.tray_clicked)
        self.tray.show()
        self.poll = QTimer(app); self.poll.setInterval(300); self.poll.timeout.connect(self.refresh); self.poll.start()
        self.app.aboutToQuit.connect(self.close)

    def tray_clicked(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.preferences()

    def close(self):
        self.poll.stop(); self.canvas.close(); self.tray.hide(); self.provider.close()
        for preview in self.previews:
            preview.close()

    def pause(self, value):
        self.paused = value
        if value:
            self.canvas.hide()

    def refresh(self):
        if self.paused or self.dialog is not None:
            self.canvas.hide(); return
        try:
            window = self.provider.current()
        except Exception as error:
            # Stop repeated failing native requests, but leave settings and exit available.
            self.pause_action.setChecked(True)
            self.tray.showMessage('Aurora Boot 已暂停', str(error), QSystemTrayIcon.MessageIcon.Warning)
            return
        if window is None or not window.matches(self.settings.match):
            self.canvas.hide(); self.active = None; return
        self.canvas.setGeometry(logical_geometry(window, self.app.screens()))
        if window.key != self.active:
            self.active = window.key
            first = window.key not in self.seen
            self.seen[window.key] = True
            if len(self.seen) > 128:
                del self.seen[next(iter(self.seen))]
            self.canvas.restart(intro=first)
        if self.canvas.intro:
            should_show = self.canvas.elapsed() < self.settings.duration or (self.settings.background and self.settings.opacity > 0)
        else:
            should_show = self.settings.background and self.settings.opacity > 0
        if should_show:
            self.canvas.show()
        else:
            self.canvas.hide()

    def replay(self):
        self.seen.clear(); self.active = None
        self.refresh()

    def preview(self):
        preview = Canvas(self.settings, preview=True)
        preview.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.previews.append(preview)
        preview.destroyed.connect(lambda: self.previews.remove(preview) if preview in self.previews else None)
        preview.show()

    def preferences(self):
        if self.dialog is not None:
            self.dialog.raise_(); self.dialog.activateWindow(); return
        self.canvas.hide()
        self.dialog = Preferences(self.settings)
        try:
            if self.dialog.exec() == QDialog.DialogCode.Accepted:
                try:
                    self.settings = self.store.save(self.dialog.result_settings())
                except OSError as error:
                    QMessageBox.warning(self.dialog, '无法保存设置', str(error)); return
                self.canvas.settings = self.settings
                self.canvas.timer.setInterval(round(1000 / self.settings.fps))
                self.replay()
        finally:
            self.dialog.deleteLater(); self.dialog = None


def parser():
    result = argparse.ArgumentParser(description='Aurora Boot — original procedural desktop animations')
    result.add_argument('--version', action='version', version=__version__)
    result.add_argument('--demo', action='store_true', help='open an independent preview window; no window monitoring')
    result.add_argument('--theme', choices=THEMES)
    result.add_argument('--match', help='comma-separated application identity substrings')
    result.add_argument('--config', type=Path, help='use a separate settings file')
    result.add_argument('--render', type=Path, help='export one original procedural frame as PNG')
    result.add_argument('--time', type=float, default=2.0, help='animation time for --render')
    result.add_argument('--smoke-test', action='store_true', help=argparse.SUPPRESS)
    result.add_argument('--diagnose', action='store_true', help='print platform and display information without starting Qt')
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    if args.diagnose:
        print(json.dumps(dict(platform=sys.platform, display=os.environ.get('DISPLAY'), session=os.environ.get('XDG_SESSION_TYPE'),
                              wayland=bool(os.environ.get('WAYLAND_DISPLAY')), version=__version__), indent=2))
        return 0
    if args.render:
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setApplicationName('Aurora Boot'); app.setOrganizationName('Aurora Boot')
    app.setWindowIcon(icon())
    store = Store(args.config)
    try:
        settings = store.load()
    except OSError as error:
        print('Cannot read or safely recover settings: ' + str(error), file=sys.stderr); return 2
    if args.theme:
        settings.theme = args.theme
    if args.match:
        settings.match = args.match
    if args.render:
        if not __import__('math').isfinite(args.time):
            print('--time must be finite', file=sys.stderr); return 2
        canvas = Canvas(settings, preview=True); canvas.fixed_time = max(0, args.time); canvas.resize(1280, 800)
        args.render.parent.mkdir(parents=True, exist_ok=True)
        if not canvas.grab().save(str(args.render), 'PNG'):
            print('Could not save frame: ' + str(args.render), file=sys.stderr); return 2
        return 0
    if args.demo or args.smoke_test:
        canvas = Canvas(settings, preview=True); canvas.show()
        if args.smoke_test:
            QTimer.singleShot(500, canvas.close)
        return app.exec()
    if not QSystemTrayIcon.isSystemTrayAvailable():
        print('No system tray is available. Use --demo, or enable your desktop\'s system-tray extension.', file=sys.stderr)
        return 2
    try:
        provider = make_provider()
    except Exception as error:
        print(str(error), file=sys.stderr); return 2
    # Prevent multiple instances from fighting over the same tray and overlay.
    from PySide6.QtCore import QLockFile
    lock = QLockFile(str(store.path.with_suffix('.lock')))
    lock.setStaleLockTime(0)  # Tray instances are intentionally long-lived.
    store.path.parent.mkdir(parents=True, exist_ok=True)
    if not lock.tryLock(0):
        provider.close(); print('Aurora Boot is already running for this configuration.', file=sys.stderr); return 2
    app.setQuitOnLastWindowClosed(False)
    controller = Controller(app, store, settings, provider)
    if store.backup:
        controller.tray.showMessage('已恢复默认设置', '原文件已备份到 ' + str(store.backup))
    try:
        return app.exec()
    finally:
        lock.unlock()


if __name__ == '__main__':
    raise SystemExit(main())
