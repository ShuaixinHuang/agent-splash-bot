"""Settings for this application; no target application's files are read or changed."""
from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import shutil
import sys
import tempfile
import uuid

THEMES = ('aurora', 'ember', 'orbit')


@dataclass
class Settings:
    match: str = 'claude,chatgpt,codex,antigravity'
    theme: str = 'aurora'
    duration: float = 3.5
    opacity: float = 0.18
    fps: int = 30
    background: bool = True

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValueError('Settings must be a JSON object')
        defaults = cls()
        def number(key, lower, upper):
            value = data.get(key, getattr(defaults, key))
            try:
                valid = not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)
            except OverflowError:
                valid = False
            if not valid:
                return getattr(defaults, key)
            return max(lower, min(upper, value))
        theme = data.get('theme')
        match = data.get('match')
        background = data.get('background')
        return cls(
            match=match.strip() if isinstance(match, str) and match.strip() else defaults.match,
            theme=theme if theme in THEMES else defaults.theme,
            duration=float(number('duration', 0.5, 20)),
            opacity=float(number('opacity', 0, 0.6)),
            fps=int(number('fps', 10, 60)),
            background=background if isinstance(background, bool) else defaults.background,
        )


def default_path():
    if sys.platform == 'win32':
        base = Path(os.environ.get('APPDATA', Path.home() / 'AppData/Roaming'))
    elif sys.platform == 'darwin':
        base = Path.home() / 'Library/Application Support'
    else:
        base = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
    return base / 'aurora-boot/config.json'


class Store:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else default_path()
        self.backup = None

    def load(self):
        if not self.path.exists():
            return Settings()
        # I/O errors are not JSON corruption and must not trigger a reset.
        raw = self.path.read_bytes()
        try:
            data = json.loads(raw.decode('utf-8'))
            return Settings.from_dict(data)
        except (ValueError, TypeError, OverflowError):
            self.backup = self.path.with_name(self.path.name + '.invalid-' + uuid.uuid4().hex)
            shutil.copy2(self.path, self.backup)
            settings = Settings()
            self.save(settings)
            return settings

    def save(self, settings):
        safe = Settings.from_dict(asdict(settings))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(prefix='.aurora-', suffix='.tmp', dir=self.path.parent)
        try:
            with os.fdopen(handle, 'w', encoding='utf-8') as stream:
                json.dump(asdict(safe), stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return safe
