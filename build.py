#!/usr/bin/env python3
"""
Cartisse build script.

Builds Cartisse from the static XCharter OTF sources in ./src:

1. Opens each OTF with FontForge
2. Applies outline cleanup (optional)
3. Removes selected ligature substitutions
4. Saves temporary SFDs
5. Applies metrics, line height, renaming, version, and copyright
6. Exports TTFs to ./out/ttf/
7. Post-processes TTFs (style flags)
8. Runs kobo-font-fix to generate Kobo variants in ./out/kf/

Run with:
  python3 build.py

If you are using Homebrew Python, create and activate a virtualenv first:
  python3 -m venv .venv
  source .venv/bin/activate
  pip install fonttools
"""

import os
import shutil
import subprocess
import sys
import textwrap
from typing import Optional


ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(ROOT_DIR, "src")
OUT_DIR = os.path.join(ROOT_DIR, "out")
OUT_TTF_DIR = os.path.join(OUT_DIR, "ttf")
OUT_KF_DIR = os.path.join(OUT_DIR, "kf")

with open(os.path.join(ROOT_DIR, "VERSION")) as version_file:
    FONT_VERSION = version_file.read().strip()

with open(os.path.join(ROOT_DIR, "COPYRIGHT")) as copyright_file:
    COPYRIGHT_TEXT = copyright_file.read().strip()

DEFAULT_FAMILY = "Cartisse"

SOURCE_STYLES = [
    ("Regular", os.path.join(SRC_DIR, "XCharter-Roman.otf")),
    ("Bold", os.path.join(SRC_DIR, "XCharter-Bold.otf")),
    ("Italic", os.path.join(SRC_DIR, "XCharter-Italic.otf")),
    ("BoldItalic", os.path.join(SRC_DIR, "XCharter-BoldItalic.otf")),
]

STYLE_MAP = {
    "Regular": ("Regular", "Book", 400),
    "Bold": ("Bold", "Bold", 700),
    "Italic": ("Italic", "Book", 400),
    "BoldItalic": ("Bold Italic", "Bold", 700),
}

LIGATURE_GLYPHS = ("ff", "fi", "fl", "ffi", "ffl")
MANUAL_KERN_PAIRS = (
    ("f", "i", -35),
    ("f", "l", -35),
)

# Additional line height expressed as a percentage of UPM.
# 0.20 means "add 20% line height", not "set total line height to 1.20 here".
LINE_HEIGHT = 0.20
ASCENDER_RATIO = 0.80

KOBOFIX_URL = "https://raw.githubusercontent.com/nicoverbruggen/kobo-font-fix/v0.6/kobofix.py"

FONTFORGE_CMD: Optional[list[str]] = None


def require_fonttools():
    try:
        __import__("fontTools")
    except Exception:
        print(
            "ERROR: fontTools is not installed.\n"
            "\n"
            "If you are using Homebrew Python, use a virtual environment:\n"
            "  python3 -m venv .venv\n"
            "  source .venv/bin/activate\n"
            "  pip install fonttools\n",
            file=sys.stderr,
        )
        sys.exit(1)


def find_fontforge():
    global FONTFORGE_CMD
    if FONTFORGE_CMD is not None:
        return FONTFORGE_CMD

    if shutil.which("fontforge"):
        FONTFORGE_CMD = ["fontforge"]
        return FONTFORGE_CMD

    if shutil.which("flatpak"):
        result = subprocess.run(
            ["flatpak", "info", "org.fontforge.FontForge"],
            capture_output=True,
        )
        if result.returncode == 0:
            FONTFORGE_CMD = [
                "flatpak",
                "run",
                "--command=fontforge",
                "org.fontforge.FontForge",
            ]
            return FONTFORGE_CMD

    mac_paths = [
        "/Applications/FontForge.app/Contents/Resources/opt/local/bin/fontforge",
        "/Applications/FontForge.app/Contents/MacOS/FontForge",
    ]
    for mac_path in mac_paths:
        if os.path.isfile(mac_path):
            FONTFORGE_CMD = [mac_path]
            return FONTFORGE_CMD

    print(
        "ERROR: FontForge not found.\n"
        "Install it via Homebrew, Flatpak, or from https://fontforge.org\n",
        file=sys.stderr,
    )
    sys.exit(1)


def run_fontforge_script(script_text):
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
        for line in result.stderr.splitlines():
            if (
                line.startswith("Copyright")
                or line.startswith(" License")
                or line.startswith(" Version")
                or line.startswith(" Based on")
                or line.startswith(" with many parts")
                or "pkg_resources" in line
            ):
                continue
            print(f"  [stderr] {line}", file=sys.stderr)

    if result.returncode != 0:
        print(
            f"\nERROR: FontForge script exited with code {result.returncode}",
            file=sys.stderr,
        )
        sys.exit(1)


def build_per_font_script(open_path, save_path, steps):
    parts = [
        "import fontforge",
        f"f = fontforge.open({open_path!r})",
        "print('\\nOpened: ' + f.fontname + '\\n')",
    ]
    for label, body in steps:
        parts.append(f"print('── {label} ──\\n')")
        parts.append(body)
    parts.append(f"f.save({save_path!r})")
    parts.append(f"print('\\nSaved: {save_path}\\n')")
    parts.append("f.close()")
    return "\n".join(parts)


def ff_remove_overlaps_script():
    return textwrap.dedent(
        """\
        f.selection.all()
        f.removeOverlap()
        f.correctDirection()
        count = sum(1 for g in f.glyphs() if g.isWorthOutputting())
        print(f"  Removed overlaps and corrected direction for {count} glyphs")
        """
    )


def ff_remove_ligatures_script():
    ligatures = repr(LIGATURE_GLYPHS)
    return textwrap.dedent(
        f"""\
        TARGETS = {ligatures}
        removed = 0
        cleared = 0

        for glyph_name in TARGETS:
            if glyph_name not in f:
                continue

            glyph = f[glyph_name]
            try:
                possubs = glyph.getPosSub('*')
            except Exception:
                possubs = ()

            for entry in possubs:
                if len(entry) >= 2 and entry[1] == 'Ligature':
                    glyph.removePosSub(entry[0])
                    removed += 1

            glyph.clear()
            glyph.unicode = -1
            glyph.width = 0
            cleared += 1

        print(f"  Removed {{removed}} ligature substitution(s)")
        print(f"  Cleared {{cleared}} ligature glyph(s)")
        """
    )


def ff_add_kern_pairs_script():
    kern_pairs = repr(MANUAL_KERN_PAIRS)
    return textwrap.dedent(
        f"""\
        LOOKUP_NAME = 'Cartisse Manual Kern'
        SUBTABLE_NAME = 'Cartisse Manual Kern Subtable'
        KERN_PAIRS = {kern_pairs}

        if LOOKUP_NAME not in f.gpos_lookups:
            f.addLookup(
                LOOKUP_NAME,
                'gpos_pair',
                (),
                ((('kern', (('latn', ('dflt',)),)),)),
            )
            f.addLookupSubtable(LOOKUP_NAME, SUBTABLE_NAME)

        added = 0
        for left_name, right_name, value in KERN_PAIRS:
            if left_name not in f or right_name not in f:
                continue
            f[left_name].addPosSub(SUBTABLE_NAME, right_name, value)
            added += 1

        print(f"  Added {{added}} manual kern pair(s)")
        """
    )


def ff_metrics_script():
    return textwrap.dedent(
        """\
        def _bbox(name):
            if name in f and f[name].isWorthOutputting():
                bb = f[name].boundingBox()
                if bb != (0, 0, 0, 0):
                    return bb
            return None

        def measure_chars(chars, axis='top'):
            idx = 3 if axis == 'top' else 1
            pick = max if axis == 'top' else min
            hits = []
            for ch in chars:
                name = fontforge.nameFromUnicode(ord(ch))
                bb = _bbox(name)
                if bb is not None:
                    hits.append((bb[idx], ch))
            if not hits:
                return None, None
            return pick(hits, key=lambda item: item[0])

        cap_h, cap_c = measure_chars('HIOX', axis='top')
        asc_h, asc_c = measure_chars('bdfhkl', axis='top')
        xht_h, xht_c = measure_chars('xuvw', axis='top')
        dsc_h, dsc_c = measure_chars('gpqyj', axis='bottom')

        design_top = asc_h if asc_h is not None else cap_h
        design_bot = dsc_h

        if design_top is None or design_bot is None:
            raise SystemExit(
                'ERROR: Could not measure ascender/cap-height or descender.'
            )

        f.os2_typoascent = int(round(design_top))
        f.os2_typodescent = int(round(design_bot))
        f.os2_typolinegap = 0
        f.os2_winascent = int(round(design_top))
        f.os2_windescent = abs(int(round(design_bot)))
        f.hhea_ascent = int(round(design_top))
        f.hhea_descent = int(round(design_bot))
        f.hhea_linegap = 0

        if hasattr(f, 'os2_xheight') and xht_h is not None:
            f.os2_xheight = int(round(xht_h))
        if hasattr(f, 'os2_capheight') and cap_h is not None:
            f.os2_capheight = int(round(cap_h))

        typo_metrics_set = False
        if hasattr(f, 'os2_use_typo_metrics'):
            f.os2_use_typo_metrics = True
            typo_metrics_set = True
        if not typo_metrics_set and hasattr(f, 'os2_fsselection'):
            f.os2_fsselection |= (1 << 7)
            typo_metrics_set = True
        if not typo_metrics_set and hasattr(f, 'os2_version') and f.os2_version < 4:
            f.os2_version = 4

        print(f"  Ascender:   {int(round(design_top))} ('{asc_c or cap_c}')")
        print(f"  Descender:  {int(round(design_bot))} ('{dsc_c}')")
        if cap_h is not None:
            print(f"  Cap height: {int(round(cap_h))}")
        if xht_h is not None:
            print(f"  x-height:   {int(round(xht_h))}")
        """
    )


def ff_lineheight_script():
    return textwrap.dedent(
        f"""\
        EXTRA_LINE_HEIGHT = {LINE_HEIGHT}
        ASCENDER_RATIO = {ASCENDER_RATIO}

        upm = f.em
        total_height = int(round(upm * (1.0 + EXTRA_LINE_HEIGHT)))
        asc = int(round(total_height * ASCENDER_RATIO))
        dsc = asc - total_height

        f.os2_typoascent = asc
        f.os2_typodescent = dsc
        f.os2_typolinegap = 0

        f.hhea_ascent = asc
        f.hhea_descent = dsc
        f.hhea_linegap = 0
        f.os2_winascent = asc
        f.os2_windescent = abs(dsc)

        print(f"  Added line height: {{int(round(EXTRA_LINE_HEIGHT * 100))}}%")
        print(f"  Typo: {{asc}} / {{dsc}} / gap 0")
        print(f"  hhea: {{asc}} / {{dsc}} / gap 0")
        print(f"  Win:  {{asc}} / {{abs(dsc)}}")
        """
    )


def ff_rename_script():
    style_map = repr(STYLE_MAP)
    return textwrap.dedent(
        f"""\
        if 'FAMILY' not in dir():
            FAMILY = {DEFAULT_FAMILY!r}

        STYLE_MAP = {style_map}

        style_suffix = f.fontname.split('-')[-1] if '-' in f.fontname else 'Regular'
        style_display, ps_weight, os2_weight = STYLE_MAP.get(
            style_suffix,
            (style_suffix, 'Book', 400),
        )

        f.fontname = f"{{FAMILY}}-{{style_suffix}}"
        f.familyname = FAMILY
        f.fullname = f"{{FAMILY}} {{style_display}}"
        f.weight = ps_weight
        f.os2_weight = os2_weight

        if hasattr(f, 'macstyle'):
            macstyle = f.macstyle
            macstyle &= ~((1 << 0) | (1 << 1))
            if 'Bold' in style_suffix:
                macstyle |= (1 << 0)
            if 'Italic' in style_suffix:
                macstyle |= (1 << 1)
            f.macstyle = macstyle

        lang = 'English (US)'
        f.appendSFNTName(lang, 'Family', FAMILY)
        f.appendSFNTName(lang, 'SubFamily', style_display)
        f.appendSFNTName(lang, 'Fullname', f"{{FAMILY}} {{style_display}}")
        f.appendSFNTName(lang, 'PostScriptName', f"{{FAMILY}}-{{style_suffix}}")
        f.appendSFNTName(lang, 'Preferred Family', FAMILY)
        f.appendSFNTName(lang, 'Preferred Styles', style_display)
        f.appendSFNTName(lang, 'Compatible Full', f"{{FAMILY}} {{style_display}}")
        f.appendSFNTName(lang, 'UniqueID', f"{{FAMILY}} {{style_display}}")

        print(f"  Renamed to {{FAMILY}} {{style_display}}")
        print(f"  PS weight: {{ps_weight}}, OS/2 usWeightClass: {{os2_weight}}")
        """
    )


def ff_version_script():
    return textwrap.dedent(
        """\
        version_str = 'Version ' + VERSION
        f.version = VERSION
        f.sfntRevision = float(VERSION)
        f.appendSFNTName('English (US)', 'Version', version_str)
        print(f"  Version set to: {version_str}")
        """
    )


def ff_license_script():
    return textwrap.dedent(
        """\
        lang = 'English (US)'
        f.copyright = COPYRIGHT_TEXT
        f.appendSFNTName(lang, 'Copyright', COPYRIGHT_TEXT)
        print(f"  Copyright: {COPYRIGHT_TEXT.splitlines()[0]}")
        """
    )


def build_export_script(sfd_path, ttf_path):
    return textwrap.dedent(
        f"""\
        import fontforge

        f = fontforge.open({sfd_path!r})
        print('Exporting: ' + f.fontname)
        flags = ('opentype', 'no-FFTM-table')
        f.generate({ttf_path!r}, flags=flags)
        print('  -> ' + {ttf_path!r})
        f.close()
        """
    )


def fix_ttf_style_flags(ttf_path, style_suffix):
    try:
        tt_lib = __import__("fontTools.ttLib", fromlist=["TTFont"])
        TTFont = tt_lib.TTFont
    except Exception as exc:
        raise RuntimeError("fontTools is required to fix style flags") from exc

    font = TTFont(ttf_path)
    os2 = font["OS/2"]
    head = font["head"]

    fs_selection = os2.fsSelection
    fs_selection &= ~((1 << 0) | (1 << 5) | (1 << 6))
    if style_suffix == "Regular":
        fs_selection |= (1 << 6)
    if "Italic" in style_suffix:
        fs_selection |= (1 << 0)
    if "Bold" in style_suffix:
        fs_selection |= (1 << 5)
    os2.fsSelection = fs_selection

    macstyle = 0
    if "Bold" in style_suffix:
        macstyle |= (1 << 0)
    if "Italic" in style_suffix:
        macstyle |= (1 << 1)
    head.macStyle = macstyle

    font.save(ttf_path)
    font.close()
    print(f"  Normalized style flags for {style_suffix}")


def fix_ttf_version_names(ttf_path):
    """Keep head.fontRevision and name ID 5 in sync with VERSION.

    FontForge's appendSFNTName only adds a Version record when one is
    absent, so stale version strings from the source fonts survive.
    Force-overwrite name ID 5 (Mac + Windows) and head.fontRevision.
    """
    try:
        tt_lib = __import__("fontTools.ttLib", fromlist=["TTFont"])
        TTFont = tt_lib.TTFont
    except Exception as exc:
        raise RuntimeError("fontTools is required to fix version names") from exc

    font = TTFont(ttf_path)
    version_string = f"Version {FONT_VERSION}"
    font["head"].fontRevision = float(FONT_VERSION)
    name_table = font["name"]
    name_table.setName(version_string, 5, 1, 0, 0)
    name_table.setName(version_string, 5, 3, 1, 0x409)
    font.save(ttf_path)
    font.close()
    print(f"  Normalized version names to {version_string}")


def download_kobofix(dest_path):
    if os.path.isfile(dest_path):
        print("  Using cached kobofix.py")
        return

    import urllib.request

    print("  Downloading kobofix.py ...")
    urllib.request.urlretrieve(KOBOFIX_URL, dest_path)
    print(f"  Saved to {dest_path}")


def run_kobofix(kobofix_path, variant_names):
    ttf_files = [os.path.join(OUT_TTF_DIR, f"{name}.ttf") for name in variant_names]
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
    print("  Cartisse Build")
    print("=" * 60)

    require_fonttools()
    ff_cmd = find_fontforge()

    family = DEFAULT_FAMILY
    outline_fix = True

    if "--name" in sys.argv:
        idx = sys.argv.index("--name")
        if idx + 1 >= len(sys.argv):
            print("ERROR: --name requires a value", file=sys.stderr)
            sys.exit(1)
        family = sys.argv[idx + 1]

    if "--customize" in sys.argv:
        print()
        family = input(f"  Font family name [{family}]: ").strip() or family
        outline_input = input(
            "  Apply outline fixes (remove overlaps)? [Y/n]: "
        ).strip().lower()
        outline_fix = outline_input not in ("n", "no")

    print(f"  FontForge: {' '.join(ff_cmd)}")
    print(f"  Family: {family}")
    print(f"  Outline fix: {'yes' if outline_fix else 'no'}")
    print(f"  Extra line height: {int(round(LINE_HEIGHT * 100))}%")

    tmp_dir = os.path.join(ROOT_DIR, "tmp")
    if os.path.exists(tmp_dir):
        shutil.rmtree(tmp_dir)
    os.makedirs(tmp_dir)

    try:
        build(tmp_dir, family=family, outline_fix=outline_fix)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def build(tmp_dir, family=DEFAULT_FAMILY, outline_fix=True):
    variants = [(f"{family}-{style}", style, source_path) for style, source_path in SOURCE_STYLES]
    variant_names = [name for name, _, _ in variants]

    print("\n── Step 1: Import OTFs and save SFDs ──\n")
    overlap_code = ff_remove_overlaps_script()
    ligature_code = ff_remove_ligatures_script()
    manual_kern_code = ff_add_kern_pairs_script()

    for name, _style, source_path in variants:
        sfd_path = os.path.join(tmp_dir, f"{name}.sfd")
        print(f"Processing: {name}")

        steps = []
        if outline_fix:
            steps.append(("Removing overlaps", overlap_code))
        steps.append(("Removing ligature substitutions", ligature_code))
        steps.append(("Adding manual kern pairs", manual_kern_code))

        script = build_per_font_script(source_path, sfd_path, steps)
        run_fontforge_script(script)

    print("\n── Step 2: Apply metrics and metadata ──\n")
    metrics_code = ff_metrics_script()
    lineheight_code = ff_lineheight_script()
    rename_code = ff_rename_script()
    version_code = ff_version_script()
    license_code = ff_license_script()

    for name in variant_names:
        sfd_path = os.path.join(tmp_dir, f"{name}.sfd")
        print(f"Processing: {name}")
        print("-" * 40)

        set_fontname = f"f.fontname = {name!r}"
        set_family = f"FAMILY = {family!r}"
        set_version = f"VERSION = {FONT_VERSION!r}"
        set_license = f"COPYRIGHT_TEXT = {COPYRIGHT_TEXT!r}"

        script = build_per_font_script(
            sfd_path,
            sfd_path,
            [
                ("Setting baseline metrics", metrics_code),
                ("Adjusting line height", lineheight_code),
                ("Setting fontname for rename", set_fontname),
                ("Updating font names", set_family + "\n" + rename_code),
                ("Setting version", set_version + "\n" + version_code),
                ("Setting copyright", set_license + "\n" + license_code),
            ],
        )
        run_fontforge_script(script)

    print("\n── Step 3: Export TTFs ──\n")
    os.makedirs(OUT_TTF_DIR, exist_ok=True)

    for name, style, _source_path in variants:
        sfd_path = os.path.join(tmp_dir, f"{name}.sfd")
        ttf_path = os.path.join(OUT_TTF_DIR, f"{name}.ttf")
        script = build_export_script(sfd_path, ttf_path)
        run_fontforge_script(script)
        fix_ttf_style_flags(ttf_path, style)
        fix_ttf_version_names(ttf_path)

    print("\n── Step 4: Generate Kobo variants ──\n")
    kobofix_path = os.path.join(tmp_dir, "kobofix.py")
    download_kobofix(kobofix_path)
    run_kobofix(kobofix_path, variant_names)

    print("\n" + "=" * 60)
    print("  Build complete!")
    print(f"  TTF fonts are in: {OUT_TTF_DIR}/")
    print(f"  KF fonts are in:  {OUT_KF_DIR}/")
    print("=" * 60)


if __name__ == "__main__":
    main()
