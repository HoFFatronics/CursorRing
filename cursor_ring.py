"""Show a high-contrast, configurable cursor ring on Windows.

Usage:
    python cursor_ring.py
    python cursor_ring.py --color white
    python cursor_ring.py --list-colors
    python cursor_ring.py --restore
"""

import argparse
import colorsys
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

from PIL import Image, ImageChops, ImageDraw

SIZE = 96
RADIUS = 23
MIN_RADIUS = 15
MAX_RADIUS = 45
RADIUS_STEP = 2
MIN_THICKNESS = 1
MAX_THICKNESS = 9
DEFAULT_THICKNESS = 5
DISCO_FRAME_COUNT = 36
DISCO_CYCLE_SECONDS = 2.4
DISCO_RADIUS_SWING = 10
DISCO_ORBIT_RADIUS = 12
MAX_DISCO_RADIUS = MAX_RADIUS + DISCO_RADIUS_SWING
MIN_PULSE_RADIUS = 18
MAX_PULSE_RADIUS = 36
PULSE_COUNT = 3
BLINK_FREQUENCY = 2.5
FRAME_INTERVAL = 1 / 15
IMAGE_CURSOR = 2
LR_LOADFROMFILE = 0x0010
SPI_SETCURSORS = 0x0057
OCR_NORMAL = 32512
IDC_ARROW = 32512
CONFIG_PATH = Path(__file__).with_name("config.json")
DEFAULT_SETTINGS = {
    "default_color": "yellow",
    "colors": {"yellow": "#FFE500", "white": "#FFFFFF", "black": "#111111"},
    "hotkey": "ctrl+alt+r",
    "animation_seconds": 2.4,
    "ring_radius": RADIUS,
    "ring_thickness": DEFAULT_THICKNESS,
}
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
WM_MOUSEWHEEL = 0x020A
PM_REMOVE = 0x0001
WH_MOUSE_LL = 14
HC_ACTION = 0
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
CTRL_C_EVENT = 0
CTRL_CLOSE_EVENT = 2
CTRL_LOGOFF_EVENT = 5
CTRL_SHUTDOWN_EVENT = 6
HOTKEY_ID = 1
PROFILE_HOTKEY_START = 2
SETTINGS_HOTKEY_ID = 6
DISCO_HOTKEY_ID = 7
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000
MOD_PROFILE = MOD_CONTROL | MOD_ALT | MOD_NOREPEAT

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


class MouseHookData(ctypes.Structure):
    _fields_ = [
        ("pt", Point),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class Bitmap(ctypes.Structure):
    _fields_ = [
        ("bmType", wintypes.LONG),
        ("bmWidth", wintypes.LONG),
        ("bmHeight", wintypes.LONG),
        ("bmWidthBytes", wintypes.LONG),
        ("bmPlanes", wintypes.WORD),
        ("bmBitsPixel", wintypes.WORD),
        ("bmBits", ctypes.c_void_p),
    ]


class IconInfo(ctypes.Structure):
    _fields_ = [
        ("fIcon", wintypes.BOOL),
        ("xHotspot", wintypes.DWORD),
        ("yHotspot", wintypes.DWORD),
        ("hbmMask", wintypes.HANDLE),
        ("hbmColor", wintypes.HANDLE),
    ]


class BitmapInfoHeader(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class RGBQuad(ctypes.Structure):
    _fields_ = [
        ("rgbBlue", wintypes.BYTE),
        ("rgbGreen", wintypes.BYTE),
        ("rgbRed", wintypes.BYTE),
        ("rgbReserved", wintypes.BYTE),
    ]


class BitmapInfo(ctypes.Structure):
    _fields_ = [("bmiHeader", BitmapInfoHeader), ("bmiColors", RGBQuad * 2)]


class ConfigurationError(ValueError):
    """Raised for malformed or inconsistent color settings."""


def parse_hex_color(value):
    if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        raise ConfigurationError("Colors must use #RRGGBB format, for example #FFE500.")
    return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5)) + (255,)


def parse_hotkey(value):
    if not isinstance(value, str):
        raise ConfigurationError("hotkey must be text, for example ctrl+alt+r.")
    parts = [part.strip().lower() for part in value.split("+")]
    modifiers = {"ctrl": MOD_CONTROL, "alt": MOD_ALT, "shift": MOD_SHIFT}
    names = set(parts[:-1])
    if len(parts) < 2 or len(names) != len(parts) - 1 or not names.issubset(modifiers):
        raise ConfigurationError("hotkey requires ctrl, alt, or shift (without duplicates).")
    key = parts[-1]
    if len(key) == 1 and key in "abcdefghijklmnopqrstuvwxyz0123456789":
        vk = ord(key.upper())
    elif re.fullmatch(r"f([1-9]|1[01])", key):
        vk = 0x70 + int(key[1:]) - 1
    else:
        raise ConfigurationError("Use a letter, digit, or F1 through F11.")
    mask = MOD_NOREPEAT
    for name in names:
        mask |= modifiers[name]
    return mask, vk


def profile_hotkeys():
    """Return (registration id, profile index, modifiers, key) for 1–4."""
    return [
        (PROFILE_HOTKEY_START + index, index, MOD_PROFILE, ord(str(index + 1)))
        for index in range(4)
    ]


def adjust_ring_geometry(radius, thickness, wheel_delta, adjust_diameter):
    """Apply one or more wheel steps, clamping values to the supported range."""
    if not wheel_delta:
        return radius, thickness
    steps = max(1, abs(int(wheel_delta)) // 120)
    direction = 1 if wheel_delta > 0 else -1
    if adjust_diameter:
        radius = max(MIN_RADIUS, min(MAX_RADIUS, radius + direction * RADIUS_STEP * steps))
    else:
        thickness = max(MIN_THICKNESS, min(MAX_THICKNESS, thickness + direction * steps))
    return radius, thickness


def cursor_canvas_size(radius, thickness, system_arrow=None, arrow_hotspot=(0, 0),
                      orbit_radius=0):
    """Return an even canvas size that contains the ring and its outlines."""
    outer_stroke = thickness + 6
    ring_extent = max(radius, MAX_PULSE_RADIUS) + 3 + outer_stroke / 2 + orbit_radius
    arrow_extent = 25
    if system_arrow is not None:
        arrow_width, arrow_height = system_arrow.size
        hotspot_x, hotspot_y = arrow_hotspot
        arrow_extent = max(
            math.hypot(x, y)
            for x in (hotspot_x, arrow_width - hotspot_x)
            for y in (hotspot_y, arrow_height - hotspot_y)
        )
    extent = max(ring_extent, arrow_extent) + 1
    return max(SIZE, 2 * math.ceil(extent))


def ensure_config(path):
    """Create the default config on first launch without overwriting user data."""
    path = Path(path)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(DEFAULT_SETTINGS, indent=2) + "\n", encoding="utf-8")
    return path


def save_profile_colors(path, colors):
    """Persist profile colors while preserving other user settings."""
    if not isinstance(colors, dict) or len(colors) != 3:
        raise ConfigurationError("Exactly three color profiles are required.")
    for color in colors.values():
        parse_hex_color(color)
    path = ensure_config(path)
    settings = json.loads(path.read_text(encoding="utf-8"))
    settings["colors"] = dict(colors)
    path.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def save_ring_geometry(path, radius, thickness):
    """Persist pointer ring geometry while preserving other settings."""
    path = ensure_config(path)
    settings = json.loads(path.read_text(encoding="utf-8"))
    settings["ring_radius"] = radius
    settings["ring_thickness"] = thickness
    path.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def create_settings_window(root, colors, save_callback, existing=None):
    """Create or raise the color profile settings window."""
    import tkinter as tk
    from tkinter import colorchooser

    if existing is not None:
        try:
            if existing.winfo_exists():
                existing.deiconify()
                existing.lift()
                existing.focus_force()
                return existing
        except tk.TclError:
            pass

    window = tk.Toplevel(root)
    window.title("CursorRing - Color Profiles")
    window.resizable(False, False)
    pending = dict(colors)
    swatches = {}

    tk.Label(window, text="Choose a ring color for each profile:").grid(
        row=0, column=0, columnspan=3, padx=14, pady=(14, 8), sticky="w"
    )
    for row, (name, color) in enumerate(colors.items(), start=1):
        tk.Label(window, text=name).grid(row=row, column=0, padx=14, pady=5, sticky="w")
        swatch = tk.Label(window, text="     ", bg=color, relief="sunken")
        swatch.grid(row=row, column=1, padx=8, pady=5)
        swatches[name] = swatch

        def choose_color(profile=name):
            _, selected = colorchooser.askcolor(
                color=pending[profile], parent=window, title=f"Color for {profile}"
            )
            if selected:
                pending[profile] = selected.upper()
                swatches[profile].configure(bg=pending[profile])

        tk.Button(window, text="Choose Color...", command=choose_color).grid(
            row=row, column=2, padx=(4, 14), pady=5
        )

    status = tk.Label(window, text="", anchor="w")
    status.grid(row=4, column=0, columnspan=3, padx=14, pady=(8, 0), sticky="ew")

    def save():
        error = save_callback(pending)
        status.configure(text=error or "Colors saved.")

    actions = tk.Frame(window)
    actions.grid(row=5, column=0, columnspan=3, padx=14, pady=12, sticky="e")
    tk.Button(actions, text="Cancel", command=window.destroy).pack(side="right", padx=(6, 0))
    tk.Button(actions, text="Save", command=save).pack(side="right")
    return window


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
        raise ConfigurationError(f"Could not read {path}: {exc}") from exc
    if not isinstance(settings, dict):
        raise ConfigurationError("Configuration must be a JSON object.")
    colors = settings.get("colors")
    if not isinstance(colors, dict) or len(colors) != 3:
        raise ConfigurationError("Configuration must contain exactly three color profiles.")
    if any(not isinstance(name, str) or not name.strip() for name in colors):
        raise ConfigurationError("Each color profile must have a name.")
    for name, hex_color in colors.items():
        try:
            parse_hex_color(hex_color)
        except ConfigurationError as exc:
            raise ConfigurationError(f"Invalid color for {name}: {exc}") from exc
    selected = settings.get("default_color")
    if not isinstance(selected, str) or selected not in colors:
        raise ConfigurationError("default_color must match one of the color profiles.")
    hotkey = settings.get("hotkey", "ctrl+alt+r")
    hotkey_modifiers, hotkey_vk = parse_hotkey(hotkey)
    if hotkey_modifiers == MOD_PROFILE and (
            ord("0") <= hotkey_vk <= ord("4") or hotkey_vk == ord("P")):
        raise ConfigurationError("hotkey cannot be Ctrl+Alt+0 through Ctrl+Alt+4 or Ctrl+Alt+P; these shortcuts control profiles and disco mode.")
    radius = settings.get("ring_radius", RADIUS)
    if (isinstance(radius, bool) or not isinstance(radius, int)
            or not MIN_RADIUS <= radius <= MAX_RADIUS
            or (radius - MIN_RADIUS) % RADIUS_STEP):
        raise ConfigurationError(f"ring_radius must be an odd integer from {MIN_RADIUS} to {MAX_RADIUS}.")
    thickness = settings.get("ring_thickness", DEFAULT_THICKNESS)
    if (isinstance(thickness, bool) or not isinstance(thickness, int)
            or not MIN_THICKNESS <= thickness <= MAX_THICKNESS):
        raise ConfigurationError(f"ring_thickness must be an integer from {MIN_THICKNESS} to {MAX_THICKNESS} pixels.")
    duration = settings.get("animation_seconds", 2.4)
    if (isinstance(duration, bool) or not isinstance(duration, (int, float))
            or not math.isfinite(duration) or not 0.5 <= duration <= 10):
        raise ConfigurationError("animation_seconds must be between 0.5 and 10 seconds.")
    return selected, colors, hotkey, float(duration), radius, thickness


def create_cursor(path, color, radius=RADIUS, show_ring=True, thickness=DEFAULT_THICKNESS,
                  canvas_size=None, system_arrow=None, arrow_hotspot=(0, 0),
                  ring_offset=(0, 0)):
    """Build a 32-bit .cur file with a black/white bordered colored ring."""
    scale = 4
    size = canvas_size or cursor_canvas_size(radius, thickness, system_arrow, arrow_hotspot)
    center = size // 2
    canvas = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    center *= scale

    # From outside to inside: black, white, chosen color. The extra
    # contours preserve visibility on bright AND dark regions of a map.
    if show_ring:
        for current_radius, width, rgba in (
            (radius + 3, thickness + 6, (0, 0, 0, 255)),
            (radius + 1, thickness + 3, (255, 255, 255, 255)),
            (radius, thickness, color),
        ):
            distance = current_radius * scale
            ring_center_x = center + ring_offset[0] * scale
            ring_center_y = center + ring_offset[1] * scale
            bounds = (ring_center_x - distance, ring_center_y - distance,
                      ring_center_x + distance, ring_center_y + distance)
            draw.ellipse(bounds, outline=rgba, width=width * scale)

    image = canvas.resize((size, size), Image.Resampling.LANCZOS)
    if system_arrow is not None:
        arrow_x = size // 2 - arrow_hotspot[0]
        arrow_y = size // 2 - arrow_hotspot[1]
        image.alpha_composite(system_arrow, dest=(arrow_x, arrow_y))

    xor = b"".join(image.crop((0, y, size, y + 1)).tobytes("raw", "BGRA")
                   for y in range(size - 1, -1, -1))
    alpha = image.getchannel("A")
    stride = ((size + 31) // 32) * 4
    mask = bytearray()
    for y in range(size - 1, -1, -1):
        row = bytearray(stride)
        for x in range(size):
            if alpha.getpixel((x, y)) == 0:
                row[x // 8] |= 0x80 >> (x % 8)
        mask.extend(row)

    dib_header = struct.pack("<IiiHHIIiiII", 40, size, size * 2,
                             1, 32, 0, len(xor), 0, 0, 0, 0)
    bitmap = dib_header + xor + mask
    directory = struct.pack("<HHH", 0, 2, 1)
    # The hotspot is at the ring center for accurate clicks.
    entry = struct.pack("<BBBBHHII", size, size, 0, 0,
                        size // 2, size // 2, len(bitmap), 22)
    path.write_bytes(directory + entry + bitmap)


def windows_api():
    api = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    api.LoadCursorW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
    api.LoadCursorW.restype = wintypes.HANDLE
    api.GetIconInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(IconInfo)]
    api.GetIconInfo.restype = wintypes.BOOL
    api.GetDC.argtypes = [wintypes.HWND]
    api.GetDC.restype = wintypes.HANDLE
    api.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HANDLE]
    api.ReleaseDC.restype = ctypes.c_int
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
    api.TranslateMessage.argtypes = [ctypes.POINTER(Message)]
    api.TranslateMessage.restype = wintypes.BOOL
    api.DispatchMessageW.argtypes = [ctypes.POINTER(Message)]
    api.DispatchMessageW.restype = wintypes.LPARAM
    api.SetWindowsHookExW.argtypes = [ctypes.c_int, ctypes.c_void_p,
                                      wintypes.HINSTANCE, wintypes.DWORD]
    api.SetWindowsHookExW.restype = wintypes.HANDLE
    api.UnhookWindowsHookEx.argtypes = [wintypes.HANDLE]
    api.UnhookWindowsHookEx.restype = wintypes.BOOL
    api.CallNextHookEx.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                   wintypes.WPARAM, wintypes.LPARAM]
    api.CallNextHookEx.restype = wintypes.LPARAM
    api.GetAsyncKeyState.argtypes = [ctypes.c_int]
    api.GetAsyncKeyState.restype = ctypes.c_short
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE
    api.GetModuleHandleW = kernel32.GetModuleHandleW
    kernel32.SetConsoleCtrlHandler.argtypes = [ctypes.c_void_p, wintypes.BOOL]
    kernel32.SetConsoleCtrlHandler.restype = wintypes.BOOL
    api.SetConsoleCtrlHandler = kernel32.SetConsoleCtrlHandler
    gdi32.GetObjectW.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p]
    gdi32.GetObjectW.restype = ctypes.c_int
    gdi32.GetDIBits.argtypes = [wintypes.HANDLE, wintypes.HANDLE, wintypes.UINT,
                                wintypes.UINT, ctypes.c_void_p,
                                ctypes.POINTER(BitmapInfo), wintypes.UINT]
    gdi32.GetDIBits.restype = ctypes.c_int
    gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
    gdi32.DeleteObject.restype = wintypes.BOOL
    api._gdi32 = gdi32
    return api


def capture_system_arrow(api):
    """Copy the Windows default arrow and its hotspot into a Pillow image."""
    resource_id = ctypes.cast(ctypes.c_void_p(IDC_ARROW), wintypes.LPCWSTR)
    cursor = api.LoadCursorW(None, resource_id)
    if not cursor:
        raise ctypes.WinError(ctypes.get_last_error())

    info = IconInfo()
    if not api.GetIconInfo(cursor, ctypes.byref(info)):
        raise ctypes.WinError(ctypes.get_last_error())

    try:
        if not info.hbmColor or not info.hbmMask:
            raise OSError("The Windows default arrow does not expose color and mask bitmaps.")
        bitmap = Bitmap()
        if not api._gdi32.GetObjectW(info.hbmColor, ctypes.sizeof(bitmap), ctypes.byref(bitmap)):
            raise ctypes.WinError(ctypes.get_last_error())
        width, height = bitmap.bmWidth, bitmap.bmHeight
        if width <= 0 or height <= 0:
            raise OSError("The Windows default arrow has invalid dimensions.")

        dc = api.GetDC(None)
        if not dc:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            color_info = BitmapInfo()
            color_info.bmiHeader.biSize = ctypes.sizeof(BitmapInfoHeader)
            color_info.bmiHeader.biWidth = width
            color_info.bmiHeader.biHeight = -height
            color_info.bmiHeader.biPlanes = 1
            color_info.bmiHeader.biBitCount = 32
            color_info.bmiHeader.biCompression = 0
            color_info.bmiHeader.biSizeImage = width * height * 4
            color_buffer = ctypes.create_string_buffer(width * height * 4)
            lines = api._gdi32.GetDIBits(
                dc, info.hbmColor, 0, height, color_buffer,
                ctypes.byref(color_info), 0,
            )
            if lines != height:
                raise ctypes.WinError(ctypes.get_last_error())
            image = Image.frombytes("RGBA", (width, height), color_buffer.raw, "raw", "BGRA")

            mask_info = BitmapInfo()
            mask_info.bmiHeader.biSize = ctypes.sizeof(BitmapInfoHeader)
            mask_info.bmiHeader.biWidth = width
            mask_info.bmiHeader.biHeight = -height
            mask_info.bmiHeader.biPlanes = 1
            mask_info.bmiHeader.biBitCount = 1
            mask_info.bmiHeader.biCompression = 0
            mask_info.bmiHeader.biSizeImage = ((width + 31) // 32) * 4 * height
            mask_info.bmiHeader.biClrUsed = 2
            mask_info.bmiColors[0] = RGBQuad(0, 0, 0, 0)
            mask_info.bmiColors[1] = RGBQuad(255, 255, 255, 0)
            mask_stride = ((width + 31) // 32) * 4
            mask_buffer = ctypes.create_string_buffer(mask_stride * height)
            lines = api._gdi32.GetDIBits(
                dc, info.hbmMask, 0, height, mask_buffer,
                ctypes.byref(mask_info), 0,
            )
            if lines != height:
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            api.ReleaseDC(None, dc)

        mask_alpha = bytearray(width * height)
        raw_mask = mask_buffer.raw
        for y in range(height):
            row_offset = y * mask_stride
            for x in range(width):
                transparent = raw_mask[row_offset + x // 8] & (0x80 >> (x % 8))
                mask_alpha[y * width + x] = 0 if transparent else 255
        alpha = image.getchannel("A")
        if alpha.getextrema()[1] == 0:
            image.putalpha(Image.frombytes("L", (width, height), bytes(mask_alpha)))
        else:
            image.putalpha(ImageChops.darker(alpha, Image.frombytes("L", (width, height), bytes(mask_alpha))))
        return image, (info.xHotspot, info.yHotspot)
    finally:
        if info.hbmColor:
            api._gdi32.DeleteObject(info.hbmColor)
        if info.hbmMask:
            api._gdi32.DeleteObject(info.hbmMask)


def restore(api):
    if not api.SystemParametersInfoW(SPI_SETCURSORS, 0, None, 0):
        raise ctypes.WinError(ctypes.get_last_error())


def enable(api, path):
    with path.open("rb") as cursor_file:
        cursor_file.seek(6)
        width, height = struct.unpack("<BB", cursor_file.read(2))
    width = width or 256
    height = height or 256
    handle = api.LoadImageW(None, str(path), IMAGE_CURSOR, width, height, LR_LOADFROMFILE)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    # SetSystemCursor assumes ownership of a successfully passed handle.
    if not api.SetSystemCursor(handle, OCR_NORMAL):
        error = ctypes.get_last_error()
        api.DestroyCursor(handle)
        raise ctypes.WinError(error)


def prepare_frames(directory, color, radius=RADIUS, thickness=DEFAULT_THICKNESS,
                   system_arrow=None, arrow_hotspot=(0, 0)):
    """Precompute cursor images, so animation only changes the active image."""
    paths = {}
    canvas_size = cursor_canvas_size(radius, thickness, system_arrow, arrow_hotspot)
    steady = directory / "normal.cur"
    create_cursor(steady, color, radius=radius, thickness=thickness, canvas_size=canvas_size,
                  system_arrow=system_arrow, arrow_hotspot=arrow_hotspot)
    paths["normal"] = steady
    hidden = directory / "arrow_only.cur"
    create_cursor(hidden, color, show_ring=False, thickness=thickness, canvas_size=canvas_size,
                  system_arrow=system_arrow, arrow_hotspot=arrow_hotspot)
    paths["hidden"] = hidden
    for pulse_radius in range(MIN_PULSE_RADIUS, MAX_PULSE_RADIUS + 1, 2):
        path = directory / f"ring_{pulse_radius}.cur"
        create_cursor(path, color, radius=pulse_radius, thickness=thickness,
                      canvas_size=canvas_size, system_arrow=system_arrow,
                      arrow_hotspot=arrow_hotspot)
        paths[pulse_radius] = path
    return paths


def prepare_disco_frames(directory, base_radius, thickness, system_arrow, arrow_hotspot):
    """Pre-render a seamless rainbow cycle that pulses across the size range."""
    directory.mkdir(parents=True, exist_ok=True)
    minimum_radius = max(MIN_RADIUS, base_radius - DISCO_RADIUS_SWING)
    maximum_radius = min(MAX_DISCO_RADIUS, base_radius + DISCO_RADIUS_SWING)
    canvas_size = cursor_canvas_size(
        maximum_radius, thickness, system_arrow, arrow_hotspot, DISCO_ORBIT_RADIUS
    )
    paths = []
    for index in range(DISCO_FRAME_COUNT):
        phase = index / DISCO_FRAME_COUNT
        pulse = (1 - math.cos(phase * 2 * math.pi)) / 2
        radius = round(minimum_radius + (maximum_radius - minimum_radius) * pulse)
        angle = phase * 2 * math.pi
        ring_offset = (
            round(DISCO_ORBIT_RADIUS * math.cos(angle)),
            round(DISCO_ORBIT_RADIUS * math.sin(angle)),
        )
        rgb = colorsys.hsv_to_rgb(phase, 1, 1)
        color = tuple(round(channel * 255) for channel in rgb) + (255,)
        path = directory / f"disco_{index:02d}.cur"
        create_cursor(
            path, color, radius=radius, thickness=thickness,
            canvas_size=canvas_size, system_arrow=system_arrow,
            arrow_hotspot=arrow_hotspot, ring_offset=ring_offset,
        )
        paths.append(path)
    return paths


def disco_frame_index(elapsed):
    """Return the pre-rendered frame for the current point in the loop."""
    phase = elapsed % DISCO_CYCLE_SECONDS
    return int(phase / DISCO_CYCLE_SECONDS * DISCO_FRAME_COUNT)


def run(api, profile_paths, profile_dirs, profile_names, colors, config_path,
        initial_profile, hotkey, duration, ring_radius, ring_thickness,
        system_arrow, arrow_hotspot, disco_paths, disco_root):
    modifiers, vk = parse_hotkey(hotkey)
    profile_ids = {hotkey_id: index for hotkey_id, index, _, _ in profile_hotkeys()}
    registered_ids = []
    cursor_modified = False
    mouse_hook_handle = None
    mouse_hook_proc = None
    console_handler = None
    console_handler_registered = False
    try:
        if not api.RegisterHotKey(None, HOTKEY_ID, modifiers, vk):
            raise OSError("Could not register the animation hotkey. Another program may already be using it.")
        registered_ids.append(HOTKEY_ID)
        for hotkey_id, profile_index, profile_modifiers, profile_vk in profile_hotkeys():
            if not api.RegisterHotKey(None, hotkey_id, profile_modifiers, profile_vk):
                raise OSError("Could not register profile shortcuts Ctrl+Alt+1-4. Another program may already be using one.")
            registered_ids.append(hotkey_id)
        if not api.RegisterHotKey(None, SETTINGS_HOTKEY_ID, MOD_PROFILE, ord("0")):
            raise OSError("Could not register the settings shortcut Ctrl+Alt+0. Another program may already be using it.")
        registered_ids.append(SETTINGS_HOTKEY_ID)
        if not api.RegisterHotKey(None, DISCO_HOTKEY_ID, MOD_PROFILE, ord("P")):
            raise OSError("Could not register the disco shortcut Ctrl+Alt+P. Another program may already be using it.")
        registered_ids.append(DISCO_HOTKEY_ID)

        console_handler_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)

        def handle_console_control(event):
            nonlocal cursor_modified
            if event in (CTRL_CLOSE_EVENT, CTRL_LOGOFF_EVENT, CTRL_SHUTDOWN_EVENT):
                if cursor_modified:
                    try:
                        restore(api)
                        cursor_modified = False
                    except Exception:
                        return False
                return True
            return False

        console_handler = console_handler_type(handle_console_control)
        if not api.SetConsoleCtrlHandler(ctypes.cast(console_handler, ctypes.c_void_p), True):
            raise ctypes.WinError(ctypes.get_last_error())
        console_handler_registered = True

        cursor_modified = True  # ensure restore after partially failed installation
        current_profile = initial_profile
        if current_profile == 0:
            restore(api)
            last_key = None
        else:
            enable(api, profile_paths[profile_names[current_profile - 1]]["normal"])
            last_key = "normal"
        labels = " | ".join(
            f"Ctrl+Alt+{index + 2}: {name}"
            for index, name in enumerate(profile_names)
        )
        active_since = None
        next_frame_at = 0.0
        settings_root = None
        settings_window = None
        pending_geometry = None
        disco_active = False
        disco_started = 0.0
        last_disco_index = None

        def make_profile_paths(color_values, radius, thickness):
            generation = f"frames_{time.time_ns()}"
            generated = {}
            for name in profile_names:
                directory = profile_dirs[name] / generation
                directory.mkdir()
                generated[name] = prepare_frames(
                    directory, parse_hex_color(color_values[name]), radius, thickness,
                    system_arrow, arrow_hotspot,
                )
            return generated

        def make_disco_paths(radius, thickness):
            directory = disco_root / f"thickness_{thickness}_{time.time_ns()}"
            return prepare_disco_frames(directory, radius, thickness, system_arrow, arrow_hotspot)

        def save_colors(updated_colors):
            nonlocal active_since, last_key, last_disco_index
            try:
                for color in updated_colors.values():
                    parse_hex_color(color)
                new_paths = make_profile_paths(updated_colors, ring_radius, ring_thickness)
                save_profile_colors(config_path, updated_colors)
                colors.update(updated_colors)
                profile_paths.update(new_paths)
                active_since = None
                if current_profile != 0 and disco_active:
                    last_disco_index = None
                elif current_profile != 0:
                    name = profile_names[current_profile - 1]
                    enable(api, profile_paths[name]["normal"])
                    last_key = "normal"
            except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
                return f"Could not save colors: {exc}"
            return None

        def update_geometry(new_radius, new_thickness):
            nonlocal ring_radius, ring_thickness, active_since, last_key
            nonlocal disco_paths, last_disco_index
            if (new_radius, new_thickness) == (ring_radius, ring_thickness):
                return
            try:
                new_disco_paths = make_disco_paths(new_radius, new_thickness)
                if new_thickness != ring_thickness:
                    new_paths = make_profile_paths(colors, new_radius, new_thickness)
                else:
                    new_paths = {}
                    for name in profile_names:
                        directory = profile_dirs[name] / f"radius_{new_radius}_{time.time_ns()}"
                        directory.mkdir()
                        normal_path = directory / "normal.cur"
                        create_cursor(
                            normal_path, parse_hex_color(colors[name]),
                            radius=new_radius, thickness=new_thickness,
                            system_arrow=system_arrow, arrow_hotspot=arrow_hotspot,
                        )
                        new_paths[name] = dict(profile_paths[name])
                        new_paths[name]["normal"] = normal_path
                save_ring_geometry(config_path, new_radius, new_thickness)
                profile_paths.update(new_paths)
                ring_radius = new_radius
                ring_thickness = new_thickness
                active_since = None
                disco_paths = new_disco_paths
                last_disco_index = None
                if current_profile != 0 and disco_active:
                    last_disco_index = None
                elif current_profile != 0:
                    name = profile_names[current_profile - 1]
                    enable(api, profile_paths[name]["normal"])
                    last_key = "normal"
            except Exception as exc:
                print(f"Could not update ring size or thickness: {exc}")

        def mouse_wheel_hook(code, message, data_pointer):
            nonlocal pending_geometry
            if code < HC_ACTION or message != WM_MOUSEWHEEL:
                return api.CallNextHookEx(mouse_hook_handle, code, message, data_pointer)
            data = ctypes.cast(data_pointer, ctypes.POINTER(MouseHookData)).contents
            delta = ctypes.c_short((data.mouseData >> 16) & 0xFFFF).value
            if not delta:
                return api.CallNextHookEx(mouse_hook_handle, code, message, data_pointer)
            control = bool(api.GetAsyncKeyState(VK_CONTROL) & 0x8000)
            shift = bool(api.GetAsyncKeyState(VK_SHIFT) & 0x8000)
            alt = bool(api.GetAsyncKeyState(VK_MENU) & 0x8000)
            base_radius, base_thickness = pending_geometry or (ring_radius, ring_thickness)
            if control and shift:
                pending_geometry = adjust_ring_geometry(
                    base_radius, base_thickness, delta, adjust_diameter=True
                )
            elif control and alt:
                pending_geometry = adjust_ring_geometry(
                    base_radius, base_thickness, delta, adjust_diameter=False
                )
            else:
                return api.CallNextHookEx(mouse_hook_handle, code, message, data_pointer)
            return 1

        def open_settings():
            nonlocal settings_root, settings_window
            try:
                import tkinter as tk
                if settings_root is None:
                    settings_root = tk.Tk()
                    settings_root.withdraw()
                settings_window = create_settings_window(
                    settings_root, colors, save_colors, settings_window
                )
            except Exception as exc:
                print(f"Could not open color settings: {exc}")

        hook_callback_type = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
        )
        mouse_hook_proc = hook_callback_type(mouse_wheel_hook)
        mouse_hook_handle = api.SetWindowsHookExW(
            WH_MOUSE_LL, ctypes.cast(mouse_hook_proc, ctypes.c_void_p),
            api.GetModuleHandleW(None), 0,
        )
        if not mouse_hook_handle:
            raise ctypes.WinError(ctypes.get_last_error())

        print(f"CursorRing is running. Ctrl+Shift+Wheel: ring diameter | Ctrl+Alt+Wheel: ring thickness | Ctrl+Alt+1: default pointer | {labels} | Ctrl+Alt+0: color settings | Ctrl+Alt+P: disco mode | {hotkey.upper()}: find effect. Press Ctrl+C to exit.")
        msg = Message()
        while True:
            while api.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                    if current_profile != 0 and not disco_active:
                        active_since = time.monotonic()
                        next_frame_at = active_since
                elif msg.message == WM_HOTKEY and msg.wParam in profile_ids:
                    profile_index = profile_ids[msg.wParam]
                    active_since = None
                    disco_active = False
                    last_disco_index = None
                    if profile_index == 0:
                        restore(api)
                        current_profile = 0
                        last_key = None
                    else:
                        name = profile_names[profile_index - 1]
                        enable(api, profile_paths[name]["normal"])
                        current_profile = profile_index
                        last_key = "normal"
                elif msg.message == WM_HOTKEY and msg.wParam == SETTINGS_HOTKEY_ID:
                    open_settings()
                elif msg.message == WM_HOTKEY and msg.wParam == DISCO_HOTKEY_ID:
                    if current_profile != 0:
                        active_since = None
                        disco_active = not disco_active
                        if disco_active:
                            disco_started = time.monotonic()
                            next_frame_at = disco_started
                            last_disco_index = None
                        else:
                            name = profile_names[current_profile - 1]
                            enable(api, profile_paths[name]["normal"])
                            last_key = "normal"
                            last_disco_index = None
                elif msg.message == WM_QUIT:
                    return
                else:
                    api.TranslateMessage(ctypes.byref(msg))
                    api.DispatchMessageW(ctypes.byref(msg))
            if settings_root is not None:
                try:
                    settings_root.update()
                except Exception:
                    settings_root = None
                    settings_window = None
            if pending_geometry is not None:
                new_radius, new_thickness = pending_geometry
                pending_geometry = None
                update_geometry(new_radius, new_thickness)
            now = time.monotonic()
            if (current_profile != 0 and disco_active and now >= next_frame_at):
                frame_index = disco_frame_index(now - disco_started)
                if frame_index != last_disco_index:
                    enable(api, disco_paths[frame_index])
                    last_disco_index = frame_index
                next_frame_at = now + FRAME_INTERVAL
            elif (current_profile != 0 and not disco_active
                  and active_since is not None and now >= next_frame_at):
                frame = animation_frame(now - active_since, duration)
                if frame is None:
                    key = "normal"
                    active_since = None
                elif frame[1]:
                    key = frame[0]
                else:
                    key = "hidden"
                if key != last_key:
                    name = profile_names[current_profile - 1]
                    enable(api, profile_paths[name][key])
                    last_key = key
                next_frame_at = now + FRAME_INTERVAL
            time.sleep(0.01)
    finally:
        try:
            if mouse_hook_handle:
                api.UnhookWindowsHookEx(mouse_hook_handle)
        finally:
            try:
                if cursor_modified:
                    restore(api)
                    cursor_modified = False
                    print("The Windows pointer has been restored.")
            finally:
                try:
                    if console_handler_registered:
                        api.SetConsoleCtrlHandler(ctypes.cast(console_handler, ctypes.c_void_p), False)
                finally:
                    for hotkey_id in registered_ids:
                        api.UnregisterHotKey(None, hotkey_id)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Show a high-contrast ring around the mouse pointer on Windows.")
    parser.add_argument("--color", help="Color profile name, such as yellow, white, or black.")
    parser.add_argument("--config", type=Path, default=CONFIG_PATH,
                        help="Path to the configuration file (default: config.json next to the script).")
    parser.add_argument("--list-colors", action="store_true", help="List color profiles and exit.")
    parser.add_argument("--restore", action="store_true", help="Restore the Windows pointer scheme.")
    args = parser.parse_args(argv)

    if args.restore:
        if os.name != "nt":
            parser.error("--restore only works on Windows.")
        restore(windows_api())
        print("The Windows pointer has been restored.")
        return

    try:
        ensure_config(args.config)
        default, colors, hotkey, duration, ring_radius, ring_thickness = load_settings(args.config)
    except (ConfigurationError, OSError) as exc:
        parser.error(str(exc))

    if args.list_colors:
        for name, hex_color in colors.items():
            label = " (default)" if name == default else ""
            print(f"{name}: {hex_color}{label}")
        print(f"Hotkey: {hotkey} | Animation: {duration:g} seconds")
        return

    chosen = args.color or default
    if chosen not in colors:
        parser.error(f"Unknown color '{chosen}'. Choose one of: {', '.join(colors)}")
    if os.name != "nt":
        parser.error("This program only runs on Windows.")

    api = windows_api()
    try:
        system_arrow, arrow_hotspot = capture_system_arrow(api)
        with tempfile.TemporaryDirectory() as tempdir:
            profile_names = list(colors)
            profile_paths = {}
            profile_dirs = {}
            for name in profile_names:
                profile_dir = Path(tempdir) / name
                profile_dir.mkdir()
                profile_dirs[name] = profile_dir
                profile_paths[name] = prepare_frames(
                    profile_dir, parse_hex_color(colors[name]), ring_radius, ring_thickness,
                    system_arrow, arrow_hotspot,
                )
            disco_root = Path(tempdir) / "disco"
            disco_paths = prepare_disco_frames(
                disco_root / f"thickness_{ring_thickness}", ring_radius, ring_thickness,
                system_arrow, arrow_hotspot,
            )
            initial_profile = profile_names.index(chosen) + 1
            run(api, profile_paths, profile_dirs, profile_names, colors,
                args.config, initial_profile, hotkey, duration, ring_radius, ring_thickness,
                system_arrow, arrow_hotspot, disco_paths, disco_root)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
