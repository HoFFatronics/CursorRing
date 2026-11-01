import json
from pathlib import Path
import struct
import tempfile
import unittest

from PIL import Image
from cursor_ring import ConfigurationError, create_cursor, load_settings, parse_hex_color


class ColorConfigurationTests(unittest.TestCase):
    def test_default_has_three_presets(self):
        default, colors, hotkey, duration = load_settings(Path(__file__).resolve().parents[1] / "config.json")
        self.assertEqual(default, "yellow")
        self.assertEqual(len(colors), 3)
        self.assertEqual(colors["yellow"], "#FFE500")
        self.assertEqual(hotkey, "ctrl+alt+r")
        self.assertEqual(duration, 2.4)

    def test_parse_hex_color(self):
        self.assertEqual(parse_hex_color("#FFE500"), (255, 229, 0, 255))
        with self.assertRaises(ConfigurationError):
            parse_hex_color("green")

    def test_missing_default_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps({"default_color": "purple", "colors": {
                "yellow": "#FFE500", "white": "#FFFFFF", "black": "#111111"}}))
            with self.assertRaises(ConfigurationError):
                load_settings(path)

    def test_cursor_file_is_64px_with_center_hotspot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ring.cur"
            create_cursor(path, parse_hex_color("#FFE500"))
            data = path.read_bytes()
            reserved, kind, count = struct.unpack_from("<HHH", data)
            self.assertEqual((reserved, kind, count), (0, 2, 1))
            width, height, count_colors, reserved, xhot, yhot, size, offset = struct.unpack_from("<BBBBHHII", data, 6)
            self.assertEqual((width, height, xhot, yhot, offset), (96, 96, 48, 48, 22))
            self.assertEqual(len(data), 22 + size)
            with Image.open(path) as icon:
                self.assertEqual(icon.size, (96, 96))


class AnimationTests(unittest.TestCase):
    def test_hotkey(self):
        modifiers, key = parse_hotkey("ctrl+alt+r")
        self.assertEqual(key, ord("R"))
        self.assertTrue(modifiers & 0x4000)
        for invalid in ("r", "ctrl+ctrl+r", "win+r", "ctrl+f12"):
            with self.assertRaises(ConfigurationError):
                parse_hotkey(invalid)

    def test_pulse_and_blink(self):
        self.assertEqual(animation_frame(0, 2.4), (18, True))
        self.assertEqual(animation_frame(0.2, 2.4), (28, False))
        self.assertEqual(animation_frame(0.4, 2.4), (36, True))
        self.assertIsNone(animation_frame(2.4, 2.4))

    def test_prepared_frames(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = prepare_frames(Path(directory), parse_hex_color("#FFE500"))
            self.assertIn("normal", paths)
            self.assertIn("hidden", paths)
            self.assertIn(36, paths)
            self.assertTrue(all(path.exists() for path in paths.values()))


if __name__ == "__main__":
    unittest.main()
