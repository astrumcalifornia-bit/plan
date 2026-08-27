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
    ap.add_argument("--pad", type=int, default=16, help="запас вокруг, где восстанавливается подложка")
    ap.add_argument("--sigma", type=float, default=14, help="радиус сглаживания подложки")
    ap.add_argument("--ink", default="26,26,26", help="цвет модулей, R,G,B")
    ap.add_argument("--margin", type=float, default=SVG_MARGIN,
                    help="доля поля вокруг модулей в файле кода")
    args = ap.parse_args()

    x0, y0, x1, y1 = (int(v) for v in args.box.split(","))
    ink = np.array([float(v) for v in args.ink.split(",")])

    page = np.asarray(Image.open(args.page).convert("RGB")).astype(np.float32)
    rx0, ry0 = x0 - args.pad, y0 - args.pad
    rx1, ry1 = x1 + args.pad + 1, y1 + args.pad + 1
    reg = page[ry0:ry1, rx0:rx1]

    # подложка: среднее по светлым пикселям, тёмные модули не участвуют
    light = (reg.mean(axis=2) > 200).astype(np.float32)[:, :, None]
    num = cv2.GaussianBlur(reg * light, (0, 0), args.sigma)
    den = cv2.GaussianBlur(np.repeat(light, 3, axis=2), (0, 0), args.sigma)
    backing = num / np.maximum(den, 1e-3)

    # маска старых модулей: только их и стираем
    box = reg[y0 - ry0:y1 - ry0 + 1, x0 - rx0:x1 - rx0 + 1]
    dark = (box.max(axis=2) < 120) & ((box.max(axis=2) - box.min(axis=2)) < 45)
    old = np.zeros(reg.shape[:2], np.uint8)
    old[y0 - ry0:y1 - ry0 + 1, x0 - rx0:x1 - rx0 + 1] = dark
    old = cv2.dilate(old, np.ones((5, 5), np.uint8)).astype(np.float32)[:, :, None]
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
