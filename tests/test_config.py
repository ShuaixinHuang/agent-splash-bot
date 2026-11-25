from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from aurora_boot.config import Settings, Store


class Configuration(unittest.TestCase):
    def test_limits_and_types(self):
        settings = Settings.from_dict(dict(duration=-4, opacity=7, fps=400, background='false', theme='missing', match='  ', extra='ignored'))
        self.assertEqual((settings.duration, settings.opacity, settings.fps), (.5, .6, 60))
        self.assertEqual(settings.theme, 'aurora'); self.assertTrue(settings.background)
        self.assertEqual(settings.match, Settings().match)
        for value in (float('nan'), float('inf'), '1', True, None, 10**500):
            self.assertEqual(Settings.from_dict(dict(duration=value)).duration, Settings().duration)

    def test_roundtrip_and_unicode(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = Store(Path(temporary) / 'nested/settings.json')
            self.assertEqual(store.load(), Settings())
            self.assertFalse(store.path.exists())
            expected = Settings(match='客户端 🌙,firefox', theme='ember', opacity=.4)
            store.save(expected)
            self.assertEqual(store.load(), expected)
            self.assertIn('客户端', store.path.read_text(encoding='utf-8'))
            self.assertEqual(list(store.path.parent.glob('*.tmp')), [])

    def test_corruption_preserves_bytes(self):
        for raw in (b'{broken', b'[]', b'null', b'\xff\xfe\xff'):
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as temporary:
                store = Store(Path(temporary) / 'config.json'); store.path.write_bytes(raw)
                self.assertEqual(store.load(), Settings())
                self.assertEqual(store.backup.read_bytes(), raw)
                self.assertEqual(json.loads(store.path.read_text()), asdict(Settings()))

    def test_backup_failure_never_overwrites(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = Store(Path(temporary) / 'config.json'); store.path.write_bytes(b'broken')
            with patch('aurora_boot.config.shutil.copy2', side_effect=PermissionError('denied')):
                with self.assertRaises(PermissionError):
                    store.load()
            self.assertEqual(store.path.read_bytes(), b'broken')

    def test_atomic_replace_failure_keeps_previous_settings(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = Store(Path(temporary) / 'config.json'); store.save(Settings(theme='orbit'))
            old = store.path.read_bytes()
            with patch('aurora_boot.config.os.replace', side_effect=OSError('disk full')):
                with self.assertRaises(OSError):
                    store.save(Settings(theme='ember'))
            self.assertEqual(store.path.read_bytes(), old)
            self.assertEqual(list(store.path.parent.glob('*.tmp')), [])
