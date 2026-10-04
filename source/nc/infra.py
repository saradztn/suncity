# Created by: Arena.ai Agent Mode (AI) - NightCity MTA:SA asset pipeline
# -----------------------------------------------------------------------------
# infra.py - elevated expressways, river bridges (girder + cable stayed), glass sky bridges, distant skyline strips.
# Every function returns (Mesh, Col, meta).  Bridges / expressways are built along +x, centred on the origin.
# (No vehicles anywhere: only the road structures themselves.)
# -----------------------------------------------------------------------------
import numpy as np
from .mb import Mesh, Col, unit
from . import parts as P
from . import bldkit as K
from .bldkit import rect
from .ground import CURB, SW, CARR, SIDE, ROAD, RIVER_Z, BED_Z


def _cap_beam_pier(M, C, x, level, thick, ytop_w=18.0, base=0.0):
    h = level - thick
    M.box((x - 1.2, -1.2, base), (x + 1.2, 1.2, h - 1.8), 'nc_pillar', tile=(2.4, 6.0))
    M.box((x - 1.5, -ytop_w / 2, h - 1.8), (x + 1.5, ytop_w / 2, h), 'nc_concrete_dark', tile=(3, 3))
    M.box((x - 1.25, -1.25, base + 0.2), (x + 1.25, 1.25, base + 0.32), 'nc_strip_cyan', tile=(1, 1), emis=1.0)
    M.light((x, 0, base + 1.0), P.CYA, 0.7, 14.0)
    C.box((x - 1.2, -1.2, base), (x + 1.2, 1.2, h - 1.8))
    C.box((x - 1.5, -ytop_w / 2, h - 1.8), (x + 1.5, ytop_w / 2, h))


def expressway(L, level, seed=0, pier=True, river=False):
    """double carriageway elevated expressway segment, length L along x, deck top at z = level"""
    rng = np.random.default_rng(seed)
    M, C = Mesh(), Col()
    hw = 13.2
    th = 2.2
    for sy in (1, -1):
        M.ribbon([(-L / 2, sy * 6.6, level), (L / 2, sy * 6.6, level)], 6.0, 'nc_road_hwy', tile_v=8.0, u=(0.0, 1.0))
    # median + outer barriers (jersey profile as stepped boxes)
    for (ya, yb) in ((-0.6, 0.6),):
        M.box((-L / 2, ya, level), (L / 2, yb, level + 1.0), 'nc_concrete', tile=(4, 2))
    for sy in (1, -1):
        y0, y1 = (12.6, 13.2) if sy > 0 else (-13.2, -12.6)
        M.box((-L / 2, y0, level), (L / 2, y1, level + 0.95), 'nc_concrete', tile=(4, 2))
        ya, yb = (12.7, 13.1) if sy > 0 else (-13.1, -12.7)
        M.box((-L / 2, ya, level + 0.95), (L / 2, yb, level + 1.05), 'nc_strip_white', tile=(1, 1), emis=0.9)
    # box girder: underside + sides + LED line
    M.hquad(-L / 2, -hw, L / 2, hw, level - th, 'nc_deck_under', tile=(4, 4), up=False)
    M.wall_strip([(L / 2, hw), (-L / 2, hw)], level - th, level, 'nc_concrete', tile=(4, 2))
    M.wall_strip([(-L / 2, -hw), (L / 2, -hw)], level - th, level, 'nc_concrete', tile=(4, 2))
    for sy in (1, -1):
        y = sy * (hw + 0.02)
        M.box((-L / 2, min(y, y + sy * 0.12), level - th + 0.15), (L / 2, max(y, y + sy * 0.12), level - th + 0.35), 'nc_strip_cyan', tile=(1, 1), emis=1.0, skip=('-z',))
    # deck end faces
    # lamps on the median every ~24 m, twin arm
    nl = max(1, int(L // 24))
    for k in range(nl):
        x = -L / 2 + (k + 0.5) * L / nl
        M.merge(P.street_lamp(10.0, 4.2, False, True), (x, 0, level + 1.0), rz=90.0)
    if river:
        for fx in (-L / 6, L / 6):
            _cap_beam_pier(M, C, fx, level, th, base=BED_Z)
    elif pier:
        _cap_beam_pier(M, C, 0.0, level, th)
    C.box((-L / 2, -hw, level - th), (L / 2, hw, level))
    C.box((-L / 2, -0.6, level), (L / 2, 0.6, level + 1.0))
    C.box((-L / 2, 12.6, level), (L / 2, 13.2, level + 0.95))
    C.box((-L / 2, -13.2, level), (L / 2, -12.6, level + 0.95))
    return M, C, dict(kind='expressway', w=float(L), d=26.4, h=float(level + 12), dist=560.0)


def bridge_girder(span, cls, seed=0, water=None):
    """river bridge of road class `cls`, deck along +y over `span` (bank street centre to bank street centre), top at z = 0.
    The structure (parapets, lamps, girder, piers) exists over the water section only (`water` m, centred)."""
    M, C = Mesh(), Col()
    water = float(span if water is None else water)
    wd = SW[cls]
    car, side = CARR[cls], SIDE[cls]
    th = 1.8
    hw = wd / 2
    jn = CARR['S'] / 2                           # half carriageway of the bank street: this band is the intersection (plain asphalt, no raised pavement)
    ya, yb = -span / 2 + jn, span / 2 - jn
    if cls in ROAD:
        M.ribbon([(0, ya, 0.0), (0, yb, 0.0)], car / 2, ROAD[cls], tile_v=8.0, u=(0.0, 1.0))
    else:
        M.hquad(-car / 2, ya, car / 2, yb, 0.0, 'nc_alley', tile=(6, 6))
    M.hquad(-hw, -span / 2, hw, ya, 0.0, 'nc_asphalt', tile=(12.0, 12.0))
    M.hquad(-hw, yb, hw, span / 2, 0.0, 'nc_asphalt', tile=(12.0, 12.0))
    for sx in (1, -1):
        x0, x1 = (car / 2, hw) if sx > 0 else (-hw, -car / 2)
        M.hquad(x0, ya, x1, yb, CURB, 'nc_sidewalk', tile=(3.6, 3.6))
        xc = car / 2 * sx
        a, b = ((xc, yb), (xc, ya)) if sx > 0 else ((xc, ya), (xc, yb))
        M.wall(np.array(a), np.array(b), 0.0, CURB, 'nc_curb', tile=(1.6, 1.6))
        px = hw * sx
        M.box((min(px, px - sx * 0.4), -water / 2, CURB), (max(px, px - sx * 0.4), water / 2, CURB + 1.1), 'nc_concrete', tile=(4, 2))
        M.box((min(px - sx * 0.05, px - sx * 0.35), -water / 2, CURB + 1.1), (max(px - sx * 0.05, px - sx * 0.35), water / 2, CURB + 1.18), 'nc_strip_cyan', tile=(1, 1), emis=1.0)
        n = max(2, int(water // 26))
        for k in range(n):
            y = -water / 2 + (k + 0.5) * water / n
            M.merge(P.street_lamp(9.0, 2.6, False, False), (px - sx * 0.7, y, CURB), rz=(-90.0 if sx > 0 else 90.0) + 180.0)
    # girder: underside + outer faces (over the water only)
    M.hquad(-hw, -water / 2, hw, water / 2, -th, 'nc_deck_under', tile=(4, 4), up=False)
    M.wall_strip([(hw, -water / 2), (hw, water / 2)], -th, 0.0, 'nc_concrete_dark', tile=(4, 2))
    M.wall_strip([(-hw, water / 2), (-hw, -water / 2)], -th, 0.0, 'nc_concrete_dark', tile=(4, 2))
    for fy in (-1 / 6, 1 / 6):
        y = water * fy
        M.box((-hw * 0.7, y - 1.6, BED_Z), (hw * 0.7, y + 1.6, -th), 'nc_concrete_dark', tile=(3, 3))
        M.box((-hw * 0.7 - 0.02, y - 1.62, -th - 1.0), (hw * 0.7 + 0.02, y + 1.62, -th - 0.9), 'nc_strip_cyan', tile=(1, 1), emis=1.0)
        C.box((-hw * 0.7, y - 1.6, BED_Z), (hw * 0.7, y + 1.6, -th))
    C.box((-hw, -water / 2, -th), (hw, water / 2, 0.0))
    C.box((-hw, -span / 2, -0.5), (hw, span / 2, 0.0))
    for sx in (1, -1):                                    # the pavements stand 0.16 m above the road, the carriageway and the junction bands are at 0
        C.box((min(car / 2 * sx, hw * sx), ya, 0.0), (max(car / 2 * sx, hw * sx), yb, CURB))
    for sx in (1, -1):
        px = hw * sx
        C.box((min(px, px - sx * 0.4), -water / 2, CURB), (max(px, px - sx * 0.4), water / 2, CURB + 1.1))
    return M, C, dict(kind='bridge', w=float(wd), d=float(span), h=15.0, dist=560.0)


def bridge_cable(span, cls='A', seed=0, pylon_h=92.0, water=None):
    """hero cable-stayed bridge (H pylon at the middle of the span, harp cables, lit)"""
    M, C, meta = bridge_girder(span, cls, seed, water)
    hw = SW[cls] / 2
    rng = np.random.default_rng(seed + 1)
    ph = pylon_h
    for sx in (-1, 1):
        x = sx * (hw - 2.0)
        # tapered pylon leg
        M.loft(rect(3.2, 4.4, x, 0), CURB, rect(2.0, 3.0, x, 0), ph, 'nc_concrete', 'nc_concrete', tile=(4, 6))
        # LED edge lines up the leg
        for dy in (-1.5, 1.5):
            P.bar(M, (x + sx * 1.6, dy * 0.9, CURB + 0.5), (x + sx * 1.0, dy * 0.7, ph - 1), 0.14, 'nc_strip_cyan', emis=1.0)
        P.beacon_light(M, (x - 0.15, -0.15, ph))
        C.box((x - 1.6, -2.2, CURB), (x + 1.6, 2.2, ph * 0.5))
        C.box((x - 1.2, -1.8, ph * 0.5), (x + 1.2, 1.8, ph))
    for z in (ph * 0.45, ph * 0.8):
        M.box((-hw + 1.0, -1.4, z), (hw - 1.0, 1.4, z + 2.0), 'nc_concrete_dark', tile=(3, 3))
        C.box((-hw + 1.0, -1.4, z), (hw - 1.0, 1.4, z + 2.0))
    # harp of stay cables on both legs, both directions
    n = 9
    for sx in (-1, 1):
        x_leg, x_deck = sx * (hw - 2.0), sx * (hw - 0.6)
        for k in range(n):
            zt = ph * 0.52 + (ph * 0.44) * k / (n - 1)
            for sd in (-1, 1):
                yd = sd * (7.0 + 6.4 * k)
                if abs(yd) > (water or span) / 2 - 2:
                    continue
                M.tube(np.array([(x_leg, sd * 0.8, zt), (x_deck, yd, CURB + 1.2)]), 0.11, 4, 'nc_strip_white', tile=(4, 1), caps=False, emis=0.7, smooth=False)
    M.light((0, 0, ph * 0.6), P.COOL, 3.0, 80.0)
    meta.update(h=float(ph + 6), dist=800.0, hero=True)
    return M, C, meta


def skybridge(length, height=3.6, width=4.2, seed=0):
    """lit glass tube + steel truss between two buildings; along x, centred"""
    M, C = Mesh(), Col()
    rng = np.random.default_rng(seed)
    M.box((-length / 2, -width / 2, 0.0), (length / 2, width / 2, height), 'nc_glass_e', tile=(3.2 * 4, 3.8 * 8), emis=0.95, skip=('+x', '-x'), uvoff=(float(rng.integers(0, 4)) / 4, 0.0))
    M.box((-length / 2, -width / 2 - 0.3, -0.9), (length / 2, width / 2 + 0.3, 0.0), 'nc_metal_dark', tile=(2, 2))
    M.box((-length / 2, -width / 2 - 0.3, height), (length / 2, width / 2 + 0.3, height + 0.5), 'nc_metal_dark', tile=(2, 2))
    M.box((-length / 2, -width / 2 - 0.32, height + 0.5), (length / 2, -width / 2 - 0.2, height + 0.58), 'nc_strip_cyan', tile=(1, 1), emis=1.0)
    M.box((-length / 2, width / 2 + 0.2, height + 0.5), (length / 2, width / 2 + 0.32, height + 0.58), 'nc_strip_cyan', tile=(1, 1), emis=1.0)
    # truss diagonals under the tube
    n = max(2, int(length // 5))
    for k in range(n):
        x0 = -length / 2 + k * length / n
        x1 = x0 + length / n
        zz = -2.2
        P.bar(M, (x0, -width / 2 - 0.2, -0.9), (x0 + (x1 - x0) / 2, -width / 2 - 0.2, zz), 0.16, 'nc_steel')
        P.bar(M, (x0 + (x1 - x0) / 2, -width / 2 - 0.2, zz), (x1, -width / 2 - 0.2, -0.9), 0.16, 'nc_steel')
        P.bar(M, (x0, width / 2 + 0.2, -0.9), (x0 + (x1 - x0) / 2, width / 2 + 0.2, zz), 0.16, 'nc_steel')
        P.bar(M, (x0 + (x1 - x0) / 2, width / 2 + 0.2, zz), (x1, width / 2 + 0.2, -0.9), 0.16, 'nc_steel')
    M.light((0, 0, height * 0.6), P.COOL, 1.5, 28.0)
    C.box((-length / 2, -width / 2 - 0.3, -0.9), (length / 2, width / 2 + 0.3, height + 0.5))
    return M, C, dict(kind='skybridge', w=float(length), d=float(width), h=float(height + 3), dist=520.0)


def skyline_strip(L, seed, rows=2, hmin=70.0, hmax=250.0):
    """distant towers (no podiums, no collision): a long strip along +x, centred, depth ~ rows * 55 m"""
    rng = np.random.default_rng(seed)
    M, C = Mesh(), Col()
    mats = ['nc_glass_a', 'nc_glass_b', 'nc_glass_c', 'nc_glass_e', 'nc_glass_h', 'nc_glass_f', 'nc_glass_d']
    x = -L / 2
    while x < L / 2 - 20:
        w = float(rng.uniform(22, 46))
        for r in range(rows):
            d = float(rng.uniform(22, 40))
            h = float(rng.uniform(hmin, hmax)) * (1.0 + 0.25 * (r == 1))
            cy = r * 52.0 + float(rng.uniform(-6, 6))
            poly = rect(w, d, x + w / 2 + (r % 2) * 6, cy)
            m = mats[int(rng.integers(len(mats)))]
            K.tier(M, C, poly, 0.0, h, m, rng, emis=0.9, ledge_every=0, corners=False, col=False)
            if h > 160:
                P.beacon_light(M, (poly[:, 0].mean(), poly[:, 1].mean(), h))
            if rng.random() < 0.4:
                M.extrude(K.offset_poly(poly, 0.3), h - 0.7, h, 'nc_strip_cyan' if rng.random() < 0.6 else 'nc_strip_white', 'nc_strip_cyan', tile=(2, 1), emis=1.0)
        x += w + float(rng.uniform(2, 10))
    M.box((-L / 2 - 4, -30, -3.0), (L / 2 + 4, rows * 52.0 + 30, 0.0), 'nc_concrete_dark', tile=(8, 8))
    return M, C, dict(kind='skyline', w=float(L), d=float(rows * 52.0 + 60), h=float(hmax * 1.3 + 30), dist=1500.0, nocol=True)
