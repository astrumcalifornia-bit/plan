#!/usr/bin/env python3
"""Заменить QR-код на растровой странице, сохранив его подложку.

Плоская заливка белым оставляет заметный квадрат, если под кодом лежит
подложка с градиентом или тенью. Поэтому подложка восстанавливается
сглаживанием по светлым пикселям (старые модули в расчёт не берутся),
а новый код накладывается по альфе.

Переписываются только пиксели старых модулей и новых: рамка, обводка или
любой другой элемент, попавший в зону работы, остаётся нетронутым.

Пример:
    python3 tools/swap_qr.py page.png new-qr.svg --box 780,1210,969,1399 -o page-new.png
"""

import argparse
import os

import cv2
import numpy as np
from PIL import Image

SVG_MARGIN = 48 / 1024          # поле вокруг модулей в QR-кодах с lnk.at


def render_qr(path, modules_px, margin_frac):
    """Отрисовать код так, чтобы его модули заняли ровно modules_px пикселей."""
    canvas = int(round(modules_px / (1 - 2 * margin_frac)))
    if path.lower().endswith(".svg"):
        import cairosvg
        tmp = path + ".raster.png"
        cairosvg.svg2png(url=path, write_to=tmp, output_width=canvas * 8, output_height=canvas * 8)
        img = Image.open(tmp).convert("L").resize((canvas, canvas), Image.LANCZOS)
        os.remove(tmp)
    else:
        img = Image.open(path).convert("L").resize((canvas, canvas), Image.LANCZOS)
    return np.asarray(img).astype(np.float32), canvas


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("page", help="страница-картинка, на которой стоит старый код")
    ap.add_argument("qr", help="новый код: SVG или PNG")
    ap.add_argument("--box", required=True, metavar="X0,Y0,X1,Y1",
                    help="габарит модулей старого кода в пикселях страницы")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--pad", default="16", metavar="N|NX,NY",
                    help="запас вокруг зоны работы; можно задать по горизонтали и вертикали раздельно, "
                         "если старый код выходил за рамку размещения только с одной стороны")
    ap.add_argument("--sigma", type=float, default=14, help="радиус сглаживания подложки")
    ap.add_argument("--ink", default="26,26,26", help="цвет модулей, R,G,B")
    ap.add_argument("--margin", type=float, default=SVG_MARGIN,
                    help="доля поля вокруг модулей в файле кода")
    ap.add_argument("--dark", type=int, default=170,
                    help="порог яркости, ниже которого пиксель считается модулем старого кода")
    args = ap.parse_args()

    x0, y0, x1, y1 = (int(v) for v in args.box.split(","))
    ink = np.array([float(v) for v in args.ink.split(",")])

    pads = [int(v) for v in args.pad.split(",")]
    pad_x, pad_y = (pads * 2)[:2]

    page = np.asarray(Image.open(args.page).convert("RGB")).astype(np.float32)
    rx0, ry0 = x0 - pad_x, y0 - pad_y
    rx1, ry1 = x1 + pad_x + 1, y1 + pad_y + 1
    reg = page[ry0:ry1, rx0:rx1]

    # подложка: среднее по светлым пикселям, тёмные модули не участвуют
    light = (reg.mean(axis=2) > 200).astype(np.float32)[:, :, None]
    num = cv2.GaussianBlur(reg * light, (0, 0), args.sigma)
    den = cv2.GaussianBlur(np.repeat(light, 3, axis=2), (0, 0), args.sigma)
    backing = num / np.maximum(den, 1e-3)

    # маска старых модулей: нейтрально-тёмное по всей зоне работы. Старый код
    # мог быть крупнее нового, поэтому ищем не только внутри рамки размещения;
    # цветные элементы (рамка, надпись) по цветности отсеиваются и уцелеют.
    span = reg.max(axis=2) - reg.min(axis=2)
    dark = (reg.max(axis=2) < args.dark) & (span < 45)
    old = cv2.dilate(dark.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(np.float32)[:, :, None]
    reg_new = reg * (1 - old) + backing * old

    qr, canvas = render_qr(args.qr, x1 - x0 + 1, args.margin)
    alpha = np.clip(1.0 - qr / 255.0, 0, 1)
    off = int(round(args.margin * canvas))
    full = np.zeros(reg.shape[:2], np.float32)
    full[y0 - off - ry0:y0 - off - ry0 + canvas, x0 - off - rx0:x0 - off - rx0 + canvas] = alpha
    a = full[:, :, None]
    page[ry0:ry1, rx0:rx1] = reg_new * (1 - a) + ink * a

    Image.fromarray(np.clip(page, 0, 255).astype(np.uint8)).save(args.output)
    ok, infos, _, _ = cv2.QRCodeDetector().detectAndDecodeMulti(cv2.imread(args.output))
    print(f"{args.output}: код заменён, чтение со страницы — {ok} {infos if ok else ''}")


if __name__ == "__main__":
    main()
