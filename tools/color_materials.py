"""Build editable material annotations from a private TCP pose capture.
Only material IDs and CHR fingerprints are exported; original artwork stays private.
Pillow is used for diagnostic sheets, not shipped or required by the runtime.
"""

import argparse
import base64
import collections
import json
import struct
from pathlib import Path
from PIL import Image, ImageDraw

# Low five bits select material; high bits select an authored shade.
COLORS = [
    0x132439,
    0x242432,
    0xE83E34,
    0xF6BD86,
    0x3267CA,
    0x824C30,
    0xF6F5E9,
    0xF6CD48,
    0x43AA55,
    0xF184B2,
    0xF7D56A,
    0xA12532,
    0x52BDD3,
    0x4C302A,
    0x243F59,
    0x182331,
    0x839EAF,
    0xEFAB35,
    0x27864A,
    0xE83E34,
]
(
    BG,
    INK,
    RED,
    SKIN,
    BLUE,
    BROWN,
    WHITE,
    YELLOW,
    GREEN,
    PINK,
    HAIR,
    MAROON,
    CYAN,
    DARKHAIR,
    NAVY,
    BLACK,
    RACKET,
    GOLD,
    SHELL,
) = range(19)
SHIRT = 19


def rgb(code):
    c = COLORS[code & 31]
    t = [100, 76, 53, 115][code >> 5]
    return tuple(min(255, ((c >> shift) & 255) * t // 100) for shift in [16, 8, 0])


def components(p, n, value):
    unseen = {i for i, v in enumerate(p) if v == value}
    out = []
    while unseen:
        start = unseen.pop()
        todo = [start]
        group = [start]
        for i in todo:
            x = i % n
            y = i // n
            for xx, yy in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                j = yy * n + xx
                if 0 <= xx < n and 0 <= yy < n and j in unseen:
                    unseen.remove(j)
                    todo.append(j)
                    group.append(j)
        out.append(group)
    return sorted(out, key=len, reverse=True)


def box(g, n):
    return (
        min(i % n for i in g),
        min(i // n for i in g),
        max(i % n for i in g),
        max(i // n for i in g),
    )


def portrait(c, p):
    # The portraits have their own ink convention: raw 1 is the outline,
    # raw 2 skin/fur, raw 3 both background and selected interior regions.
    n = 32
    m = [INK] * 1024
    outside = set()
    for g in components(p, n, 3):
        if any(i % n in (0, 31) or i // n in (0, 31) for i in g):
            outside.update(g)
    if c == 1:
        # Luigi's taller cap is cropped at the top of the 32-pixel portrait;
        # its interior is connected to the exterior in the native artwork.
        for y, left in enumerate([7, 6, 5, 4, 3, 3, 2, 2, 2, 3, 3]):
            outside.difference_update(y * 32 + x for x in range(left + 1, 31 - left))
    for i, v in enumerate(p):
        x = i % 32
        y = i // 32
        if i in outside:
            m[i] = BG
            continue
        if v == 1:
            m[i] = INK
            continue
        if c in (0, 1):
            brim = 14 if c == 0 else 11
            m[i] = RED if c == 0 else GREEN
            if y >= brim:
                m[i] = SKIN
            # Sideburns and eyebrows, with white sclera and blue irises.
            if c == 0:
                if 8 <= x <= 10 and 15 <= y <= 20 or 21 <= x <= 23 and 15 <= y <= 20:
                    m[i] = DARKHAIR
                if 12 <= x <= 13 and 15 <= y <= 18 or 18 <= x <= 19 and 15 <= y <= 18:
                    m[i] = WHITE if v == 3 else BLUE
                if 10 <= x <= 21 and 23 <= y <= 26:
                    m[i] = DARKHAIR
                if 11 <= x <= 20 and 2 <= y <= 7:
                    m[i] = WHITE if v != 3 else RED
            else:
                if x in (10, 11, 20, 21) and 10 <= y <= 15:
                    m[i] = DARKHAIR
                if 13 <= x <= 14 and 12 <= y <= 15 or 17 <= x <= 18 and 12 <= y <= 15:
                    m[i] = WHITE if v == 3 else BLUE
                if 9 <= x <= 22 and 21 <= y <= 25:
                    m[i] = DARKHAIR
                if 11 <= x <= 20 and y <= 3:
                    m[i] = WHITE if v != 3 else GREEN
        elif c == 2:
            m[i] = HAIR if y < 16 or x < 7 or x > 24 else SKIN
            if y < 5:
                m[i] = GOLD
            if y in (1, 2, 3) and x in (13, 14, 16, 17):
                m[i] = CYAN
            if 8 <= x <= 12 and 18 <= y <= 23 or 19 <= x <= 23 and 18 <= y <= 23:
                m[i] = WHITE if v == 3 else BLUE
            if y >= 27 and 14 <= x <= 17:
                m[i] = PINK
            if 3 <= x <= 5 and 24 <= y <= 28 or 26 <= x <= 28 and 24 <= y <= 28:
                m[i] = CYAN
        elif c == 3:
            m[i] = GREEN
            if y >= 18 and (x < 8 or x > 23 or y >= 26):
                m[i] = WHITE
            if y < 11 and 10 <= x <= 21:
                m[i] = WHITE if v == 3 else GREEN
            if 13 <= x <= 14 and 6 <= y <= 9 or 17 <= x <= 18 and 6 <= y <= 9:
                m[i] = BLACK
        elif c == 4:
            m[i] = WHITE if y < 18 else SKIN
            if y < 17 and v == 1:
                m[i] = RED
            if y < 18 and v == 2:
                m[i] = RED | 32
            if y >= 18 and x in (13, 18):
                m[i] = BLACK
        elif c == 5:
            m[i] = YELLOW
            if y < 15 and 8 <= x <= 23:
                m[i] = WHITE if v == 3 else YELLOW
            if y in (8, 9, 10) and x in (13, 14, 17, 18):
                m[i] = BLACK
        else:
            m[i] = BROWN if y < 9 or x < 6 or x > 25 else SKIN
            if y < 14 and 11 <= x <= 13 or y < 14 and 17 <= x <= 19:
                m[i] = WHITE if v == 3 else SKIN
    # Region-specific ink: retain legible logo, pupils, mouth and cap spots.
    for i, v in enumerate(p):
        x = i % 32
        y = i // 32
        if v != 1 or i in outside:
            continue
        if c == 0 and 11 <= x <= 20 and 2 <= y <= 7:
            m[i] = WHITE
        if c == 1 and 11 <= x <= 20 and y <= 3:
            m[i] = WHITE
        if (
            c in (0, 1)
            and (23 if c == 0 else 21) <= y <= (26 if c == 0 else 24)
            and 9 <= x <= 22
        ):
            m[i] = DARKHAIR
        if c == 4 and y < 17 and 1 < x < 30:
            spot = (
                ((x - 17) / 6) ** 2 + ((y - 6) / 5) ** 2 < 1.1
                or ((x - 3) / 6) ** 2 + ((y - 11) / 5) ** 2 < 1.1
                or ((x - 29) / 5) ** 2 + ((y - 14) / 4) ** 2 < 1.1
            )
            if spot:
                m[i] = RED
        if c == 6 and y < 16:
            m[i] = BROWN
            if (11 <= x <= 13 or 17 <= x <= 19) and 9 <= y <= 12:
                m[i] = BLACK
    # Single-pixel eye reflections and the native open-mouth tongue detail.
    for x, y in {
        0: [(12, 16), (19, 16)],
        1: [(13, 13), (18, 13)],
        2: [(10, 20), (21, 20)],
        3: [(13, 7), (18, 7)],
        4: [(13, 19), (18, 19)],
        5: [(14, 9), (17, 9)],
        6: [(12, 10), (18, 10)],
    }[c]:
        m[y * 32 + x] = WHITE
    if c == 4:
        for y in (27, 28):
            for x in range(14, 18):
                m[y * 32 + x] = PINK
    return m


def sprite(c, p, n):
    if n == 128:
        occupied = [i for i, v in enumerate(p) if v]
        if not occupied:
            return [BG] * len(p)
        x0, y0, x1, y1 = box(occupied, n)
        side = max(x1 - x0 + 1, y1 - y0 + 1)
        ox = (x0 + x1 - side + 1) // 2
        oy = y1 - side + 1
        cropped = [
            p[(oy + y) * n + ox + x] if 0 <= oy + y < n and 0 <= ox + x < n else 0
            for y in range(side)
            for x in range(side)
        ]
        painted = sprite(c, cropped, side)
        result = [BG] * len(p)
        for y in range(side):
            for x in range(side):
                if 0 <= oy + y < n and 0 <= ox + x < n:
                    result[(oy + y) * n + ox + x] = painted[y * side + x]
        return result
    m = [BG if not v else INK for v in p]
    groups = components(p, n, 1)
    scale = n / 64
    small_holes = []
    for value in (0, 2, 3):
        for g in components(p, n, value):
            if len(g) <= max(4, round(4 * scale * scale)):
                boundary = set()
                for i in g:
                    x = i % n
                    y = i // n
                    for xx, yy in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                        if 0 <= xx < n and 0 <= yy < n:
                            boundary.add(yy * n + xx)
                boundary.difference_update(g)
                small_holes.append((box(g, n), boundary))
    racket_groups = []
    for g in groups:
        b = box(g, n)
        members = set(g)
        holes = sum(
            b[0] < h[0]
            and h[2] < b[2]
            and b[1] < h[1]
            and h[3] < b[3]
            and boundary.issubset(members)
            for h, boundary in small_holes
        )
        if holes >= max(4, round(5 * scale)):
            racket_groups.append(g)
    # Native ink separates hat, shirt, shorts, hands, socks and shoes. Assign
    # whole enclosed artwork regions, then shade their original edge texels.
    candidates = [
        g
        for g in groups
        if len(g) >= max(3, 20 * scale * scale) and g not in racket_groups
    ]

    def center(g):
        return sum(i % n for i in g) / len(g), sum(i // n for i in g) / len(g)

    tops = [g for g in candidates if box(g, n)[1] < n * 0.2]
    cap = (
        max(
            tops, key=lambda g: len(g) / (1 + ((center(g)[0] - n / 2) / (n * 0.3)) ** 2)
        )
        if tops
        else (candidates[0] if candidates else [])
    )
    others = [
        g
        for g in candidates
        if g is not cap and box(g, n)[1] > box(cap, n)[1] + 5 * scale
    ]
    torso = (
        max(
            others,
            key=lambda g: len(g)
            / (
                1
                + ((center(g)[0] - n / 2) / (n * 0.15)) ** 2
                + ((center(g)[1] - n * 0.52) / (n * 0.18)) ** 2
            ),
        )
        if others
        else cap
    )
    cb = box(cap, n) if cap else (0, 0, n - 1, n // 3)
    tb = box(torso, n) if torso else (n // 3, n // 3, n * 2 // 3, n * 2 // 3)
    shorts_candidates = [
        g
        for g in others
        if g is not torso
        and box(g, n)[1] >= tb[1] + 8 * scale
        and box(g, n)[1] < n * 0.84
    ]
    shorts = max(shorts_candidates, key=len) if shorts_candidates else []
    sb = (
        box(shorts, n)
        if shorts
        else (tb[0], tb[3], tb[2], min(n - 1, tb[3] + int(8 * scale)))
    )
    capset = set(cap)
    cx = (cb[0] + cb[2]) / 2
    symmetry = sum(
        1 for i in cap if i // n * n + int(cb[0] + cb[2] - i % n) not in capset
    ) / max(1, len(cap))
    back = symmetry < 0.21
    shirt = [SHIRT, GREEN, PINK, GREEN, BLUE, YELLOW, WHITE][c]
    head = [RED, GREEN, HAIR, GREEN, WHITE, YELLOW, BROWN][c]
    bottom = [BLUE, BLUE, PINK, GREEN, WHITE, SHELL, BROWN][c]
    bodycenter = (tb[0] + tb[2]) / 2
    for g in groups:
        b = box(g, n)
        gx = sum(i % n for i in g) / len(g)
        gy = sum(i // n for i in g) / len(g)
        material = shirt
        if g is cap:
            material = head
        elif g is torso:
            material = shirt
        elif g is shorts:
            material = bottom
        elif gy > sb[3] + 3 * scale:
            material = BROWN if gy > n * 0.88 else WHITE
        elif gy < tb[1]:
            material = head if b[2] - b[0] > 4 * scale or c > 1 else WHITE
        elif gx < tb[0] + 4 * scale or gx > tb[2] - 4 * scale:
            material = WHITE if c in (0, 1, 4) else SKIN if c == 2 else head
        elif gy > tb[3] - 2 * scale:
            material = bottom
        for i in g:
            m[i] = material
            if g is cap and c in (0, 1):
                x = i % n
                y = i // n
                h = max(1, cb[3] - cb[1])
                w = max(1, cb[2] - cb[0])
                if y > cb[1] + h * 0.73 + ((x - cx) / w) ** 2 * h * 0.4:
                    m[i] |= 32
                elif ((x - cx + w * 0.1) / (w * 0.32)) ** 2 + (
                    (y - cb[1] - h * 0.24) / (h * 0.18)
                ) ** 2 < 1:
                    m[i] |= 96
    # Assign antialias edges from their immediate material neighbors. Native
    # mid-tone filled regions (hair, exposed arms/legs) receive their own IDs.
    for g in components(p, n, 2):
        b = box(g, n)
        gy = sum(i // n for i in g) / len(g)
        gx = sum(i % n for i in g) / len(g)
        for i in g:
            x = i % n
            y = i // n
            near = []
            for yy in range(max(0, y - 1), min(n, y + 2)):
                for xx in range(max(0, x - 1), min(n, x + 2)):
                    j = yy * n + xx
                    if p[j] == 1:
                        near.append(m[j] & 31)
            if near:
                m[i] = collections.Counter(near).most_common(1)[0][0] | 32
            else:
                material = SKIN if c in (0, 1, 2, 4) else head
                if c in (0, 1) and y < tb[1]:
                    material = DARKHAIR
                    if back:
                        if (x < cb[0] + 3 * scale or x > cb[2] - 3 * scale) and y > cb[
                            1
                        ] + 8 * scale:
                            material = SKIN
                    elif (x - cx) * (bodycenter - cx) > 0:
                        material = SKIN
                if c in (0, 1) and y > sb[3] + 3 * scale and y < n * 0.84:
                    material = SKIN
                if (
                    c == 6
                    and tb[1] <= y <= tb[3]
                    and tb[0] + 4 * scale < x < tb[2] - 4 * scale
                ):
                    material = WHITE | 32
                m[i] = material
    # Preserve dark ink. Color only interior ink adjacent to cap/hair or
    # garment materials, avoiding black silhouettes turning into pale seams.
    for i, v in enumerate(p):
        if v != 3:
            continue
        x = i % n
        y = i // n
        if (
            c in (0, 1)
            and cb[3] - 2 * scale < y < tb[1] + 2 * scale
            and cb[0] < x < cb[2]
        ):
            m[i] = DARKHAIR | 32
    if c == 2:
        mids = components(p, n, 2)
        hair = max(mids, key=len) if mids else []
        hb = box(hair, n) if hair else cb
        for i, v in enumerate(p):
            if not v:
                continue
            x = i % n
            y = i // n
            if v == 2:
                m[i] = SKIN
            if v == 1:
                m[i] = PINK if y >= hb[3] - 2 * scale else HAIR | 96
            if y < hb[1] + 2 * scale:
                m[i] = GOLD if v != 3 else GOLD | 32
            if y > n * 0.86:
                m[i] = PINK if v != 3 else MAROON
        for i in hair:
            m[i] = HAIR
        hs = set(hair)
        hc = (hb[0] + hb[2]) / 2
        asymmetric = (
            sum(i // n * n + int(hb[0] + hb[2] - i % n) not in hs for i in hair)
            / max(1, len(hair))
            > 0.22
        )
        mass = sum(i % n for i in hair) / max(1, len(hair))
        front = -1 if mass > hc else 1
        for g in groups:
            b = box(g, n)
            if b[1] >= hb[3] + 3 * scale and b[3] < n * 0.9:
                for i in g:
                    m[i] = SKIN
            elif (
                asymmetric
                and hb[1] + 3 * scale < b[1] < hb[3] - 4 * scale
                and (center(g)[0] - mass) * front > 3 * scale
            ):
                for i in g:
                    m[i] = SKIN
            elif b[0] <= hc <= b[2] and hb[1] + 3 * scale < b[1] < hb[3] - 3 * scale:
                # Front-facing forehead/cheeks cross the hair's centerline;
                # the two back-facing hair highlights sit to either side.
                for i in g:
                    m[i] = SKIN
            elif (
                len(g) <= max(6, 8 * scale * scale)
                and hb[1] + 5 * scale < b[1] < hb[1] + (hb[3] - hb[1]) * 0.65
                and abs(center(g)[0] - hc) > 3 * scale
            ):
                for i in g:
                    m[i] = WHITE
                if len(g) > 2:
                    m[g[len(g) // 2]] = BLUE
        dresses = [
            g
            for g in groups
            if g not in racket_groups
            and box(g, n)[1] >= hb[3] - 4 * scale
            and center(g)[1] < n * 0.8
        ]
        for g in sorted(dresses, key=len, reverse=True)[:2]:
            for i in g:
                m[i] = PINK
        for value in (1, 2):
            for g in components(p, n, value):
                b = box(g, n)
                gx, gy = center(g)
                if g in racket_groups or g == hair:
                    continue
                if (
                    n * 0.52 < gy < n * 0.8
                    and abs(gx - hc) < n * 0.26
                    and b[2] - b[0] > n * 0.12
                ):
                    if value == 1 or b[3] - b[1] < n * 0.15:
                        for i in g:
                            m[i] = PINK if value == 1 else PINK | 32
    elif c == 3:
        head_pixels = [i for i, v in enumerate(p) if v == 2 and i // n < n * 0.5]
        body_pixels = [
            i for i, v in enumerate(p) if v == 2 and n * 0.55 < i // n < n * 0.8
        ]
        hx = sum(i % n for i in head_pixels) / max(1, len(head_pixels))
        bx = sum(i % n for i in body_pixels) / max(1, len(body_pixels))
        for i, v in enumerate(p):
            if v == 1:
                m[i] = WHITE
            elif v == 2:
                m[i] = GREEN
            if v and i // n > n * 0.88:
                m[i] = GOLD if v != 3 else BROWN
        for g in groups:
            b = box(g, n)
            gx, gy = center(g)
            # Red dorsal spines are separate narrow white ink islands.
            if gy < n * 0.55 and (
                b[3] - b[1] > n * 0.16
                and b[2] - b[0] < n * 0.13
                or abs(bx - hx) > 2 * scale
                and (gx - hx) * (1 if bx > hx else -1) > 3 * scale
            ):
                for i in g:
                    m[i] = RED
        for g in components(p, n, 3):
            b = box(g, n)
            if (
                n * 0.45 < b[1] < n * 0.65
                and b[2] - b[0] > n * 0.18
                and b[3] - b[1] < n * 0.14
            ):
                for i in g:
                    m[i] = RED | 32
    elif c == 4:
        for i, v in enumerate(p):
            if not v:
                continue
            x = i % n
            y = i // n
            if y <= cb[3] + 2 * scale:
                if v == 3:
                    m[i] = RED
                elif v == 2:
                    m[i] = WHITE | 32
                else:
                    m[i] = WHITE
            if y > n * 0.9:
                m[i] = BROWN if v != 3 else DARKHAIR
    elif c == 5:
        for i, v in enumerate(p):
            if v == 1:
                m[i] = WHITE
            elif v == 2:
                m[i] = YELLOW
            if v and i // n > n * 0.86:
                m[i] = GREEN if v != 3 else SHELL | 32
        rings = [
            g
            for g in groups
            if g not in racket_groups
            and box(g, n)[1] > n * 0.25
            and box(g, n)[1] < n * 0.7
            and box(g, n)[3] - box(g, n)[1] > n * 0.16
        ]
        ring = (
            max(
                rings,
                key=lambda g: len(g) / (1 + ((center(g)[0] - n / 2) / (n * 0.2)) ** 2),
            )
            if rings
            else []
        )
        if ring:
            rb = box(ring, n)
            for i, v in enumerate(p):
                x = i % n
                y = i // n
                if (
                    v in (2, 3)
                    and rb[0] - 2 * scale <= x <= rb[2] + 2 * scale
                    and rb[1] + 2 * scale <= y <= rb[3]
                ):
                    m[i] = SHELL if v == 2 else SHELL | 64
    elif c == 6:
        for i, v in enumerate(p):
            if v == 1:
                m[i] = WHITE
            elif v == 2:
                m[i] = SKIN
            elif v == 3:
                x = i % n
                y = i // n
                edge = any(
                    xx < 0 or xx >= n or yy < 0 or yy >= n or not p[yy * n + xx]
                    for xx, yy in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))
                )
                m[i] = DARKHAIR if edge else BROWN
    if c in (0, 1):
        # Frontal poses have two separate native pupil islands. Use these
        # anatomical anchors for face/eyes/nose/moustache; a back-facing hat
        # must never be mistaken for the face underneath it.
        pupils = []
        for g in components(p, n, 3):
            b = box(g, n)
            if (
                len(g) <= max(6, n * n * 0.004)
                and n * 0.2 < b[1] < n * 0.47
                and 1 <= b[3] - b[1] <= n * 0.12
            ):
                boundary = {
                    j
                    for i in g
                    for j in (i - 1, i + 1, i - n, i + n)
                    if 0 <= j < n * n and j not in g
                }
                if any(p[j] == 1 for j in boundary) and all(
                    p[j] != 0 for j in boundary
                ):
                    pupils.append(g)
        pairs = []
        for a in pupils:
            for b in pupils:
                ax, ay = center(a)
                bx, by = center(b)
                if n * 0.08 < bx - ax < n * 0.3 and abs(ay - by) <= max(1, scale):
                    pairs.append(
                        (
                            abs((ay + by) / 2 - n * 0.32)
                            + abs((ax + bx) / 2 - n / 2) * 0.3,
                            a,
                            b,
                        )
                    )
        if pairs:
            _, a, b = min(pairs, key=lambda q: q[0])
            ab = box(a, n)
            bb = box(b, n)
            ex = (center(a)[0] + center(b)[0]) / 2
            ey = max(ab[3], bb[3])
            face_end = min(n * 0.56, ey + n * 0.19)
            for i, v in enumerate(p):
                x = i % n
                y = i // n
                if (
                    not v
                    or abs(x - ex) > n * 0.25
                    or not min(ab[1], bb[1]) - scale <= y <= face_end
                ):
                    continue
                if v in (1, 2):
                    m[i] = SKIN
                if (
                    v == 3
                    and abs(x - ex) < n * 0.19
                    and ey + n * 0.06 <= y <= ey + n * 0.15
                ):
                    m[i] = DARKHAIR
                if (
                    v == 2
                    and (
                        min(
                            ((x - ex - n * 0.1) / (n * 0.105)) ** 2,
                            ((x - ex + n * 0.1) / (n * 0.105)) ** 2,
                        )
                        + ((y - ey - n * 0.12) / (n * 0.035)) ** 2
                    )
                    < 1
                ):
                    m[i] = DARKHAIR
            for pupil in (a, b):
                for i in pupil:
                    x = i % n
                    y = i // n
                    m[i] = BLACK
                    for xx, yy in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                        if 0 <= xx < n and 0 <= yy < n and p[yy * n + xx] == 1:
                            m[yy * n + xx] = WHITE
            if n < 40:
                for i, v in enumerate(p):
                    x = i % n
                    y = i // n
                    if v == 3 and face_end < y < n * 0.79 and abs(x - ex) < n * 0.22:
                        m[i] = shirt if y < n * 0.68 else BLUE
        elif n < 40:
            eye_whites = [
                g
                for g in groups
                if n * 0.18 < box(g, n)[1] < n * 0.43
                and box(g, n)[3] - box(g, n)[1] >= 1
                and box(g, n)[2] - box(g, n)[0] < n * 0.25
                and len(g) < n * 0.65
            ]
            for eye in eye_whites:
                eb = box(eye, n)
                for i in eye:
                    m[i] = WHITE
                for y in range(eb[1], min(n, eb[3] + max(2, round(n * 0.12)))):
                    for x in range(max(0, eb[0] - 1), min(n, eb[2] + 3)):
                        i = y * n + x
                        if p[i] == 2:
                            m[i] = SKIN
            if not back:
                for i, v in enumerate(p):
                    if n * 0.24 < i // n < n * 0.5:
                        if v == 2:
                            m[i] = SKIN
                        elif v == 1 and i not in capset:
                            m[i] = WHITE
    # Tennis racket strings have enclosed transparent holes. They identify
    # the racket independently of swing direction and screen location.
    holes = set()
    for g in components(p, n, 0):
        if not any(i % n in (0, n - 1) or i // n in (0, n - 1) for i in g):
            holes.update(g)
    radius = max(2, round(4 * scale))
    racquet = set()
    for i, v in enumerate(p):
        if not v:
            continue
        x = i % n
        y = i // n
        count = sum(
            yy * n + xx in holes
            for yy in range(max(0, y - radius), min(n, y + radius + 1))
            for xx in range(max(0, x - radius), min(n, x + radius + 1))
        )
        if count >= max(3, round(7 * scale * scale)):
            racquet.add(i)
    for i in racquet:
        m[i] = RACKET if p[i] == 3 else WHITE if p[i] == 1 else RACKET | 32
    for g in racket_groups:
        b = box(g, n)
        for y in range(max(0, b[1] - 1), min(n, b[3] + 2)):
            for x in range(max(0, b[0] - 1), min(n, b[2] + 2)):
                i = y * n + x
                if p[i]:
                    m[i] = WHITE if p[i] == 1 else RACKET if p[i] == 3 else RACKET | 32
    return m


def main():
    a = argparse.ArgumentParser()
    a.add_argument("capture", type=Path)
    a.add_argument("portraits", type=Path)
    a.add_argument("output", type=Path)
    a.add_argument("--extra-capture", type=Path, action="append", default=[])
    a.add_argument(
        "--base-catalog",
        type=Path,
        help="Keep previously reviewed texels while adding new captures",
    )
    args = a.parse_args()
    portraits = json.loads(args.portraits.read_text())
    pm = [portrait(c, p) for c, p in enumerate(portraits)]
    image = Image.new("RGB", (7 * 144, 144), rgb(BG))
    for c, m in enumerate(pm):
        image.paste(
            Image.frombytes(
                "RGB", (32, 32), bytes(v for code in m for v in rgb(code))
            ).resize((128, 128), Image.Resampling.NEAREST),
            (c * 144, 8),
        )
    image.save(args.capture / "colored-portraits.png")
    records = {}
    baseline = {}
    if args.base_catalog:
        data = args.base_catalog.read_bytes()
        if data[:8] != b"VBMAT002" or len(data) < 12:
            raise ValueError("Invalid base catalog")
        count = struct.unpack_from("<I", data, 8)[0]
        if len(data) != 12 + 7 * 1024 + 72 * count:
            raise ValueError("Invalid base catalog length")
        for offset in range(12 + 7 * 1024, len(data), 72):
            key = struct.unpack_from("<BBBBI", data, offset)
            baseline[key] = data[offset + 8 : offset + 72]
            records[key] = collections.Counter()
    counts = collections.Counter()
    for c in range(7):
        paths = {
            p.stem: p
            for root in [args.capture] + args.extra_capture
            for p in (root / "poses").glob(f"c{c}-*.json")
        }
        preview = []
        paths = [paths[key] for key in sorted(paths)]
        for path in paths:
            d = json.loads(path.read_text())
            n = d["size"]
            p = (
                base64.b64decode(d["pixels"])
                if isinstance(d["pixels"], str)
                else bytes(d["pixels"])
            )
            m = sprite(c, p, n)
            for tx, ty, h, hflip, vflip in d["tiles"]:
                mask = bytearray(64)
                for y in range(8):
                    for x in range(8):
                        mask[
                            (y ^ (7 if vflip else 0)) * 8 + (x ^ (7 if hflip else 0))
                        ] = m[(ty * 8 + y) * n + tx * 8 + x]
                key = (c, n, tx, ty, h)
                if key not in records:
                    records[key] = collections.Counter()
                records[key][bytes(mask)] += 1
            if n == 128:
                im = Image.frombytes(
                    "RGB", (n, n), bytes(v for code in m for v in rgb(code))
                )
                bounds = box([i for i, v in enumerate(p) if v], n)
                art = im.crop((bounds[0], bounds[1], bounds[2] + 1, bounds[3] + 1))
                factor = 128 / max(art.size)
                art = art.resize(
                    (
                        max(1, round(art.width * factor)),
                        max(1, round(art.height * factor)),
                    ),
                    Image.Resampling.NEAREST,
                )
                im = Image.new("RGB", (128, 128), rgb(BG))
                im.paste(art, ((128 - art.width) // 2, (128 - art.height) // 2))
                preview.append((path.stem, im))
            counts[c] += 1
        if preview:
            sheet = Image.new(
                "RGB", (8 * 144, ((len(preview) + 7) // 8) * 150), "#1c2028"
            )
            draw = ImageDraw.Draw(sheet)
            for i, (name, im) in enumerate(preview):
                x = i % 8 * 144
                y = i // 8 * 150
                sheet.paste(im, (x, y))
                draw.text((x, y + 130), f"{i}: {name[-5:]}", fill="white")
            sheet.save(args.capture / f"colored-c{c}.png")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("wb") as f:
        f.write(b"VBMAT002")
        f.write(struct.pack("<I", len(records)))
        f.write(bytes(code for m in pm for code in m))
        for (c, n, x, y, h), votes in sorted(records.items()):
            # A tile can be partly hidden by the net or another sprite. Merge
            # observed texels, not whole masks: an occluded zero is no vote.
            mask = []
            for i in range(64):
                choices = collections.Counter()
                for candidate, count in votes.items():
                    if candidate[i]:
                        choices[candidate[i]] += count
                reviewed = baseline.get((c, n, x, y, h), bytes(64))[i]
                mask.append(
                    reviewed or (choices.most_common(1)[0][0] if choices else 0)
                )
            f.write(struct.pack("<BBBBI", c, n, x, y, h))
            f.write(bytes(mask))
    print("Material tiles:", len(records), "pose coverage:", dict(counts))


if __name__ == "__main__":
    main()
