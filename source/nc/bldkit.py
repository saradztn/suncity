# Created by: Arena.ai Agent Mode (AI) - NightCity MTA:SA asset pipeline
# -----------------------------------------------------------------------------
# bldkit.py - building construction helpers: floor-aligned curtain-wall facades, tiers, ledges, fins, podiums with shop
#             fronts, roofs with machinery, sign mounting.  The facade UVs are aligned to the cells of the facade textures
#             (4 bays x 8 floors per tile) so that every window is complete.
# -----------------------------------------------------------------------------
import numpy as np
from .mb import Mesh, Col, TAU, unit
from . import parts as P

FLOOR_H = 3.8
BAY_W = 3.2
POD_H = 6.4


def rect(w, d, cx=0.0, cy=0.0):
    return np.array([[cx - w / 2, cy - d / 2], [cx + w / 2, cy - d / 2], [cx + w / 2, cy + d / 2], [cx - w / 2, cy + d / 2]], float)


def chamfer(w, d, c, cx=0.0, cy=0.0):
    x0, x1, y0, y1 = cx - w / 2, cx + w / 2, cy - d / 2, cy + d / 2
    return np.array([[x0 + c, y0], [x1 - c, y0], [x1, y0 + c], [x1, y1 - c], [x1 - c, y1], [x0 + c, y1], [x0, y1 - c], [x0, y0 + c]], float)


def regular(n, r, cx=0.0, cy=0.0, th0=0.0):
    th = th0 + np.arange(n) * TAU / n
    return np.stack([cx + r * np.cos(th), cy + r * np.sin(th)], -1)


def offset_poly(poly, d):
    """grow (d>0) / shrink a convex CCW polygon by d (mitre joins)"""
    p = np.asarray(poly, float)
    n = len(p)
    out = []
    for i in range(n):
        a, b, c = p[i - 1], p[i], p[(i + 1) % n]
        e1, e2 = unit(b - a), unit(c - b)
        n1, n2 = np.array([e1[1], -e1[0]]), np.array([e2[1], -e2[0]])
        m = n1 + n2
        k = 1.0 + float(np.dot(n1, n2))
        out.append(b + m * d / max(k, 1e-3))
    return np.array(out)


def facade(M, a, b, z0, z1, mat, rng, bays_tile=4, floors_tile=8, bay_w=BAY_W, floor_h=FLOOR_H, emis=0.9):
    """floor / bay aligned wall quad (outside = right of a->b)"""
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    L = float(np.linalg.norm(b - a))
    if L < 0.2 or z1 - z0 < 0.2:
        return
    nb = max(1, int(round(L / bay_w)))
    nf = max(1, int(round((z1 - z0) / floor_h)))
    uspan, vspan = nb / bays_tile, nf / floors_tile
    tu, tv = L / uspan, (z1 - z0) / vspan
    uoff = int(rng.integers(0, bays_tile)) / bays_tile
    k = int(rng.integers(1, floors_tile + 1))
    voff = z0 / tv + k / floors_tile
    M.wall(a, b, z0, z1, mat, tile=(tu, tv), uoff=uoff, voff=voff, emis=emis)


def ledge(M, poly, z0, z1, out=0.3, mat='nc_concrete_dark'):
    M.extrude(offset_poly(poly, out), z0, z1, mat, mat, tile=(4.0, 1.0))


def fins(M, poly, z0, z1, every=1.0, w=0.35, depth=0.45, mat='nc_metal_dark', bay=BAY_W):
    n = len(poly)
    for i in range(n):
        a, b = np.asarray(poly[i], float), np.asarray(poly[(i + 1) % n], float)
        L = float(np.linalg.norm(b - a))
        nb = max(1, int(round(L / bay)))
        e = (b - a) / L
        nrm = np.array([e[1], -e[0]])
        for k in range(0, nb + 1, max(1, int(every))):
            p = a + e * (L * k / nb) + nrm * (depth / 2 - 0.02)
            P.bar(M, (p[0], p[1], z0), (p[0], p[1], z1), max(w, depth) if False else w, mat)


def tier(M, C, poly, z0, z1, mat, rng, emis=0.9, ledge_every=0, fin_every=0, corners=True, roof=True, roof_mat='nc_roof',
         bays_tile=4, floors_tile=8, bay_w=BAY_W, floor_h=FLOOR_H, col=True, fin_w=0.35, fin_depth=0.45):
    poly = np.asarray(poly, float)
    n = len(poly)
    for i in range(n):
        facade(M, poly[i], poly[(i + 1) % n], z0, z1, mat, rng, bays_tile, floors_tile, bay_w, floor_h, emis)
    if corners:
        for p in poly:
            M.box((p[0] - 0.28, p[1] - 0.28, z0), (p[0] + 0.28, p[1] + 0.28, z1), 'nc_metal_dark', tile=(1, 1))
    if ledge_every:
        nf = int(round((z1 - z0) / floor_h))
        for k in range(ledge_every, nf, ledge_every):
            zz = z0 + k * (z1 - z0) / nf
            ledge(M, poly, zz - 0.25, zz + 0.25, 0.22)
    if fin_every:
        fins(M, poly, z0, z1, fin_every, fin_w, fin_depth)
    if roof:
        M.poly([(p[0], p[1], z1) for p in poly], roof_mat, (4.0, 4.0), up=True)
    if col:
        lo, hi = poly.min(0), poly.max(0)
        C.box((lo[0], lo[1], z0), (hi[0], hi[1], z1))


def parapet(M, poly, z, h=1.0, mat='nc_concrete_dark', t=0.35):
    poly = np.asarray(poly, float)
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        e = unit(b - a)
        nrm = np.array([e[1], -e[0]])
        # thin wall: outer face + top (inner face omitted: not visible from the street)
        M.wall(a, b, z, z + h, mat, tile=(4, 2))
        a2, b2 = a - nrm * t, b - nrm * t
        M.quad((a[0], a[1], z + h), (b[0], b[1], z + h), (b2[0], b2[1], z + h), (a2[0], a2[1], z + h), mat, tile=(2, 2))


def roof_clutter(M, rng, poly, z, n_ac=4, n_tank=0, n_ant=1, n_dish=0, n_stack=0, n_hvac=1, edge=2.5):
    lo, hi = np.asarray(poly).min(0) + edge, np.asarray(poly).max(0) - edge
    if (hi - lo).min() < 2.0:
        return
    taken = []

    def spot(r):
        for _ in range(30):
            p = rng.uniform(lo, hi)
            if all(np.linalg.norm(p - q) > r + rr for q, rr in taken):
                taken.append((p, r))
                return p
        return None

    for _ in range(n_hvac):
        p = spot(2.2)
        if p is not None:
            M.merge(P.hvac_box(float(rng.choice([2.4, 3.0, 3.6])), 2.2, 1.5), (p[0], p[1], z), rz=float(rng.choice([0, 90, 180, 270])))
    for _ in range(n_ac):
        p = spot(1.0)
        if p is not None:
            M.merge(P.ac_unit(), (p[0], p[1], z), rz=float(rng.choice([0, 90, 180, 270])))
    for _ in range(n_tank):
        p = spot(2.2)
        if p is not None:
            M.merge(P.water_tank(float(rng.choice([1.3, 1.6])), 2.4), (p[0], p[1], z))
    for _ in range(n_ant):
        p = spot(0.8)
        if p is not None:
            M.merge(P.antenna(float(rng.uniform(8, 18)), True), (p[0], p[1], z))
    for _ in range(n_dish):
        p = spot(1.2)
        if p is not None:
            M.merge(P.dish(float(rng.uniform(0.7, 1.1))), (p[0], p[1], z), rz=float(rng.uniform(0, 360)))
    for _ in range(n_stack):
        p = spot(0.9)
        if p is not None:
            M.merge(P.stack(0.5, float(rng.uniform(2.5, 4.5))), (p[0], p[1], z))


def podium(M, C, w, d, rng, kinds=('retail', 'club', 'food'), h=POD_H, mat_base='nc_concrete_dark', canopy=True, z0=0.0):
    """shop-front band around a rectangle w x d (centred), plus slab roof / canopy"""
    poly = rect(w, d)
    for i in range(4):
        a, b = poly[i], poly[(i + 1) % 4]
        L = float(np.linalg.norm(b - a))
        nb = max(1, int(round(L / BAY_W)))
        kind = kinds[int(rng.integers(len(kinds)))]
        uspan = nb / 4.0
        uoff = int(rng.integers(0, 4)) / 4.0
        M.wall(a, b, z0, z0 + h, 'nc_shop_' + kind, tile=(L / uspan, h / 1.0), uoff=uoff, voff=0.0 + (z0 / h), emis=0.85)
        # shop light spill (for the vertex light bake)
        e = unit(b - a)
        nrm = np.array([e[1], -e[0]])
        for k in range(max(1, nb // 2)):
            p = a + e * (L * (k + 0.5) / max(1, nb // 2)) + nrm * 1.5
            c = [P.WARMW, P.MAG, P.CYA, P.COOL][int(rng.integers(4))] if kind != 'retail' else P.COOL
            M.light((p[0], p[1], z0 + 2.5), c, 0.7, 9.0, n=(nrm[0], nrm[1], 0))
    if canopy:
        M.extrude(offset_poly(poly, 0.9), z0 + h, z0 + h + 0.35, mat_base, mat_base, tile=(4, 1), bottom_mat=mat_base)
    C.box((-w / 2, -d / 2, z0), (w / 2, d / 2, z0 + h + 0.35))


def blade_sign(M, wall_pt, wall_n, z, kind, idx, w, h, out=0.8):
    """hanging double sided sign perpendicular to the wall"""
    wx, wy = wall_pt
    nx, ny = wall_n
    cx, cy = wx + nx * (out + 0.2), wy + ny * (out + 0.2)
    along = np.array([ny, -nx])        # direction along the wall
    for side in (1, -1):
        s = P.neon_sign(kind, idx, w, h)
        M.merge(s, (cx + along[0] * side * 0.14, cy + along[1] * side * 0.14, z), rz=P.yaw_facing(along[0] * side, along[1] * side))
    # mounting arms
    for dz in (-h * 0.35, h * 0.35):
        P.bar(M, (wx, wy, z + dz), (cx, cy, z + dz), 0.07, P.MD)


def wall_sign(M, a, b, z, kind, idx, w, h, t=0.0, along=0.5):
    """flush sign on wall segment a->b at fractional position `along`, centre height z"""
    a, b = np.asarray(a, float), np.asarray(b, float)
    L = float(np.linalg.norm(b - a))
    e = (b - a) / L
    nrm = np.array([e[1], -e[0]])
    p = a + e * L * along + nrm * (0.18 + t)
    s = P.neon_sign(kind, idx, w, h) if kind in ('h', 'v') else (P.ad_panel(idx, w, h) if kind == 'ad' else P.led_panel(idx, w, h))
    M.merge(s, (p[0], p[1], z), rz=P.yaw_facing(nrm[0], nrm[1]))
