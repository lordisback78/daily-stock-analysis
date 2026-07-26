#!/usr/bin/env python3
"""Génère les icônes PNG de l'app (aucune dépendance : zlib + struct).

    python3 revision/mobile/make_icons.py

Motif : un paquet de cartes blanches en éventail sur un dégradé violet,
identité reprise de l'app desktop (accent #6c5ce7).
"""
import math
import os
import struct
import zlib

OUT_DIR = os.path.dirname(os.path.abspath(__file__))

TOP = (0x7C, 0x6C, 0xF0)      # violet clair
BOTTOM = (0x3E, 0x2A, 0xA8)   # violet profond


def lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def rounded_rect_coverage(x, y, left, top, right, bottom, radius):
    """Couverture 0..1 d'un pixel dans un rectangle à coins arrondis (anti-aliasé)."""
    if x < left - 1 or x > right + 1 or y < top - 1 or y > bottom + 1:
        return 0.0
    # Distance signée au rectangle arrondi.
    cx = min(max(x, left + radius), right - radius)
    cy = min(max(y, top + radius), bottom - radius)
    dx, dy = x - cx, y - cy
    distance = (dx * dx + dy * dy) ** 0.5 - radius
    if distance <= -0.5:
        return 1.0
    if distance >= 0.5:
        return 0.0
    return 0.5 - distance


def render(size):
    scale = size / 512
    # Un paquet de flashcards en éventail : (centre x, centre y, largeur, hauteur, angle°, opacité)
    cards = [
        (238, 250, 236, 300, -17, 0.42),
        (256, 258, 236, 300, -7, 0.68),
        (274, 266, 236, 300, 4, 1.0),
    ]
    prepared = []
    for cx, cy, width, height, angle, alpha in cards:
        radians = angle * 3.141592653589793 / 180
        prepared.append((cx * scale, cy * scale, width * scale / 2, height * scale / 2,
                         math.cos(radians), math.sin(radians), alpha))

    pixels = bytearray()
    for y in range(size):
        pixels.append(0)  # filtre PNG "none"
        for x in range(size):
            t = (x / size * 0.55) + (y / size * 0.45)
            base = lerp(TOP, BOTTOM, t)
            # Halo lumineux en haut à gauche.
            glow = max(0.0, 1 - (((x - size * 0.22) ** 2 + (y - size * 0.16) ** 2) ** 0.5) / (size * 0.85))
            colour = tuple(min(255, round(channel + 34 * glow ** 2)) for channel in base)
            for cx, cy, half_w, half_h, cos_a, sin_a, alpha in prepared:
                # Repasse dans le repère de la carte (rotation inverse).
                dx, dy = x - cx, y - cy
                local_x, local_y = dx * cos_a + dy * sin_a, -dx * sin_a + dy * cos_a
                coverage = rounded_rect_coverage(local_x, local_y, -half_w, -half_h, half_w, half_h, 30 * scale)
                if coverage:
                    weight = coverage * alpha
                    colour = tuple(round(channel + (255 - channel) * weight) for channel in colour)
            pixels += bytes(colour)
    return bytes(pixels)


def write_png(path, size):
    raw = render(size)

    def chunk(kind, payload):
        data = kind + payload
        return struct.pack(">I", len(payload)) + data + struct.pack(">I", zlib.crc32(data) & 0xFFFFFFFF)

    header = struct.pack(">2I5B", size, size, 8, 2, 0, 0, 0)  # RGB 8 bits
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", header)
           + chunk(b"IDAT", zlib.compress(raw, 9))
           + chunk(b"IEND", b""))
    with open(path, "wb") as handle:
        handle.write(png)
    print(f"✅ {os.path.basename(path)} ({size}×{size}, {len(png) // 1024} Ko)")


if __name__ == "__main__":
    for size in (180, 192, 512):
        write_png(os.path.join(OUT_DIR, f"icon-{size}.png"), size)
