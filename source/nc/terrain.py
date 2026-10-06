# Created by: Arena.ai Agent Mode (AI) - NightCity MTA:SA asset pipeline
# -----------------------------------------------------------------------------
# terrain.py - the natural ground of the Night City region: an organic land mass with a wiggly east
#              coastline, a southern bay, mountain ranges in the north-west, rolling hills in the
#              north-east, beaches, the river estuary and farmland outskirts.  The city itself sits
#              on the flat plain in the middle; the terrain rises around it and dives under the sea.
#
#              Land is a heightfield (land_h) clipped by a signed land mask (land_s).  Models are
#              square tiles of the heightfield; far mountain rings are coarse LOD tiles (no collision
#              beyond the walkable range).  Trees and rocks are merged into the tiles - never objects.
#
#              Water: the sea lives in NC_WATER rectangles on the even GTA water grid; everything
#              above the water line is land mesh.  GTA treats every point below a water polygon as
#              water, so no walkable / drivable geometry of ours may ever dip below -3.0 under the
#              sea rectangles (the metro tunnel honours this too).
# -----------------------------------------------------------------------------
import numpy as np
from .mb import Mesh, Col
from .ground import RIVER_Z

SEA_Z = RIVER_Z                 # -3.0 the water level
BEACH_Z = 1.2                   # the sand strip top at the shore line
TILE = 320.0                    # terrain tile edge (m)
RES = 16.0                      # heightfield step (m) in the walkable ring
FAR_RES = 64.0                  # LOD step for the distant ranges


def _fbm(x, y, seed, octaves=4, base=420.0):
    """cheap deterministic fractal noise on world coordinates (no per-pixel work)"""
    out = np.zeros(np.broadcast(x, y).shape, np.float64)
    amp, freq = 1.0, 1.0 / base
    rng = np.random.default_rng(seed)
    for k in range(octaves):
        ang = rng.uniform(0, 2 * np.pi)
        c, s = np.cos(ang), np.sin(ang)
        u = (x * c + y * s) * freq
        v = (-x * s + y * c) * freq
        out = out + amp * (np.sin(u * 2.1 + rng.uniform(0, 6)) * np.sin(v * 1.7 + rng.uniform(0, 6))
                           + 0.6 * np.sin(u * 3.9 + 1.3) * np.sin(v * 3.1 + 2.2))
        amp *= 0.52
        freq *= 2.13
    return out / 1.85


def _gauss(x, y, cx, cy, sx, sy):
    return np.exp(-(((x - cx) / sx) ** 2 + ((y - cy) / sy) ** 2))


RIVER_Y = -262.0            # the canalised river row of the city grid (its mouth is the bay)


TRENCH = None   # plan.py sets the road-tunnel cut so the land dips into it


def set_trench(x, y_in, y_out, z_floor, L_open, PT):
    global TRENCH
    TRENCH = dict(x=float(x), y_in=float(y_in), y_out=float(y_out), z_floor=float(z_floor), L_open=float(L_open), PT=float(PT))


def set_river_y(y):
    """align the terrain's river-mouth bay with the plan's river row centre"""
    global RIVER_Y
    RIVER_Y = float(y)


def coast_x(y):
    """the east shoreline: x of the water line at north-south coordinate y (organic wiggles).
    A bay cuts inland where the river meets the sea (the estuary)."""
    return (1460.0
            + 170.0 * np.sin(y / 640.0 + 0.6)
            + 105.0 * np.sin(y / 275.0 + 1.9)
            + 60.0 * np.sin(y / 133.0 + 3.1)
            - 330.0 * np.exp(-((y - RIVER_Y) / 190.0) ** 2))


def south_y(x):
    """the south shoreline (the bay): y of the water line at east-west coordinate x"""
    return (-1420.0
            + 190.0 * np.sin(x / 720.0 - 0.4)
            + 95.0 * np.sin(x / 310.0 + 1.1)
            + 55.0 * np.sin(x / 150.0 + 2.6))


def land_s(x, y):
    """signed land margin (>0 = land, <0 = water).  The urban plain is deep land; the sea is beyond
    the wiggly east coast and the south bay.  The river mouth is a bay carved into coast_x()."""
    s_e = coast_x(y) - x                       # east coast
    s_s = y - south_y(x)                       # south bay
    return np.minimum(s_e, s_s)


def land_h(x, y):
    """terrain height in city coordinates (0 = street level of the urban plain)"""
    x = np.asarray(x, np.float64)
    y = np.asarray(y, np.float64)
    flat = _fbm(x, y, 11)
    # ---- urban plain: flat, kept flat everywhere the city lives
    h = np.zeros_like(x, dtype=np.float64)
    # ---- north-west mountains: three overlapping massifs with noisy ridgelines
    m = (395.0 * _gauss(x, y, -1620.0, 1560.0, 620.0, 520.0)
         + 320.0 * _gauss(x, y, -980.0, 2020.0, 540.0, 430.0)
         + 262.0 * _gauss(x, y, -1980.0, 780.0, 420.0, 620.0)
         + 240.0 * _gauss(x, y, 260.0, 2210.0, 780.0, 380.0)
         + 175.0 * _gauss(x, y, -1500.0, 2320.0, 620.0, 330.0))
    m *= (0.72 + 0.28 * (0.5 + 0.5 * flat))                # irregular silhouettes
    # ---- north-east hills (the luxury hillside): softer bumps
    hills = (74.0 * _gauss(x, y, 900.0, 1350.0, 480.0, 360.0)
             + 52.0 * _gauss(x, y, 1180.0, 880.0, 380.0, 300.0)
             + 38.0 * _gauss(x, y, 480.0, 1680.0, 420.0, 260.0))
    hills *= (0.8 + 0.2 * (0.5 + 0.5 * flat))
    # ---- southern farmland roll
    south = 22.0 * np.clip(-y - 700.0, 0, 700.0) / 700.0 * (0.55 + 0.45 * (0.5 + 0.5 * flat))
    # ---- beach slope: the land falls into the water near the coast line
    s = land_s(x, y)
    shore = np.clip(1.0 - s / 90.0, 0.0, 1.0)               # 0 inland .. 1 at the water line
    beach = -shore ** 2 * (BEACH_Z - SEA_Z + 2.2) + shore * (BEACH_Z - 1.4)
    hills_tot = m + hills + south
    # the urban plain stays flat: the hills rise only outside the city grid (rect mask)
    mx = np.clip((np.abs(x) - 1180.0) / 420.0, 0.0, 1.0)
    my = np.clip((np.abs(y) - 1000.0) / 420.0, 0.0, 1.0)
    mask = np.maximum(mx, my) ** 1.3                          # 0 in the city, 1 outside
    h = hills_tot * mask * np.clip(s / 90.0, 0.0, 1.0) + np.where(s < 90.0, beach, 0.0)
    # the road tunnel cuts a trench through the land at its two open mouths
    if TRENCH is not None:
        T = TRENCH
        ya = T['y_in'] + T['L_open'] + T['PT']
        yb = T['y_out'] - T['L_open'] - T['PT']
        zp = np.interp(y, [T['y_in'], ya, yb, T['y_out']], [0.0, T['z_floor'], T['z_floor'], 0.0], left=0.0, right=0.0)
        band_x = np.clip(1.0 - (np.abs(x - T['x']) - 8.0) / 5.0, 0.0, 1.0)
        band_y = np.clip((y - (T['y_in'] - 1.0)), 0.0, 1.0) * np.clip(((T['y_out'] + 1.0) - y), 0.0, 1.0)
        eff = band_x * band_y
        h = h * (1.0 - eff) + np.minimum(h, zp - 0.25) * eff
    return h


def in_land(x, y, margin=0.0):
    return np.asarray(land_s(x, y) > margin, bool)


# ------------------------------------------------------------------------------------------
# mesh builders
# ------------------------------------------------------------------------------------------
def _tile_mesh(x0, y0, x1, y1, res, seed, trees=True, cliffs=True, walk=True, zoff=0.0):
    """one square tile of the land heightfield (with beach band, rocks and merged vegetation)"""
    M, C = Mesh(), Col()
    nx = max(2, int(round((x1 - x0) / res)))
    ny = max(2, int(round((y1 - y0) / res)))
    xs = np.linspace(x0, x1, nx + 1)
    ys = np.linspace(y0, y1, ny + 1)
    X, Y = np.meshgrid(xs, ys, indexing='ij')
    H = land_h(X, Y)
    S = land_s(X, Y)
    ox, oy = (x0 + x1) / 2.0, (y0 + y1) / 2.0   # models are placed at the tile centre
    rng = np.random.default_rng(seed)
    # material per vertex: sand near the water line, grass on the low land, rock high up, dirt on slopes
    mat = np.where(H > 150.0, 2, np.where(H > 42.0, 3, np.where(S < 26.0, 1, 0)))   # 0 grass 1 sand 2 rock 3 dirt
    P = np.stack([X - ox, Y - oy, H - zoff], -1)
    for i in range(nx):
        for j in range(ny):
            if S[i, j] < -2.0 and S[i + 1, j] < -2.0 and S[i, j + 1] < -2.0 and S[i + 1, j + 1] < -2.0:
                continue                                    # deep water: the sea covers it
            q = np.array([P[i, j], P[i + 1, j], P[i + 1, j + 1], P[i, j + 1]])
            # average material of the four corners
            mm = int(round((mat[i, j] + mat[i + 1, j] + mat[i, j + 1] + mat[i + 1, j + 1]) / 4.0))
            M.quad(q[0], q[1], q[2], q[3], ['nc_grass', 'nc_sand', 'nc_rock', 'nc_dirt'][mm], tile=(res, res))
    # collision: coarse prism grid over the walkable part (cheap and solid under the player)
    if walk:
        cres = max(res, 16.0)
        cx = np.unique(np.append(np.arange(x0, x1 + 1, cres), x1))
        cy = np.unique(np.append(np.arange(y0, y1 + 1, cres), y1))
        for i in range(len(cx) - 1):
            for j in range(len(cy) - 1):
                xa, ya = cx[i], cy[j]
                xb, yb = cx[i + 1], cy[j + 1]
                if land_s((xa + xb) / 2, (ya + yb) / 2) < -8.0:
                    continue
                hh = [float(land_h(xa + dxx, ya + dyy)) for dxx, dyy in ((0, 0), (xb - xa, 0), (xb - xa, yb - ya), (0, yb - ya))]
                hmax, hmin = max(hh), min(hh)
                if hmax - hmin < 0.25:
                    C.box((xa - ox - 1.5, ya - oy - 1.5, hmin - zoff - 2.5), (xb - ox + 1.5, yb - oy + 1.5, hmin - zoff + 0.02))
                else:
                    top = np.array([[xa - ox, ya - oy, hh[0] - zoff + 0.02], [xb - ox, ya - oy, hh[1] - zoff + 0.02],
                                    [xb - ox, yb - oy, hh[2] - zoff + 0.02], [xa - ox, yb - oy, hh[3] - zoff + 0.02]], float)
                    bot = top.copy()
                    bot[:, 2] = hmin - zoff - 3.0
                    C.mesh(np.vstack([top, bot]),
                           [(0, 1, 2), (0, 2, 3), (4, 6, 5), (4, 7, 6),
                            (0, 4, 5), (0, 5, 1), (1, 5, 6), (1, 6, 2), (2, 6, 7), (2, 7, 3), (3, 7, 4), (3, 4, 0)])
    # merged trees on the grass and rocks in the alpine band (never separate objects)
    if trees:
        from . import veg
        n = int((x1 - x0) * (y1 - y0) / 9000.0)
        for k in range(n):
            tx = float(rng.uniform(x0 + 20.0, x1 - 20.0))   # keep merged props inside the COL int16 range
            ty = float(rng.uniform(y0 + 20.0, y1 - 20.0))
            s = float(land_s(tx, ty))
            h = float(land_h(tx, ty))
            if s < 20.0 or h > 260.0:
                continue
            if 1150.0 < tx < 1500.0 and -1400.0 < ty < -1050.0:
                continue                                    # the port apron: no trees there
            z = h - 0.25
            r = float(rng.random())
            if r < 0.62:
                M.merge(veg.pine(seed=int(rng.integers(1, 9999)))[0], (tx - ox, ty - oy, z), rz=float(rng.uniform(0, 360)))
            elif r < 0.86:
                M.merge(veg.broadleaf(seed=int(rng.integers(1, 9999)))[0], (tx - ox, ty - oy, z), rz=float(rng.uniform(0, 360)))
            else:
                M.merge(veg.bush(seed=int(rng.integers(1, 9999)))[0], (tx - ox, ty - oy, z), rz=float(rng.uniform(0, 360)))
        # rocky outcrops in the high band
        if cliffs:
            for k in range(int(n * 0.35)):
                tx = float(rng.uniform(x0, x1))
                ty = float(rng.uniform(y0, y1))
                h = float(land_h(tx, ty))
                if not (60.0 < h < 330.0):
                    continue
                z = h - 1.2
                rr = float(rng.uniform(3.0, 11.0))
                M.merge(veg.outcrop(r=rr, seed=int(rng.integers(1, 9999)))[0], (tx - ox, ty - oy, z), rz=float(rng.uniform(0, 360)))
    return M, C, dict(kind='terrain', dist=2600.0, amb=1.0)


def tile(x0, y0, x1, y1, seed=0, res=RES, trees=True, cliffs=True, walk=True, zoff=0.0):
    return _tile_mesh(x0, y0, x1, y1, res, seed, trees=trees, cliffs=cliffs, walk=walk, zoff=zoff)


def far_ring(x0, y0, x1, y1, seed=0):
    """coarse LOD mountains for the horizon (no collision, long draw distance)"""
    M, C, _ = _tile_mesh(x0, y0, x1, y1, FAR_RES, seed, trees=False, cliffs=False, walk=False, zoff=120.0)
    return M, C, dict(kind='terrain', dist=4200.0, amb=1.0, nocol=True)


def sea_floor(x0, y0, x1, y1, seed=0):
    """dark seabed under the shallow bay so the water is not see-through to the void"""
    M, C = Mesh(), Col()
    n = 12
    ox, oy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    xs = np.linspace(x0, x1, n + 1) - ox
    ys = np.linspace(y0, y1, n + 1) - oy
    for i in range(n):
        for j in range(n):
            M.quad((xs[i], ys[j], -9.5), (xs[i + 1], ys[j], -9.5), (xs[i + 1], ys[j + 1], -9.5), (xs[i], ys[j + 1], -9.5),
                   'nc_riverbed', tile=(90.0, 90.0))
    return M, C, dict(kind='terrain', dist=2600.0, amb=1.0, nocol=True)
