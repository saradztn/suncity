# Created by: Arena.ai Agent Mode (AI) - NightCity MTA:SA asset pipeline
# -----------------------------------------------------------------------------
# parts.py - prefab sub-meshes (street furniture, rooftop machinery, signs, billboards, balconies, fire escapes ...).
# All prefabs are built around their own origin (ground / mounting point) and merged with Mesh.merge(sub, pos, rz).
# Deliberately NO people, vehicles, bikes or animals anywhere in the kit (validate.py checks the material / model names).
# -----------------------------------------------------------------------------
import functools
import numpy as np
from .mb import Mesh, Col, TAU, unit
from . import textures as TX
from .texsign import atlas_uv, ad_uv, led_uv, NEON_ATLAS, AD_CELLS

COOL = (0.70, 0.85, 1.00)
SODIUM = (1.00, 0.60, 0.25)
WARMW = (1.00, 0.80, 0.55)
MAG = (1.00, 0.15, 0.60)
CYA = (0.10, 0.85, 1.00)

MD, ML, MR = 'nc_metal_dark', 'nc_metal_light', 'nc_metal_rust'


def yaw_facing(nx, ny):
    """rotz angle (deg) that turns local +y into the horizontal direction (nx, ny)"""
    return float(np.degrees(np.arctan2(-nx, ny)))


# ---------------------------------------------------------------------------------------------
# sign / screen colours measured from the generated atlases (used by the light bake)
# ---------------------------------------------------------------------------------------------
@functools.lru_cache(maxsize=None)
def neon_colors(kind):
    p = TX.generate('nc_neon_h' if kind == 'h' else 'nc_neon_v')
    cols, rows = NEON_ATLAS[kind]
    h, w = p.shape
    ch, cw = h // rows, w // cols
    out = []
    for i in range(cols * rows):
        c, r = i % cols, i // cols
        e = p.emit[r * ch:(r + 1) * ch, c * cw:(c + 1) * cw].reshape(-1, 3)
        lum = e.sum(1)
        sel = e[lum > np.percentile(lum, 90)] if len(e) else e
        m = sel.mean(0) if len(sel) else np.array([1.0, 1.0, 1.0])
        out.append(tuple(float(x) for x in m / max(m.max(), 1e-3)))
    return out


@functools.lru_cache(maxsize=None)
def ad_colors():
    p = TX.generate('nc_ads')
    cols, rows = AD_CELLS
    h, w = p.shape
    ch, cw = h // rows, w // cols
    out = []
    for i in range(cols * rows):
        c, r = i % cols, i // cols
        e = p.emit[r * ch:(r + 1) * ch, c * cw:(c + 1) * cw].reshape(-1, 3)
        m = e.mean(0)
        out.append(tuple(float(x) for x in m / max(m.max(), 1e-3)))
    return out


# ---------------------------------------------------------------------------------------------
# generic helpers
# ---------------------------------------------------------------------------------------------
def face(M, a, b, z0, z1, mat, uvrect, emis=0.0, tint=None):
    """quad above the 2D segment a->b (outside = right hand side) with explicit uv rect (u0, v0 top, u1, v1 bottom)"""
    a = np.asarray(a, float)[:2]
    b = np.asarray(b, float)[:2]
    u0, v0, u1, v1 = uvrect
    P = np.array([[a[0], a[1], z0], [b[0], b[1], z0], [b[0], b[1], z1], [a[0], a[1], z1]])
    UV = np.array([[u0, v1], [u1, v1], [u1, v0], [u0, v0]])
    M.quads(P[None], mat, UV[None], emis, tint=tint)


def bar(M, p0, p1, w, mat, tile=(1.0, 1.0), emis=0.0):
    """square section bar between two 3D points"""
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    d = unit(p1 - p0)
    r = np.cross(d, [0, 0, 1.0])
    if np.linalg.norm(r) < 1e-6:
        r = np.array([1.0, 0, 0])
    r = unit(r)
    u = unit(np.cross(r, d))
    h = w / 2
    c = [p0 - r * h - u * h, p0 + r * h - u * h, p0 + r * h + u * h, p0 - r * h + u * h]
    e = [q + (p1 - p0) for q in c]
    quads = []
    for i in range(4):
        j = (i + 1) % 4
        q = [c[i], c[j], e[j], e[i]]
        nf = np.cross(q[1] - q[0], q[3] - q[0])
        mid = (c[i] + c[j]) / 2 - p0
        if np.dot(nf, mid) < 0:
            q = [q[1], q[0], q[3], q[2]]
        quads.append(q)
    L = float(np.linalg.norm(p1 - p0))
    uv = np.array([[0, 1], [L / tile[0], 1], [L / tile[0], 0], [0, 0]], float)
    M.quads(np.array(quads), mat, np.tile(uv, (4, 1, 1)), emis)
    cap = np.array([c, e[::-1]])
    M.quads(cap, mat, None, emis)


def glow_sprite(M, c, size, color, emis=1.0):
    """corona / halo: stored as a billboard record, drawn by the client at run time (dxDrawMaterialLine3D)"""
    M.sprites.append(dict(p=tuple(map(float, c)), size=float(size), c=tuple(map(float, color)), kind='glow'))


def steam_puff(M, c, size, color=(0.55, 0.5, 0.6)):
    M.sprites.append(dict(p=tuple(map(float, c)), size=float(size), c=tuple(map(float, color)), kind='steam'))


# ---------------------------------------------------------------------------------------------
# street furniture
# ---------------------------------------------------------------------------------------------
@functools.lru_cache(maxsize=None)
def street_lamp(h=9.0, arm=2.8, sodium=False, twin=False):
    """pole + arm (towards +y) + LED head.  Light pool, glow and a soft light cone included."""
    M = Mesh()
    col = SODIUM if sodium else COOL
    M.box((-0.17, -0.17, 0), (0.17, 0.17, 0.5), 'nc_concrete_dark', tile=(1, 1), skip=('-z',))
    M.cyl((0, 0), 0.10, 0.5, h, 6, MD, tile=(1, 1), top_mat=MD)
    ys = [arm] + ([-arm] if twin else [])
    for ay in ys:
        M.box((-0.05, min(0, ay), h - 0.36), (0.05, max(0, ay), h - 0.26), MD, tile=(1, 1), skip=('-z', '+z'))
        M.box((-0.20, ay - 0.46, h - 0.40), (0.20, ay + 0.46, h - 0.22), MD, tile=(1, 1), skip=('-z',))
        M.hquad(-0.17, ay - 0.42, 0.17, ay + 0.42, h - 0.405, 'nc_light_warm' if sodium else 'nc_light_white', tile=(1, 1), emis=1.0, up=False)
        M.light((0, ay, h - 0.6), col, 1.0, 17.0, n=(0, 0, -1))
        glow_sprite(M, (0, ay, h - 0.55), 2.2, col)
    return M


@functools.lru_cache(maxsize=None)
def traffic_signal(state=0):
    """mast + arm over the carriageway (towards +y) with two signal heads; state 0 red, 1 green, 2 amber"""
    M = Mesh()
    M.cyl((0, 0), 0.11, 0, 5.8, 8, MD, tile=(1, 1), top_mat=MD)
    M.box((-0.30, -0.30, 0), (0.30, 0.30, 0.35), MD, tile=(1, 1))
    M.box((-0.06, 0, 5.4), (0.06, 5.2, 5.54), MD, tile=(1, 1))
    lens = {0: 'nc_light_red', 1: 'nc_light_green', 2: 'nc_light_amber'}[state]
    lcol = {0: (1, 0.1, 0.05), 1: (0.2, 1, 0.4), 2: (1, 0.6, 0.1)}[state]
    for y in (3.0, 5.0):
        M.box((-0.17, y - 0.16, 4.35), (0.17, y + 0.16, 5.35), MD, tile=(1, 1), skip=('-z',))
        for k, name in enumerate(('nc_light_red', 'nc_light_amber', 'nc_light_green')):
            zc = 5.05 - k * 0.31
            on = name == lens
            face(M, (0.15, y + 0.161), (-0.15, y + 0.161), zc - 0.11, zc + 0.11, name if on else MD, (0.1, 0.1, 0.9, 0.9), emis=1.0 if on else 0.0)
        M.light((0, y, 4.9), lcol, 0.7, 9.0, n=(0, 1, 0))
        glow_sprite(M, (0, y + 0.2, 5.0 - {0: 0, 2: 0.31, 1: 0.62}[state]), 1.0, lcol)
    return M


@functools.lru_cache(maxsize=None)
def bollard():
    M = Mesh()
    M.cyl((0, 0), 0.11, 0, 0.9, 8, MD, tile=(1, 1), top_mat=MD)
    M.cyl((0, 0), 0.115, 0.7, 0.78, 8, 'nc_strip_cyan', tile=(1, 1), emis=1.0)
    M.light((0, 0, 0.8), CYA, 0.12, 3.0)
    return M


@functools.lru_cache(maxsize=None)
def trash_bin():
    M = Mesh()
    M.cyl((0, 0), 0.30, 0.05, 0.95, 10, MD, tile=(1, 1), top_mat=MD)
    M.cyl((0, 0), 0.32, 0.95, 1.05, 10, ML, tile=(1, 1), top_mat=ML)
    M.cyl((0, 0), 0.31, 0.45, 0.52, 10, 'nc_strip_white', tile=(1, 1), emis=0.6)
    return M


@functools.lru_cache(maxsize=None)
def hydrant():
    M = Mesh()
    M.cyl((0, 0), 0.14, 0, 0.75, 8, 'nc_container_a', tile=(1, 1), top_mat='nc_container_a')
    M.cyl((0, 0), 0.17, 0.62, 0.74, 8, 'nc_container_a', tile=(1, 1), top_mat='nc_container_a')
    M.box((-0.26, -0.07, 0.4), (0.26, 0.07, 0.52), 'nc_container_a', tile=(1, 1))
    return M


@functools.lru_cache(maxsize=None)
def bench():
    M = Mesh()
    M.box((-0.9, -0.22, 0.42), (0.9, 0.22, 0.48), 'nc_concrete_dark', tile=(1, 1))
    M.box((-0.9, 0.18, 0.48), (0.9, 0.23, 0.95), 'nc_concrete_dark', tile=(1, 1))
    for x in (-0.75, 0.75):
        M.box((x - 0.05, -0.2, 0), (x + 0.05, 0.2, 0.42), MD, tile=(1, 1))
    M.box((-0.9, -0.22, 0.38), (0.9, -0.17, 0.42), 'nc_strip_cyan', tile=(1, 1), emis=0.8)
    return M


@functools.lru_cache(maxsize=None)
def planter(w=3.0, d=1.0):
    M = Mesh()
    M.box((-w / 2, -d / 2, 0), (w / 2, d / 2, 0.7), 'nc_concrete_dark', tile=(2, 2))
    M.box((-w / 2 + 0.1, -d / 2 + 0.1, 0.7), (w / 2 - 0.1, d / 2 - 0.1, 0.78), MD, tile=(1, 1), skip=('-z',))
    M.box((-w / 2 + 0.05, d / 2 + 0.001, 0.05), (w / 2 - 0.05, d / 2 + 0.03, 0.1), 'nc_strip_cyan', tile=(1, 1), emis=1.0, skip=('-y', '+z', '-z', '+x', '-x'))
    M.light((0, d / 2 + 0.2, 0.3), CYA, 0.2, 4.0)
    return M


@functools.lru_cache(maxsize=None)
def kiosk(idx=0):
    """small lit booth (shop window on +y, neon sign on the roof)"""
    M = Mesh()
    M.box((-1.6, -1.2, 0), (1.6, 1.2, 2.7), MD, tile=(2, 2), skip=('+y',))
    face(M, (1.6, 1.2), (-1.6, 1.2), 0.0, 2.7, 'nc_shop_food', (0.0, 0.0, 0.25, 0.75), emis=1.0)
    M.box((-1.8, -1.4, 2.7), (1.8, 1.5, 2.85), 'nc_concrete_dark', tile=(2, 2))
    u = atlas_uv('h', idx)
    face(M, (1.2, 1.52), (-1.2, 1.52), 2.9, 3.6, 'nc_neon_h', u, emis=1.0)
    c = neon_colors('h')[idx % 32]
    M.light((0, 2.2, 2.0), WARMW, 0.9, 7.0, n=(0, 1, 0))
    M.light((0, 2.0, 3.2), c, 0.8, 8.0, n=(0, 1, 0))
    return M


@functools.lru_cache(maxsize=None)
def vending(idx=0):
    M = Mesh()
    M.box((-0.5, -0.4, 0), (0.5, 0.4, 1.85), MD, tile=(1, 1), skip=('+y',))
    face(M, (0.5, 0.4), (-0.5, 0.4), 0.05, 1.8, 'nc_ads', ad_uv(idx), emis=1.0)
    c = ad_colors()[idx % 8]
    M.light((0, 1.2, 1.0), c, 0.55, 5.0, n=(0, 1, 0))
    return M


@functools.lru_cache(maxsize=None)
def canopy(idx=0):
    """transit canopy: glass-roofed shelter with a lit ad panel (no vehicles involved - pure street furniture)"""
    M = Mesh()
    for x in (-2.2, 2.2):
        M.box((x - 0.06, -0.8, 0), (x + 0.06, -0.7, 2.5), MD, tile=(1, 1))
    M.box((-2.4, -1.1, 2.5), (2.4, 0.5, 2.6), MD, tile=(1, 1))
    M.box((-2.2, -0.82, 0.1), (2.2, -0.78, 2.4), 'nc_glass_a', tile=(3, 3), emis=0.4, skip=('-y',))
    face(M, (0.7, -0.72), (-0.7, -0.72), 0.5, 2.0, 'nc_ads', ad_uv(idx + 3), emis=1.0)
    M.box((-1.6, -0.5, 0.45), (1.6, -0.2, 0.5), 'nc_concrete_dark', tile=(1, 1))
    c = ad_colors()[(idx + 3) % 8]
    M.light((0, -0.2, 1.5), c, 0.6, 6.0, n=(0, 1, 0))
    return M


@functools.lru_cache(maxsize=None)
def manhole():
    M = Mesh()
    M.cyl((0, 0), 0.45, 0.0, 0.015, 10, MD, tile=(1, 1), top_mat=MD, smooth=False)
    return M


@functools.lru_cache(maxsize=None)
def steam_vent():
    M = Mesh()
    M.cyl((0, 0), 0.35, 0, 0.9, 8, MD, tile=(1, 1), top_mat=MD)
    M.cyl((0, 0), 0.30, 0.9, 1.0, 8, MD, tile=(1, 1), top_mat=MD)
    for dz, s in ((1.8, 2.6), (3.6, 3.8), (5.6, 5.0)):
        steam_puff(M, (0, 0, dz), s)
    return M


@functools.lru_cache(maxsize=None)
def utility_pole(h=9.0):
    M = Mesh()
    M.cyl((0, 0), 0.16, 0, h, 8, 'nc_concrete_dark', tile=(1, 1), top_mat='nc_concrete_dark')
    M.box((-1.1, -0.06, h - 0.9), (1.1, 0.06, h - 0.78), MD, tile=(1, 1))
    M.box((-0.8, -0.06, h - 1.7), (0.8, 0.06, h - 1.58), MD, tile=(1, 1))
    M.box((-0.25, -0.2, h - 3.2), (0.25, 0.2, h - 2.2), MD, tile=(1, 1))              # transformer can
    for x in (-1.0, -0.4, 0.4, 1.0):
        M.cyl((x, 0), 0.04, h - 0.78, h - 0.6, 6, ML, tile=(1, 1), top_mat=ML)
    return M


def cable(M, p0, p1, sag=0.5, r=0.03, mat=MD, n=4, k=9):
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    t = np.linspace(0, 1, k)[:, None]
    pts = p0 + (p1 - p0) * t
    pts[:, 2] -= 4 * sag * t[:, 0] * (1 - t[:, 0])
    M.tube(pts, r, n, mat, tile=(2.0, 1.0), caps=False)


# ---------------------------------------------------------------------------------------------
# rooftop machinery
# ---------------------------------------------------------------------------------------------
@functools.lru_cache(maxsize=None)
def ac_unit(w=0.95, h=0.75, d=0.55):
    M = Mesh()
    M.box((-w / 2, 0, 0), (w / 2, d, h), ML, tile=(1, 1), skip=('+y', '-y'))
    face(M, (w / 2, d), (-w / 2, d), 0.0, h, 'nc_ac', (0, 0, 1, 1))
    M.box((-w / 2 + 0.05, -0.12, -0.12), (w / 2 - 0.05, 0.0, 0.02), MD, tile=(1, 1))
    return M


@functools.lru_cache(maxsize=None)
def hvac_box(w=3.0, d=2.2, h=1.5):
    M = Mesh()
    M.box((-w / 2, -d / 2, 0), (w / 2, d / 2, h), ML, tile=(2, 2), skip=('+y',))
    face(M, (w / 2, d / 2), (-w / 2, d / 2), 0.1, h - 0.1, 'nc_vent', (0, 0, 1, 1))
    M.cyl((w * 0.25, 0), 0.5, h, h + 0.35, 10, MD, tile=(1, 1), top_mat='nc_ac')
    return M


@functools.lru_cache(maxsize=None)
def water_tank(r=1.5, h=2.6):
    M = Mesh()
    for a in (45, 135, 225, 315):
        x, y = np.cos(np.radians(a)) * r * 0.7, np.sin(np.radians(a)) * r * 0.7
        M.box((x - 0.07, y - 0.07, 0), (x + 0.07, y + 0.07, 1.2), MD, tile=(1, 1))
    M.cyl((0, 0), r, 1.2, 1.2 + h, 14, MR, tile=(2, 2), top_mat=MR, bottom_mat=MR)
    M.cone((0, 0), r, 0.1, 1.2 + h, 1.2 + h + 0.8, 14, MR, tile=(2, 2))
    return M


@functools.lru_cache(maxsize=None)
def antenna(h=14.0, beacon=True):
    M = Mesh()
    M.tube(np.array([(0, 0, 0), (0, 0, h)]), 0.07, 6, MD, tile=(2, 1), caps=True)
    for z, w in ((h * 0.45, 1.6), (h * 0.7, 1.1), (h * 0.9, 0.7)):
        M.box((-w / 2, -0.03, z), (w / 2, 0.03, z + 0.06), MD, tile=(1, 1))
    if beacon:
        M.cyl((0, 0), 0.16, h, h + 0.3, 8, 'nc_light_red', tile=(1, 1), top_mat='nc_light_red', emis=1.0)
        M.light((0, 0, h + 0.3), (1, 0.05, 0.03), 0.6, 14.0)
        glow_sprite(M, (0, 0, h + 0.15), 1.6, (1, 0.1, 0.05))
    return M


@functools.lru_cache(maxsize=None)
def dish(r=0.9):
    M = Mesh()
    M.cone((0, 0), r, 0.1, 1.0, 1.0 + 0.35, 12, ML, tile=(1, 1), top_mat=ML)
    M.cyl((0, 0), 0.06, 0, 1.0, 6, MD, tile=(1, 1), top_mat=MD)
    return M


@functools.lru_cache(maxsize=None)
def stack(r=0.55, h=3.5):
    M = Mesh()
    M.cyl((0, 0), r, 0, h, 10, MD, tile=(1, 1), top_mat=MD)
    M.cyl((0, 0), r * 1.25, h - 0.3, h, 10, ML, tile=(1, 1), top_mat=ML)
    return M


def pipe_run(M, pts, r=0.12, mat=MR):
    M.tube(np.asarray(pts, float), r, 6, mat, tile=(2.0, 1.0), caps=True)


# ---------------------------------------------------------------------------------------------
# facade attachments
# ---------------------------------------------------------------------------------------------
@functools.lru_cache(maxsize=None)
def fire_escape(floors=4, floor_h=3.4, w=2.6):
    """zig-zag iron fire escape on a wall at y = 0, projecting towards +y"""
    M = Mesh()
    dep = 1.1
    for k in range(floors):
        z = (k + 1) * floor_h - 0.1
        M.box((-w / 2, 0.02, z - 0.07), (w / 2, dep, z), MR, tile=(1, 1))
        # rails
        M.box((-w / 2, dep - 0.04, z), (w / 2, dep, z + 0.04), MR, tile=(1, 1))
        M.box((-w / 2, dep - 0.04, z + 0.45), (w / 2, dep, z + 0.49), MR, tile=(1, 1))
        M.box((-w / 2, dep - 0.04, z + 0.95), (w / 2, dep, z + 1.0), MR, tile=(1, 1))
        for sx in (-w / 2, w / 2 - 0.04):
            M.box((sx, 0.02, z + 0.45), (sx + 0.04, dep, z + 0.49), MR, tile=(1, 1))
            M.box((sx, 0.02, z + 0.95), (sx + 0.04, dep, z + 1.0), MR, tile=(1, 1))
            M.box((sx, dep - 0.04, z), (sx + 0.04, dep, z + 1.0), MR, tile=(1, 1))
        if k > 0:       # stair flight down to the platform below, alternating sides
            side = 1 if k % 2 else -1
            x0 = side * (w / 2 - 0.55)
            n = 7
            for s in range(n):
                zz = z - (s + 1) * (floor_h / (n + 0.5)) + 0.02
                yy = 0.15 + s * (dep - 0.3) / n
                M.box((x0 - 0.45, yy, zz), (x0 + 0.45, yy + 0.22, zz + 0.04), MR, tile=(1, 1))
            M.box((x0 - 0.47, 0.1, z - floor_h), (x0 - 0.43, dep - 0.1, z - 0.2), MR, tile=(1, 1), skip=('+x', '-x'))
    M.box((-0.04, 0.0, 0.0), (0.04, 0.02, floors * floor_h), MR, tile=(1, 1))
    return M


@functools.lru_cache(maxsize=None)
def awning(w=3.0, d=1.4, h=0.5):
    """slanted fabric awning above a shop (back edge at y = 0, projects towards +y)"""
    M = Mesh()
    P = np.array([[w / 2, 0, h], [-w / 2, 0, h], [-w / 2, d, 0], [w / 2, d, 0]], float)
    M.quads(P[None], 'nc_container_b', None, 0.0)
    M.quads(P[None][:, ::-1], 'nc_metal_dark', None, 0.0)
    M.box((-w / 2, d - 0.03, -0.18), (w / 2, d + 0.01, 0.0), 'nc_container_b', tile=(1, 1))
    return M


def neon_sign(kind, idx, w, h, thick=0.22):
    """flat sign board facing +y.  kind 'h' | 'v' (atlas of 32 signs each).  origin = board centre"""
    M = Mesh()
    t = thick / 2
    M.box((-w / 2, -t, -h / 2), (w / 2, t, h / 2), MD, tile=(1, 1), skip=('+y',))
    face(M, (w / 2 - 0.04, t + 0.002), (-w / 2 + 0.04, t + 0.002), -h / 2 + 0.04, h / 2 - 0.04, 'nc_neon_h' if kind == 'h' else 'nc_neon_v', atlas_uv(kind, idx), emis=1.0)
    c = neon_colors(kind)[idx % 32]
    M.light((0, 1.2, 0), c, 1.1 * min(1.6, (w * h) ** 0.5 / 2.0), 10.0 + (w * h) ** 0.5, n=(0, 1, 0))
    glow_sprite(M, (0, t + 0.3, 0), max(w, h) * 1.25, c)
    return M


def ad_panel(idx, w, h, thick=0.35):
    M = Mesh()
    t = thick / 2
    M.box((-w / 2 - 0.12, -t, -h / 2 - 0.12), (w / 2 + 0.12, t, h / 2 + 0.12), MD, tile=(1, 1), skip=('+y',))
    face(M, (w / 2, t + 0.002), (-w / 2, t + 0.002), -h / 2, h / 2, 'nc_ads', ad_uv(idx), emis=1.0)
    c = ad_colors()[idx % 8]
    M.light((0, 2.0, 0), c, 1.3 * min(2.0, (w * h) ** 0.5 / 3.0), 14.0 + (w * h) ** 0.5, n=(0, 1, 0))
    return M


def led_panel(idx, w, h, thick=0.3):
    M = Mesh()
    t = thick / 2
    M.box((-w / 2 - 0.1, -t, -h / 2 - 0.1), (w / 2 + 0.1, t, h / 2 + 0.1), MD, tile=(1, 1), skip=('+y',))
    face(M, (w / 2, t + 0.002), (-w / 2, t + 0.002), -h / 2, h / 2, 'nc_led', led_uv(idx), emis=1.0)
    c = [(0.9, 0.5, 1.0), (0.4, 0.8, 1.0), (0.4, 1.0, 0.5), (1.0, 0.6, 0.3)][idx % 4]
    M.light((0, 2.0, 0), c, 1.2 * min(2.0, (w * h) ** 0.5 / 3.0), 14.0 + (w * h) ** 0.5, n=(0, 1, 0))
    return M


def beacon_light(M, p, color=(1, 0.05, 0.03), size=0.35):
    x, y, z = p
    M.box((x - size / 2, y - size / 2, z), (x + size / 2, y + size / 2, z + size), 'nc_light_red', tile=(1, 1), emis=1.0)
    M.light((x, y, z + size), color, 0.5, 12.0)
    glow_sprite(M, (x, y, z + size / 2), 2.2, color)


# ---------------------------------------------------------------------------------------------
# industrial / infrastructure bits
# ---------------------------------------------------------------------------------------------
@functools.lru_cache(maxsize=None)
def floodlight_mast(h=16.0):
    M = Mesh()
    M.cyl((0, 0), 0.22, 0, h, 8, MD, tile=(1, 1), top_mat=MD)
    M.box((-1.4, -0.12, h), (1.4, 0.12, h + 0.12), MD, tile=(1, 1))
    for x in (-1.1, -0.37, 0.37, 1.1):
        M.box((x - 0.28, 0.1, h + 0.12), (x + 0.28, 0.5, h + 0.55), MD, tile=(1, 1), skip=('+y',))
        face(M, (x + 0.26, 0.502), (x - 0.26, 0.502), h + 0.14, h + 0.53, 'nc_light_warm', (0.1, 0.1, 0.9, 0.9), emis=1.0)
    M.light((0, 3.0, h), SODIUM, 2.4, 32.0, n=(0, 0.6, -0.8))
    glow_sprite(M, (0, 0.8, h + 0.35), 5.0, SODIUM)
    return M


@functools.lru_cache(maxsize=None)
def jersey_barrier(L=4.0):
    M = Mesh()
    M.box((-L / 2, -0.3, 0), (L / 2, 0.3, 0.45), 'nc_concrete', tile=(2, 2))
    M.box((-L / 2, -0.15, 0.45), (L / 2, 0.15, 0.9), 'nc_concrete', tile=(2, 2))
    return M


def fence(M, p0, p1, h=2.4, mat=MD):
    """chain-link look-alike security fence: posts + two rails + a darker band (no alpha needed)"""
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    L = float(np.linalg.norm(p1 - p0))
    n = max(1, int(L / 3.0))
    d = (p1 - p0) / L
    for i in range(n + 1):
        p = p0 + d * (L * i / n)
        M.box((p[0] - 0.05, p[1] - 0.05, 0), (p[0] + 0.05, p[1] + 0.05, h), mat, tile=(1, 1))
    for z in (0.3, h - 0.1):
        bar(M, (p0[0], p0[1], z), (p1[0], p1[1], z), 0.05, mat)
