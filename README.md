# CursorRing

CursorRing highlights the mouse pointer with a clear, adjustable ring. It is designed for presenters who point at maps during screen recordings, especially when recording a single application window instead of the entire desktop.

The ring uses a bright color with contrasting black and white outlines to stay visible over varied map backgrounds. You can change its color, diameter, and outline thickness while the program is running. A brief animated effect helps viewers find the pointer.

## Install and run

Requirements: **Windows 10 or 11**, **Python 3.10 or newer**, and **Pillow**.

```powershell
python -m pip install -r requirements.txt
python cursor_ring.py
```

On first launch, CursorRing creates `config.json` in the same folder as `cursor_ring.py`. The file stores the color profiles and ring settings.

Keep the terminal open while CursorRing is running. Press **Ctrl+C** or click the terminal window's **X** button to exit; CursorRing attempts to restore the Windows pointer scheme in either case.

## Keyboard and mouse controls

| Input | Action |
| --- | --- |
| **Ctrl+Alt+1** | Restore the normal Windows pointer. |
| **Ctrl+Alt+2** | Select the first color profile. |
| **Ctrl+Alt+3** | Select the second color profile. |
| **Ctrl+Alt+4** | Select the third color profile. |
| **Ctrl+Alt+0** | Open the color settings window. |
| **Ctrl+Alt+R** | Play the find animation on the active ring profile. |
| **Ctrl+Shift + mouse wheel** | Increase or decrease the ring diameter. Scroll up to enlarge it; down to reduce it. |
| **Ctrl+Alt + mouse wheel** | Increase or decrease the outline thickness. Scroll up to thicken it; down to thin it. |

Each wheel step changes the diameter by 4 pixels. Diameter and thickness stay within supported limits so the ring fits inside the cursor image. Both settings are saved in `config.json` and retained after restarting CursorRing.

The find animation pulses and blinks the ring for a short time while keeping the mouse arrow visible. Press **Ctrl+Alt+R** again during the animation to restart it. The animation does not run while the normal Windows pointer is selected.

## Change profile colors

Press **Ctrl+Alt+0** to open the color settings window. Choose a color for each profile, then click **Save**. The active ring updates immediately, and the new colors are saved for future runs. Click **Cancel** to discard unsaved changes.

The default profiles are:

| Shortcut | Profile | Default color |
| --- | --- | --- |
| **Ctrl+Alt+2** | Yellow | `#FFE500` |
| **Ctrl+Alt+3** | White | `#FFFFFF` |
| **Ctrl+Alt+4** | Black | `#111111` |

Profile shortcuts follow the order of the profiles in the `colors` section of `config.json`.

## Configuration and command-line options

`config.json` is created with these defaults:

```json
{
  "default_color": "yellow",
  "colors": {
    "yellow": "#FFE500",
    "white": "#FFFFFF",
    "black": "#111111"
  },
  "hotkey": "ctrl+alt+r",
  "animation_seconds": 2.4,
  "ring_radius": 23,
  "ring_thickness": 1
}
```

The color settings window is the easiest way to change profile colors. You can also start the program with a different profile or configuration file:

```powershell
python cursor_ring.py --color white
python cursor_ring.py --color black
python cursor_ring.py --list-colors
python cursor_ring.py --config .\config.json
python cursor_ring.py --restore
```

The configured animation shortcut and duration can be changed in `config.json`. Do not assign `ctrl+alt+0` through `ctrl+alt+4` to the animation shortcut; those are used for settings and profile selection.

## Screen recording

CursorRing changes the Windows system pointer so it can be captured alongside the pointer in a recording. In OBS Studio, try **Window Capture** with **Capture Cursor** enabled and make a short test recording. Capture behavior can vary between applications and recording methods, so check the resulting video before using CursorRing for a presentation.

> CursorRing changes the pointer across the entire Windows session, not just inside the recorded window. If the process is forcibly terminated or the pointer is not restored, run `python cursor_ring.py --restore` or select the normal pointer scheme in Windows mouse settings.
