#!/usr/bin/env python3
"""Свести орнаментальные полосы соседних страниц в один непрерывный бордюр."""
import numpy as np
from PIL import Image

W, H = 1053, 1494
TOP_H, BOT_H = 74, 68          # высота верхней и нижней полосы (как на обложке)
TARGET_BG = np.array([245.0, 227.3, 208.0])
# страница: (высота старой верхней полосы, высота старой нижней полосы, чистый крем y0..y1)
PAGES = {
    "1.png": (84, 60, (544, 573)),
    "2.png": (75, 68, (620, 638)),
    "3.png": (88, 86, (903, 964)),
    "4.png": (101, 95, (750, 766)),
}
FEATHER = 8                    # растушёвка края заплатки, строк


def bg_of(arr, rows):
    """Тон бумаги: медиана по заведомо чистой полосе крема во всю ширину."""
    y0, y1 = rows
    return np.median(arr[y0:y1 + 1].reshape(-1, 3), axis=0)


def normalize_tone(arr, rows):
    """Привести кремовый фон к общему тону, не трогая краску."""
    bg = bg_of(arr, rows)
    dist = np.abs(arr - bg).sum(axis=2)
    mask = np.clip((60.0 - dist) / 35.0, 0.0, 1.0)[:, :, None]
    return np.clip(arr + (TARGET_BG - bg) * mask, 0, 255)


def refine_period(sig, lo=45, hi=110):
    s = sig - sig.mean()
    corr = np.array([float((s[:-p] * s[p:]).mean()) for p in range(lo, hi)])
    i = int(corr.argmax())
    p = lo + i
    if 0 < i < len(corr) - 1:                      # уточнение параболой
        a, b, c = corr[i - 1], corr[i], corr[i + 1]
        denom = a - 2 * b + c
        if denom != 0:
            p += 0.5 * (a - c) / denom
    return p


def tile_strip(band, out_w):
    """Размножить полосу на всю ширину листа без сдвига фазы."""
    sig = band.mean(axis=2).mean(axis=0)
    p = refine_period(sig)
    # подобрать плитку так, чтобы целое число повторов легло точно в ширину листа
    best = None
    for k in range(1, 13):
        tw = int(round(k * p))
        n = max(1, int(round(out_w / tw)))
        err = abs(n * tw - out_w)
        if best is None or err < best[0]:
            best = (err, tw, n)
    _, tw, n = best
    x0 = (band.shape[1] - tw) // 2
    tile = band[:, x0:x0 + tw]
    wide = np.tile(tile, (1, n, 1))
    img = Image.fromarray(wide.astype(np.uint8)).resize((out_w, band.shape[0]), Image.LANCZOS)
    return np.asarray(img).astype(float), p, tw * n / out_w


def cream_block(arr, rows, height):
    y0, y1 = rows
    src = arr[y0:y1 + 1]
    reps = int(np.ceil(height / src.shape[0])) + 1
    stack = np.concatenate([src if i % 2 == 0 else src[::-1] for i in range(reps)], axis=0)
    return stack[:height]


def patch(arr, y0, y1, rows, down):
    """Закрасить кремом строки y0..y1 и растушевать край в соседний фон."""
    h = y1 - y0
    block = cream_block(arr, rows, h + FEATHER)
    if down:
        alpha = np.concatenate([np.ones(h), np.linspace(1, 0, FEATHER + 2)[1:-1]])
        top, bot = y0, y1 + FEATHER
    else:
        block = block[::-1]
        alpha = np.concatenate([np.linspace(0, 1, FEATHER + 2)[1:-1], np.ones(h)])
        top, bot = y0 - FEATHER, y1
    a = alpha[:, None, None]
    arr[top:bot] = arr[top:bot] * (1 - a) + block * a


def build_sheet(left_name, right_name, master_top, master_bot, out_left, out_right):
    halves = []
    for name in (left_name, right_name):
        old_top, old_bot, rows = PAGES[name]
        arr = normalize_tone(np.asarray(Image.open(f"real/{name}").convert("RGB")).astype(float), rows)
        if old_top > TOP_H:                       # стереть остаток старой полосы
            patch(arr, TOP_H, old_top, rows, down=True)
        if old_bot > BOT_H:
            patch(arr, H - old_bot, H - BOT_H, rows, down=False)
        halves.append(arr)

    sheet = np.concatenate(halves, axis=1)
    top, p_t, s_t = tile_strip(master_top, sheet.shape[1])
    bot, p_b, s_b = tile_strip(master_bot, sheet.shape[1])
    sheet[:TOP_H] = top
    sheet[H - BOT_H:] = bot
    print(f"  {left_name}+{right_name}: период верх {p_t:.2f}px (правка масштаба {s_t:.4f}), "
          f"низ {p_b:.2f}px ({s_b:.4f})")

    Image.fromarray(sheet[:, :W].astype(np.uint8)).save(out_left)
    Image.fromarray(sheet[:, W:].astype(np.uint8)).save(out_right)


cover = normalize_tone(np.asarray(Image.open("real/2.png").convert("RGB")).astype(float), PAGES["2.png"][2])
MASTER_TOP = cover[:TOP_H].copy()
MASTER_BOT = cover[H - BOT_H:].copy()

import os
os.makedirs("fixed", exist_ok=True)
print("Свожу бордюры:")
build_sheet("1.png", "2.png", MASTER_TOP, MASTER_BOT, "fixed/p4-back.png", "fixed/p1-cover.png")
build_sheet("3.png", "4.png", MASTER_TOP, MASTER_BOT, "fixed/p2-inside-left.png", "fixed/p3-inside-right.png")
print("готово")
