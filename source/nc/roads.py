# Created by: Arena.ai Agent Mode (AI) - NightCity MTA:SA asset pipeline
# -----------------------------------------------------------------------------
# roads.py - curved / graded arterial roads, expressway segments, ramps and roundabouts.
#            A segment model runs along +x through the origin (chord), bending with radius r and
#            climbing dz across its length.  Corridors are laid down as chains of these pieces
#            (rotated placements) along a spline in plan.py - the road therefore curves with the
#            geography instead of running as one straight grid line.
#
#            Every piece carries its own kerb skirt down to the terrain so no gap can open between
#            the road and the heightfield below.
# -----------------------------------------------------------------------------
import numpy as np
from .mb import Mesh, Col
from . import parts as P

SIDEWALK = 'nc_sidewalk'
CURB = 'nc_curb'
ROADM = {'A': 'nc_road_ave', 'H': 'nc_road_hwy', 'S': 'nc_road_str'}


def _arc_pts(L, r, n, dz):
    """centre-line sample of a segment: chord along +x, bending with radius r (sign = left/right)"""
    if abs(r) < 1e-6:
        t = np.linspace(-L / 2, L / 2, n)
        return np.stack([t, np.zeros(n), t * (dz / L)], -1)
    th = L / abs(r)                      # sweep angle (chord approximation)
    a0 = -th / 2
    aa = np.linspace(a0, a0 + th, n)
    R = abs(r)
    s = np.sign(r)
    cx, cy = 0.0, s * R                  # centre offset to the left/right
    px = cx + R * np.sin(aa)
    py = cy - s * R * np.cos(aa)
    # keep the chord centered on x = 0
    px = px - (px[0] + px[-1]) / 2
    py = py - (py[0] + py[-1]) / 2
    return np.stack([px, py, np.linspace(-dz / 2, dz / 2, n)], -1)


def _norm2(pts):
    d = np.gradient(pts[:, :2], axis=0)
    n = np.stack([-d[:, 1], d[:, 0]], -1)
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
    return n


def road_seg(L=96.0, r=0.0, dz=0.0, cls='A', seed=0, lamps=True, skirt=2.2, barrier=False):
    """ground arterial: carriageway + kerbs + two pavements + lamps + skirt into the terrain"""
    M, C = Mesh(), Col()
    rng = np.random.default_rng(seed)
    cw = {'A': 24.0, 'S': 14.0, 'H': 22.0}[cls]
    sw = {'A': 6.0, 'S': 4.0, 'H': 2.0}[cls]
    n = max(8, int(L / 8.0))
    pts = _arc_pts(L, r, n, dz)
    nor = _norm2(pts)
    hw = cw / 2
    path = [tuple(p) for p in pts]
    M.ribbon(path, hw, ROADM[cls], tile_v=9.0, u=(0.0, 1.0), up=True)
    for s in (-1, 1):
        # pavement
        p_edge = pts.copy()
        p_edge[:, 0] += nor[:, 0] * s * (hw + sw / 2)
        p_edge[:, 1] += nor[:, 1] * s * (hw + sw / 2)
        M.ribbon([tuple(p) for p in p_edge], sw / 2, SIDEWALK, tile_v=6.0, u=(0.0, 1.0), up=True)
        # kerb + skirt to the ground
        pk = pts.copy()
        pk[:, 0] += nor[:, 0] * s * hw
        pk[:, 1] += nor[:, 1] * s * hw
        M.ribbon([tuple(p) for p in pk], 0.28, CURB, tile_v=4.0, u=(0.0, 1.0), zoff=0.045, up=True)
        pl = pts.copy()
        pl[:, 0] += nor[:, 0] * s * (hw + sw)
        pl[:, 1] += nor[:, 1] * s * (hw + sw)
        M.wall_strip([tuple(p[:2]) for p in pl], -skirt, 0.12, 'nc_concrete', tile=(3.0, 1.2))
        C.poly_slab([(p[0] + nor[i, 0] * s * (hw + sw), p[1] + nor[i, 1] * s * (hw + sw)) for i, p in enumerate(pts)]
                    + [(p[0] + nor[i, 0] * s * (hw - 0.2), p[1] + nor[i, 1] * s * (hw - 0.2)) for i, p in enumerate(pts)][::-1],
                    -0.35, 0.12)
    # carriageway collision slab (follows the chord; gentle grades are fine as one slab)
    zlo = float(pts[:, 2].min()) - 0.4
    zhi = float(pts[:, 2].max()) + 0.12
    C.poly_slab([(p[0] + nor[i, 0] * hw, p[1] + nor[i, 1] * hw) for i, p in enumerate(pts)]
                + [(p[0] - nor[i, 0] * hw, p[1] - nor[i, 1] * hw) for i, p in enumerate(pts)][::-1],
                zlo, zhi)
    if barrier:
        for s in (-1, 1):
            pb = pts.copy()
            pb[:, 0] += nor[:, 0] * s * (hw + 0.5)
            pb[:, 1] += nor[:, 1] * s * (hw + 0.5)
            for i in range(len(pb) - 1):
                a, b = pb[i], pb[i + 1]
                M.box((min(a[0], b[0]) - 0.35, min(a[1], b[1]) - 0.35, max(a[2], b[2]) + 0.02),
                      (max(a[0], b[0]) + 0.35, max(a[1], b[1]) + 0.35, max(a[2], b[2]) + 0.85), 'nc_concrete', tile=(2.0, 0.7))
    if lamps:
        for i in range(1, n - 1):
            if i % 2:
                continue
            p = pts[i]
            nn = nor[i]
            s = 1 if (i // 2 + seed) % 2 == 0 else -1
            arm = 1 if s > 0 else -1
            M.merge(P.street_lamp(9.0, 2.6, cls == 'H', cls == 'H'),
                    (p[0] + nn[0] * s * (hw + sw * 0.55), p[1] + nn[1] * s * (hw + sw * 0.55), p[2] + 0.12),
                    rz=(np.degrees(np.arctan2(nn[1], nn[0])) - 90.0 * arm) % 360.0)
    return M, C, dict(kind='road', dist=1700.0, amb=1.0)


def expressway_seg(L=120.0, r=0.0, dz=0.0, level=12.0, seed=0, pier=True):
    """elevated expressway deck on piers: same language as the old straight expressway, but curvable"""
    M, C = Mesh(), Col()
    n = max(8, int(L / 10.0))
    pts = _arc_pts(L, r, n, dz)
    nor = _norm2(pts)
    hw = 11.0
    path = [tuple(p) for p in pts]
    # deck box under the carriageway
    under = [(p[0], p[1], p[2] - 1.35) for p in pts]
    M.ribbon(path, hw, 'nc_road_hwy', tile_v=9.0, u=(0.0, 1.0), up=True)
    M.ribbon(under, hw, 'nc_deck_under', tile_v=6.0, u=(0.0, 1.0), up=False)
    for s in (-1, 1):
        pe = [tuple(pts[i] + np.array([nor[i, 0] * s * hw, nor[i, 1] * s * hw, -0.65])) for i in range(n)]
        M.wall_strip([(p[0], p[1]) for p in pe], -0.75, 0.62, 'nc_concrete', tile=(3.0, 1.1))
        pb = pts.copy()
        pb[:, 0] += nor[:, 0] * s * (hw - 0.8)
        pb[:, 1] += nor[:, 1] * s * (hw - 0.8)
        for i in range(len(pb) - 1):
            a, b = pb[i], pb[i + 1]
            M.box((min(a[0], b[0]) - 0.3, min(a[1], b[1]) - 0.3, max(a[2], b[2]) + 0.02),
                  (max(a[0], b[0]) + 0.3, max(a[1], b[1]) + 0.3, max(a[2], b[2]) + 0.95), 'nc_concrete', tile=(2.0, 0.8))
    # piers
    if pier:
        step = 42.0
        k = step / 2
        while k < L / 2 - 6:
            for s in (-1, 1):
                t = s * k
                i = int(np.clip((t + L / 2) / L * (n - 1), 0, n - 1))
                p = pts[i]
                M.box((p[0] - 1.6, p[1] - 1.6, -13.5), (p[0] + 1.6, p[1] + 1.6, p[2] - 1.3), 'nc_concrete', tile=(2.2, 3.0))
                M.box((p[0] - 2.6, p[1] - 2.6, p[2] - 2.35), (p[0] + 2.6, p[1] + 2.6, p[2] - 1.3), 'nc_concrete', tile=(2.2, 0.8))
                C.box((p[0] - 1.9, p[1] - 1.9, -13.5), (p[0] + 1.9, p[1] + 1.9, p[2] - 1.2))
            k += step
    # deck collision
    C.poly_slab([(pts[i, 0] + nor[i, 0] * hw, pts[i, 1] + nor[i, 1] * hw) for i in range(n)]
                + [(pts[i, 0] - nor[i, 0] * hw, pts[i, 1] - nor[i, 1] * hw) for i in range(n)][::-1],
                float(pts[:, 2].min()) - 1.5, float(pts[:, 2].max()) + 0.1)
    for i in range(1, n - 1, 3):
        p = pts[i]
        nn = nor[i]
        s = 1 if (i // 3 + seed) % 2 == 0 else -1
        M.merge(P.street_lamp(10.0, 3.0, False, True),
                (p[0] + nn[0] * s * (hw - 1.1), p[1] + nn[1] * s * (hw - 1.1), p[2] + 0.05),
                rz=(np.degrees(np.arctan2(nn[1], nn[0])) - 90.0 * (1 if s > 0 else -1)) % 360.0)
    return M, C, dict(kind='road', dist=2600.0, amb=1.0)


def ramp(L=90.0, r=60.0, dz=6.0, w=8.0, seed=0):
    """one curved slip road climbing between two levels"""
    M, C = Mesh(), Col()
    n = 10
    pts = _arc_pts(L, r, n, dz)
    nor = _norm2(pts)
    hw = w / 2
    M.ribbon([tuple(p) for p in pts], hw, 'nc_road_ave', tile_v=8.0, u=(0.0, 1.0), up=True)
    M.ribbon([(p[0], p[1], p[2] - 0.85) for p in pts], hw, 'nc_deck_under', tile_v=5.0, u=(0.0, 1.0), up=False)
    for s in (-1, 1):
        pe = [tuple(pts[i] + np.array([nor[i, 0] * s * hw, nor[i, 1] * s * hw, -0.45])) for i in range(n)]
        M.wall_strip([(p[0], p[1]) for p in pe], -0.6, 0.55, 'nc_concrete', tile=(2.5, 0.9))
    for i in range(2, n - 1, 2):
        p = pts[i]
        if p[2] > 1.2:
            M.box((p[0] - 1.1, p[1] - 1.1, p[2] - 12.0), (p[0] + 1.1, p[1] + 1.1, p[2] - 0.8), 'nc_concrete', tile=(1.8, 3.0))
            C.box((p[0] - 1.3, p[1] - 1.3, p[2] - 12.0), (p[0] + 1.3, p[1] + 1.3, p[2] - 0.7))
    C.poly_slab([(pts[i, 0] + nor[i, 0] * hw, pts[i, 1] + nor[i, 1] * hw) for i in range(n)]
                + [(pts[i, 0] - nor[i, 0] * hw, pts[i, 1] - nor[i, 1] * hw) for i in range(n)][::-1],
                float(pts[:, 2].min()) - 1.1, float(pts[:, 2].max()) + 0.1)
    return M, C, dict(kind='road', dist=1500.0, amb=1.0)


def roundabout(r=26.0, cls='S', seed=0):
    """a proper roundabout: ring road, kerbed island with a palm cluster"""
    from . import veg
    M, C = Mesh(), Col()
    n = 20
    aa = np.linspace(0, 2 * np.pi, n, endpoint=False)
    cw = {'A': 12.0, 'S': 9.0}[cls]
    ring_in, ring_out = r, r + cw
    for k in range(n):
        a0, a1 = aa[k], aa[(k + 1) % n]
        p = [(ring_in * np.cos(a0), ring_in * np.sin(a0), 0), (ring_out * np.cos(a0), ring_out * np.sin(a0), 0),
             (ring_out * np.cos(a1), ring_out * np.sin(a1), 0), (ring_in * np.cos(a1), ring_in * np.sin(a1), 0)]
        M.quad(p[0], p[1], p[2], p[3], ROADM[cls], tile=(4.0, 4.0))
    # island
    M.cyl((0, 0), r - 0.6, 0, 0.34, n, 'nc_concrete', tile=(2.4, 0.5), top_mat='nc_grass')
    for k in range(3):
        a = aa[k * 5]
        M.merge(veg.palm(seed=seed * 7 + k)[0], (np.cos(a) * (r * 0.42), np.sin(a) * (r * 0.42), 0.34), rz=float(k * 47))
    C.poly_slab([(np.cos(a) * (r - 0.6), np.sin(a) * (r - 0.6)) for a in aa], -0.4, 0.36)
    C.poly_slab([(ring_in * np.cos(a), ring_in * np.sin(a)) for a in aa] + [(ring_out * np.cos(a), ring_out * np.sin(a)) for a in aa][::-1],
                -0.35, 0.12)
    return M, C, dict(kind='road', dist=1200.0, amb=1.0)


def junction_pad(w=42.0, d=42.0, seed=0):
    """asphalt apron for complex intersections (T junctions, market squares, depot yards)"""
    M, C = Mesh(), Col()
    M.hquad(-w / 2, -d / 2, w / 2, d / 2, 0.02, 'nc_asphalt', tile=(12.0, 12.0))
    C.box((-w / 2, -d / 2, -0.35), (w / 2, d / 2, 0.1))
    return M, C, dict(kind='road', dist=900.0, amb=1.0)
