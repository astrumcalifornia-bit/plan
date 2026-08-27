#!/usr/bin/env python3
"""Собрать двухсторонний макет A4 из картинок страниц A5.

Каждый лист A4 кладётся горизонтально и делится пополам: две страницы A5
рядом. Лист печатается с двух сторон, поэтому в PDF стороны идут парами:
лицо листа 1, оборот листа 1, лицо листа 2, оборот листа 2, ...

Режимы раскладки (--mode):

  booklet  Брошюра на скрепку: стопка листов складывается пополам.
           Порядок страниц переставляется (8|1, 2|7, 6|3, 4|5 для 8 страниц).
           Это то, что нужно, если макет сгибается, а не режется.

  duplicate  Две одинаковые копии на листе: обе половины несут одну и ту же
           страницу. Для двустороннего изделия из двух страниц (лицо и оборот)
           получается один лист, который режется пополам на два готовых экземпляра.

  simple   Разрезать и сложить стопкой: левая половина листов -- первая
           половина страниц, правая -- вторая. После печати пачка режется
           пополам по сгибу, правая стопка кладётся под левую, порядок 1..N.

Порядок страниц берётся из имён файлов (натуральная сортировка: 2 < 10),
либо из явного списка файлов в аргументах.

Пример:
    python3 tools/a5_to_a4.py pages/ -o booklet.pdf --mode booklet
    python3 tools/a5_to_a4.py pages/*.jpg -o print.pdf --mode simple --flip long
"""

import argparse
import os
import re
import sys
import tempfile

from PIL import Image, ImageDraw

import img2pdf

MM = 1 / 25.4
A4_W_MM, A4_H_MM = 210.0, 297.0          # лист A4 (портрет)
SHEET_W_MM, SHEET_H_MM = A4_H_MM, A4_W_MM  # лист в макете лежит горизонтально
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp", ".gif"}


def natural_key(path):
    name = os.path.basename(path)
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", name)]


def collect_pages(inputs):
    files = []
    for item in inputs:
        if os.path.isdir(item):
            found = [
                os.path.join(item, f)
                for f in os.listdir(item)
                if os.path.splitext(f)[1].lower() in IMAGE_EXT
            ]
            files.extend(sorted(found, key=natural_key))
        else:
            files.append(item)
    if not files:
        sys.exit("Не найдено ни одной картинки страницы.")
    missing = [f for f in files if not os.path.isfile(f)]
    if missing:
        sys.exit("Нет таких файлов: " + ", ".join(missing))
    return files


def booklet_order(n_pages):
    """Пары (лево, право) для лицевой и оборотной стороны каждого листа.

    Нумерация страниц с 1, 0 -- пустая страница."""
    sheets = []
    for i in range(n_pages // 4):
        front = (n_pages - 2 * i, 2 * i + 1)
        back = (2 * i + 2, n_pages - 2 * i - 1)
        sheets.append((front, back))
    return sheets


def duplicate_order(n_pages):
    """Две одинаковые копии изделия на листе; 1 или 2 страницы на входе."""
    back = 2 if n_pages > 1 else 0
    return [((1, 1), (back, back))]


def stack_order(n_pages):
    """Раскладка «разрезать и сложить стопкой»."""
    half = n_pages // 2
    sheets = []
    for i in range(n_pages // 4):
        left_front, left_back = 2 * i + 1, 2 * i + 2
        right_front, right_back = half + 2 * i + 1, half + 2 * i + 2
        # На обороте лево и право меняются местами: при перевороте листа
        # левая половина оказывается там, где на лице была правая.
        sheets.append(((left_front, right_front), (right_back, left_back)))
    return sheets


def place(page_img, slot_w, slot_h, fit, background):
    """Вписать страницу в половину листа: contain -- целиком, cover -- в обрез."""
    canvas = Image.new("RGB", (slot_w, slot_h), background)
    if page_img is None:
        return canvas
    src = page_img.convert("RGB")
    scale = max if fit == "cover" else min
    factor = scale(slot_w / src.width, slot_h / src.height)
    new_size = (max(1, round(src.width * factor)), max(1, round(src.height * factor)))
    src = src.resize(new_size, Image.LANCZOS)
    canvas.paste(src, ((slot_w - src.width) // 2, (slot_h - src.height) // 2))
    return canvas


def build_sheet(pair, pages, geom, args):
    sheet = Image.new("RGB", (geom["w"], geom["h"]), args.background)
    slot_w, slot_h = geom["slot_w"], geom["slot_h"]
    for index, page_no in enumerate(pair):
        # Номера сверх реального количества страниц -- добивка до кратности 4.
        img = pages[page_no - 1] if 0 < page_no <= len(pages) else None
        half = place(img, slot_w, slot_h, args.fit, args.background)
        x = geom["margin"] + index * (slot_w + 2 * geom["gutter"])
        sheet.paste(half, (x, geom["margin"]))
    if args.fold_line:
        draw = ImageDraw.Draw(sheet)
        mid = geom["w"] // 2
        step = max(2, geom["h"] // 120)
        for y in range(0, geom["h"], step * 2):
            draw.line([(mid, y), (mid, y + step)], fill=(170, 170, 170), width=1)
    if args.crop_marks:
        draw = ImageDraw.Draw(sheet)
        length = max(6, geom["margin"] or round(5 * geom["px_mm"]))
        for x in (geom["margin"], geom["w"] // 2, geom["w"] - geom["margin"]):
            x = min(max(x, 0), geom["w"] - 1)
            draw.line([(x, 0), (x, length)], fill=(0, 0, 0), width=2)
            draw.line([(x, geom["h"] - length), (x, geom["h"])], fill=(0, 0, 0), width=2)
    return sheet


def main():
    parser = argparse.ArgumentParser(
        description="Двухсторонний макет A4 из страниц A5.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("inputs", nargs="+", help="папка со страницами или список файлов по порядку")
    parser.add_argument("-o", "--output", default="a4-print.pdf", help="итоговый PDF")
    parser.add_argument("--mode", choices=["booklet", "simple", "duplicate"], default="booklet",
                        help="booklet -- брошюра на сгиб (по умолчанию), simple -- разрезать и сложить "
                             "стопкой, duplicate -- две одинаковые копии на листе")
    parser.add_argument("--flip", choices=["short", "long"], default="short",
                        help="сторона переворота при двусторонней печати; для горизонтального макета "
                             "обычно 'по короткой стороне' (short)")
    parser.add_argument("--fit", choices=["contain", "cover"], default="contain",
                        help="contain -- страница целиком (по умолчанию), cover -- заполнить с обрезкой")
    parser.add_argument("--dpi", type=int, default=300, help="разрешение растра, по умолчанию 300")
    parser.add_argument("--margin", type=float, default=0.0, help="поле по краю листа, мм")
    parser.add_argument("--gutter", type=float, default=0.0, help="отступ от линии сгиба, мм")
    parser.add_argument("--background", default="#ffffff", help="цвет фона листа")
    parser.add_argument("--fold-line", action="store_true", help="пунктир по линии сгиба/реза")
    parser.add_argument("--crop-marks", action="store_true", help="метки реза по краям")
    parser.add_argument("--format", choices=["auto", "png", "jpeg"], default="auto",
                        help="как вложить растр в PDF: png без потерь, jpeg компактнее")
    parser.add_argument("--jpeg-quality", type=int, default=95)
    parser.add_argument("--preview", metavar="DIR", help="дополнительно выгрузить листы картинками в папку")
    args = parser.parse_args()

    files = collect_pages(args.inputs)
    pages = [Image.open(f) for f in files]
    n = len(pages)
    if args.mode == "duplicate":
        if n > 2:
            sys.exit("Режим duplicate рассчитан на одну или две страницы (лицо и оборот).")
        padded, order = n, duplicate_order(n)
    else:
        padded = n + (-n % 4)
        order = booklet_order(padded) if args.mode == "booklet" else stack_order(padded)

    px_mm = args.dpi * MM
    geom = {
        "px_mm": px_mm,
        "w": round(SHEET_W_MM * px_mm),
        "h": round(SHEET_H_MM * px_mm),
        "margin": round(args.margin * px_mm),
        "gutter": round(args.gutter * px_mm),
    }
    geom["slot_w"] = (geom["w"] - 2 * geom["margin"] - 2 * geom["gutter"]) // 2
    geom["slot_h"] = geom["h"] - 2 * geom["margin"]

    if args.format == "auto":
        fmt = "jpeg" if any(os.path.splitext(f)[1].lower() in {".jpg", ".jpeg"} for f in files) else "png"
    else:
        fmt = args.format

    sheet_files = []
    tmpdir = tempfile.mkdtemp(prefix="a5toa4-")
    preview_dir = args.preview
    if preview_dir:
        os.makedirs(preview_dir, exist_ok=True)

    for sheet_no, (front, back) in enumerate(order, start=1):
        for side_name, pair in (("front", front), ("back", back)):
            sheet = build_sheet(pair, pages, geom, args)
            # Переворот по длинной стороне разворачивает оборот вверх ногами
            # для горизонтального макета -- компенсируем поворотом на 180 градусов.
            if side_name == "back" and args.flip == "long":
                sheet = sheet.rotate(180)
            path = os.path.join(tmpdir, f"sheet{sheet_no:03d}-{side_name}.{ 'jpg' if fmt=='jpeg' else 'png'}")
            if fmt == "jpeg":
                sheet.save(path, "JPEG", quality=args.jpeg_quality, dpi=(args.dpi, args.dpi), subsampling=0)
            else:
                sheet.save(path, "PNG", dpi=(args.dpi, args.dpi))
            sheet_files.append(path)
            if preview_dir:
                small = sheet.copy()
                small.thumbnail((1400, 1400), Image.LANCZOS)
                small.save(os.path.join(preview_dir, f"sheet{sheet_no:03d}-{side_name}.png"))

    layout = img2pdf.get_layout_fun(
        (img2pdf.mm_to_pt(SHEET_W_MM), img2pdf.mm_to_pt(SHEET_H_MM))
    )
    with open(args.output, "wb") as fh:
        fh.write(img2pdf.convert(sheet_files, layout_fun=layout))

    blanks = padded - n
    print(f"Страниц A5: {n}" + (f" (+{blanks} пустых для кратности 4)" if blanks else ""))
    print(f"Листов A4: {len(order)}, сторон в PDF: {len(sheet_files)}")
    print(f"Режим: {args.mode}, переворот: по {'короткой' if args.flip == 'short' else 'длинной'} стороне")
    print(f"Готово: {args.output}")


if __name__ == "__main__":
    main()
