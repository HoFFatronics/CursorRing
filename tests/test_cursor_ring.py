import json
from pathlib import Path
import struct
import tempfile
import unittest

from PIL import Image
from cursor_ring import (
    ConfigurationError,
    adjust_ring_geometry,
    animation_frame,
    create_cursor,
    ensure_config,
    load_settings,
    parse_hex_color,
    parse_hotkey,
    profile_hotkeys,
    prepare_frames,
    save_profile_colors,
    save_ring_geometry,
)


class ColorConfigurationTests(unittest.TestCase):
    def test_config_is_created_once_and_profile_colors_are_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            ensure_config(path)
            self.assertTrue(path.exists())
            initial = json.loads(path.read_text(encoding="utf-8"))
            colors = {"yellow": "#FFCC00", "white": "#EEEEEE", "black": "#222222"}
            save_profile_colors(path, colors)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["colors"], colors)
            self.assertEqual(saved["hotkey"], initial["hotkey"])
            self.assertEqual(saved["default_color"], initial["default_color"])
            save_ring_geometry(path, 25, 2)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual((saved["ring_radius"], saved["ring_thickness"]), (25, 2))
            self.assertEqual(saved["colors"], colors)
            ensure_config(path)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), saved)

    def test_default_has_three_presets(self):
        default, colors, hotkey, duration, radius, thickness = load_settings(Path(__file__).resolve().parents[1] / "config.json")
        self.assertEqual(default, "yellow")
        self.assertEqual(len(colors), 3)
        self.assertEqual(colors["yellow"], "#FFE500")
        self.assertEqual(hotkey, "ctrl+alt+r")
        self.assertEqual(duration, 2.4)
        self.assertEqual((radius, thickness), (23, 1))

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

    def test_settings_and_profile_hotkeys_cannot_be_used_for_animation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad-hotkey.json"
            settings = {
                "default_color": "yellow",
                "colors": {"yellow": "#FFE500", "white": "#FFFFFF", "black": "#111111"},
            }
            for hotkey in ("ctrl+alt+0", "ctrl+alt+1"):
                with self.subTest(hotkey=hotkey):
                    path.write_text(json.dumps({**settings, "hotkey": hotkey}))
                    with self.assertRaises(ConfigurationError):
                        load_settings(path)

    def test_cursor_file_is_96px_with_center_hotspot(self):
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

    def test_profile_hotkeys_cover_normal_and_three_color_profiles(self):
        bindings = profile_hotkeys()
        self.assertEqual([binding[3] for binding in bindings], [ord("1"), ord("2"), ord("3"), ord("4")])
        self.assertEqual([binding[1] for binding in bindings], [0, 1, 2, 3])
        self.assertEqual(len({binding[0] for binding in bindings}), 4)

    def test_wheel_adjustments_clamp_diameter_and_thickness(self):
        self.assertEqual(adjust_ring_geometry(23, 1, 120, adjust_diameter=True), (25, 1))
        self.assertEqual(adjust_ring_geometry(23, 1, -120, adjust_diameter=True), (21, 1))
        self.assertEqual(adjust_ring_geometry(31, 1, 120, adjust_diameter=True), (31, 1))
        self.assertEqual(adjust_ring_geometry(15, 1, -120, adjust_diameter=True), (15, 1))
        self.assertEqual(adjust_ring_geometry(23, 1, 120, adjust_diameter=False), (23, 2))
        self.assertEqual(adjust_ring_geometry(23, 3, 120, adjust_diameter=False), (23, 3))

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
