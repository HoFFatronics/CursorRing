"""Show a high-contrast, configurable cursor ring on Windows.

Usage:
    python cursor_ring.py
    python cursor_ring.py --color white
    python cursor_ring.py --list-colors
    python cursor_ring.py --restore
"""

import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import re
import struct
import sys
import tempfile
import time

from PIL import Image, ImageDraw

SIZE = 64
CENTER = SIZE // 2
RADIUS = 23
IMAGE_CURSOR = 2
LR_LOADFROMFILE = 0x0010
SPI_SETCURSORS = 0x0057
OCR_NORMAL = 32512
OCR_HAND = 32649
CONFIG_PATH = Path(__file__).with_name("config.json")


class ConfigurationError(ValueError):
    """Raised for malformed or inconsistent color settings."""


def parse_hex_color(value):
    if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        raise ConfigurationError("Färger ska anges som #RRGGBB, exempelvis #FFE500.")
    return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5)) + (255,)


def load_settings(path):
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"Kunde inte läsa {path}: {exc}") from exc
    if not isinstance(settings, dict):
        raise ConfigurationError("Konfigurationen måste vara ett JSON-objekt.")
    colors = settings.get("colors")
    if not isinstance(colors, dict) or len(colors) != 3:
        raise ConfigurationError("Konfigurationen ska innehålla exakt tre färgprofiler.")
    if any(not isinstance(name, str) or not name.strip() for name in colors):
        raise ConfigurationError("Varje färgprofil måste ha ett namn.")
    for name, hex_color in colors.items():
        try:
            parse_hex_color(hex_color)
        except ConfigurationError as exc:
            raise ConfigurationError(f"Ogiltig färg för {name}: {exc}") from exc
    selected = settings.get("default_color")
    if not isinstance(selected, str) or selected not in colors:
        raise ConfigurationError("default_color måste vara en av färgprofilerna.")
    return selected, colors


def create_cursor(path, color):
    """Build a 32-bit .cur file with a black/white bordered colored ring."""
    scale = 4
    canvas = Image.new("RGBA", (SIZE * scale, SIZE * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    center = CENTER * scale

    # From outside to inside: black, white, chosen color. The extra
    # contours preserve visibility on bright AND dark regions of a map.
    for radius, width, rgba in (
        (RADIUS + 3, 11, (0, 0, 0, 255)),
        (RADIUS + 1, 8, (255, 255, 255, 255)),
        (RADIUS, 5, color),
    ):
        distance = radius * scale
        bounds = (center - distance, center - distance,
                  center + distance, center + distance)
        draw.ellipse(bounds, outline=rgba, width=width * scale)

    # Arrow tip is the hotspot, centered within the ring.
    outline = [(32, 32), (33, 53), (39, 47), (45, 57),
               (50, 54), (44, 44), (53, 43)]
    points = [(x * scale, y * scale) for x, y in outline]
    draw.polygon(points, fill="white")
    draw.line(points + [points[0]], fill="black", width=2 * scale, joint="curve")
    image = canvas.resize((SIZE, SIZE), Image.Resampling.LANCZOS)

    xor = b"".join(image.crop((0, y, SIZE, y + 1)).tobytes("raw", "BGRA")
                   for y in range(SIZE - 1, -1, -1))
    alpha = image.getchannel("A")
    stride = ((SIZE + 31) // 32) * 4
    mask = bytearray()
    for y in range(SIZE - 1, -1, -1):
        row = bytearray(stride)
        for x in range(SIZE):
            if alpha.getpixel((x, y)) == 0:
                row[x // 8] |= 0x80 >> (x % 8)
        mask.extend(row)

    dib_header = struct.pack("<IiiHHIIiiII", 40, SIZE, SIZE * 2,
                             1, 32, 0, len(xor), 0, 0, 0, 0)
    bitmap = dib_header + xor + mask
    directory = struct.pack("<HHH", 0, 2, 1)
    # The hotspot is at the ring center for accurate clicks.
    entry = struct.pack("<BBBBHHII", SIZE, SIZE, 0, 0,
                        CENTER, CENTER, len(bitmap), 22)
    path.write_bytes(directory + entry + bitmap)


def windows_api():
    api = ctypes.WinDLL("user32", use_last_error=True)
    api.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR,
                               wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT]
    api.LoadImageW.restype = wintypes.HANDLE
    api.SetSystemCursor.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    api.SetSystemCursor.restype = wintypes.BOOL
    api.SystemParametersInfoW.argtypes = [wintypes.UINT, wintypes.UINT,
                                          ctypes.c_void_p, wintypes.UINT]
    api.SystemParametersInfoW.restype = wintypes.BOOL
    return api


def restore(api):
    if not api.SystemParametersInfoW(SPI_SETCURSORS, 0, None, 0):
        raise ctypes.WinError(ctypes.get_last_error())


def enable(api, path):
    for cursor_id in (OCR_NORMAL, OCR_HAND):
        handle = api.LoadImageW(None, str(path), IMAGE_CURSOR,
                                SIZE, SIZE, LR_LOADFROMFILE)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        # SetSystemCursor assumes ownership of a successfully passed handle.
        if not api.SetSystemCursor(handle, cursor_id):
            raise ctypes.WinError(ctypes.get_last_error())


def main(argv=None):
    parser = argparse.ArgumentParser(description="Visa en tydlig ring runt muspekaren i Windows.")
    parser.add_argument("--color", help="Namn på färgprofil, t.ex. yellow, white eller black.")
    parser.add_argument("--config", type=Path, default=CONFIG_PATH,
                        help="Sökväg till konfigurationen (standard: config.json bredvid skriptet).")
    parser.add_argument("--list-colors", action="store_true", help="Visa färgprofilerna och avsluta.")
    parser.add_argument("--restore", action="store_true", help="Återställ Windows-muspekare.")
    args = parser.parse_args(argv)

    if args.restore:
        if os.name != "nt":
            parser.error("--restore fungerar bara i Windows.")
        restore(windows_api())
        print("Windows-muspekaren är återställd.")
        return

    try:
        default, colors = load_settings(args.config)
    except ConfigurationError as exc:
        parser.error(str(exc))

    if args.list_colors:
        for name, hex_color in colors.items():
            label = " (standard)" if name == default else ""
            print(f"{name}: {hex_color}{label}")
        return

    chosen = args.color or default
    if chosen not in colors:
        parser.error(f"Okänd färg '{chosen}'. Välj någon av: {', '.join(colors)}")
    if os.name != "nt":
        parser.error("Programmet fungerar bara i Windows.")

    api = windows_api()
    try:
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "cursor_ring.cur"
            create_cursor(path, parse_hex_color(colors[chosen]))
            enable(api, path)
            print(f"CursorRing aktiv: {chosen} ({colors[chosen]}). Avsluta med Ctrl+C.")
            while True:
                time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        restore(api)
        print("Windows-muspekaren är återställd.")


if __name__ == "__main__":
    main()
