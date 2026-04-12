#!/usr/bin/env python3
"""
Sourcerer Build Script
──────────────────────
Orchestrates the full font build pipeline:

  1. Instances variable fonts into static TTFs (fontTools.instancer)
  2. Applies outline fixes via FontForge (overlap removal)
  3. Scales glyphs (if GLYPH_XSCALE/YSCALE ≠ 100%)
  4. Applies vertical metrics, line height, rename
  5. Exports to TTF → ./out/ttf/
  6. Post-processes TTFs: style flags, modify lowercase e
  7. Generates Kobo (KF) variants via kobofix.py

Uses FontForge (detected automatically).
Run with: python3 build.py
"""

import os
import shutil
import subprocess
import sys
import textwrap

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#
# Most of these values are safe to tweak. The --customize flag only toggles
# a small subset at runtime (family name, outline fixes).
#
# Quick reference (what each knob does):
# - REGULAR_VF / ITALIC_VF: input variable fonts from ./src
# - DEFAULT_FAMILY: default output family name
# - VARIANT_STYLES: (style, source VF, wght) per-style instancing
# - OPTICAL_SIZE: opsz axis value (shared across all styles)
# - GLYPH_XSCALE / GLYPH_YSCALE: post-instance glyph scaling (%)
# - LINE_HEIGHT: Typo line height (default line spacing)
# - SELECTION_HEIGHT: Win/hhea selection box height and clipping
# - ASCENDER_RATIO: ascender share of total height
# - STYLE_MAP: naming/weight metadata per style

ROOT_DIR    = os.path.dirname(os.path.abspath(__file__))
SRC_DIR     = os.path.join(ROOT_DIR, "src")
OUT_DIR     = os.path.join(ROOT_DIR, "out")
OUT_TTF_DIR = os.path.join(OUT_DIR, "ttf")  # generated TTFs
OUT_KF_DIR  = os.path.join(OUT_DIR, "kf")   # Kobo (KF) variants

REGULAR_VF = os.path.join(SRC_DIR, "SourceSerif4Variable-Roman.ttf")
ITALIC_VF  = os.path.join(SRC_DIR, "SourceSerif4Variable-Italic.ttf")

with open(os.path.join(ROOT_DIR, "VERSION")) as _vf:
    FONT_VERSION = _vf.read().strip()

with open(os.path.join(ROOT_DIR, "COPYRIGHT")) as _cf:
    COPYRIGHT_TEXT = _cf.read().strip()

DEFAULT_FAMILY = "Sourcerer"  # default if --customize not used

OPTICAL_SIZE = 20       # opsz axis: 8 (caption) → 20 (text) → 60 (display)
GLYPH_XSCALE = 100     # horizontal glyph scaling (100 = no change)
GLYPH_YSCALE = 100     # vertical glyph scaling   (100 = no change)

VARIANT_STYLES = [
    # (style_suffix, source_vf, wght)
    ("Regular",    REGULAR_VF, 450),
    ("Bold",       REGULAR_VF, 700),
    ("Italic",     ITALIC_VF,  450),
    ("BoldItalic", ITALIC_VF,  700),
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# INLINE FONTFORGE SCRIPT CONFIG
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Vertical metrics + line spacing (relative to UPM)
# - LINE_HEIGHT drives OS/2 Typo metrics (default line spacing)
# - SELECTION_HEIGHT drives Win/hhea metrics (selection box + clipping)
# - ASCENDER_RATIO splits the total height between ascender/descender
LINE_HEIGHT = 1.0
SELECTION_HEIGHT = 1.0
ASCENDER_RATIO = 0.8

# ttfautohint options (hinting for Kobo's FreeType renderer)
AUTOHINT_OPTS = [
    "--no-info",
    "--stem-width-mode=nss",
    # "--increase-x-height=0",
    # '--x-height-snapping-exceptions=-',
]

# Naming and style metadata (used by the rename step)
STYLE_MAP = {
    "Regular":    ("Regular",     "Book", 400),
    "Bold":       ("Bold",        "Bold", 700),
    "Italic":     ("Italic",      "Book", 400),
    "BoldItalic": ("Bold Italic", "Bold", 700),
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FONTFORGE_CMD = None

def find_fontforge():
    """Detect FontForge on the system. Returns a command list."""
    global FONTFORGE_CMD
    if FONTFORGE_CMD is not None:
        return FONTFORGE_CMD

    # 1. fontforge on PATH (native install, Homebrew, Windows, etc.)
    if shutil.which("fontforge"):
        FONTFORGE_CMD = ["fontforge"]
        return FONTFORGE_CMD

    # 2. Flatpak (Linux)
    if shutil.which("flatpak"):
        result = subprocess.run(
            ["flatpak", "info", "org.fontforge.FontForge"],
            capture_output=True,
        )
        if result.returncode == 0:
            FONTFORGE_CMD = [
                "flatpak", "run",
                "--command=fontforge", "org.fontforge.FontForge",
            ]
            return FONTFORGE_CMD

    # 3. macOS app bundle
    mac_paths = [
        "/Applications/FontForge.app/Contents/MacOS/FontForge",
        "/Applications/FontForge.app/Contents/Resources/opt/local/bin/fontforge",
    ]
    for mac_path in mac_paths:
        if os.path.isfile(mac_path):
            FONTFORGE_CMD = [mac_path]
            return FONTFORGE_CMD

    print(
        "ERROR: FontForge not found.\n"
        "Install it via your package manager, Flatpak, or from https://fontforge.org",
        file=sys.stderr,
    )
    sys.exit(1)


def run_fontforge_script(script_text):
    """Run a Python script inside FontForge."""
    cmd = find_fontforge() + ["-lang=py", "-script", "-"]
    result = subprocess.run(
        cmd,
        input=script_text,
        capture_output=True,
        text=True,
    )
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        # FontForge prints various info/warnings to stderr; filter noise
        for line in result.stderr.splitlines():
            if line.startswith("Copyright") or line.startswith(" License") or \
               line.startswith(" Version") or line.startswith(" Based on") or \
               line.startswith(" with many parts") or \
               "pkg_resources is deprecated" in line or \
               "Invalid 2nd order spline" in line:
                continue
            print(f"  [stderr] {line}", file=sys.stderr)
    if result.returncode != 0:
        print(f"\nERROR: FontForge script exited with code {result.returncode}", file=sys.stderr)
        sys.exit(1)


def build_per_font_script(open_path, save_path, steps):
    """
    Build a FontForge Python script that opens a font file, runs the given
    step scripts (which expect `f` to be the active font), saves as .sfd,
    and closes.

    Each step is a (label, script_body) tuple. The script_body should use `f`
    as the font variable.
    """
    parts = [
        f'import fontforge',
        f'f = fontforge.open({open_path!r})',
        f'print("\\nOpened: " + f.fontname + "\\n")',
    ]
    for label, body in steps:
        parts.append(f'print("── {label} ──\\n")')
        parts.append(body)
    parts.append(f'f.save({save_path!r})')
    parts.append(f'print("\\nSaved: {save_path}\\n")')
    parts.append('f.close()')
    return "\n".join(parts)


def ff_remove_overlaps_script():
    """FontForge script: merge overlapping contours and fix direction."""
    return textwrap.dedent("""\
        f.selection.all()
        f.removeOverlap()
        f.correctDirection()

        count = sum(1 for g in f.glyphs() if g.isWorthOutputting())
        print(f"  Removed overlaps and corrected direction for {count} glyphs")
    """)


def ff_scale_glyphs_script():
    """FontForge script: scale all glyphs horizontally and/or vertically."""
    return textwrap.dedent(f"""\
        import psMat

        xscale = {GLYPH_XSCALE} / 100.0
        yscale = {GLYPH_YSCALE} / 100.0

        mat = psMat.scale(xscale, yscale)
        count = 0
        for g in f.glyphs():
            if not g.isWorthOutputting():
                continue
            g.transform(mat)
            g.width = int(round(g.width * xscale))
            count += 1

        print(f"  Scaled {{count}} glyphs (x={{xscale:.2f}}, y={{yscale:.2f}})")
    """)


def ff_metrics_script():
    """FontForge script: measure landmarks and set OS/2 Typo metrics."""
    return textwrap.dedent("""\
def _bbox(name):
    # Return bounding box (xmin, ymin, xmax, ymax) or None.
    if name in f and f[name].isWorthOutputting():
        bb = f[name].boundingBox()
        if bb != (0, 0, 0, 0):
            return bb
    return None

def measure_chars(chars, *, axis="top"):
    # Measure a set of reference characters.
    #   axis="top"    -> return the highest yMax
    #   axis="bottom" -> return the lowest  yMin
    # Returns (value, display_char) or (None, None).
    idx  = 3 if axis == "top" else 1
    pick = max if axis == "top" else min
    hits = []
    for ch in chars:
        name = fontforge.nameFromUnicode(ord(ch))
        bb = _bbox(name)
        if bb is not None:
            hits.append((bb[idx], ch))
    if not hits:
        return None, None
    return pick(hits, key=lambda t: t[0])

def scan_font_extremes():
    # Walk every output glyph; return (yMax, yMin, max_name, min_name).
    y_max, y_min = 0, 0
    max_nm, min_nm = None, None
    for g in f.glyphs():
        if not g.isWorthOutputting():
            continue
        bb = g.boundingBox()
        if bb == (0, 0, 0, 0):
            continue
        if bb[3] > y_max:
            y_max, max_nm = bb[3], g.glyphname
        if bb[1] < y_min:
            y_min, min_nm = bb[1], g.glyphname
    return y_max, y_min, max_nm, min_nm

print("─── Design landmarks ───\\n")

cap_h, cap_c = measure_chars("HIOX", axis="top")
asc_h, asc_c = measure_chars("bdfhkl", axis="top")
xht_h, xht_c = measure_chars("xuvw", axis="top")
dsc_h, dsc_c = measure_chars("gpqyj", axis="bottom")

for label, val, ch in [
    ("Cap height", cap_h, cap_c),
    ("Ascender",   asc_h, asc_c),
    ("x-height",   xht_h, xht_c),
    ("Descender",  dsc_h, dsc_c),
]:
    if val is not None:
        print(f"  {label:12s}  {int(val):>6}  ('{ch}')")
    else:
        print(f"  {label:12s}  {'N/A':>6}")

print("\\n─── Full font scan ───\\n")

font_ymax, font_ymin, ymax_name, ymin_name = scan_font_extremes()
print(f"  Highest glyph:  {int(font_ymax):>6}  ({ymax_name})")
print(f"  Lowest  glyph:  {int(font_ymin):>6}  ({ymin_name})")

upm = f.em

design_top = asc_h if asc_h is not None else cap_h
design_bot = dsc_h   # negative value

if design_top is None or design_bot is None:
    raise SystemExit(
        "ERROR: Could not measure ascender/cap-height or descender.\\n"
        "       Make sure your font contains basic Latin glyphs (H, b, p, etc.)."
    )

typo_ascender  = int(round(design_top))
typo_descender = int(round(design_bot))

f.os2_typoascent  = typo_ascender
f.os2_typodescent = typo_descender
f.os2_typolinegap = 0

if hasattr(f, "os2_xheight") and xht_h is not None:
    f.os2_xheight = int(round(xht_h))
if hasattr(f, "os2_capheight") and cap_h is not None:
    f.os2_capheight = int(round(cap_h))

# Win/hhea set to same initial values; lineheight step overrides these.
f.os2_winascent  = typo_ascender
f.os2_windescent = abs(typo_descender)
f.hhea_ascent    = typo_ascender
f.hhea_descent   = typo_descender
f.hhea_linegap   = 0

typo_metrics_set = False

if hasattr(f, "os2_use_typo_metrics"):
    f.os2_use_typo_metrics = True
    typo_metrics_set = True

if not typo_metrics_set and hasattr(f, "os2_fsselection"):
    f.os2_fsselection |= (1 << 7)
    typo_metrics_set = True

if not typo_metrics_set:
    if hasattr(f, "os2_version") and f.os2_version < 4:
        f.os2_version = 4

if not typo_metrics_set:
    print("  WARNING: Could not set USE_TYPO_METRICS programmatically.")
    print("  -> In Font Info -> OS/2 -> Misc, tick 'USE_TYPO_METRICS'.\\n")

typo_line = typo_ascender - typo_descender

print(f"\\n─── Applied metrics ───\\n")
print(f"  UPM:  {upm}")
print(f"  Typo: {typo_ascender} / {typo_descender} (ink span: {typo_line}, {typo_line/upm:.2f}x UPM)")

if cap_h is not None:
    print(f"  Cap height:   {int(cap_h)}")
if xht_h is not None:
    print(f"  x-height:     {int(xht_h)}")
""")


def ff_lineheight_script():
    """FontForge script: set line height and selection box metrics."""
    return textwrap.dedent(f"""\
        # Line height (Typo) as a multiple of UPM.
        LINE_HEIGHT = {LINE_HEIGHT}

        # Selection box height (Win/hhea) as a multiple of UPM.
        SELECTION_HEIGHT = {SELECTION_HEIGHT}

        # Ascender share of the line/selection height.
        ASCENDER_RATIO = {ASCENDER_RATIO}

        upm = f.em

        # OS/2 Typo — controls line spacing
        typo_total = int(round(upm * LINE_HEIGHT))
        typo_asc   = int(round(typo_total * ASCENDER_RATIO))
        typo_dsc   = typo_asc - typo_total   # negative

        f.os2_typoascent  = typo_asc
        f.os2_typodescent = typo_dsc
        f.os2_typolinegap = 0

        # Win/hhea — controls selection box height and clipping
        sel_total = int(round(upm * SELECTION_HEIGHT))
        sel_asc   = int(round(sel_total * ASCENDER_RATIO))
        sel_dsc   = sel_total - sel_asc

        f.hhea_ascent    = sel_asc
        f.hhea_descent   = -sel_dsc
        f.hhea_linegap   = 0
        f.os2_winascent  = sel_asc
        f.os2_windescent = sel_dsc

        print(f"  Typo: {{typo_asc}} / {{typo_dsc}} / gap 0  (line height: {{typo_total}}, {LINE_HEIGHT:.2f}x UPM)")
        print(f"  hhea: {{sel_asc}} / {{-sel_dsc}} / gap 0  (selection: {{sel_total}}, {SELECTION_HEIGHT:.2f}x UPM)")
        print(f"  Win:  {{sel_asc}} / {{sel_dsc}}")
    """)


def ff_rename_script():
    """FontForge script: update font name metadata."""
    style_map = repr(STYLE_MAP)
    return textwrap.dedent(f"""\
        # FAMILY is injected by build.py; default if run standalone.
        if "FAMILY" not in dir():
            FAMILY = "Sourcerer"

        STYLE_MAP = {style_map}

        # Determine style from the current fontname (e.g. "Sourcerer-BoldItalic")
        style_suffix = f.fontname.split("-")[-1] if "-" in f.fontname else "Regular"
        style_display, ps_weight, os2_weight = STYLE_MAP.get(
            style_suffix, (style_suffix, "Book", 400)
        )

        f.fontname = f"{{FAMILY}}-{{style_suffix}}"
        f.familyname = FAMILY
        f.fullname = f"{{FAMILY}} {{style_display}}"
        f.weight = ps_weight
        f.os2_weight = os2_weight

        # Set head.macStyle for style linking if supported by FontForge
        if hasattr(f, "macstyle"):
            macstyle = f.macstyle
            macstyle &= ~((1 << 0) | (1 << 1))
            if "Bold" in style_suffix:
                macstyle |= (1 << 0)
            if "Italic" in style_suffix:
                macstyle |= (1 << 1)
            f.macstyle = macstyle

        lang = "English (US)"

        f.appendSFNTName(lang, "Family", FAMILY)
        f.appendSFNTName(lang, "SubFamily", style_display)
        f.appendSFNTName(lang, "Fullname", f"{{FAMILY}} {{style_display}}")
        f.appendSFNTName(lang, "PostScriptName", f"{{FAMILY}}-{{style_suffix}}")
        f.appendSFNTName(lang, "Preferred Family", FAMILY)
        f.appendSFNTName(lang, "Preferred Styles", style_display)
        f.appendSFNTName(lang, "Compatible Full", f"{{FAMILY}} {{style_display}}")
        f.appendSFNTName(lang, "UniqueID", f"{{FAMILY}} {{style_display}}")

        # Clear Source Serif-specific entries
        f.appendSFNTName(lang, "Trademark", "")
        f.appendSFNTName(lang, "Manufacturer", "")
        f.appendSFNTName(lang, "Designer", "")
        f.appendSFNTName(lang, "Vendor URL", "")
        f.appendSFNTName(lang, "Designer URL", "")

        count = 0
        for _name in f.sfnt_names:
            count += 1
        print(f"  Updated {{count}} name entries for {{FAMILY}} {{style_display}}")
        print(f"  PS weight: {{ps_weight}}, OS/2 usWeightClass: {{os2_weight}}")
    """)


def ff_version_script():
    """FontForge script: set font version."""
    return textwrap.dedent("""\
        # VERSION is injected by build.py before this script runs.
        version_str = "Version " + VERSION

        f.version = VERSION
        f.sfntRevision = float(VERSION)
        f.appendSFNTName("English (US)", "Version", version_str)

        print(f"  Version set to: {version_str}")
        print(f"  head.fontRevision set to: {float(VERSION)}")
    """)


def ff_license_script():
    """FontForge script: set copyright."""
    return textwrap.dedent("""\
        # COPYRIGHT_TEXT is injected by build.py before this script runs.
        lang = "English (US)"

        f.copyright = COPYRIGHT_TEXT
        f.appendSFNTName(lang, "Copyright", COPYRIGHT_TEXT)

        print(f"  Copyright: {COPYRIGHT_TEXT.splitlines()[0]}")
    """)


def build_export_script(sfd_path, ttf_path):
    """Build a FontForge script that opens an .sfd and exports to TTF."""
    return textwrap.dedent(f"""\
        import fontforge

        f = fontforge.open({sfd_path!r})
        print("Exporting: " + f.fontname)

        flags = ("opentype", "no-FFTM-table")
        f.generate({ttf_path!r}, flags=flags)

        print("  -> " + {ttf_path!r})
        f.close()
    """)


def clean_ttf_degenerate_contours(ttf_path):
    """Remove zero-area contours (<=2 points) from a TTF in-place."""
    try:
        from fontTools.ttLib import TTFont
        from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates
    except Exception:
        print("  [warn] Skipping cleanup: fontTools not available", file=sys.stderr)
        return

    font = TTFont(ttf_path)
    glyf = font["glyf"]  # type: ignore[index]

    removed_total = 0
    modified = set()
    for name in font.getGlyphOrder():
        glyph = glyf[name]  # type: ignore[index]
        if glyph.isComposite():
            continue
        end_pts = getattr(glyph, "endPtsOfContours", None)
        if not end_pts:
            continue

        coords = glyph.coordinates
        flags = glyph.flags

        new_coords = []
        new_flags = []
        new_end_pts = []

        start = 0
        removed = 0
        for end in end_pts:
            count = end - start + 1
            if count <= 2:
                removed += 1
            else:
                new_coords.extend(coords[start:end + 1])
                new_flags.extend(flags[start:end + 1])
                new_end_pts.append(len(new_coords) - 1)
            start = end + 1

        if removed:
            removed_total += removed
            modified.add(name)
            glyph.coordinates = GlyphCoordinates(new_coords)
            glyph.flags = new_flags
            glyph.endPtsOfContours = new_end_pts
            glyph.numberOfContours = len(new_end_pts)

    if removed_total:
        glyph_set = font.getGlyphSet()
        for name in modified:
            glyph = glyf[name]  # type: ignore[index]
            if hasattr(glyph, "recalcBounds"):
                glyph.recalcBounds(glyph_set)
        if hasattr(glyf, "recalcBounds"):
            glyf.recalcBounds(glyph_set)  # type: ignore[attr-defined]
        font.save(ttf_path)
        print(f"  Cleaned {removed_total} zero-area contour(s)")
    font.close()



def fix_ttf_style_flags(ttf_path, style_suffix):
    """Normalize OS/2 fsSelection and head.macStyle for style linking."""
    try:
        from fontTools.ttLib import TTFont
    except Exception:
        print("  [warn] Skipping style flag fix: fontTools not available", file=sys.stderr)
        return

    font = TTFont(ttf_path)
    os2 = font["OS/2"]
    head = font["head"]

    fs_sel = os2.fsSelection
    fs_sel &= ~((1 << 0) | (1 << 5) | (1 << 6))
    if style_suffix == "Regular":
        fs_sel |= (1 << 6)
    if "Italic" in style_suffix:
        fs_sel |= (1 << 0)
    if "Bold" in style_suffix:
        fs_sel |= (1 << 5)
    os2.fsSelection = fs_sel

    macstyle = 0
    if "Bold" in style_suffix:
        macstyle |= (1 << 0)
    if "Italic" in style_suffix:
        macstyle |= (1 << 1)
    head.macStyle = macstyle

    font.save(ttf_path)
    font.close()
    print(f"  Normalized style flags for {style_suffix}")


def fix_e_ink_trap(ttf_path):
    """Remove the ink trap notch on the 'e' glyph's inner counter.

    Source Serif 4 has an ink trap where the crossbar meets the right
    side of the bowl — a small concave notch designed for small printed
    text.  On e-readers this serves no purpose and looks odd.

    Detection: in the inner counter contour, find the pattern
      on A → on B (horizontal) → off C → off D → on E
    where B is the right end of the crossbar and E is the bowl's right
    side above.  Fix: extend B rightward to E.x and drop C/D.
    """
    from fontTools.ttLib import TTFont
    from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates

    font = TTFont(ttf_path)
    glyf = font["glyf"]
    cmap = font.getBestCmap()

    e_name = cmap.get(ord('e'))
    if not e_name:
        font.close()
        return

    g = glyf[e_name]
    if not g.numberOfContours or g.numberOfContours < 2:
        font.close()
        return

    coords = list(g.coordinates)
    flag_list = list(g.flags)
    ends = list(g.endPtsOfContours)

    modified = False
    new_coords = []
    new_flags = []
    new_ends = []

    prev_end = -1
    for ci, end_pt in enumerate(ends):
        start = prev_end + 1
        c_coords = [(coords[j][0], coords[j][1]) for j in range(start, end_pt + 1)]
        c_flags = [flag_list[j] for j in range(start, end_pt + 1)]
        n = len(c_coords)

        to_remove = set()
        to_adjust = {}

        for j in range(n - 4):
            af, bf = c_flags[j] & 1, c_flags[j+1] & 1
            cf, df = c_flags[j+2] & 1, c_flags[j+3] & 1
            ef = c_flags[j+4] & 1

            # Pattern: on, on (horizontal), off, off, on
            if not (af and bf and not cf and not df and ef):
                continue

            a, b, e = c_coords[j], c_coords[j+1], c_coords[j+4]

            # Horizontal segment (same y)
            if abs(a[1] - b[1]) > 5:
                continue
            # B is the rightmost point of the crossbar
            if a[0] >= b[0]:
                continue
            # E is to the right of and above B (bowl curving up)
            if e[0] <= b[0] or e[1] <= b[1]:
                continue
            # Gap should be meaningful (ink trap) but not huge
            if not (10 < e[0] - b[0] < 100):
                continue

            # Fix: extend B to E.x, remove the two off-curve points
            to_adjust[j+1] = (e[0], b[1])
            to_remove.add(j+2)
            to_remove.add(j+3)
            modified = True
            break

        for j in range(n):
            if j in to_remove:
                continue
            new_coords.append(to_adjust[j] if j in to_adjust else c_coords[j])
            new_flags.append(c_flags[j])

        new_ends.append(len(new_coords) - 1)
        prev_end = end_pt

    if modified:
        g.coordinates = GlyphCoordinates(new_coords)
        g.flags = new_flags
        g.endPtsOfContours = new_ends
        g.numberOfContours = len(new_ends)
        glyph_set = font.getGlyphSet()
        if hasattr(g, "recalcBounds"):
            g.recalcBounds(glyph_set)
        font.save(ttf_path)
        print(f"  Fixed ink trap on 'e'")

    font.close()


def autohint_ttf(ttf_path):
    """Run ttfautohint to add proper TrueType hinting.

    Kobo uses FreeType for font rasterization. Without embedded hints,
    FreeType's auto-hinter computes "blue zones" from the outlines.
    ttfautohint replaces FreeType's built-in auto-hinter with its own
    hinting. The resulting bytecode is baked into the font, so FreeType
    uses the TrueType interpreter instead of falling back to auto-hinting.
    """
    if not shutil.which("ttfautohint"):
        print("  [warn] ttfautohint not found, skipping", file=sys.stderr)
        return

    tmp_path = ttf_path + ".autohint.tmp"
    result = subprocess.run(
        ["ttfautohint"] + AUTOHINT_OPTS + [ttf_path, tmp_path],
        capture_output=True, text=True,
    )

    if result.returncode != 0:
        print(f"  [warn] ttfautohint failed: {result.stderr.strip()}", file=sys.stderr)
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        return

    os.replace(tmp_path, ttf_path)
    print(f"  Autohinted with ttfautohint")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def check_ttfautohint():
    """Verify ttfautohint is installed before starting the build."""
    if shutil.which("ttfautohint"):
        return
    print(
        "ERROR: ttfautohint not found.\n"
        "\n"
        "ttfautohint is required for proper rendering on Kobo e-readers.\n"
        "Install it with:\n"
        "  macOS/Bazzite:      brew install ttfautohint\n"
        "  Debian/Ubuntu:      sudo apt install ttfautohint\n"
        "  Fedora:             sudo dnf install ttfautohint\n"
        "  Arch:               sudo pacman -S ttfautohint\n",
        file=sys.stderr,
    )
    sys.exit(1)


KOBOFIX_URL = (
    "https://raw.githubusercontent.com/nicoverbruggen/kobo-font-fix/main/kobofix.py"
)


def _download_kobofix(dest):
    """Download kobofix.py if not already cached."""
    if os.path.isfile(dest):
        print(f"  Using cached kobofix.py")
        return
    import urllib.request
    print(f"  Downloading kobofix.py ...")
    urllib.request.urlretrieve(KOBOFIX_URL, dest)
    print(f"  Saved to {dest}")


def _run_kobofix(kobofix_path, variant_names):
    """Run kobofix.py --preset kf on built TTFs, move KF_ files to out/kf/."""
    ttf_files = [os.path.join(OUT_TTF_DIR, f"{n}.ttf") for n in variant_names]
    cmd = [sys.executable, kobofix_path, "--preset", "kf"] + ttf_files
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout, end="")
    if result.returncode != 0:
        print("\nERROR: kobofix.py failed", file=sys.stderr)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        sys.exit(1)

    os.makedirs(OUT_KF_DIR, exist_ok=True)
    import glob
    moved = 0
    for kf_file in glob.glob(os.path.join(OUT_TTF_DIR, "KF_*.ttf")):
        dest = os.path.join(OUT_KF_DIR, os.path.basename(kf_file))
        shutil.move(kf_file, dest)
        moved += 1
    print(f"  Moved {moved} KF font(s) to {OUT_KF_DIR}/")


def main():
    print("=" * 60)
    print("  Sourcerer Build")
    print("=" * 60)

    ff_cmd = find_fontforge()
    print(f"  FontForge: {' '.join(ff_cmd)}")
    check_ttfautohint()
    print(f"  ttfautohint: {shutil.which('ttfautohint')}")

    family   = DEFAULT_FAMILY
    outline_fix  = True

    # --name "Foo" sets the family name directly
    if "--name" in sys.argv:
        idx = sys.argv.index("--name")
        if idx + 1 < len(sys.argv):
            family = sys.argv[idx + 1]
        else:
            print("ERROR: --name requires a value", file=sys.stderr)
            sys.exit(1)

    if "--customize" in sys.argv:
        print()
        family = input(f"  Font family name [{family}]: ").strip() or family
        outline_input = input("  Apply outline fixes (remove overlaps + zero-area cleanup)? [Y/n]: ").strip().lower()
        outline_fix = outline_input not in ("n", "no")

    print()
    print(f"  Family:      {family}")
    print(f"  Outline fix: {'yes' if outline_fix else 'no'}")
    print(f"  Optical size: {OPTICAL_SIZE}")
    print(f"  Glyph scale: {GLYPH_XSCALE}% x {GLYPH_YSCALE}%")
    print()

    tmp_dir = os.path.join(ROOT_DIR, "tmp")
    if os.path.exists(tmp_dir):
        shutil.rmtree(tmp_dir)
    os.makedirs(tmp_dir)

    try:
        _build(tmp_dir, family=family, outline_fix=outline_fix)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _build(tmp_dir, family=DEFAULT_FAMILY, outline_fix=True):
    variants = [(f"{family}-{style}", vf, wght)
                for style, vf, wght in VARIANT_STYLES]
    variant_names = [name for name, _, _ in variants]

    # Step 1: Instance variable fonts into static TTFs
    print("\n── Step 1: Instance variable fonts ──\n")

    for name, vf_path, wght in variants:
        ttf_out = os.path.join(tmp_dir, f"{name}.ttf")
        print(f"  Instancing {name} (wght={wght}, opsz={OPTICAL_SIZE})")

        cmd = [
            sys.executable, "-m", "fontTools.varLib.instancer",
            vf_path,
            f"wght={wght}",
            f"opsz={OPTICAL_SIZE}",
            "-o", ttf_out,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.stdout:
            print(result.stdout, end="")
        if result.returncode != 0:
            print(f"\nERROR: instancer failed for {name}", file=sys.stderr)
            if result.stderr:
                print(result.stderr, file=sys.stderr)
            sys.exit(1)


    print(f"  {len(variants)} font(s) instanced.")

    # Step 2: Apply outline fixes (opens TTF, saves as SFD)
    print("\n── Step 2: Outline fixes ──\n")

    overlap_code = ff_remove_overlaps_script()
    needs_scaling = GLYPH_XSCALE != 100 or GLYPH_YSCALE != 100
    scale_code = ff_scale_glyphs_script() if needs_scaling else None

    for name in variant_names:
        ttf_path = os.path.join(tmp_dir, f"{name}.ttf")
        sfd_path = os.path.join(tmp_dir, f"{name}.sfd")
        print(f"Processing: {name}")

        steps = []
        if outline_fix:
            steps.append(("Removing overlaps", overlap_code))
        if scale_code:
            steps.append(("Scaling glyphs", scale_code))
        script = build_per_font_script(ttf_path, sfd_path, steps)
        run_fontforge_script(script)

    # Step 3: Apply metrics and rename (opens SFD, saves as SFD)
    print("\n── Step 3: Apply metrics and rename ──\n")

    metrics_code = ff_metrics_script()
    lineheight_code = ff_lineheight_script()
    rename_code = ff_rename_script()
    version_code = ff_version_script()
    license_code = ff_license_script()

    for name in variant_names:
        sfd_path = os.path.join(tmp_dir, f"{name}.sfd")
        print(f"Processing: {name}")
        print("-" * 40)

        # Set fontname so rename.py can detect the correct style suffix
        set_fontname = f'f.fontname = {name!r}'
        set_family   = f'FAMILY = {family!r}'
        set_version  = f'VERSION = {FONT_VERSION!r}'
        set_license  = f'COPYRIGHT_TEXT = {COPYRIGHT_TEXT!r}'

        script = build_per_font_script(sfd_path, sfd_path, [
            ("Setting vertical metrics", metrics_code),
            ("Adjusting line height", lineheight_code),
            ("Setting fontname for rename", set_fontname),
            ("Updating font names", set_family + "\n" + rename_code),
            ("Setting version", set_version + "\n" + version_code),
            ("Setting license", set_license + "\n" + license_code),
        ])
        run_fontforge_script(script)

    # Step 4: Export to out/ttf
    print("\n── Step 4: Export ──\n")
    os.makedirs(OUT_TTF_DIR, exist_ok=True)

    for name in variant_names:
        sfd_path = os.path.join(tmp_dir, f"{name}.sfd")
        ttf_path = os.path.join(OUT_TTF_DIR, f"{name}.ttf")
        style_suffix = name.split("-")[-1] if "-" in name else "Regular"

        # Export TTF
        script = build_export_script(sfd_path, ttf_path)
        run_fontforge_script(script)
        if outline_fix:
            clean_ttf_degenerate_contours(ttf_path)
        fix_ttf_style_flags(ttf_path, style_suffix)
        fix_e_ink_trap(ttf_path)
        autohint_ttf(ttf_path)


    # Step 5: Generate Kobo (KF) variants via kobofix.py
    print("\n── Step 5: Generate Kobo (KF) variants ──\n")

    kobofix_path = os.path.join(tmp_dir, "kobofix.py")
    _download_kobofix(kobofix_path)
    _run_kobofix(kobofix_path, variant_names)

    print("\n" + "=" * 60)
    print("  Build complete!")
    print(f"  TTF fonts are in: {OUT_TTF_DIR}/")
    print(f"  KF fonts are in:  {OUT_KF_DIR}/")
    print("=" * 60)


if __name__ == "__main__":
    main()
