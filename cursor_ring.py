"""Windows: röd ring som en del av muspekaren (Python + Pillow).

Kör: python cursor_ring.py
Återställ efter tvångsavslut: python cursor_ring.py --restore
"""

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import struct
import sys
import tempfile

from PIL import Image, ImageDraw

SIZE = 64
CENTER = SIZE // 2
RADIUS = 24
THICKNESS = 4
RED = (235, 20, 30, 255)

SPI_SETCURSORS = 0x0057
IMAGE_CURSOR = 2
LR_LOADFROMFILE = 0x0010
OCR_NORMAL = 32512
OCR_HAND = 32649


def create_cursor(path: Path):
    """Skapa en 32-bitars .cur-fil med genomskinlig bakgrund."""
    scale = 4
    canvas = Image.new('RGBA', (SIZE * scale, SIZE * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    cx = cy = CENTER * scale
    r = RADIUS * scale

    draw.ellipse((cx-r, cy-r, cx+r, cy+r), outline=RED, width=THICKNESS * scale)

    # Normal muspil. Spetsen ligger exakt på ringens mitt.
    outline = [(32, 32), (33, 53), (39, 47), (45, 57),
               (50, 54), (44, 44), (53, 43)]
    points = [(x * scale, y * scale) for x, y in outline]
    draw.polygon(points, fill='white')
    draw.line(points + [points[0]], fill='black', width=2 * scale, joint='curve')

    image = canvas.resize((SIZE, SIZE), Image.Resampling.LANCZOS)

    # CUR använder ett BMP-liknande format: BGRA underifrån och en AND-mask.
    xor = b''.join(image.crop((0, y, SIZE, y + 1)).tobytes('raw', 'BGRA')
                   for y in range(SIZE - 1, -1, -1))

    alpha = image.getchannel('A')
    stride = ((SIZE + 31) // 32) * 4
    mask = bytearray()
    for y in range(SIZE - 1, -1, -1):
        row = bytearray(stride)
        for x in range(SIZE):
            if alpha.getpixel((x, y)) == 0:
                row[x // 8] |= 0x80 >> (x % 8)
        mask.extend(row)

    dib_header = struct.pack('<IiiHHIIiiII', 40, SIZE, SIZE * 2,
                             1, 32, 0, len(xor), 0, 0, 0, 0)
    bitmap = dib_header + xor + mask

    # Hotspot mitt i ringen: klickpunkten ska inte flyttas.
    directory = struct.pack('<HHH', 0, 2, 1)
    entry = struct.pack('<BBBBHHII', SIZE, SIZE, 0, 0,
                        CENTER, CENTER, len(bitmap), 22)
    path.write_bytes(directory + entry + bitmap)


def windows_api():
    api = ctypes.WinDLL('user32', use_last_error=True)
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
        if not api.SetSystemCursor(handle, cursor_id):
            raise ctypes.WinError(ctypes.get_last_error())


def main():
    if os.name != 'nt':
        sys.exit('Detta skript fungerar bara i Windows.')
    api = windows_api()
    if '--restore' in sys.argv:
        restore(api)
        print('Windows-muspekaren är återställd.')
        return

    # Även ett misslyckat startförsök återställer pekarna.
    try:
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / 'rod_ring.cur'
            create_cursor(path)
            enable(api, path)
            print('Röd ring aktiv. Tryck Ctrl+C i terminalen för att avsluta.')
            import time
            while True:
                time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        restore(api)
        print('Windows-muspekaren är återställd.')


if __name__ == '__main__':
    main()
