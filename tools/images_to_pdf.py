#!/usr/bin/env python3
"""Собрать PDF точного формата из картинок страниц: по странице на лист.

Для двусторонней печати страницы идут по порядку: лицо, оборот, лицо, оборот.

Пример:
    python3 tools/images_to_pdf.py side-1.png side-2.png -o flyer-a5.pdf --size a5
"""

import argparse
import os
import sys
import tempfile

import img2pdf
from PIL import Image

MM = 1 / 25.4
SIZES = {"a4": (210.0, 297.0), "a5": (148.0, 210.0), "a6": (105.0, 148.0),
         "letter": (215.9, 279.4)}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("images", nargs="+", help="страницы по порядку")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--size", default="a5", help="формат листа: a4, a5, a6, letter или ШхВ в мм")
    ap.add_argument("--landscape", action="store_true", help="положить лист горизонтально")
    ap.add_argument("--fit", choices=["contain", "cover"], default="cover",
                    help="cover -- заполнить лист с обрезкой (по умолчанию), contain -- целиком с полями")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--background", default="#ffffff")
    args = ap.parse_args()

    if args.size.lower() in SIZES:
        w_mm, h_mm = SIZES[args.size.lower()]
    else:
        try:
            w_mm, h_mm = (float(v) for v in args.size.lower().split("x"))
        except ValueError:
            sys.exit(f"Не понимаю формат листа: {args.size}")
    if args.landscape:
        w_mm, h_mm = h_mm, w_mm

    px_mm = args.dpi * MM
    pw, ph = round(w_mm * px_mm), round(h_mm * px_mm)

    tmpdir = tempfile.mkdtemp(prefix="img2pdf-")
    sheets = []
    for i, path in enumerate(args.images, start=1):
        src = Image.open(path).convert("RGB")
        scale = max if args.fit == "cover" else min
        f = scale(pw / src.width, ph / src.height)
        src = src.resize((max(1, round(src.width * f)), max(1, round(src.height * f))), Image.LANCZOS)
        page = Image.new("RGB", (pw, ph), args.background)
        page.paste(src, ((pw - src.width) // 2, (ph - src.height) // 2))
        out = os.path.join(tmpdir, f"page{i:03d}.png")
        page.save(out, "PNG", dpi=(args.dpi, args.dpi))
        sheets.append(out)

    layout = img2pdf.get_layout_fun((img2pdf.mm_to_pt(w_mm), img2pdf.mm_to_pt(h_mm)))
    with open(args.output, "wb") as fh:
        fh.write(img2pdf.convert(sheets, layout_fun=layout))
    print(f"{args.output}: страниц {len(sheets)}, лист {w_mm:g}x{h_mm:g} мм, растр {pw}x{ph} px")


if __name__ == "__main__":
    main()
