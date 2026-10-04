# Created by: Arena.ai Agent Mode (AI) - NightCity MTA:SA asset pipeline
# -----------------------------------------------------------------------------
# bld.py - building archetypes.  Every function returns (Mesh, Col, meta).  Local frame: origin = footprint centre at
#          street level, z up.  Deterministic per seed.  Facades use floor / bay aligned UVs (see bldkit.facade).
# -----------------------------------------------------------------------------
import numpy as np
from .mb import Mesh, Col, TAU, unit
from . import parts as P
from . import bldkit as K
from .bldkit import FLOOR_H, POD_H, rect, chamfer, regular, offset_poly

STRIP = ['nc_strip_cyan', 'nc_strip_white', 'nc_strip_cyan']
GLASSES = ['nc_glass_a', 'nc_glass_b', 'nc_glass_c', 'nc_glass_d', 'nc_glass_e', 'nc_glass_f', 'nc_glass_g', 'nc_glass_h']
LEDCOL = {'nc_strip_cyan': P.CYA, 'nc_strip_white': P.COOL, 'nc_light_magenta': P.MAG, 'nc_light_amber': (1.0, 0.55, 0.1)}


def glow_band(M, poly, z, h=0.55, mat='nc_strip_cyan', out=0.25, lights=0, rng=None):
    """emissive LED band around a tier top"""
    off = offset_poly(poly, out)
    M.extrude(off, z, z + h, mat, mat, tile=(2, 1), emis=1.0)
    col = LEDCOL.get(mat, P.COOL)
    for i in range(lights):
        p = off[i % len(off)]
        M.light((p[0], p[1], z + 0.5), col, 1.0, 22.0)


def crown(M, C, poly, z, style, rng, mat_led='nc_strip_cyan'):
    poly = np.asarray(poly, float)
    lo, hi = poly.min(0), poly.max(0)
    ctr = poly.mean(0)
    K.parapet(M, poly, z, 1.2)
    if style == 'flat':
        K.roof_clutter(M, rng, poly, z, n_ac=int(rng.integers(3, 7)), n_tank=1, n_ant=2, n_dish=1, n_stack=1, n_hvac=2)
    elif style == 'spire':
        s0 = offset_poly(poly, -1.0)
        s1 = ctr + (s0 - ctr) * 0.45
        n = len(poly)
        M.loft(s0, z + 0.4, s1, z + 14.0, 'nc_metal_dark', 'nc_metal_dark', tile=(4, 4))
        glow_band(M, poly, z, 0.5, mat_led, 0.35, lights=2)
        M.merge(P.antenna(float(rng.uniform(22, 36)), True), (ctr[0], ctr[1], z + 14.0))
        K.roof_clutter(M, rng, poly, z, n_ac=2, n_ant=0, n_hvac=1, edge=1.5)
    elif style == 'ring':
        glow_band(M, poly, z, 0.7, mat_led, 0.4, lights=3)
        s0 = offset_poly(poly, -1.5)
        M.extrude(s0, z, z + 5.0, 'nc_wall_metal', 'nc_roof', tile=(4, 4))
        glow_band(M, s0, z + 5.0, 0.4, 'nc_strip_white', 0.2)
        glow_band(M, s0, z + 2.4, 0.35, mat_led, 0.12)
        M.merge(P.antenna(float(rng.uniform(14, 24)), True), (ctr[0], ctr[1], z + 5.0))
        K.roof_clutter(M, rng, poly, z, n_ac=2, n_ant=0, n_hvac=1, edge=1.5)
    elif style == 'prongs':
        for p in poly[:4] if len(poly) >= 4 else poly:
            q = ctr + (p - ctr) * 0.86
            M.loft(regular(4, 1.3, q[0], q[1], np.pi / 4), z, regular(4, 0.35, q[0], q[1], np.pi / 4), z + 16.0, 'nc_metal_dark', 'nc_metal_dark', tile=(2, 2))
            P.beacon_light(M, (q[0] - 0.15, q[1] - 0.15, z + 16.0))
        glow_band(M, poly, z, 0.5, mat_led, 0.3, lights=2)
        K.roof_clutter(M, rng, poly, z, n_ac=3, n_ant=0, n_hvac=1, n_dish=1, edge=3.0)
    elif style == 'dish':
        K.roof_clutter(M, rng, poly, z, n_ac=3, n_ant=1, n_hvac=1, edge=3.0)
        M.merge(P.dish(2.6), (ctr[0], ctr[1], z), rz=float(rng.uniform(0, 360)))
        glow_band(M, poly, z, 0.5, mat_led, 0.3, lights=2)


def _meta(kind, w, d, h, floors, dist=600.0, **kw):
    m = dict(kind=kind, w=float(w), d=float(d), h=float(h), floors=int(floors), dist=float(dist))
    m.update(kw)
    return m


# ---------------------------------------------------------------------------------------------
# skyscrapers
# ---------------------------------------------------------------------------------------------
def tower_setback(w, d, floors, mat, seed, crown_style='spire', steps=2, scale_top=0.62, pod=1, fin=0, signs=2, led='nc_strip_cyan', octo=False):
    rng = np.random.default_rng(seed)
    M, C = Mesh(), Col()
    zp = 0.0
    kinds = [('retail', 'club', 'food'), ('retail', 'retail', 'club')]
    for k in range(pod):
        K.podium(M, C, w + 6, d + 6, rng, kinds=kinds[k % 2], z0=zp, canopy=(k == pod - 1))
        zp += POD_H
    z = zp + 0.35
    fl_tot = max(8, floors)
    shares = np.array([1.0 / (steps + 1)] * (steps + 1))
    shares = shares * np.linspace(1.5, 0.6, steps + 1)
    shares = shares / shares.sum()
    scale = np.linspace(1.0, scale_top, steps + 1)
    poly = None
    for i in range(steps + 1):
        nf = max(3, int(round(fl_tot * shares[i])))
        c = 2.4 if octo else 0.0
        poly = chamfer(w * scale[i], d * scale[i], c) if octo else rect(w * scale[i], d * scale[i])
        z1 = z + nf * FLOOR_H
        K.tier(M, C, poly, z, z1, mat, rng, emis=0.9, ledge_every=int(rng.choice([4, 6, 8])), fin_every=(2 if (fin and i == 0) else 0))
        if i < steps:
            # terrace slab where the next tier steps back + glowing edge strip
            K.ledge(M, poly, z1, z1 + 0.5, 0.5)
            glow_band(M, poly, z1 + 0.5, 0.3, led, 0.5, lights=2)
            C.box((poly[:, 0].min(), poly[:, 1].min(), z1), (poly[:, 0].max(), poly[:, 1].max(), z1 + 0.5))
            z1 += 0.5
        z = z1
    # mechanical floor band + vents on the top tier
    crown(M, C, poly, z, crown_style, rng, led)
    # big screens and neon on the tower lower facade
    w0, d0 = w, d
    sides = [(rect(w0, d0)[i], rect(w0, d0)[(i + 1) % 4]) for i in range(4)]
    order = rng.permutation(4)
    zs = zp + 0.35
    for j in range(min(signs, 4)):
        a, b = sides[order[j]]
        L = np.linalg.norm(b - a)
        K.wall_sign(M, a, b, zs + 9.0 + 1.5 * j, 'ad' if j % 2 == 0 else 'led', int(rng.integers(0, 8)), min(L * 0.6, 16.0), 9.0, along=0.5)
    for j in range(2):
        a, b = sides[order[(j + 2) % 4]]
        K.wall_sign(M, a, b, zs + 3.0, 'h', int(rng.integers(0, 32)), 6.0, 1.5, along=float(rng.uniform(0.25, 0.75)))
    H = z + 24.0
    return M, C, _meta('tower', w + 6, d + 6, H, floors, 800.0, mat=mat)


def tower_cyl(r, floors, mat, seed, ring_every=8, n=24, led='nc_strip_cyan', crown_style='ring', pod=1):
    rng = np.random.default_rng(seed)
    M, C = Mesh(), Col()
    # round podium with shop band (polygon sides = bays)
    zp = POD_H
    pr = r + 3.5
    poly_p = regular(n, pr)
    chord = 2 * pr * np.sin(np.pi / n)
    kind = ('retail', 'club', 'food')[int(rng.integers(3))]
    M.extrude(poly_p, 0, zp, 'nc_shop_' + kind, 'nc_concrete_dark', tile=(chord * 4, POD_H), emis=0.85, smooth=False)
    for i in range(n // 3):
        a = poly_p[(3 * i) % n]
        c = [P.WARMW, P.MAG, P.CYA][int(rng.integers(3))]
        M.light((a[0] * 0.9, a[1] * 0.9, 2.5), c, 0.8, 10.0, n=(a[0], a[1], 0))
    M.extrude(offset_poly(poly_p, 0.8), zp, zp + 0.35, 'nc_concrete_dark', 'nc_concrete_dark', tile=(4, 1), bottom_mat='nc_concrete_dark')
    C.box((-pr, -pr, 0), (pr, pr, zp + 0.35))
    z = zp + 0.35
    nf = max(10, floors)
    poly = regular(n, r)
    chord = 2 * r * np.sin(np.pi / n)
    z1 = z + nf * FLOOR_H
    M.extrude(poly, z, z1, mat, 'nc_roof', tile=(chord * 4, FLOOR_H * 8), smooth=True, emis=0.9, uvoff=(0.0, z / (FLOOR_H * 8)))
    for k in range(ring_every, nf, ring_every):
        zz = z + k * FLOOR_H
        M.extrude(offset_poly(poly, 0.55), zz - 0.3, zz + 0.3, 'nc_concrete_dark', 'nc_concrete_dark', tile=(4, 1))
        glow_band(M, poly, zz + 0.3, 0.3, led, 0.5, lights=1)
    C.box((-r, -r, z), (r, r, z1))
    crown(M, C, poly, z1, crown_style, rng, led)
    return M, C, _meta('tower', pr * 2, pr * 2, z1 + 24, floors, 800.0, mat=mat)


def tower_twin(w, d, floors, gap, mat, seed, led='nc_strip_cyan'):
    rng = np.random.default_rng(seed)
    M, C = Mesh(), Col()
    W = 2 * w + gap
    K.podium(M, C, W + 6, d + 6, rng, kinds=('retail', 'club', 'food'))
    z0 = POD_H + 0.35
    nf = max(14, floors)
    zt = z0 + nf * FLOOR_H
    for sx in (-1, 1):
        cx = sx * (gap / 2 + w / 2)
        poly = rect(w, d, cx, 0)
        K.tier(M, C, poly, z0, zt, mat, rng, ledge_every=6, fin_every=2)
        K.ledge(M, poly, zt, zt + 0.5, 0.45)
        crown(M, C, poly, zt + 0.5, 'prongs' if sx > 0 else 'ring', rng, led)
    # sky bridge: glass tube between the towers (2 storeys), lit
    zb = z0 + int(nf * 0.58) * FLOOR_H
    bh = FLOOR_H * 2
    M.box((-gap / 2 - 0.2, -d * 0.18, zb), (gap / 2 + 0.2, d * 0.18, zb + bh), 'nc_glass_e', tile=(3.2 * 4, bh * 4), emis=0.95, skip=('+x', '-x'), uvoff=(0, 0.25))
    M.box((-gap / 2 - 0.2, -d * 0.18 - 0.2, zb - 0.9), (gap / 2 + 0.2, d * 0.18 + 0.2, zb), 'nc_metal_dark', tile=(2, 2))
    M.box((-gap / 2 - 0.2, -d * 0.18 - 0.2, zb + bh), (gap / 2 + 0.2, d * 0.18 + 0.2, zb + bh + 0.5), 'nc_metal_dark', tile=(2, 2))
    M.box((-gap / 2, -d * 0.18, zb + bh + 0.5), (gap / 2, d * 0.18, zb + bh + 0.56), 'nc_strip_cyan', tile=(1, 1), emis=1.0)
    M.light((0, 0, zb + bh / 2), P.COOL, 1.4, 30.0)
    C.box((-gap / 2, -d * 0.18 - 0.2, zb - 0.9), (gap / 2, d * 0.18 + 0.2, zb + bh + 0.5))
    for j in range(2):
        a, b = rect(W, d)[j * 2], rect(W, d)[(j * 2 + 1) % 4]
        K.wall_sign(M, a, b, POD_H + 10, 'ad', int(rng.integers(0, 8)), 16.0, 8.0)
    return M, C, _meta('tower', W + 6, d + 6, zt + 40, floors, 800.0, mat=mat)


def arcology(w, floors, seed, mat='nc_glass_e'):
    """hero: stepped pyramid megastructure"""
    rng = np.random.default_rng(seed)
    M, C = Mesh(), Col()
    K.podium(M, C, w + 8, w + 8, rng, kinds=('retail', 'club', 'food'), h=POD_H)
    z = POD_H + 0.35
    steps = 6
    scale = np.linspace(1.0, 0.22, steps)
    nfs = [int(round(floors * s)) for s in np.array([0.26, 0.22, 0.18, 0.14, 0.12, 0.08])]
    poly = None
    for i in range(steps):
        poly = chamfer(w * scale[i], w * scale[i], 3.0 * scale[i] + 1.0)
        nf = max(4, nfs[i])
        z1 = z + nf * FLOOR_H
        K.tier(M, C, poly, z, z1, mat if i % 2 == 0 else 'nc_glass_c', rng, ledge_every=4, fin_every=2 if i < 3 else 0, corners=True)
        K.ledge(M, poly, z1, z1 + 0.6, 0.7)
        glow_band(M, poly, z1 + 0.6, 0.35, 'nc_strip_cyan' if i % 2 == 0 else 'nc_strip_white', 0.7, lights=3)
        C.box((poly[:, 0].min(), poly[:, 1].min(), z1), (poly[:, 0].max(), poly[:, 1].max(), z1 + 0.6))
        z = z1 + 0.6
    crown(M, C, poly, z, 'spire', rng, 'nc_strip_white')
    for j in range(4):
        a, b = rect(w, w)[j], rect(w, w)[(j + 1) % 4]
        K.wall_sign(M, a, b, POD_H + 14, 'led', j, 22.0, 12.0, along=0.5)
        K.wall_sign(M, a, b, POD_H + 32, 'ad', j + 2, 18.0, 9.0, along=0.3)
    return M, C, _meta('tower', w + 8, w + 8, z + 40, floors, 900.0, mat=mat, hero=True)


# ---------------------------------------------------------------------------------------------
# mid and low rise
# ---------------------------------------------------------------------------------------------
def midrise(w, d, floors, mat, seed, signs=3, led='nc_strip_white'):
    rng = np.random.default_rng(seed)
    M, C = Mesh(), Col()
    K.podium(M, C, w, d, rng)
    z0 = POD_H + 0.35
    nf = max(4, floors)
    poly = rect(w - 1.2, d - 1.2)
    z1 = z0 + nf * FLOOR_H
    K.tier(M, C, poly, z0, z1, mat, rng, ledge_every=int(rng.choice([2, 3, 4])), fin_every=int(rng.choice([0, 0, 2])))
    crown(M, C, poly, z1, str(rng.choice(['flat', 'flat', 'ring', 'prongs'])), rng, led)
    sides = [(poly[i], poly[(i + 1) % 4]) for i in range(4)]
    order = rng.permutation(4)
    for j in range(min(signs, 4)):
        a, b = sides[order[j]]
        L = np.linalg.norm(b - a)
        kind = ['led', 'ad', 'led', 'ad'][j % 4]
        K.wall_sign(M, a, b, z0 + 7.0 + 3.0 * (j % 2), kind, int(rng.integers(0, 8)), min(L * 0.55, 14.0), min(9.0, 4.0 + nf * 0.4), along=float(rng.uniform(0.35, 0.65)))
    for j in range(3):
        a, b = sides[order[(j + 1) % 4]]
        L = np.linalg.norm(b - a)
        e = (b - a) / L
        nrm = np.array([e[1], -e[0]])
        p = a + e * L * float(rng.uniform(0.15, 0.85))
        K.blade_sign(M, p, nrm, POD_H + 2.5 + float(rng.uniform(0, 3)), 'v', int(rng.integers(0, 32)), 1.3, 4.2)
    return M, C, _meta('mid', w, d, z1 + 10, floors, 520.0, mat=mat)


def tenement(w, d, floors, mat, seed, escapes=2):
    rng = np.random.default_rng(seed)
    M, C = Mesh(), Col()
    K.podium(M, C, w, d, rng, kinds=('food', 'club', 'retail'), canopy=True)
    z0 = POD_H + 0.35
    nf = max(4, floors)
    poly = rect(w - 1.0, d - 1.0)
    z1 = z0 + nf * 3.3
    K.tier(M, C, poly, z0, z1, mat, rng, emis=0.62, ledge_every=0, bays_tile=4, floors_tile=4, bay_w=3.0, floor_h=3.3, corners=True)
    K.ledge(M, poly, z1, z1 + 0.45, 0.35)
    K.parapet(M, poly, z1 + 0.45, 1.0)
    K.roof_clutter(M, rng, poly, z1 + 0.45, n_ac=int(rng.integers(3, 8)), n_tank=int(rng.integers(1, 3)), n_ant=int(rng.integers(1, 3)), n_dish=int(rng.integers(1, 3)), n_stack=2, n_hvac=1)
    sides = [(poly[i], poly[(i + 1) % 4]) for i in range(4)]
    order = rng.permutation(4)
    for j in range(escapes):
        a, b = sides[order[j]]
        L = np.linalg.norm(b - a)
        e = (b - a) / L
        nrm = np.array([e[1], -e[0]])
        p = a + e * L * float(rng.uniform(0.3, 0.7))
        M.merge(P.fire_escape(min(4, nf - 1), 3.3, 2.6), (p[0], p[1], z0 + 0.0), rz=P.yaw_facing(nrm[0], nrm[1]))
    # air conditioners bolted on the facades
    for j in range(int(nf * 1.6)):
        a, b = sides[int(rng.integers(4))]
        L = np.linalg.norm(b - a)
        e = (b - a) / L
        nrm = np.array([e[1], -e[0]])
        p = a + e * L * float(rng.uniform(0.08, 0.92)) + nrm * 0.02
        z = z0 + 0.8 + 3.3 * int(rng.integers(0, nf)) + 0.3
        M.merge(P.ac_unit(), (p[0], p[1], z), rz=P.yaw_facing(nrm[0], nrm[1]))
    # vertical neon blades + a flush sign
    for j in range(int(rng.integers(2, 4))):
        a, b = sides[order[(j + 1) % 4]]
        L = np.linalg.norm(b - a)
        e = (b - a) / L
        nrm = np.array([e[1], -e[0]])
        p = a + e * L * float(rng.uniform(0.1, 0.9))
        K.blade_sign(M, p, nrm, POD_H + 3.5 + float(rng.uniform(0, 5)), 'v', int(rng.integers(0, 32)), 1.2, 3.8)
    a, b = sides[order[0]]
    K.wall_sign(M, a, b, POD_H + 0.35 + 1.2, 'h', int(rng.integers(0, 32)), 5.0, 1.8, along=float(rng.uniform(0.3, 0.7)))
    # awnings on the shops
    for j in range(int(rng.integers(1, 3))):
        a, b = sides[int(rng.integers(4))]
        L = np.linalg.norm(b - a)
        e = (b - a) / L
        nrm = np.array([e[1], -e[0]])
        p = a - nrm * 0.0 + e * L * float(rng.uniform(0.2, 0.8)) + nrm * 0.62
        M.merge(P.awning(3.0, 1.4, 0.5), (p[0] - nrm[0] * 0.6, p[1] - nrm[1] * 0.6, 3.6), rz=P.yaw_facing(nrm[0], nrm[1]))
    return M, C, _meta('tenement', w, d, z1 + 12, floors, 420.0, mat=mat)


def slab(w, d, floors, mat, seed, balcony=True):
    rng = np.random.default_rng(seed)
    M, C = Mesh(), Col()
    K.podium(M, C, w, d, rng, kinds=('retail', 'food'), canopy=True)
    z0 = POD_H + 0.35
    nf = max(8, floors)
    poly = rect(w - 1.2, d - 1.2)
    z1 = z0 + nf * FLOOR_H
    K.tier(M, C, poly, z0, z1, mat, rng, emis=0.78, ledge_every=0, corners=True)
    if balcony:
        # continuous balcony bands on the two long faces (south: outside = -y, north: outside = +y)
        x0, x1 = poly[:, 0].min() + 0.3, poly[:, 0].max() - 0.3
        ys, yn = poly[:, 1].min(), poly[:, 1].max()
        for k in range(2, nf):
            zz = z0 + k * FLOOR_H
            for ya, yb, yr in ((ys - 1.5, ys, ys - 1.46), (yn, yn + 1.5, yn + 1.46)):
                M.box((x0, ya, zz - 0.18), (x1, yb, zz), 'nc_concrete', tile=(4, 1))
                M.box((x0, min(yr, yr + 0.04) - 0.02, zz), (x1, max(yr, yr + 0.04) + 0.02, zz + 1.05), 'nc_glass_a', tile=(3.2, 3.2), emis=0.45)
                M.box((x0, min(yr, yr + 0.04) - 0.03, zz + 1.02), (x1, max(yr, yr + 0.04) + 0.03, zz + 1.08), 'nc_strip_white', tile=(1, 1), emis=0.9)
        C.box((x0, ys - 1.5, z0), (x1, ys, z0 + 0.4))
    K.ledge(M, poly, z1, z1 + 0.45, 0.35)
    K.parapet(M, poly, z1 + 0.45, 1.0)
    K.roof_clutter(M, rng, poly, z1 + 0.45, n_ac=4, n_tank=2, n_ant=2, n_dish=2, n_stack=1, n_hvac=2)
    a, b = poly[0], poly[1]
    K.wall_sign(M, a, b, z0 + nf * FLOOR_H * 0.6, 'ad', int(rng.integers(0, 8)), min(14.0, w * 0.4), 8.0)
    return M, C, _meta('slab', w, d, z1 + 12, floors, 520.0, mat=mat)


def megablock(w, d, floors, seed):
    rng = np.random.default_rng(seed)
    M, C = Mesh(), Col()
    K.podium(M, C, w, d, rng, kinds=('food', 'retail', 'club'))
    z = POD_H + 0.35
    scale = [1.0, 0.82, 0.62]
    nfs = [int(floors * 0.4), int(floors * 0.33), int(floors * 0.27)]
    poly = None
    for i in range(3):
        poly = rect((w - 1.0) * scale[i], (d - 1.0) * scale[i])
        nf = max(3, nfs[i])
        z1 = z + nf * 3.3
        K.tier(M, C, poly, z, z1, 'nc_wall_brutal' if i != 1 else 'nc_wall_tenement_b', rng, emis=0.6, bays_tile=4, floors_tile=4, bay_w=3.0, floor_h=3.3)
        K.ledge(M, poly, z1, z1 + 0.5, 0.6)
        # terrace edge planters
        sides = [(poly[j], poly[(j + 1) % 4]) for j in range(4)]
        for a, b in sides:
            L = np.linalg.norm(b - a)
            e = (b - a) / L
            for k in range(int(L // 6)):
                p = a + e * (3 + 6 * k) + np.array([e[1], -e[0]]) * 1.0
                M.merge(P.planter(3.0, 0.9), (p[0], p[1], z1 + 0.5), rz=P.yaw_facing(e[1], -e[0]))
        z = z1 + 0.5
        for j in range(int(nf * 0.8)):
            a, b = sides[int(rng.integers(4))]
            L = np.linalg.norm(b - a)
            e = (b - a) / L
            nrm = np.array([e[1], -e[0]])
            p = a + e * L * float(rng.uniform(0.08, 0.92)) + nrm * 0.02
            M.merge(P.ac_unit(), (p[0], p[1], z - 0.5 - 3.3 * int(rng.integers(1, nf)) + 0.3), rz=P.yaw_facing(nrm[0], nrm[1]))
    crown(M, C, poly, z, 'flat', rng)
    a, b = rect(w, d)[0], rect(w, d)[1]
    K.wall_sign(M, a, b, POD_H + 12, 'led', int(rng.integers(0, 4)), min(16.0, w * 0.45), 10.0)
    for j in range(3):
        a, b = rect(w, d)[(j + 1) % 4], rect(w, d)[(j + 2) % 4]
        L = np.linalg.norm(b - a)
        e = (b - a) / L
        nrm = np.array([e[1], -e[0]])
        K.blade_sign(M, a + e * L * float(rng.uniform(0.2, 0.8)), nrm, POD_H + 4 + 3 * j, 'v', int(rng.integers(0, 32)), 1.3, 4.0)
    return M, C, _meta('mega', w, d, z + 12, floors, 560.0)


# ---------------------------------------------------------------------------------------------
# industrial
# ---------------------------------------------------------------------------------------------
def warehouse(w, d, h, seed):
    rng = np.random.default_rng(seed)
    M, C = Mesh(), Col()
    poly = rect(w - 1.0, d - 1.0)
    M.extrude(poly, 0, 1.2, 'nc_concrete_dark', None, tile=(4, 4))
    for i in range(4):
        a, b = poly[i], poly[(i + 1) % 4]
        L = np.linalg.norm(b - a)
        M.wall(a, b, 1.2, h, 'nc_wall_corrug', tile=(L / max(1, round(L / 2.0)) * 0 + 4.0, 4.0), uoff=float(rng.random()))
    # roof: shallow gable
    x0, x1, y0, y1 = poly[0][0], poly[2][0], poly[0][1], poly[2][1]
    rh = 2.2
    ym = (y0 + y1) / 2
    M.quad((x0 - 0.4, y0 - 0.4, h), (x1 + 0.4, y0 - 0.4, h), (x1 + 0.4, ym, h + rh), (x0 - 0.4, ym, h + rh), 'nc_roof', tile=(4, 4))
    M.quad((x1 + 0.4, y1 + 0.4, h), (x0 - 0.4, y1 + 0.4, h), (x0 - 0.4, ym, h + rh), (x1 + 0.4, ym, h + rh), 'nc_roof', tile=(4, 4))
    M.quad((x1, y0, h), (x1, ym, h + rh), (x1, y1, h), (x1, y0, h), 'nc_wall_corrug', tile=(4, 4))
    M.quad((x0, y1, h), (x0, ym, h + rh), (x0, y0, h), (x0, y1, h), 'nc_wall_corrug', tile=(4, 4))
    for k in range(int(w // 14)):
        x = x0 + 8 + k * 14
        M.box((x - 0.6, ym - 0.6, h + rh), (x + 0.6, ym + 0.6, h + rh + 0.9), 'nc_metal_light', tile=(1, 1))
    C.box((x0, y0, 0), (x1, y1, h + rh))
    # loading docks on the long south wall with lamps
    nd = max(2, int(w // 12))
    for k in range(nd):
        x = x0 + (k + 0.5) * (x1 - x0) / nd
        M.box((x - 2.2, y0 - 0.5, 0.0), (x + 2.2, y0, 4.2), 'nc_metal_dark', tile=(2, 2), skip=('+y',))
        M.box((x - 0.25, y0 - 0.9, 5.0), (x + 0.25, y0 - 0.4, 5.4), 'nc_metal_dark', tile=(1, 1))
        M.hquad(x - 0.2, y0 - 0.85, x + 0.2, y0 - 0.45, 4.995, 'nc_light_warm', tile=(1, 1), emis=1.0, up=False)
        M.light((x, y0 - 1.5, 4.6), P.SODIUM, 1.1, 14.0, n=(0, -1, 0))
    # side pipe rack + tank
    for k in range(int(d // 10)):
        M.merge(P.floodlight_mast(14.0), (x1 + 3, y0 + 6 + k * 10), rz=90.0) if k % 3 == 0 else None
    return M, C, _meta('warehouse', w, d, h + rh, 0, 420.0)


def factory(w, d, seed):
    rng = np.random.default_rng(seed)
    M, C = Mesh(), Col()
    # main hall
    hw, hd, hh = w * 0.62, d * 0.55, 16.0
    cx, cy = -w * 0.15, -d * 0.18
    poly = rect(hw, hd, cx, cy)
    M.extrude(poly, 0, 1.2, 'nc_concrete_dark', None, tile=(4, 4))
    for i in range(4):
        M.wall(poly[i], poly[(i + 1) % 4], 1.2, hh, 'nc_wall_corrug', tile=(4.0, 4.0), uoff=float(rng.random()))
    M.poly([(p[0], p[1], hh) for p in poly], 'nc_roof', (4, 4))
    K.parapet(M, poly, hh, 0.8)
    C.box((cx - hw / 2, cy - hd / 2, 0), (cx + hw / 2, cy + hd / 2, hh))
    # side annex
    ap = rect(w * 0.28, d * 0.4, w * 0.34, -d * 0.2)
    M.extrude(ap, 0, 9.0, 'nc_wall_metal', 'nc_roof', tile=(4, 4))
    C.box((ap[:, 0].min(), ap[:, 1].min(), 0), (ap[:, 0].max(), ap[:, 1].max(), 9.0))
    # smoke stacks with red beacons and steam
    for k, sx in enumerate((0.25, 0.38, 0.51)):
        x, y = w * (sx - 0.1), d * 0.3
        sh = 52.0 + 12 * k
        M.cone((x, y), 2.4, 1.5, 0, sh, 14, 'nc_concrete_dark', tile=(4, 6), top_mat='nc_concrete_dark')
        for z in (sh * 0.45, sh * 0.8):
            M.cyl((x, y), 2.4 - (2.4 - 1.5) * z / sh + 0.12, z, z + 1.4, 14, 'nc_metal_rust', tile=(4, 2))
        P.beacon_light(M, (x - 0.2, y - 0.2, sh))
        for dz, s in ((6.0, 12.0), (14.0, 18.0)):
            P.steam_puff(M, (x, y, sh + dz), s, (0.62, 0.52, 0.66))
        C.box((x - 2.4, y - 2.4, 0), (x + 2.4, y + 2.4, sh))
    # cooling tower
    tx, ty = w * 0.22, d * 0.3 - 1
    M.loft(regular(20, 9.0, tx, ty), 0, regular(20, 6.5, tx, ty), 22.0, 'nc_concrete_dark', None, tile=(6, 6))
    M.loft(regular(20, 6.5, tx, ty), 22.0, regular(20, 7.6, tx, ty), 30.0, 'nc_concrete_dark', None, tile=(6, 6))
    for dz, s in ((8.0, 18.0), (18.0, 26.0)):
        P.steam_puff(M, (tx, ty, 31 + dz), s, (0.62, 0.52, 0.66))
    C.box((tx - 9, ty - 9, 0), (tx + 9, ty + 9, 30))
    # pipe rack along the front
    y = -d / 2 + 1.5
    for z in (4.0, 5.2, 6.4):
        P.pipe_run(M, [(-w / 2 + 2, y, z), (w / 2 - 2, y, z)], 0.18, P.MR)
    for k in range(int(w // 8)):
        x = -w / 2 + 3 + k * 8
        M.box((x - 0.15, y - 0.15, 0), (x + 0.15, y + 0.15, 6.8), 'nc_steel', tile=(1, 1))
    # flare
    fx = -w / 2 + 6
    M.cyl((fx, d * 0.35), 0.35, 0, 38.0, 8, 'nc_steel', tile=(2, 2), top_mat='nc_steel')
    for z in (6, 14, 22, 30):
        M.box((fx - 0.7, d * 0.35 - 0.04, z), (fx + 0.7, d * 0.35 + 0.04, z + 0.06), 'nc_steel', tile=(1, 1))
    M.cone((fx, d * 0.35), 0.5, 0.05, 38.0, 41.5, 8, 'nc_light_amber', emis=1.0)
    M.light((fx, d * 0.35, 40), (1.0, 0.45, 0.1), 3.0, 60.0)
    P.glow_sprite(M, (fx, d * 0.35, 40.0), 14.0, (1.0, 0.5, 0.12))
    C.box((fx - 0.6, d * 0.35 - 0.6, 0), (fx + 0.6, d * 0.35 + 0.6, 38.0))
    for k in range(3):
        M.merge(P.floodlight_mast(15.0), (-w / 2 + 8 + k * w / 3, -d / 2 - 1.5))
    return M, C, _meta('factory', w, d, 62.0, 0, 560.0)


def tank_farm(w, d, seed):
    rng = np.random.default_rng(seed)
    M, C = Mesh(), Col()
    M.extrude(rect(w - 0.6, d - 0.6), 0, 0.9, 'nc_concrete_dark', 'nc_concrete_dark', tile=(4, 4))       # bund slab
    C.box((-w / 2, -d / 2, 0), (w / 2, d / 2, 0.9))
    nx, ny = max(1, int(w // 24)), max(1, int(d // 24))
    cells = [(i, j) for i in range(nx) for j in range(ny)]
    for i, j in cells:
        x = -w / 2 + (i + 0.5) * w / nx
        y = -d / 2 + (j + 0.5) * d / ny
        r = float(rng.uniform(8.0, min(11.0, w / nx / 2 - 1.5, d / ny / 2 - 1.5)))
        h = float(rng.uniform(12, 18))
        M.cyl((x, y), r, 0.9, 0.9 + h, 20, 'nc_tank', tile=(6, 3), top_mat='nc_metal_light', smooth=True)
        M.cone((x, y), r, r * 0.12, 0.9 + h, 0.9 + h + 1.6, 20, 'nc_metal_light', tile=(4, 4))
        M.cyl((x, y), r + 0.12, 0.9 + h - 1.2, 0.9 + h - 1.0, 20, 'nc_steel', tile=(4, 1), top_mat='nc_steel')          # walkway ring
        M.cyl((x, y), r + 0.06, 0.9 + h * 0.5, 0.9 + h * 0.5 + 0.12, 20, 'nc_steel', tile=(4, 1))
        a = rng.uniform(0, TAU)
        P.beacon_light(M, (x - 0.15, y - 0.15, 0.9 + h + 1.6))
        C.box((x - r, y - r, 0.9), (x + r, y + r, 0.9 + h + 1.6))
        # pipe to the next tank
        P.pipe_run(M, [(x + r * 0.7, y - r * 0.7, 1.4), (x + r * 0.7 + 2.5, y - r * 0.7, 1.4), (x + r * 0.7 + 2.5, y - r * 0.7 - 2.0, 1.4)], 0.22, P.MR)
        M.cyl((x + r * 0.7, y - r * 0.7), 0.4, 0.9, 1.5, 8, 'nc_metal_rust', tile=(1, 1), top_mat='nc_metal_rust')
    for k in range(2):
        M.merge(P.floodlight_mast(18.0), (-w / 2 + 3 + k * (w - 6), -d / 2 + 3), rz=45.0)
    return M, C, _meta('tanks', w, d, 36.0, 0, 520.0)


def container_yard(w, d, seed):
    rng = np.random.default_rng(seed)
    M, C = Mesh(), Col()
    M.extrude(rect(w - 0.4, d - 0.4), 0, 0.3, 'nc_concrete_dark', 'nc_alley', tile=(4, 4))
    C.box((-w / 2, -d / 2, 0), (w / 2, d / 2, 0.3))
    mats = ['nc_container_a', 'nc_container_b', 'nc_container_c']
    L, W, H = 12.2, 2.45, 2.6
    nx = max(1, int((w - 8) // (L + 2)))
    ny = max(1, int((d - 6) // (W * 2 + 2.5)))
    for i in range(nx):
        for j in range(ny):
            hgt = int(rng.integers(1, 5))
            x = -w / 2 + 5 + L / 2 + i * (L + 2.0)
            for jj in range(2):
                y = -d / 2 + 4 + W / 2 + j * (W * 2 + 2.5) + jj * W
                for k in range(hgt):
                    m = mats[int(rng.integers(3))]
                    M.box((x - L / 2, y - W / 2, 0.3 + k * H), (x + L / 2, y + W / 2, 0.3 + (k + 1) * H), m, tile=(6.0, 2.6), uvoff=(float(rng.random()), 0))
                C.box((x - L / 2, y - W / 2, 0.3), (x + L / 2, y + W / 2, 0.3 + hgt * H))
    for k in range(3):
        M.merge(P.floodlight_mast(20.0), (-w / 2 + 6 + k * (w - 12) / 2, -d / 2 + 1.5))
    return M, C, _meta('yard', w, d, 0.3 + 4 * H + 20, 0, 480.0)


def garage(w, d, levels, seed):
    """open multi-storey car park structure - kept EMPTY (this city has no vehicles); lit ceilings, LED edge bars"""
    rng = np.random.default_rng(seed)
    M, C = Mesh(), Col()
    lh = 3.2
    for k in range(levels + 1):
        z = k * lh
        M.box((-w / 2, -d / 2, z), (w / 2, d / 2, z + 0.35), 'nc_concrete', tile=(4, 4), skip=())
        if k < levels:
            for cx in np.arange(-w / 2 + 3, w / 2, 9.0):
                for cy in (-d / 2 + 1.0, d / 2 - 1.0, 0.0):
                    M.box((cx - 0.35, cy - 0.35, z + 0.35), (cx + 0.35, cy + 0.35, z + lh), 'nc_concrete', tile=(1, 1))
            # parapet + LED bar on the facade sides
            for (x0, y0, x1, y1) in ((-w / 2, -d / 2, w / 2, -d / 2 + 0.3), (-w / 2, d / 2 - 0.3, w / 2, d / 2), (-w / 2, -d / 2, -w / 2 + 0.3, d / 2), (w / 2 - 0.3, -d / 2, w / 2, d / 2)):
                M.box((x0, y0, z + 0.35), (x1, y1, z + 1.2), 'nc_concrete_dark', tile=(2, 2))
            M.box((-w / 2 + 0.3, -d / 2 - 0.04, z + 1.2), (w / 2 - 0.3, -d / 2 + 0.02, z + 1.28), 'nc_strip_white', tile=(1, 1), emis=1.0, skip=('-z', '+z', '+x', '-x', '+y'))
            M.box((-w / 2 + 0.3, d / 2 - 0.02, z + 1.2), (w / 2 - 0.3, d / 2 + 0.04, z + 1.28), 'nc_strip_white', tile=(1, 1), emis=1.0, skip=('-z', '+z', '+x', '-x', '-y'))
            # ceiling light strips
            for cx in np.arange(-w / 2 + 6, w / 2 - 3, 9.0):
                M.box((cx - 0.12, -d / 2 + 3, z + lh - 0.04), (cx + 0.12, d / 2 - 3, z + lh), 'nc_strip_white', tile=(1, 1), emis=1.0, skip=('+z',))
            M.light((0, 0, z + lh - 0.5), P.COOL, 1.1, max(w, d) * 0.8)
    top = levels * lh + 0.35
    K.roof_clutter(M, rng, rect(w, d), top, n_ac=2, n_ant=1, n_hvac=1, edge=3.0)
    C.box((-w / 2, -d / 2, 0), (w / 2, d / 2, top))
    K.wall_sign(M, rect(w, d)[0], rect(w, d)[1], levels * lh - 1.0, 'h', int(rng.integers(0, 32)), 9.0, 2.6)
    return M, C, _meta('garage', w, d, top + 14, 0, 420.0)


def plaza_gate(w, h, seed):
    """hero landmark: a giant gate (two piers + beam) carrying huge LED screens on both faces"""
    rng = np.random.default_rng(seed)
    M, C = Mesh(), Col()
    pw, pd = 7.0, 9.0
    for sx in (-1, 1):
        cx = sx * (w / 2 - pw / 2)
        poly = rect(pw, pd, cx, 0)
        K.tier(M, C, poly, 0, h, 'nc_glass_f', rng, emis=0.9, corners=True, ledge_every=6)
        glow_band(M, poly, h, 0.5, 'nc_strip_cyan', 0.3, lights=1)
        K.ledge(M, poly, h - 0.5, h, 0.4)
    bz = h - 22.0
    M.box((-w / 2, -pd / 2, bz), (w / 2, pd / 2, h), 'nc_metal_dark', tile=(4, 4), skip=('+y', '-y'))
    for sy in (-1, 1):
        a, b = (np.array([w / 2 - 1, sy * pd / 2]), np.array([-w / 2 + 1, sy * pd / 2])) if sy > 0 else (np.array([-w / 2 + 1, sy * pd / 2]), np.array([w / 2 - 1, sy * pd / 2]))
        M.merge(P.led_panel(int(rng.integers(0, 4)), w - 8, 15.0), (0, sy * (pd / 2 + 0.2), bz + 11), rz=0.0 if sy > 0 else 180.0)
        M.merge(P.neon_sign('h', int(rng.integers(0, 32)), 14.0, 3.0), (0, sy * (pd / 2 + 0.3), bz + 2.0), rz=0.0 if sy > 0 else 180.0)
    M.box((-w / 2, -pd / 2, h), (w / 2, pd / 2, h + 0.6), 'nc_strip_cyan', tile=(1, 1), emis=1.0)
    M.light((0, 0, h + 1.0), P.CYA, 3.0, 60.0)
    C.box((-w / 2, -pd / 2, bz), (w / 2, pd / 2, h))
    return M, C, _meta('gate', w, pd, h + 1, 0, 700.0, hero=True)


# registry used by the plan / builder
ARCH = {
    'tower_setback': tower_setback, 'tower_cyl': tower_cyl, 'tower_twin': tower_twin, 'arcology': arcology,
    'midrise': midrise, 'tenement': tenement, 'slab': slab, 'megablock': megablock,
    'warehouse': warehouse, 'factory': factory, 'tank_farm': tank_farm, 'container_yard': container_yard, 'garage': garage,
    'plaza_gate': plaza_gate,
}
