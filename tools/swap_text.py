#!/usr/bin/env python3
"""Заменить строку текста на растровой странице.

Старые буквы стираются восстановлением по краям (inpainting): фактура и тон
бумаги вокруг остаются нетронутыми, в отличие от заливки прямоугольником.
Новый текст рисуется тем же цветом и подгоняется по высоте под старый;
если он не влезает в отведённую ширину, кегль уменьшается, а не выходит
за границу.

Пример:
    python3 tools/swap_text.py cover.png "tatiksvareniki.com" \\
        --box 777,1259,915,1279 --font Anton.ttf --limit-x 955 -o cover-new.png
"""

import argparse

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


def ink_bbox(mask):
    ys, xs = np.where(mask)
    return xs.min(), ys.min(), xs.max(), ys.max()


def render_line(text, font_path, size, tracking):
    font = ImageFont.truetype(font_path, size)
    img = Image.new("L", (4000, size * 4), 0)
    draw = ImageDraw.Draw(img)
    x = 50.0
    for ch in text:
        draw.text((x, size), ch, fill=255, font=font)
        x += draw.textlength(ch, font=font) + tracking
    arr = np.asarray(img)
    x0, y0, x1, y1 = ink_bbox(arr > 40)
    return arr[y0:y1 + 1, x0:x1 + 1].astype(np.float32) / 255.0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("page")
    ap.add_argument("text", help="новая строка")
    ap.add_argument("--box", required=True, metavar="X0,Y0,X1,Y1", help="габарит старого текста")
    ap.add_argument("--font", required=True)
    ap.add_argument("--tracking", type=float, default=0.0, help="межбуквенный интервал, px")
    ap.add_argument("--limit-x", type=int, help="правая граница, за которую нельзя заходить")
    ap.add_argument("--color", help="цвет текста R,G,B; по умолчанию берётся со старого")
    ap.add_argument("--grow", type=int, default=2, help="насколько расширить маску букв перед стиранием")
    ap.add_argument("-o", "--output", required=True)
    args = ap.parse_args()

    x0, y0, x1, y1 = (int(v) for v in args.box.split(","))
    page = np.asarray(Image.open(args.page).convert("RGB")).astype(np.float32)

    old = page[y0:y1 + 1, x0:x1 + 1]
    paper = np.median(old.reshape(-1, 3), axis=0)
    strokes = np.abs(old - paper).sum(axis=2) > 60
    # цвет берём по ядру букв, без размытых краёв: самые тёмные пиксели рамки
    lum = old.mean(axis=2)
    core = lum <= np.percentile(lum, 12)
    color = (np.array([float(v) for v in args.color.split(",")]) if args.color
             else np.median(old[core], axis=0))

    # стереть старые буквы, дорисовав бумагу от их краёв
    mask = np.zeros(page.shape[:2], np.uint8)
    mask[y0:y1 + 1, x0:x1 + 1] = strokes.astype(np.uint8) * 255
    if args.grow:
        k = np.ones((args.grow * 2 + 1,) * 2, np.uint8)
        mask = cv2.dilate(mask, k)
    page = cv2.inpaint(np.clip(page, 0, 255).astype(np.uint8), mask, 4,
                       cv2.INPAINT_TELEA).astype(np.float32)

    target_h = y1 - y0 + 1
    max_w = (args.limit_x - x0) if args.limit_x else (x1 - x0 + 1)
    glyphs = None
    for size in range(target_h * 3, 4, -1):                 # подобрать кегль по высоте
        g = render_line(args.text, args.font, size, args.tracking)
        if g.shape[0] > target_h:
            continue
        if g.shape[1] > max_w:                              # не влезает по ширине -- мельче
            continue
        glyphs = g
        break
    if glyphs is None:
        raise SystemExit("Не удалось подобрать кегль: строка не помещается в отведённое место.")

    gh, gw = glyphs.shape
    ty = y0 + (target_h - gh)                                # выровнять по базовой линии
    a = glyphs[:, :, None]
    dst = page[ty:ty + gh, x0:x0 + gw]
    page[ty:ty + gh, x0:x0 + gw] = dst * (1 - a) + color * a

    Image.fromarray(np.clip(page, 0, 255).astype(np.uint8)).save(args.output)
    print(f"{args.output}: «{args.text}» — {gw}x{gh} px, кегль подобран, "
          f"цвет {color.astype(int).tolist()}, правый край {x0 + gw}")


if __name__ == "__main__":
    main()
