# Created by: Arena.ai Agent Mode (AI) - NightCity MTA:SA asset pipeline
# -----------------------------------------------------------------------------
# texgen.py - procedural materials, part 1: road / pavement / concrete / metal.
# fn(h, w, seed) -> PBR.  All maps tile seamlessly in both directions unless the texture is a road cross-section
# (those tile along the road only).  Authored in sRGB; asphalt is genuinely dark (sRGB 0.14-0.25 = 2-5 % reflectance).
# -----------------------------------------------------------------------------
import numpy as np
from lib.noise import worley, smooth
from .texkit import (PBR, coords, lerp, rgb, blur, fbm, grain, rect_aa, height_ao, scratches)

REG = {}


def reg(name, w, h, fmt='DXT1'):
    """register a material: pixel size at 1x and the DXT format it is stored with in the TXD"""
    def deco(fn):
        REG[name] = dict(fn=fn, w=w, h=h, fmt=fmt)
        return fn
    return deco


def _bar(m, c, wdt, px):
    return np.clip((wdt / 2 - np.abs(m - c)) / px + 0.5, 0, 1)


# ---------------------------------------------------------------------------------------------
# asphalt
# ---------------------------------------------------------------------------------------------
def _asphalt_core(h, w, seed, tone=0.20, crack=0.5, patches=7, oil=0.5):
    n1 = fbm(h, w, seed, 2.6)
    n2 = fbm(h, w, seed + 1, 1.5)
    n3 = fbm(h, w, seed + 2, 0.3)
    g = grain(h, w, seed + 3, 0.65)
    stones = np.clip((g - 1.15) / 1.4, 0, 1)
    base = tone * (1 + 0.11 * n1 + 0.07 * n2 + 0.05 * n3)
    alb = base[..., None] * rgb(1.0, 1.0, 1.05) + stones[..., None] * 0.085
    rough = 0.50 + 0.10 * n2 - 0.10 * stones + 0.05 * n3
    hgt = 0.35 * stones + 0.10 * n3 + 0.05 * n2
    # cracks (partial voronoi edges, jittered)
    F1, F2, ID = worley(h, w, 6, 6, seed + 4)
    edge = (F2 - F1) + 0.018 * fbm(h, w, seed + 5, 0.8)
    live = smooth(0.10, 0.55, fbm(h, w, seed + 6, 2.2) * 0.5 + 0.35 + crack - 0.5)
    cr = (1 - smooth(0.0, 0.032, edge)) * live
    alb = alb * (1 - 0.55 * cr[..., None])
    hgt = hgt - 0.9 * cr
    rough = rough + 0.12 * cr
    # repaired patches
    rng = np.random.default_rng(seed + 7)
    X, Y = coords(h, w)
    for _ in range(patches):
        cx, cy = rng.uniform(0.12, 0.88, 2)
        wx, wy = rng.uniform(0.05, 0.16), rng.uniform(0.04, 0.12)
        m = rect_aa(X, Y, cx - wx, cy - wy, cx + wx, cy + wy, 0.004)
        m = blur(m, max(h, w) * 0.002)
        t = rng.uniform(-0.05, 0.06)
        alb = alb + m[..., None] * t
        rough = rough - m * 0.12
        hgt = hgt + m * 0.08
    # oil / rain polish blotches (very smooth, darker)
    o = smooth(0.55, 1.25, fbm(h, w, seed + 8, 2.8) + oil - 0.5)
    alb = alb * (1 - 0.30 * o[..., None])
    rough = rough * (1 - 0.65 * o)
    return alb, rough, hgt, o


@reg('nc_asphalt', 1024, 1024)
def asphalt(h, w, seed):
    alb, rough, hgt, _ = _asphalt_core(h, w, seed + 100)
    return PBR(alb * 0.92, rough * 0.8, None, hgt)


@reg('nc_alley', 512, 512)
def alley(h, w, seed):
    alb, rough, hgt, o = _asphalt_core(h, w, seed + 140, tone=0.235, crack=0.8, patches=5, oil=0.75)
    X, Y = coords(h, w)
    # drain gutter line + rust stained grate marks
    gut = rect_aa(X, Y, 0.0, 0.47, 1.0, 0.53, 1.0 / w, 1.0 / h)
    alb = alb * (1 - 0.35 * gut[..., None])
    hgt = hgt - 0.6 * gut
    return PBR(alb * 0.9, rough * 0.7, None, hgt)


def _road(h, w, seed, width_m, lanes, median, edge_line, center_double, hwy=False, tone=0.20):
    alb, rough, hgt, o = _asphalt_core(h, w, seed, tone=tone)
    X, Y = coords(h, w)
    mx = X * width_m
    my = Y * 8.0
    pxm = width_m / w
    pym = 8.0 / h
    # lane geometry (metres from the left edge)
    e = 0.35
    lane_w = (width_m - median - 2 * e) / (2 * lanes)
    centers = [e + lane_w * (i + 0.5) for i in range(lanes)] + [width_m - e - lane_w * (i + 0.5) for i in range(lanes)]
    # tyre tracks: slightly darker, polished bands
    for c in centers:
        for off in (-0.85, 0.85):
            t = np.exp(-((mx - (c + off)) / 0.32) ** 2)
            alb = alb * (1 - 0.14 * t[..., None])
            rough = rough * (1 - 0.35 * t)
            hgt = hgt - 0.06 * t
    wear = np.clip(0.45 + 0.7 * fbm(h, w, seed + 20, 1.2) + 0.5 * grain(h, w, seed + 21, 0.8) * 0.5, 0, 1)
    wear = smooth(0.18, 0.62, wear)
    white = np.zeros((h, w), np.float32)
    yellow = np.zeros((h, w), np.float32)
    dash = np.clip((3.0 - (my % 8.0)) / pym + 0.5, 0, 1) * np.clip(((my % 8.0)) / pym + 0.5, 0, 1)
    if edge_line:
        white += _bar(mx, e, 0.18, pxm) + _bar(mx, width_m - e, 0.18, pxm)
    for side in (0, 1):
        for i in range(1, lanes):
            c = e + lane_w * i if side == 0 else width_m - e - lane_w * i
            white += _bar(mx, c, 0.14, pxm) * dash
    mid = width_m / 2
    if center_double:
        yellow += _bar(mx, mid - 0.17, 0.12, pxm) + _bar(mx, mid + 0.17, 0.12, pxm)
    elif median > 0:
        yellow += _bar(mx, mid - median / 2 + 0.05, 0.14, pxm) + _bar(mx, mid + median / 2 - 0.05, 0.14, pxm)
        # painted chevron hatching inside the median
        hat = np.clip(1 - np.abs(((my + (mx - mid) * 1.2) % 4.0) - 2.0) / 0.18, 0, 1) * _bar(mx, mid, median - 0.4, pxm)
        white += hat * 0.8
    white = np.clip(white, 0, 1) * wear
    yellow = np.clip(yellow, 0, 1) * wear
    alb = lerp(alb, rgb(0.64, 0.64, 0.62), white[..., None] * 0.95)
    alb = lerp(alb, rgb(0.66, 0.50, 0.08), yellow[..., None] * 0.95)
    paint = np.clip(white + yellow, 0, 1)
    rough = lerp(rough, 0.42, paint)
    hgt = hgt + 0.10 * paint
    return PBR(alb * 0.95, rough * 0.8, None, hgt)


@reg('nc_road_ave', 1024, 512)
def road_ave(h, w, seed):
    return _road(h, w, seed + 200, 24.0, 3, 2.0, True, False)


@reg('nc_road_str', 1024, 512)
def road_str(h, w, seed):
    return _road(h, w, seed + 230, 14.0, 2, 0.0, False, True, tone=0.215)


@reg('nc_road_hwy', 1024, 512)
def road_hwy(h, w, seed):
    return _road(h, w, seed + 260, 12.0, 3, 0.0, True, False, hwy=True, tone=0.17)


@reg('nc_crosswalk', 512, 512)
def crosswalk(h, w, seed):
    alb, rough, hgt, o = _asphalt_core(h, w, seed + 300)
    X, Y = coords(h, w)
    wear = smooth(0.15, 0.6, 0.5 + 0.6 * fbm(h, w, seed + 301, 1.4) + 0.25 * grain(h, w, seed + 302, 0.8))
    st = np.clip((0.5 - (X * 4 % 1.0)) / (4.0 / w) * 0.25 + 0.5, 0, 1) * np.clip((X * 4 % 1.0) / (4.0 / w) * 0.25 + 0.5, 0, 1)
    # stripes: 0.5 m wide every 1.0 m (4 m tile), stop line (0.5 m) at the bottom edge
    stop = np.clip((Y - 0.865) / (4.0 / h) * 0.25 + 0.5, 0, 1)
    paint = np.clip(np.maximum(st * (Y < 0.84), stop * (Y < 0.99)), 0, 1) * wear
    alb = lerp(alb, rgb(0.66, 0.66, 0.64), paint[..., None] * 0.95)
    rough = lerp(rough, 0.40, paint)
    return PBR(alb * 0.95, rough * 0.8, None, hgt + 0.1 * paint)


# ---------------------------------------------------------------------------------------------
# pavements
# ---------------------------------------------------------------------------------------------
def _slabs(h, w, seed, n, joint, tone, tint, gloss=0.35):
    X, Y = coords(h, w)
    fx, fy = (X * n) % 1.0, (Y * n) % 1.0
    ix, iy = np.floor(X * n).astype(int), np.floor(Y * n).astype(int)
    rng = np.random.default_rng(seed)
    tv = rng.normal(0, 1, (n, n)).astype(np.float32)
    slab_t = tv[iy % n, ix % n]
    jw = joint * n
    ex = np.minimum(fx, 1 - fx)
    ey = np.minimum(fy, 1 - fy)
    ed = np.minimum(ex, ey)
    jmask = np.clip(1 - ed / jw, 0, 1) ** 1.4
    n1 = fbm(h, w, seed + 1, 2.4)
    n2 = fbm(h, w, seed + 2, 1.0)
    g = grain(h, w, seed + 3, 0.8)
    base = tone * (1 + 0.08 * slab_t + 0.10 * n1 + 0.05 * n2)
    alb = base[..., None] * tint + 0.03 * np.clip(g, 0, 3)[..., None]
    alb = alb * (1 - 0.65 * jmask[..., None])
    # wet darker patches
    wetm = smooth(0.2, 0.9, fbm(h, w, seed + 4, 2.7))
    alb = alb * (1 - 0.30 * wetm[..., None])
    rough = gloss + 0.15 * n2 + 0.12 * jmask - 0.22 * wetm
    hgt = -0.55 * jmask + 0.05 * n2 + 0.06 * g
    return alb, rough, hgt, ed, slab_t


@reg('nc_sidewalk', 1024, 1024)
def sidewalk(h, w, seed):
    alb, rough, hgt, ed, st = _slabs(h, w, seed + 400, 4, 0.010, 0.27, rgb(1.0, 0.99, 0.97))
    X, Y = coords(h, w)
    # gum / stains
    rng = np.random.default_rng(seed + 401)
    for _ in range(26):
        cx, cy = rng.random(2)
        r = rng.uniform(0.002, 0.005)
        m = np.exp(-(((X - cx) ** 2 + (Y - cy) ** 2) / r ** 2))
        alb = alb * (1 - 0.25 * m[..., None])
    return PBR(alb, rough, None, hgt)


@reg('nc_curb', 256, 256)
def curb(h, w, seed):
    g = grain(h, w, seed + 500, 0.9)
    n1 = fbm(h, w, seed + 501, 2.0)
    base = 0.33 * (1 + 0.1 * n1 + 0.04 * g)
    alb = base[..., None] * rgb(1.0, 1.0, 1.02)
    X, Y = coords(h, w)
    alb = alb * (1 - 0.5 * np.clip(1 - np.abs(X - 0.5) / 0.004, 0, 1)[..., None] * 0)   # (no joint: the curb is long)
    return PBR(alb, 0.55 + 0.1 * n1, None, 0.05 * g)


@reg('nc_plaza', 1024, 1024)
def plaza(h, w, seed):
    alb, rough, hgt, ed, st = _slabs(h, w, seed + 600, 4, 0.006, 0.12, rgb(0.92, 0.95, 1.06), gloss=0.16)
    X, Y = coords(h, w)
    em = np.zeros((h, w, 3), np.float32)
    # inlaid light lines: on every second joint + a thin ring pattern
    fx, fy = (X * 4) % 1.0, (Y * 4) % 1.0
    ix, iy = np.floor(X * 4).astype(int), np.floor(Y * 4).astype(int)
    lw = 1.6 / w * 4
    lx = np.clip(1 - np.abs(fx - 0.5) / lw, 0, 1) * ((ix + iy) % 2 == 0)
    ly = np.clip(1 - np.abs(fy - 0.5) / lw, 0, 1) * ((ix + iy) % 2 == 1)
    line = np.clip(lx + ly, 0, 1)
    cyan = rgb(0.10, 0.85, 1.0)
    em += line[..., None] * cyan * 1.0
    alb = lerp(alb, rgb(0.05, 0.12, 0.14), line[..., None] * 0.8)
    rough = rough * (1 - 0.5 * line)
    return PBR(alb, rough, None, hgt, em)


# ---------------------------------------------------------------------------------------------
# concrete, metal, walls
# ---------------------------------------------------------------------------------------------
def _concrete(h, w, seed, tone, panels, tint, stain=0.5, dirt=0.4, wet=0.0):
    X, Y = coords(h, w)
    n1 = fbm(h, w, seed, 2.5)
    n2 = fbm(h, w, seed + 1, 1.2)
    g = grain(h, w, seed + 2, 0.7)
    base = tone * (1 + 0.10 * n1 + 0.06 * n2 + 0.035 * g)
    alb = base[..., None] * tint
    hgt = 0.06 * g + 0.05 * n2
    rough = 0.72 + 0.10 * n2 - 0.15 * wet
    if panels > 0:
        fx, fy = (X * panels) % 1.0, (Y * panels) % 1.0
        ed = np.minimum(np.minimum(fx, 1 - fx), np.minimum(fy, 1 - fy))
        j = np.clip(1 - ed / (0.5 * panels / w * 2), 0, 1)
        alb = alb * (1 - 0.55 * j[..., None])
        hgt = hgt - 0.5 * j
        # tie holes
        for ox in (0.2, 0.8):
            for oy in (0.2, 0.8):
                d = np.sqrt((((X * panels) % 1.0 - ox)) ** 2 + (((Y * panels) % 1.0 - oy)) ** 2)
                hole = np.clip(1 - d / 0.012, 0, 1)
                alb = alb * (1 - 0.5 * hole[..., None])
                hgt = hgt - 0.3 * hole
    # rain streaks (anisotropic noise) + dirt creeping up from the bottom
    st_n = np.random.default_rng(seed + 3).standard_normal((h, w)).astype(np.float32)
    from scipy import ndimage as ndi
    st_n = ndi.gaussian_filter(st_n, (h / 6.0, 1.2), mode='wrap')
    st_n = st_n / (st_n.std() + 1e-9)
    streak = smooth(0.2, 1.8, st_n)
    alb = alb * (1 - stain * 0.32 * streak[..., None])
    rough = rough - 0.20 * streak * stain
    dirty = smooth(0.0, 1.0, (Y - 0.55) * 2.2 + 0.4 * n1) * dirt
    alb = alb * (1 - 0.35 * dirty[..., None])
    return alb, rough, hgt


@reg('nc_concrete', 512, 512)
def concrete(h, w, seed):
    alb, rough, hgt = _concrete(h, w, seed + 700, 0.37, 2, rgb(1.0, 0.99, 0.97))
    return PBR(alb, rough, None, hgt)


@reg('nc_concrete_dark', 512, 512)
def concrete_dark(h, w, seed):
    alb, rough, hgt = _concrete(h, w, seed + 720, 0.22, 0, rgb(0.98, 1.0, 1.04), stain=0.9, dirt=0.7, wet=0.4)
    return PBR(alb, rough, None, hgt)


@reg('nc_pillar', 256, 512)
def pillar(h, w, seed):
    alb, rough, hgt = _concrete(h, w, seed + 740, 0.31, 0, rgb(1.0, 0.99, 0.98), stain=0.8, dirt=0.6)
    X, Y = coords(h, w)
    # form-work: horizontal pour lines every 0.5 and vertical seams
    pl = np.clip(1 - np.abs(((Y * 4) % 1.0) - 0.5) / 0.02, 0, 1) * 0 + np.clip(1 - np.minimum((Y * 8) % 1.0, 1 - (Y * 8) % 1.0) / 0.03, 0, 1)
    alb = alb * (1 - 0.35 * pl[..., None])
    hgt = hgt - 0.35 * pl
    return PBR(alb, rough, None, hgt)


@reg('nc_deck_under', 256, 256)
def deck_under(h, w, seed):
    alb, rough, hgt = _concrete(h, w, seed + 760, 0.20, 2, rgb(1.0, 1.0, 1.02), stain=0.9, dirt=0.2)
    return PBR(alb, rough, None, hgt)


def _metal(h, w, seed, col, rough0, scratchy=0.5, rust=0.0, metal=0.9, seam=0):
    n1 = fbm(h, w, seed, 2.2)
    g = grain(h, w, seed + 1, 0.6)
    s = scratches(h, w, int(h * 0.4), h * 0.05, h * 0.3, seed + 2, angle=0.05, spread=0.4)
    alb = np.asarray(col, np.float32)[None, None, :] * (1 + 0.08 * n1[..., None] + 0.03 * g[..., None])
    alb = alb + s[..., None] * 0.06 * scratchy
    X, Y = coords(h, w)
    hgt = 0.04 * g
    rough = rough0 + 0.12 * n1 - 0.1 * s
    mt = np.full((h, w), metal, np.float32)
    if seam:
        sm = np.clip(1 - np.abs(((Y * seam) % 1.0) - 0.5) / (0.6 / h * seam), 0, 1) * 0 + np.clip(1 - np.minimum((Y * seam) % 1.0, 1 - (Y * seam) % 1.0) / (1.5 / h * seam), 0, 1)
        alb = alb * (1 - 0.5 * sm[..., None])
        hgt = hgt - 0.5 * sm
    if rust > 0:
        r = smooth(0.2, 0.9, fbm(h, w, seed + 5, 2.6) * 0.8 + rust - 0.5 + 0.3 * grain(h, w, seed + 6, 1.5))
        alb = lerp(alb, rgb(0.34, 0.15, 0.06) * (0.8 + 0.4 * n1[..., None]), r[..., None] * 0.9)
        rough = lerp(rough, 0.85, r)
        mt = mt * (1 - r)
    return alb, rough, mt, hgt


@reg('nc_metal_dark', 256, 256)
def metal_dark(h, w, seed):
    a, r, m, hg = _metal(h, w, seed + 800, (0.07, 0.075, 0.085), 0.42, 0.6)
    return PBR(a, r, m * 0.8, hg)


@reg('nc_metal_light', 256, 256)
def metal_light(h, w, seed):
    a, r, m, hg = _metal(h, w, seed + 820, (0.45, 0.47, 0.49), 0.38, 0.8, seam=2)
    return PBR(a, r, m, hg)


@reg('nc_metal_rust', 256, 256)
def metal_rust(h, w, seed):
    a, r, m, hg = _metal(h, w, seed + 840, (0.20, 0.21, 0.22), 0.6, 0.5, rust=0.62)
    return PBR(a, r, m, hg)


@reg('nc_steel', 256, 256)
def steel(h, w, seed):
    a, r, m, hg = _metal(h, w, seed + 860, (0.12, 0.13, 0.15), 0.45, 0.5, rust=0.12, seam=4)
    return PBR(a, r, m * 0.9, hg)


@reg('nc_wall_metal', 256, 256)
def wall_metal(h, w, seed):
    a, r, m, hg = _metal(h, w, seed + 880, (0.11, 0.12, 0.14), 0.36, 0.7, seam=4)
    X, Y = coords(h, w)
    ver = np.clip(1 - np.minimum((X * 2) % 1.0, 1 - (X * 2) % 1.0) / (1.5 / w * 2), 0, 1)
    a = a * (1 - 0.4 * ver[..., None])
    for ox in (0.06, 0.94):
        for k in range(8):
            d = np.sqrt(((X * 2) % 1.0 - ox) ** 2 + (((Y * 8) % 1.0) - 0.5) ** 2 * 0.25)
            a = a + np.clip(1 - d / 0.01, 0, 1)[..., None] * 0.05
    return PBR(a, r, m * 0.85, hg - 0.3 * ver)


@reg('nc_wall_corrug', 256, 256)
def wall_corrug(h, w, seed):
    X, Y = coords(h, w)
    ph = (X * 12) % 1.0
    prof = np.sin(ph * 2 * np.pi)
    a, r, m, hg = _metal(h, w, seed + 900, (0.20, 0.23, 0.24), 0.5, 0.4, rust=0.30)
    a = a * (0.80 + 0.22 * prof[..., None])
    # vertical rust streaks
    from scipy import ndimage as ndi
    st = ndi.gaussian_filter(np.random.default_rng(seed + 901).standard_normal((h, w)).astype(np.float32), (h / 5.0, 0.8), mode='wrap')
    st = smooth(0.4, 2.2, st / (st.std() + 1e-9))
    a = lerp(a, rgb(0.25, 0.12, 0.06), st[..., None] * 0.45)
    return PBR(a, r, m * 0.7, hg + 0.5 * prof)


@reg('nc_roof', 256, 256)
def roof(h, w, seed):
    g = grain(h, w, seed + 950, 0.6)
    n = fbm(h, w, seed + 951, 2.2)
    stones = np.clip((grain(h, w, seed + 952, 0.9) - 1.0) / 1.5, 0, 1)
    base = 0.12 * (1 + 0.14 * n + 0.05 * g)
    alb = base[..., None] * rgb(1.0, 1.0, 1.04) + stones[..., None] * 0.10
    return PBR(alb, 0.8 - 0.3 * smooth(0.5, 1.2, n), None, 0.2 * stones + 0.05 * g)


@reg('nc_riverbed', 256, 256)
def riverbed(h, w, seed):
    alb, rough, hgt = _concrete(h, w, seed + 970, 0.15, 0, rgb(0.9, 1.0, 0.95), stain=1.0, dirt=0.9, wet=1.0)
    return PBR(alb, rough * 0.6, None, hgt)


def _container(h, w, seed, col):
    X, Y = coords(h, w)
    ph = (X * 10) % 1.0
    prof = np.sin(ph * 2 * np.pi)
    n1 = fbm(h, w, seed, 2.2)
    g = grain(h, w, seed + 1, 0.7)
    base = np.asarray(col, np.float32)[None, None, :] * (1 + 0.14 * n1[..., None] + 0.03 * g[..., None])
    alb = base * (0.80 + 0.22 * prof[..., None])
    from scipy import ndimage as ndi
    st = ndi.gaussian_filter(np.random.default_rng(seed + 2).standard_normal((h, w)).astype(np.float32), (h / 5.0, 1.0), mode='wrap')
    st = smooth(0.3, 2.2, st / (st.std() + 1e-9))
    alb = lerp(alb, rgb(0.22, 0.10, 0.05), st[..., None] * 0.35)
    alb = alb * (1 - 0.5 * np.clip(1 - np.minimum(Y, 1 - Y) / 0.02, 0, 1)[..., None])
    return PBR(alb, 0.55 + 0.15 * n1 - 0.15 * st, None, 0.5 * prof + 0.05 * g)


@reg('nc_container_a', 256, 256)
def container_a(h, w, seed):
    return _container(h, w, seed + 1000, (0.35, 0.10, 0.07))


@reg('nc_container_b', 256, 256)
def container_b(h, w, seed):
    return _container(h, w, seed + 1020, (0.07, 0.24, 0.27))


@reg('nc_container_c', 256, 256)
def container_c(h, w, seed):
    return _container(h, w, seed + 1040, (0.42, 0.28, 0.06))


@reg('nc_tank', 256, 256)
def tank(h, w, seed):
    a, r, m, hg = _metal(h, w, seed + 1060, (0.62, 0.64, 0.64), 0.5, 0.2, rust=0.10)
    X, Y = coords(h, w)
    wl = np.clip(1 - np.minimum((Y * 4) % 1.0, 1 - (Y * 4) % 1.0) / (1.2 / h * 4), 0, 1)
    a = a * (1 - 0.4 * wl[..., None])
    return PBR(a * 0.55, r, m * 0.2, hg - 0.3 * wl)


@reg('nc_sky_noise', 256, 256)
def sky_noise(h, w, seed):
    """tileable value-noise field for the sky dome shader (sky.fx): the three channels are independent
    periodic fbm fields at different spectral slopes; the shader samples them at several scales to build
    the cloud layers (R broad billows, G medium detail, B fine wisps)."""
    r = np.clip(0.5 + 0.20 * fbm(h, w, seed + 1, 2.2), 0, 1)
    g = np.clip(0.5 + 0.22 * fbm(h, w, seed + 2, 1.6), 0, 1)
    b = np.clip(0.5 + 0.24 * fbm(h, w, seed + 3, 1.1), 0, 1)
    return PBR(np.stack([r, g, b], -1), 1.0, 0.0, 0.0)
