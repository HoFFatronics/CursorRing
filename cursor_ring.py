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
import math
import os
from pathlib import Path
import re
import struct
import sys
import tempfile
import time

from PIL import Image, ImageDraw

SIZE = 96
CENTER = SIZE // 2
RADIUS = 23
MIN_PULSE_RADIUS = 18
MAX_PULSE_RADIUS = 36
PULSE_COUNT = 3
BLINK_FREQUENCY = 2.5
FRAME_INTERVAL = 1 / 15
IMAGE_CURSOR = 2
LR_LOADFROMFILE = 0x0010
SPI_SETCURSORS = 0x0057
OCR_NORMAL = 32512
OCR_HAND = 32649
CONFIG_PATH = Path(__file__).with_name("config.json")
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
PM_REMOVE = 0x0001
HOTKEY_ID = 1
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000

class Point(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

class Message(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", Point),
        ("lPrivate", wintypes.DWORD),
    ]


class ConfigurationError(ValueError):
    """Raised for malformed or inconsistent color settings."""


def parse_hex_color(value):
    if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        raise ConfigurationError("Färger ska anges som #RRGGBB, exempelvis #FFE500.")
    return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5)) + (255,)


def parse_hotkey(value):
    if not isinstance(value, str):
        raise ConfigurationError("hotkey måste vara text, exempelvis ctrl+alt+r.")
    parts = [part.strip().lower() for part in value.split("+")]
    modifiers = {"ctrl": MOD_CONTROL, "alt": MOD_ALT, "shift": MOD_SHIFT}
    names = set(parts[:-1])
    if len(parts) < 2 or len(names) != len(parts) - 1 or not names.issubset(modifiers):
        raise ConfigurationError("hotkey kräver ctrl, alt eller shift (utan upprepningar).")
    key = parts[-1]
    if len(key) == 1 and key in "abcdefghijklmnopqrstuvwxyz0123456789":
        vk = ord(key.upper())
    elif re.fullmatch(r"f([1-9]|1[01])", key):
        vk = 0x70 + int(key[1:]) - 1
    else:
        raise ConfigurationError("Använd en bokstav, siffra eller F1 till F11.")
    mask = MOD_NOREPEAT
    for name in names:
        mask |= modifiers[name]
    return mask, vk


def animation_frame(elapsed, duration):
    """Returns (radius, visible), or None when the animation is complete."""
    if elapsed < 0 or elapsed >= duration:
        return None
    phase = (elapsed / duration) * PULSE_COUNT * 2 * math.pi
    size = (1 - math.cos(phase)) / 2
    radius = MIN_PULSE_RADIUS + (MAX_PULSE_RADIUS - MIN_PULSE_RADIUS) * size
    radius = 2 * round(radius / 2)
    blink_phase = (elapsed * BLINK_FREQUENCY + 0.5) % 1
    return radius, blink_phase >= 0.35


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
    hotkey = settings.get("hotkey", "ctrl+alt+r")
    parse_hotkey(hotkey)
    duration = settings.get("animation_seconds", 2.4)
    if (isinstance(duration, bool) or not isinstance(duration, (int, float))
            or not math.isfinite(duration) or not 0.5 <= duration <= 10):
        raise ConfigurationError("animation_seconds måste vara mellan 0.5 och 10 sekunder.")
    return selected, colors, hotkey, float(duration)


def create_cursor(path, color, radius=RADIUS, show_ring=True):
    """Build a 32-bit .cur file with a black/white bordered colored ring."""
    scale = 4
    canvas = Image.new("RGBA", (SIZE * scale, SIZE * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    center = CENTER * scale

    # From outside to inside: black, white, chosen color. The extra
    # contours preserve visibility on bright AND dark regions of a map.
    if show_ring:
        for current_radius, width, rgba in (
            (radius + 3, 11, (0, 0, 0, 255)),
            (radius + 1, 8, (255, 255, 255, 255)),
            (radius, 5, color),
        ):
            distance = current_radius * scale
            bounds = (center - distance, center - distance,
                      center + distance, center + distance)
            draw.ellipse(bounds, outline=rgba, width=width * scale)

    # Arrow tip is the hotspot, centered within the ring.
    outline = [(0, 0), (1, 21), (7, 15), (13, 25),
               (18, 22), (12, 12), (21, 11)]
    points = [((CENTER + x) * scale, (CENTER + y) * scale) for x, y in outline]
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
    api.DestroyCursor.argtypes = [wintypes.HANDLE]
    api.DestroyCursor.restype = wintypes.BOOL
    api.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
    api.RegisterHotKey.restype = wintypes.BOOL
    api.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
    api.UnregisterHotKey.restype = wintypes.BOOL
    api.PeekMessageW.argtypes = [ctypes.POINTER(Message), wintypes.HWND,
                                 wintypes.UINT, wintypes.UINT, wintypes.UINT]
    api.PeekMessageW.restype = wintypes.BOOL
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
            error = ctypes.get_last_error()
            api.DestroyCursor(handle)
            raise ctypes.WinError(error)


def prepare_frames(directory, color):
    """Precompute cursor images, so animation only changes the active image."""
    paths = {}
    steady = directory / "normal.cur"
    create_cursor(steady, color)
    paths["normal"] = steady
    hidden = directory / "arrow_only.cur"
    create_cursor(hidden, color, show_ring=False)
    paths["hidden"] = hidden
    for radius in range(MIN_PULSE_RADIUS, MAX_PULSE_RADIUS + 1, 2):
        path = directory / f"ring_{radius}.cur"
        create_cursor(path, color, radius=radius)
        paths[radius] = path
    return paths


def run(api, paths, hotkey, duration):
    modifiers, vk = parse_hotkey(hotkey)
    if not api.RegisterHotKey(None, HOTKEY_ID, modifiers, vk):
        raise OSError("Snabbtangenten kunde inte registreras. Den används möjligen av ett annat program.")
    cursor_modified = False
    try:
        cursor_modified = True  # ensure restore after partially failed installation
        enable(api, paths["normal"])
        print(f"CursorRing aktiv. Tryck {hotkey.upper()} för att hitta pekaren. Avsluta med Ctrl+C.")
        active_since = None
        last_key = "normal"
        next_frame_at = 0.0
        msg = Message()
        while True:
            while api.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                    active_since = time.monotonic()
                    next_frame_at = active_since
                elif msg.message == WM_QUIT:
                    return
            now = time.monotonic()
            if active_since is not None and now >= next_frame_at:
                frame = animation_frame(now - active_since, duration)
                if frame is None:
                    key = "normal"
                    active_since = None
                elif frame[1]:
                    key = frame[0]
                else:
                    key = "hidden"
                if key != last_key:
                    enable(api, paths[key])
                    last_key = key
                next_frame_at = now + FRAME_INTERVAL
            time.sleep(0.01)
    finally:
        try:
            if cursor_modified:
                restore(api)
                print("Windows-muspekaren är återställd.")
        finally:
            api.UnregisterHotKey(None, HOTKEY_ID)


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
        default, colors, hotkey, duration = load_settings(args.config)
    except ConfigurationError as exc:
        parser.error(str(exc))

    if args.list_colors:
        for name, hex_color in colors.items():
            label = " (standard)" if name == default else ""
            print(f"{name}: {hex_color}{label}")
        print(f"Snabbtangent: {hotkey} | Animation: {duration:g} sekunder")
        return

    chosen = args.color or default
    if chosen not in colors:
        parser.error(f"Okänd färg '{chosen}'. Välj någon av: {', '.join(colors)}")
    if os.name != "nt":
        parser.error("Programmet fungerar bara i Windows.")

    api = windows_api()
    try:
        with tempfile.TemporaryDirectory() as tempdir:
            paths = prepare_frames(Path(tempdir), parse_hex_color(colors[chosen]))
            run(api, paths, hotkey, duration)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
