"""Draw original ribbons, orbital paths and stars entirely from equations."""
import math
import random
import time
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

PALETTES = {
    'aurora': ('#06131e', '#65efce', '#7779ff', '#c6fff3'),
    'ember': ('#1b101b', '#ffbc73', '#f06797', '#fff0d7'),
    'orbit': ('#0a102a', '#85bcff', '#c09cff', '#e4efff'),
}


def envelope(elapsed, duration, background_opacity, background):
    """Return window opacity and whether the animation still has visible work."""
    fade = min(0.8, duration / 2)
    target = background_opacity if background else 0.0
    blend = max(0.0, min(1.0, (elapsed - duration + fade) / fade))
    alpha = 0.96 * (1 - blend) + target * blend
    return alpha, elapsed < duration or (background and target > 0)


class Canvas(QWidget):
    def __init__(self, settings, preview=False):
        flags = Qt.WindowType.Window if preview else (
            Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowTransparentForInput |
            Qt.WindowType.WindowDoesNotAcceptFocus)
        super().__init__(None, flags)
        self.settings = settings
        self.preview = preview
        self.started = time.monotonic()
        self.fixed_time = None
        self.intro = True
        self.setWindowTitle('Aurora Boot — procedural preview')
        self.resize(1100, 700)
        if not preview:
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.advance)
        rng = random.Random(7021)
        self.stars = [(rng.random(), rng.random(), rng.uniform(0.6, 1.8), rng.random() * math.tau) for _ in range(62)]

    def elapsed(self):
        return self.fixed_time if self.fixed_time is not None else time.monotonic() - self.started

    def restart(self, intro=True):
        self.started = time.monotonic()
        self.intro = intro
        self.setWindowOpacity(0.96 if intro else self.settings.opacity)
        self.update()

    def showEvent(self, event):
        if self.fixed_time is None:
            self.timer.start(round(1000 / self.settings.fps))
        super().showEvent(event)

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def keyPressEvent(self, event):
        if self.preview and event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def advance(self):
        if not self.preview:
            if self.intro:
                opacity, visible = envelope(self.elapsed(), self.settings.duration, self.settings.opacity, self.settings.background)
            else:
                opacity, visible = self.settings.opacity, self.settings.background and self.settings.opacity > 0
            if not visible:
                self.hide()
                return
            self.setWindowOpacity(opacity)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.draw(painter, self.width(), self.height(), self.elapsed())
        painter.end()

    def draw(self, p, width, height, elapsed):
        base, first, second, ink = PALETTES[self.settings.theme]
        p.fillRect(0, 0, width, height, QColor(base))
        scale = min(width / 1100, height / 700)
        t = elapsed
        glow = QRadialGradient(QPointF(width * .53, height * .57), width * .64)
        tint = QColor(second); tint.setAlpha(50)
        glow.setColorAt(0, tint); glow.setColorAt(1, QColor(0, 0, 0, 0))
        p.fillRect(0, 0, width, height, glow)
        # Ribbons are sampled sine curves, rather than images or prerecorded footage.
        for band in range(7):
            path = QPainterPath()
            for step in range(121):
                x = width * step / 120
                phase = step / 120 * 5.7 + t * .32 + band * .18
                y = height * (.56 + .10 * math.sin(phase) + .055 * math.sin(phase * 1.7 - t * .18)) + band * 8 * scale
                point = QPointF(x, y)
                if step == 0:
                    path.moveTo(point)
                else:
                    path.lineTo(point)
            gradient = QLinearGradient(0, 0, width, height)
            a, b = QColor(first), QColor(second)
            a.setAlpha(65 + band * 12); b.setAlpha(100)
            gradient.setColorAt(0, a); gradient.setColorAt(1, b)
            p.setPen(QPen(gradient, (1.0 + band * .27) * scale))
            p.drawPath(path)
        p.setPen(Qt.PenStyle.NoPen)
        for sx, sy, radius, phase in self.stars:
            color = QColor(ink)
            color.setAlpha(int(55 + 125 * (.5 + .5 * math.sin(t * .65 + phase))))
            p.setBrush(color)
            p.drawEllipse(QPointF(sx * width, sy * height), radius * scale, radius * scale)
        cx, cy = width * .5, height * .32
        radius = 43 * scale
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(first), 1.2 * scale))
        for orbit in range(3):
            p.save()
            p.translate(cx, cy)
            p.rotate(orbit * 60 + t * 7)
            p.drawEllipse(QRectF(-radius, -radius * .38, radius * 2, radius * .76))
            p.restore()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(ink))
        p.drawEllipse(QPointF(cx, cy), 3 * scale, 3 * scale)
        title_alpha = 1.0 if self.preview else max(0, min(1, (self.settings.duration - t) / .7)) if self.intro else 0
        if title_alpha > 0:
            p.save()
            p.setOpacity(title_alpha)
            title = QFont('Sans Serif', max(12, round(31 * scale)))
            title.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 8 * scale)
            p.setFont(title); p.setPen(QColor(ink))
            p.drawText(QRectF(0, height * .66, width, height * .1), Qt.AlignmentFlag.AlignCenter, 'AURORA BOOT')
            p.setFont(QFont('Sans Serif', max(9, round(12 * scale))))
            muted = QColor(ink); muted.setAlpha(150); p.setPen(muted)
            p.drawText(QRectF(0, height * .76, width, height * .07), Qt.AlignmentFlag.AlignCenter, 'Your workspace, in motion.')
            p.setPen(Qt.PenStyle.NoPen)
            track = QRectF(cx - 90 * scale, height * .87, 180 * scale, 2 * scale)
            dim = QColor(first); dim.setAlpha(35); p.setBrush(dim); p.drawRoundedRect(track, scale, scale)
            progress = min(1, max(0, t / self.settings.duration))
            p.setBrush(QColor(first)); p.drawRoundedRect(QRectF(track.x(), track.y(), track.width() * progress, track.height()), scale, scale)
            p.restore()
        p.setPen(QColor(ink)); p.setOpacity(.28)
        p.setFont(QFont('Monospace', max(8, round(9 * scale))))
        p.drawText(QRectF(24 * scale, 20 * scale, width - 48 * scale, 30 * scale), Qt.AlignmentFlag.AlignLeft, 'A / B    •    ' + self.settings.theme.upper())
        p.setOpacity(1)
