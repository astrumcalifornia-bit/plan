#!/usr/bin/env python3
"""Заменить QR на обложке, сохранив подложку и её мягкий градиент."""
import cairosvg, cv2, numpy as np
from PIL import Image

PAGE = "fixed/p1-cover.png"
SVG = "newqr/https_lnk_at_tatikvareniki.svg"
MOD = (428, 1225, 615, 1412)      # координаты модулей старого QR: x0,y0,x1,y1
FRAC = (975 - 48 + 1) / 1024      # доля холста SVG, занятая модулями
PAD = 16                          # запас вокруг, где восстанавливаем подложку

page = np.asarray(Image.open(PAGE).convert("RGB")).astype(np.float32)
x0, y0, x1, y1 = MOD
rx0, ry0 = x0 - PAD, y0 - PAD
rx1, ry1 = x1 + PAD + 1, y1 + PAD + 1
reg = page[ry0:ry1, rx0:rx1].copy()

# 1. подложка: сгладить по светлым пикселям, тёмные модули игнорировать
light = (reg.mean(axis=2) > 200).astype(np.float32)[:, :, None]
num = cv2.GaussianBlur(reg * light, (0, 0), 14)
den = cv2.GaussianBlur(np.repeat(light, 3, axis=2), (0, 0), 14)
backing = num / np.maximum(den, 1e-3)

# 2. новый QR: альфа из яркости, цвет модулей -- чёрный
canvas = int(round((x1 - x0 + 1) / FRAC))
cairosvg.svg2png(url=SVG, write_to="newqr/qr-big.png", output_width=canvas*8, output_height=canvas*8)
qr = np.asarray(Image.open("newqr/qr-big.png").convert("L")
                .resize((canvas, canvas), Image.LANCZOS)).astype(np.float32)
alpha = np.clip(1.0 - qr / 255.0, 0, 1)

# 3. наложить модули на восстановленную подложку
off = int(round(48 / 1024 * canvas))          # поле внутри холста SVG
ax, ay = x0 - off - rx0, y0 - off - ry0
full = np.zeros(reg.shape[:2], np.float32)
full[ay:ay+canvas, ax:ax+canvas] = alpha
ink = np.array([26.0, 26.0, 26.0])            # мягкий чёрный, как в исходной печати
page[ry0:ry1, rx0:rx1] = backing * (1 - full[:, :, None]) + ink * full[:, :, None]

Image.fromarray(np.clip(page, 0, 255).astype(np.uint8)).save(PAGE)

ok, infos, _, _ = cv2.QRCodeDetector().detectAndDecodeMulti(cv2.imread(PAGE))
print("QR заменён, чтение со страницы:", ok, infos if ok else "")
