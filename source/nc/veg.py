# Created by: Arena.ai Agent Mode (AI) - NightCity MTA:SA asset pipeline
# -----------------------------------------------------------------------------
# veg.py - vegetation and rock props, MERGED into terrain tiles / park cells (never free objects).
#          Low-poly, deterministic, styled for a warm coastal city: pines, broadleaf trees, palms
#          for the waterfront, bushes and rocky outcrops for the mountains.
# -----------------------------------------------------------------------------
import numpy as np
from .mb import Mesh, Col

BARK = 'nc_bark'
LEAF = 'nc_leaf'
PALM = 'nc_palm'
ROCK = 'nc_rock'


def _canopy_blob(M, c, r, z, mat, squash=0.72, n=7, seed=0):
    """one squashed low-poly leaf ball"""
    rng = np.random.default_rng(seed)
    r1 = r * float(rng.uniform(0.85, 1.15))
    M.cyl((c[0], c[1]), r1, z, z + r1 * 1.15, n, mat, tile=(2.6, 1.4), top_mat=mat)
    M.cone((c[0], c[1]), r1 * 0.98, 0.05, z + r1 * 1.15, z + r1 * (1.15 + 1.35 * squash), n, mat, tile=(2.2, 1.6))
    M.cone((c[0], c[1]), r1, r1 * 0.98, z - 0.15, z, n, mat, tile=(2.2, 0.6))


def pine(h=None, seed=0):
    """mediterranean pine: bare trunk, umbrella canopy"""
    M, C = Mesh(), Col()
    rng = np.random.default_rng(seed)
    h = h or float(rng.uniform(7.5, 13.0))
    r0 = 0.32 * (h / 10.0)
    M.cyl((0, 0), r0, -0.2, h * 0.55, 6, BARK, tile=(1.0, 2.0))
    M.cone((0, 0), r0 * 1.15, r0 * 0.9, h * 0.55, h * 0.62, 6, BARK, tile=(1.0, 0.4))
    R = h * 0.42
    _canopy_blob(M, (0, 0), R, h * 0.52, LEAF, squash=0.55, n=8, seed=seed + 1)
    for k in range(2):
        a = rng.uniform(0, 2 * np.pi)
        d = R * 0.55
        _canopy_blob(M, (np.cos(a) * d, np.sin(a) * d), R * 0.6, h * 0.62 + k * R * 0.35, LEAF, squash=0.5, n=7, seed=seed + 2 + k)
    return M, C, dict(kind='veg')


def broadleaf(seed=0):
    """round street / park tree"""
    M, C = Mesh(), Col()
    rng = np.random.default_rng(seed)
    h = float(rng.uniform(6.5, 11.0))
    r0 = 0.36 * (h / 9.0)
    M.cyl((0, 0), r0, -0.2, h * 0.62, 6, BARK, tile=(1.0, 2.2))
    R = h * 0.46
    _canopy_blob(M, (0, 0), R, h * 0.55, LEAF, squash=0.85, n=8, seed=seed + 3)
    for k in range(3):
        a = rng.uniform(0, 2 * np.pi)
        d = R * 0.62
        _canopy_blob(M, (np.cos(a) * d, np.sin(a) * d), R * 0.55, h * 0.66 + (k - 1) * R * 0.30, LEAF, squash=0.8, n=7, seed=seed + 4 + k)
    return M, C, dict(kind='veg')


def palm(seed=0):
    """waterfront palm: leaning trunk, frond crown"""
    M, C = Mesh(), Col()
    rng = np.random.default_rng(seed)
    h = float(rng.uniform(8.0, 13.5))
    lean = float(rng.uniform(-0.14, 0.14))
    segs = 5
    for k in range(segs):
        z0 = h * k / segs - 0.2
        z1 = h * (k + 1) / segs
        off0 = lean * (z0 / h) ** 2 * h
        off1 = lean * (z1 / h) ** 2 * h
        r = 0.30 * (1.0 - 0.5 * k / segs)
        # tilted trunk segment approximated with a short cylinder
        M.cyl((off0, 0), r, z0, z1, 6, BARK, tile=(1.0, 1.1))
        if abs(off1 - off0) > 0.01:
            M.box((min(off0, off1) - r, -r, z0), (max(off0, off1) + r, r, z1), BARK, tile=(1.0, 1.0))
    zc = h
    xoff = lean * h
    n = 8
    for k in range(n):
        a = 2 * np.pi * k / n + 0.2
        ca, sa = np.cos(a), np.sin(a)
        L = h * 0.42
        droop = 0.35 + 0.35 * ((k % 3) / 2.0)
        p0 = (xoff, 0.0, zc)
        p1 = (xoff + ca * L * 0.55, sa * L * 0.55, zc + h * 0.10)
        p2 = (xoff + ca * L, sa * L, zc - h * droop * 0.22)
        M.ribbon([p0, p1, p2], 0.85, PALM, tile_v=1.6, u=(0.0, 1.0), up=True)
        M.ribbon([p0, p1, p2], 0.85, PALM, tile_v=1.6, u=(0.0, 1.0), up=False)
    M.cyl((xoff, 0), 0.35, zc - 0.35, zc + 0.35, 6, BARK, tile=(1.0, 0.5))
    return M, C, dict(kind='veg')


def bush(seed=0):
    """small shrub"""
    M, C = Mesh(), Col()
    rng = np.random.default_rng(seed)
    r = float(rng.uniform(1.1, 2.2))
    _canopy_blob(M, (0, 0), r, -0.1, LEAF, squash=0.75, n=7, seed=seed + 5)
    return M, C, dict(kind='veg')


def outcrop(r=8.0, seed=0):
    """weathered rock cluster for the mountains"""
    M, C = Mesh(), Col()
    rng = np.random.default_rng(seed)
    n = int(rng.integers(3, 6))
    for k in range(n):
        a = rng.uniform(0, 2 * np.pi)
        d = r * rng.uniform(0.0, 0.8)
        rr = r * rng.uniform(0.35, 0.85)
        h = rr * rng.uniform(1.1, 2.2)
        cx, cy = np.cos(a) * d, np.sin(a) * d
        m = int(rng.integers(5, 8))
        M.cone((cx, cy), rr, rr * rng.uniform(0.25, 0.55), -rr * 0.35, h, m, ROCK, tile=(rr, h))
        if rng.random() < 0.5:
            M.cone((cx + rr * 0.3, cy - rr * 0.2), rr * 0.55, 0.1, -rr * 0.2, h * 0.55, m, ROCK, tile=(rr, h))
    return M, C, dict(kind='veg')


def planter_tree(kind=0, seed=0):
    """street tree in a concrete planter (for cell sidewalks)"""
    M, C = Mesh(), Col()
    M.box((-1.1, -1.1, 0.0), (1.1, 1.1, 0.62), 'nc_concrete', tile=(1.1, 0.5))
    M.hquad(-1.0, -1.0, 1.0, 1.0, 0.64, 'nc_dirt', tile=(1.0, 1.0))
    if kind == 0:
        sub = palm(seed=seed)
    elif kind == 1:
        sub = pine(seed=seed)
    else:
        sub = broadleaf(seed=seed)
    M.merge(sub[0], (0, 0, 0.55), 0.0)
    return M, C, dict(kind='veg')
