# Cartisse

This repository contains **Cartisse**, a modified version of [XCharter](https://www.ctan.org/tex-archive/fonts/xcharter/), which is an extension for [Bitstream Charter](https://en.wikipedia.org/wiki/Bitstream_Charter).

## What is this?

**Cartisse is specifically intended to be used with Kobo e-readers.** You can also use it for general word processing and the like, but if you need more glyph coverage or advanced typography features I recommend looking at alternatives like [Charis](https://software.sil.org/charis/download/). 

Take a look at a screenshot of it on my [Kobo Libra Color](https://be.kobobooks.com/nl/products/kobo-libra-colour?variant=40852311736406) here:

<kbd><img src="./screenshot.png" width='400px'/></kbd>

This version omits a few ligatures that consistently looked bad on e-ink displays and has adjusted metrics for improved line height.

A more verbose [license](./LICENSE) is also included as part of the distributed font files.

## How was this made?

Automatically, with `build.py`. The following changes are made:

- A few ligatures that did not render well on certain e-readers were removed, namely: `ff`, `ffi`, `ffl`, `fl`, `fi`.
- Minor replacement kern pairs were added for `fi` and `fl` after removing those ligatures.
- Improved line height metrics were set using a 20% line-height adjustment.
- The copyright notice has been updated to reflect the new name.

### Build pipeline

The script processes the original XCharter `.otf` files in `src/` like this:

1. Open the source fonts with FontForge.
2. Remove the `ff`, `fi`, `fl`, `ffi`, and `ffl` ligature substitutions and clear those glyphs.
3. Apply a small replacement kern pair adjustment for `fi` and `fl`.
4. Update vertical metrics, names, version metadata, and copyright text.
5. Export TrueType fonts to `out/ttf/`.
6. Run `kobo-font-fix` to produce Kobo variants in `out/kf/`.

### Building locally

Cartisse is built with Python, FontForge, `fonttools`, and `kobo-font-fix`.

If you are using Homebrew Python on macOS, a virtual environment is recommended:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install fonttools skia-pathops
python build.py
```

You also need FontForge installed and available on your system.

The build script writes normal TrueType fonts to `out/ttf/` and Kobo-ready variants to `out/kf/`.

### Automated builds

This repository also includes a GitHub Actions workflow that builds the fonts automatically and attaches zip files to tagged releases.

### Source files

I've included the original XCharter files in this repository; you can find them in `src/`.

You can download the TrueType version of these fonts via [Releases](https://github.com/nicoverbruggen/cartisse/releases), which are ready to be copied to your favorite e-reader. Alternatively, you can export the source files yourself.

## License

In 1992 Bitstream donated a version of Charter, along with its version of Courier, to the X Consortium under terms that allowed the font to be modified and redistributed.

This font is _not_ related to the proprietary version, Charter BT.

```
Copyright (c) 1989-1992, Bitstream Inc., Cambridge, MA.
Copyright (c) 2009, 2010, 2011, 2012 Andrey V. Panov 
Copyright (c) 2013-2024 Michael Sharpe
Copyright (c) 2025-2026 Nico Verbruggen

XCharter is an extension of Bitstream Charter, whose original license is reproduced below, as required under the terms of that license. The extension provides small caps, oldstyle figures and superior figures in all four styles, accompanied by LaTeX font support files.

Cartisse is based on XCharter, but contains some metrics modifications and removes certain ligatures.

---

You are hereby granted permission under all Bitstream propriety rights
to use, copy, modify, sublicense, sell, and redistribute the 4 Bitstream
Charter (r) Type 1 outline fonts and the 4 Courier Type 1 outline fonts
for any purpose and without restriction; provided, that this notice is
left intact on all copies of such fonts and that Bitstream's trademark
is acknowledged as shown below on all unmodified copies of the 4 Charter
Type 1 fonts.

BITSTREAM CHARTER is a registered trademark of Bitstream Inc.
```
