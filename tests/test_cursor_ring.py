import json
from pathlib import Path
import struct
import tempfile
import unittest

from PIL import Image
from cursor_ring import ConfigurationError, create_cursor, load_settings, parse_hex_color


class ColorConfigurationTests(unittest.TestCase):
    def test_default_has_three_presets(self):
        default, colors = load_settings(Path(__file__).resolve().parents[1] / "config.json")
        self.assertEqual(default, "yellow")
        self.assertEqual(len(colors), 3)
        self.assertEqual(colors["yellow"], "#FFE500")

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
            self.assertEqual((width, height, xhot, yhot, offset), (64, 64, 32, 32, 22))
            self.assertEqual(len(data), 22 + size)
            with Image.open(path) as icon:
                self.assertEqual(icon.size, (64, 64))


if __name__ == "__main__":
    unittest.main()
