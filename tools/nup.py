#!/usr/bin/env python3
"""Разложить копии изделия сеткой на печатный лист.

Изделие может быть односторонним (одна страница) или двусторонним (две).
Все копии на листе одинаковые, поэтому после печати лист режется по сетке
и получается нужное число готовых экземпляров.

Переворот при двусторонней печати. Содержимое здесь вертикальное на
вертикальном листе, поэтому переворот по длинной стороне даёт правильную
ориентацию оборота сам собой, а по короткой -- требует поворота на 180
градусов, что инструмент и делает.

Пример:
    python3 tools/nup.py ru.png en.png -o cards-a4.pdf --sheet a4 --grid 2x2 --flip long
"""

import argparse
import os
import sys
import tempfile

import img2pdf
from PIL import Image, ImageDraw

MM = 1 / 25.4
SHEETS = {"a4": (210.0, 297.0), "a3": (297.0, 420.0), "letter": (215.9, 279.4)}


def fit(img, w, h, mode, background):
    slot = Image.new("RGB", (w, h), background)
    if img is None:
        return slot
    src = img.convert("RGB")
    scale = max if mode == "cover" else min
    f = scale(w / src.width, h / src.height)
    src = src.resize((max(1, round(src.width * f)), max(1, round(src.height * f))), Image.LANCZOS)
    slot.paste(src, ((w - src.width) // 2, (h - src.height) // 2))
    return slot


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pages", nargs="+", help="лицо и, если нужно, оборот изделия")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--sheet", default="a4", help="лист: a4, a3, letter или ШxВ в мм")
    ap.add_argument("--landscape", action="store_true")
    ap.add_argument("--grid", default="2x2", help="сетка КОЛОНКИxСТРОКИ")
    ap.add_argument("--flip", choices=["short", "long"], default="long",
                    help="сторона переворота при двусторонней печати")
    ap.add_argument("--fit", choices=["contain", "cover"], default="cover")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--background", default="#ffffff")
    ap.add_argument("--cut-marks", action="store_true", help="метки реза по краям листа")
    args = ap.parse_args()

    if len(args.pages) > 2:
        sys.exit("Ожидается одна страница (одностороннее изделие) или две (лицо и оборот).")
    if args.sheet.lower() in SHEETS:
        w_mm, h_mm = SHEETS[args.sheet.lower()]
    else:
        try:
            w_mm, h_mm = (float(v) for v in args.sheet.lower().split("x"))
        except ValueError:
            sys.exit(f"Не понимаю формат листа: {args.sheet}")
    if args.landscape:
        w_mm, h_mm = h_mm, w_mm
    cols, rows = (int(v) for v in args.grid.lower().split("x"))

    px_mm = args.dpi * MM
    sw, sh = round(w_mm * px_mm), round(h_mm * px_mm)
    cw, ch = sw // cols, sh // rows
    print(f"Лист {w_mm:g}x{h_mm:g} мм, сетка {cols}x{rows}, "
          f"ячейка {cw / px_mm:.1f}x{ch / px_mm:.1f} мм")

    pages = [Image.open(p) for p in args.pages]
    sides = [pages[0], pages[1] if len(pages) > 1 else None]

    tmpdir = tempfile.mkdtemp(prefix="nup-")
    files = []
    for idx, page in enumerate(sides):
        if page is None:
            continue
        sheet = Image.new("RGB", (sw, sh), args.background)
        cell = fit(page, cw, ch, args.fit, args.background)
        for r in range(rows):
            for c in range(cols):
                sheet.paste(cell, (c * cw, r * ch))
        if idx == 1 and args.flip == "short":
            sheet = sheet.rotate(180)
        if args.cut_marks:
            d = ImageDraw.Draw(sheet)
            length = round(4 * px_mm)
            for c in range(1, cols):
                x = c * cw
                d.line([(x, 0), (x, length)], fill=(0, 0, 0), width=2)
                d.line([(x, sh - length), (x, sh)], fill=(0, 0, 0), width=2)
            for r in range(1, rows):
                y = r * ch
                d.line([(0, y), (length, y)], fill=(0, 0, 0), width=2)
                d.line([(sw - length, y), (sw, y)], fill=(0, 0, 0), width=2)
        path = os.path.join(tmpdir, f"side{idx + 1}.png")
        sheet.save(path, "PNG", dpi=(args.dpi, args.dpi))
        files.append(path)

    layout = img2pdf.get_layout_fun((img2pdf.mm_to_pt(w_mm), img2pdf.mm_to_pt(h_mm)))
    with open(args.output, "wb") as fh:
        fh.write(img2pdf.convert(files, layout_fun=layout))
    print(f"{args.output}: сторон {len(files)}, копий на листе {cols * rows}, "
          f"переворот по {'короткой' if args.flip == 'short' else 'длинной'} стороне")


if __name__ == "__main__":
    main()
