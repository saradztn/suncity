# Created by: Arena.ai Agent Mode (AI) - NightCity MTA:SA asset pipeline
# -----------------------------------------------------------------------------
# plan.py - the Night City master plan (2026 restructuring).
#
# Geography (city frame: origin = city centre, x east, y north, z = street level):
#   - the urban plain (flat, z = 0) fills the middle: a 16 x 14 district grid with varied blocks
#   - the SEA lies beyond the wiggly east coast; the bay cuts inland where the river meets it
#   - mountain ranges rise in the north-west, soft hills in the north-east (hillside villas)
#   - farmland + airfield roll away in the south; the canalised river crosses the city east-west
#
# Districts are shaped by the letter map below - each letter is a recipe with its own buildings,
# materials, park pads and street life.  Cells beyond the water line are dropped, so the built
# footprint follows the geography instead of a rectangle.  Curved corridors (bayshore parkway,
# crest road, airport parkway) and the metro loop are spline chains of segment models.
#
# Everything is deterministic.  Model specs are deduplicated by (builder, args).
# -----------------------------------------------------------------------------
import numpy as np
from .ground import SW, CARR, SIDE, CURB, QUAY, RIVER_Z, BED_Z, cell_dims
from . import ground, bld, infra, tunnel as TUN, terrain, roads, veg
from .bldkit import POD_H

SEA_Z = RIVER_Z

# ---------------------------------------------------------------------------------
# the district grid (block widths / street classes, west -> east and south -> north)
# ---------------------------------------------------------------------------------
XB = [96, 88, 72, 96, 88, 128, 88, 128, 88, 96, 128, 88, 160, 96, 128, 96]
XC = ['S', 'S', 'N', 'A', 'S', 'A', 'S', 'A', 'S', 'S', 'A', 'S', 'S', 'S', 'S', 'S', 'S']
YB = [96, 128, 88, 96, 128, 72, 88, 96, 72, 128, 88, 128, 96, 128]
YC = ['S', 'A', 'S', 'S', 'A', 'S', 'S', 'A', 'S', 'A', 'S', 'A', 'S', 'S', 'S']
RIVER_J = 6                                # the canalised river row (water cells)
HERO = (7, 10)                             # the CBD heart (arcology block)

# district letters: rows j = 13 (north) .. 0 (south), 16 columns west -> east
#   C CBD towers   K arcology   P plaza gate   F financial glass   H high-rise residential
#   R residential  S suburb     O old town     M market            E entertainment
#   W waterfront   Q port       I industrial   T tank farms        Y container yards
#   X factories    V parks      ~ river water
DISTRICTS = [
    "SSSVVRRHHHRRVSSS",   # 13  northern hills edge: suburb, parks, residential
    "SSVVRRRHHHHRRVSS",   # 12
    "SOOMMRHHFFCHHWWW",   # 11
    "SOOMMCCFKCCHHWWW",   # 10  CBD core (K = the arcology)
    "SOOMMCCCPCCEEHWW",   # 9   (P = the plaza gate landmark)
    "SSOMMCCEEEEEEWWW",   # 8
    "SWWWWWWEEEEWCWWW",   # 7   riverside north bank (C = tower on the quay)
    "~~~~~~~~~~~~~~~~",   # 6   THE RIVER
    "IIIIIIIIIIWWWWII",   # 5   south bank: industrial west, waterfront east
    "IIITTTIIYYWWQQII",   # 4
    "IIITTTXXIYYQQQQI",   # 3   the port apron reaches the bay
    "IIIIIIIIIIQQQQII",   # 2
    "VVIIIIIIIIIIIIVV",   # 1
    "VVVVIIIIIIIIVVVV",   # 0   southern fields
]
DIST = {j: DISTRICTS[13 - j] for j in range(14)}

EXPRESS_EW = dict(line=7, level=12.0)      # y line 7: the riverside east-west expressway
EXPRESS_NS = dict(line=7, level=22.0)      # x line 7: the north-south elevated through the CBD
BRIDGE_LINES = {1: 'N', 3: 'A', 5: 'S', 7: 'A', 9: 'A', 11: 'S', 13: 'A'}
HERO_BRIDGE_LINE = 7
TUNNEL = dict(line=9, row_in=7, g=0.10, L_open=64.0, PT=1.2, flat_L=64.0, flat_n=5, variants=(0, 1, 2, 1, 0), start=18.0)

STYLE = {'C': 'core', 'K': 'core', 'P': 'core', 'F': 'core', 'H': 'res', 'R': 'res', 'S': 'res',
         'O': 'market', 'M': 'market', 'E': 'ent', 'W': 'ent', 'Q': 'ind', 'I': 'ind',
         'T': 'ind', 'Y': 'ind', 'X': 'ind', 'V': 'ent', '~': 'ent'}
PAD = {'C': 'nc_plaza', 'K': 'nc_plaza', 'P': 'nc_plaza', 'F': 'nc_plaza', 'E': 'nc_plaza',
       'H': 'nc_sidewalk', 'R': 'nc_sidewalk', 'S': 'nc_sidewalk', 'O': 'nc_sidewalk',
       'M': 'nc_sidewalk', 'W': 'nc_sidewalk', 'Q': 'nc_concrete', 'I': 'nc_concrete',
       'T': 'nc_concrete', 'Y': 'nc_concrete', 'X': 'nc_concrete', 'V': 'nc_grass'}

GLASSES = ['nc_glass_a', 'nc_glass_b', 'nc_glass_c', 'nc_glass_d', 'nc_glass_e', 'nc_glass_f', 'nc_glass_g', 'nc_glass_h']
LEDS = ['nc_strip_cyan', 'nc_strip_white', 'nc_light_magenta', 'nc_strip_cyan']

# the metro loop: a closed organic circuit (clockwise) - elevated over the harbour, at grade along
# the bay, underground beneath the CBD and the market, elevated again through the western heights.
# z = rail top.  The route never passes below a water polygon (GTA rule).
METRO_WPS = [
    (720.0, -820.0, 13.0), (980.0, -560.0, 13.0), (1120.0, -140.0, 0.55), (1060.0, 220.0, 0.55),
    (900.0, 380.0, -9.5), (320.0, 520.0, -9.5), (-260.0, 470.0, -9.5), (-620.0, 330.0, -9.5),
    (-880.0, 150.0, 1.5), (-1010.0, -120.0, 13.0), (-880.0, -520.0, 13.0), (-420.0, -760.0, 13.0),
    (120.0, -880.0, 12.0), (520.0, -860.0, 13.0),
]
# stations: (name, kind) at the waypoint index
METRO_STATIONS = [
    ('DOCKS', 0, 'elevated'), ('BAY', 2, 'ground'), ('UNION', 5, 'underground'),
    ('MARKET', 7, 'underground'), ('HEIGHTS', 9, 'elevated'), ('WORKS', 11, 'elevated'),
]


class Plan:
    def __init__(self):
        self.models = {}
        self.keys = {}
        self.placements = []
        self.water = []
        self.points = {}
        self.tour = []
        self.counts = {'g': 0, 'b': 0, 'i': 0, 's': 0}

    def model(self, cat, builder, args, hint='', name=None):
        key = (builder, tuple(sorted((k, v if not isinstance(v, (list, tuple)) else tuple(v)) for k, v in args.items())))
        if key in self.keys:
            return self.keys[key]
        self.counts[cat] += 1
        name = name or ('nc_%s%03d' % (cat, self.counts[cat]))
        self.models[name] = dict(cat=cat, builder=builder, args=dict(args), hint=hint)
        self.keys[key] = name
        return name

    def place(self, name, x, y, z, rz, tag):
        self.placements.append(dict(model=name, x=float(x), y=float(y), z=float(z), rz=float(rz), tag=tag))


def tunnel_geom(X, Y):
    """river tunnel in city coordinates -> dict(... parts=[...], holes=[...], prof=[...])"""
    T = TUNNEL
    g, Lo, PT = T['g'], T['L_open'], T['PT']
    Lt = Lo + PT
    fl, fn = T['flat_L'], T['flat_n']
    x = X[T['line']]
    y_in = Y[T['row_in']] + T['start']
    z_floor = -g * Lt
    parts = [dict(builder='tunnel_open', args=dict(L=Lo, pt=PT, g=g), y=y_in + Lt / 2, z=-g * Lt / 2, rz=0.0)]
    y = y_in + Lt
    y_a = y
    for k in range(fn):
        parts.append(dict(builder='tunnel_tube', args=dict(L=fl, dz=0.0, variant=T['variants'][k % len(T['variants'])]), y=y + fl / 2, z=z_floor, rz=0.0))
        y += fl
    y_b = y
    parts.append(dict(builder='tunnel_open', args=dict(L=Lo, pt=PT, g=g), y=y_b + Lt / 2, z=-g * Lt / 2, rz=180.0))
    y_out = y_b + Lt
    prof = [(y_in, 0.0), (y_a, z_floor), (y_b, z_floor), (y_out, 0.0)]
    return dict(x=x, y_in=y_in, y_out=y_out, y_cov0=y_a, y_cov1=y_b, y_a=y_a, y_b=y_b, z_floor=z_floor, parts=parts, prof=prof,
                holes=[(y_in, y_in + Lo), (y_b + PT, y_out)])


def tunnel_z(tg, y):
    ys = [p[0] for p in tg['prof']]
    zs = [p[1] for p in tg['prof']]
    return float(np.interp(y, ys, zs))


def tunnel_tour(tg):
    x = tg['x']

    def at(ye, yt, sec, h=1.7, ht=1.2):
        return (x, ye, tunnel_z(tg, ye) + h, x, yt, tunnel_z(tg, yt) + ht, sec)
    yi, yo, ya, yb = tg['y_in'], tg['y_out'], tg['y_a'], tg['y_b']
    return [
        (x, yi - 70.0, 7.0, x, yi + 40.0, tunnel_z(tg, yi + 40.0) + 0.5, 5.0),
        (x, yi - 14.0, 2.4, x, yi + 70.0, tunnel_z(tg, yi + 70.0) + 1.2, 3.0),      # ease the descent into the mouth
        at(yi + 25.0, yi + 125.0, 5.0),
        at(ya + 10.0, ya + 110.0, 8.0),
        at(ya + 130.0, ya + 230.0, 8.0),
        at(ya + 250.0, ya + 350.0, 6.0),
        at(yb - 40.0, yb + 60.0, 5.0),
        at(yb + 20.0, yo, 5.0),
        (x, yb + 70.0, tunnel_z(tg, yb + 70.0) + 1.9, x, yo + 40.0, 2.2, 3.0),      # ease out over the exit ramp
        (x, yo + 8.0, 1.9, x, yo + 110.0, 2.6, 6.0),
    ]


def grid_lines():
    W = [XB[i] + SW[XC[i]] / 2 + SW[XC[i + 1]] / 2 for i in range(16)]
    D = [YB[j] + SW[YC[j]] / 2 + SW[YC[j + 1]] / 2 for j in range(14)]
    X = [0.0]
    for w in W:
        X.append(X[-1] + w)
    Y = [0.0]
    for d in D:
        Y.append(Y[-1] + d)
    cx = (X[0] + X[-1]) / 2
    cy = (Y[0] + Y[-1]) / 2
    X = [x - cx for x in X]
    Y = [y - cy for y in Y]
    return X, Y, W, D


# ---------------------------------------------------------------------------------
# building palettes
# ---------------------------------------------------------------------------------
def _palettes():
    rng = np.random.default_rng(2077)
    towers = []
    sizes = [(36, 36), (40, 36), (44, 38), (48, 40), (40, 44), (36, 44), (44, 44), (32, 32)]
    floors = [34, 40, 46, 52, 58, 64, 70, 78, 86, 96]
    for k in range(34):
        w, d = sizes[k % len(sizes)]
        f = floors[(k * 3 + int(rng.integers(0, 3))) % len(floors)]
        r = rng.random()
        mat = GLASSES[(k * 5 + int(rng.integers(0, 8))) % 8]
        led = LEDS[int(rng.integers(len(LEDS)))]
        if r < 0.58:
            towers.append(('tower_setback', dict(w=w, d=d, floors=f, mat=mat, seed=int(rng.integers(1, 9999)), crown_style=str(rng.choice(['spire', 'ring', 'prongs', 'flat', 'dish'])),
                                                 steps=int(rng.integers(1, 4)), scale_top=float(round(rng.uniform(0.55, 0.78), 2)), pod=int(rng.integers(1, 3)),
                                                 fin=int(rng.random() < 0.4), signs=int(rng.integers(2, 4)), led=led, octo=bool(rng.random() < 0.25))))
        elif r < 0.86:
            towers.append(('tower_cyl', dict(r=float(rng.choice([13, 14, 15, 16])), floors=f, mat=mat, seed=int(rng.integers(1, 9999)), ring_every=int(rng.choice([6, 8, 10])), led=led,
                                              crown_style=str(rng.choice(['ring', 'spire', 'flat'])))))
        else:
            towers.append(('tower_twin', dict(w=24, d=28, floors=min(f, 70), gap=float(rng.choice([16, 20])), mat=mat, seed=int(rng.integers(1, 9999)), led=led)))
    mids = []
    for k in range(18):
        w, d = [(36, 36), (40, 36), (32, 40), (44, 32), (36, 28)][k % 5]
        mids.append(('midrise', dict(w=w, d=d, floors=int(rng.integers(8, 20)), mat=GLASSES[(k * 3 + 1) % 8], seed=int(rng.integers(1, 9999)), signs=int(rng.integers(2, 4)),
                                     led=LEDS[int(rng.integers(len(LEDS)))])))
    tens = []
    for k in range(14):
        w, d = [(26, 22), (26, 24), (24, 22), (26, 26)][k % 4]
        tens.append(('tenement', dict(w=w, d=d, floors=int(rng.integers(6, 14)), mat=['nc_wall_tenement_a', 'nc_wall_tenement_b', 'nc_wall_brutal'][k % 3], seed=int(rng.integers(1, 9999)),
                                      escapes=int(rng.integers(1, 3)))))
    slabs = []
    for k in range(8):
        w, d = [(64, 18), (56, 18), (48, 16), (60, 20)][k % 4]
        slabs.append(('slab', dict(w=w, d=d, floors=int(rng.integers(14, 28)), mat=['nc_glass_b', 'nc_glass_g', 'nc_wall_brutal', 'nc_glass_h'][k % 4], seed=int(rng.integers(1, 9999)))))
    megas = [('megablock', dict(w=w, d=d, floors=int(f), seed=int(rng.integers(1, 9999)))) for (w, d, f) in ((48, 48, 30), (48, 44, 36), (52, 48, 32), (40, 40, 34))]
    warehouses = [('warehouse', dict(w=w, d=d, h=float(h), seed=int(rng.integers(1, 9999)))) for (w, d, h) in ((56, 36, 11), (60, 40, 12), (52, 34, 10), (64, 38, 13), (48, 32, 10))]
    rows = [('rowhouse', dict(w=float(w), d=11.0, seed=int(rng.integers(1, 9999)), floors=int(f))) for (w, f) in ((22, 3), (26, 4), (30, 3), (24, 2), (28, 4), (32, 3), (20, 2), (26, 3))]
    villas = [('villa', dict(w=float(w), d=float(d), seed=int(rng.integers(1, 9999)), pool=bool(rng.random() < 0.7))) for (w, d) in ((18, 14), (22, 16), (16, 13), (24, 18), (20, 15))]
    return dict(towers=towers, mids=mids, tens=tens, slabs=slabs, megas=megas, warehouses=warehouses, rows=rows, villas=villas)


PAL = None


def pal():
    global PAL
    if PAL is None:
        PAL = _palettes()
    return PAL


def _footprint(arch, a):
    if arch == 'tower_setback':
        return a['w'] + 6, a['d'] + 6
    if arch == 'tower_cyl':
        return 2 * (a['r'] + 3.5), 2 * (a['r'] + 3.5)
    if arch == 'tower_twin':
        return 2 * a['w'] + a['gap'] + 6, a['d'] + 6
    if arch == 'arcology':
        return a['w'] + 8, a['w'] + 8
    if arch == 'plaza_gate':
        return a['w'], 9.0
    return a['w'], a['d']


def pick(items, bw, bd, target, rng, key=lambda it: it[1].get('floors', 0), margin=2.0, avoid=()):
    fit = [it for it in items if _footprint(it[0], it[1])[0] <= bw - margin and _footprint(it[0], it[1])[1] <= bd - margin]
    if not fit:
        fit = sorted(items, key=lambda it: _footprint(it[0], it[1])[0] * _footprint(it[0], it[1])[1])[:3]
    fit = [it for it in fit if (it[0], it[1].get('seed')) not in avoid] or fit
    fit.sort(key=lambda it: abs(key(it) - target))
    return fit[int(rng.integers(0, min(3, len(fit))))]


# ---------------------------------------------------------------------------------
# spline helpers (for the metro path and the curved corridors)
# ---------------------------------------------------------------------------------
def catmull(points, n=12, closed=True):
    """sample a Catmull-Rom spline through points (dense polyline)"""
    P = np.asarray(points, float)
    k = len(P)
    out = []
    idx = range(k) if closed else range(k - 1)
    for i in idx:
        p0 = P[(i - 1) % k] if closed else P[max(0, i - 1)]
        p1 = P[i % k]
        p2 = P[(i + 1) % k]
        p3 = P[(i + 2) % k] if closed else P[min(k - 1, i + 2)]
        for s in np.linspace(0, 1, n, endpoint=False):
            s2, s3 = s * s, s * s * s
            pt = 0.5 * ((2 * p1) + (-p0 + p2) * s + (2 * p0 - 5 * p1 + 4 * p2 - p3) * s2 + (-p0 + 3 * p1 - 3 * p2 + p3) * s3)
            out.append(pt)
    if not closed:
        out.append(P[-1])
    return np.array(out)


def path_stats(P):
    """cumulative length + per-sample tangents/curvature"""
    d = np.gradient(P, axis=0)
    seg = np.linalg.norm(np.diff(np.vstack([P, P[:1]]), axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg[:-1])])
    return s, d


def _quant_r(kappa):
    """curvature -> quantised radius (0 = straight)"""
    if abs(kappa) < 1e-5:
        return 0.0
    r = 1.0 / kappa
    for q in (120.0, 180.0, 260.0, 380.0, 550.0, 800.0, 1300.0):
        if abs(r) <= q * 1.12:
            return q if r > 0 else -q
    return 1800.0 if r > 0 else -1800.0


def lay_corridor(plan, pts, seg_len=88.0, cls='A', tag='road', seed=0, builder='road_seg', **kw):
    """walk a spline and cover it with quantised segment models (curves + grades)."""
    P = catmull(pts, n=18, closed=False)
    dP = np.diff(P, axis=0)
    seg = np.linalg.norm(dP, axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    total = float(s[-1])

    def at(t):
        i = int(min(np.searchsorted(s, t, 'right') - 1, len(P) - 2))
        u = (t - s[i]) / max(s[i + 1] - s[i], 1e-9)
        u = min(max(u, 0.0), 1.0)
        return P[i] * (1 - u) + P[i + 1] * u, P[i + 1] - P[i]
    d2 = np.gradient(P, axis=0)
    cur = np.gradient(d2[:, :2], axis=0)
    kappa = (d2[:, 0] * cur[:, 1] - d2[:, 1] * cur[:, 0]) / np.maximum(np.linalg.norm(d2[:, :2], axis=1) ** 3, 1e-6)
    n_seg = max(1, int(round(total / seg_len)))
    for k in range(n_seg):
        t0, t1 = total * k / n_seg, total * (k + 1) / n_seg
        p0, d0 = at(t0 + 0.05)
        p1, d1 = at(t1 - 0.05)
        mid = (p0 + p1) / 2
        dx, dy = float(p1[0] - p0[0]), float(p1[1] - p0[1])
        L = float(np.hypot(dx, dy))
        if L < 3.0:
            continue
        rz = float(np.degrees(np.arctan2(dy, dx)))
        dz = float(p1[2] - p0[2])
        i_m = int(np.searchsorted(s, (t0 + t1) / 2, 'right') - 1)
        r = _quant_r(float(kappa[max(0, min(i_m, len(kappa) - 1))]))
        args = dict(L=round(L + 1.6, 1), r=r, dz=round(dz, 1), seed=seed % 3, **kw)   # overlap the joints 0.8 m each side so curved corridors leave no sliver
        if cls:
            args['cls'] = cls
        m = plan.model('i', builder, args, hint='%s %s' % (builder, cls))
        plan.place(m, float(mid[0]), float(mid[1]), float((p0[2] + p1[2]) / 2), rz, tag)


# ---------------------------------------------------------------------------------
# the plan
# ---------------------------------------------------------------------------------
def build_plan():
    plan = Plan()
    X, Y, W, D = grid_lines()
    rng = np.random.default_rng(31337)
    P_ = pal()
    recent = []
    cx0 = X[HERO[0]] + W[HERO[0]] / 2
    cy0 = Y[HERO[1]] + D[HERO[1]] / 2
    plan.extent = (X[0] - 40.0, Y[0] - 40.0, X[-1] + 40.0, Y[-1] + 40.0)
    # the river row drives the terrain (the bay cuts inland at the river mouth)
    river_y = (Y[RIVER_J] + Y[RIVER_J + 1]) / 2
    terrain.set_river_y(river_y)
    tg = tunnel_geom(X, Y)
    plan.tunnel = tg
    terrain.set_trench(tg['x'], tg['y_in'], tg['y_out'], tg['z_floor'], TUNNEL['L_open'], TUNNEL['PT'])
    for (hy0, hy1) in tg['holes']:
        jj = [j for j in range(14) if Y[j] < hy0 and hy1 < Y[j + 1]]
        assert len(jj) == 1, (hy0, hy1)
        j = jj[0]
        lo = Y[j] + CARR[YC[j]] / 2 + 4.0 + 1.0
        hi = Y[j + 1] - CARR[YC[j + 1]] / 2 - 4.0 - 1.0
        assert lo <= hy0 and hy1 <= hi, ('tunnel cut leaves its street', hy0, hy1, lo, hi)
    skyblocks = {}
    for j in range(14):
        for i in range(16):
            ch = DIST[j][i]
            cls = (XC[i], XC[i + 1], YC[j], YC[j + 1])
            bw, bd = XB[i], YB[j]
            cxm = X[i] + W[i] / 2
            cym = Y[j] + D[j] / 2
            # ---- organic silhouette: drop cells that sit on / too near the water line
            if ch != '~':
                s_here = float(terrain.land_s(cxm, cym))
                s_edge = min(float(terrain.land_s(X[i], cym)), float(terrain.land_s(X[i + 1], cym)),
                             float(terrain.land_s(cxm, Y[j])), float(terrain.land_s(cxm, Y[j + 1])))
                if s_here < 26.0 or s_edge < -30.0:
                    continue
            style = STYLE[ch]
            bcx = cxm + (SW[cls[0]] / 2 - SW[cls[1]] / 2) / 2
            bcy = cym + (SW[cls[2]] / 2 - SW[cls[3]] / 2) / 2
            alley = ('x', 0.0, 8.0) if ch == 'M' else None
            spec = dict(bw=bw, bd=bd, cls=cls, style=style, pad=PAD.get(ch, 'nc_sidewalk'), alley=alley, river=(ch == '~'), seed=1000 + 13 * bw + bd)
            if spec['river']:
                spec['seed'] = 3000 + bw
                gp = []
                if i in BRIDGE_LINES:
                    gp.append((-W[i] / 2, -W[i] / 2 + SW[XC[i]] / 2))
                if (i + 1) in BRIDGE_LINES:
                    gp.append((W[i] / 2 - SW[XC[i + 1]] / 2, W[i] / 2))
                spec['gaps'] = tuple((float(a), float(b)) for a, b in gp)
            holes = []
            for (hy0, hy1) in tg['holes']:
                if Y[j] < hy0 and hy1 < Y[j + 1]:
                    if i + 1 == TUNNEL['line']:
                        holes.append(('e', round(hy0 - cym, 3), round(hy1 - cym, 3)))
                    if i == TUNNEL['line']:
                        holes.append(('w', round(hy0 - cym, 3), round(hy1 - cym, 3)))
            if holes:
                spec['holes'] = tuple(holes)
            gname = plan.model('g', 'cell', spec, hint='%s %dx%d' % (ch, bw, bd))
            plan.place(gname, cxm, cym, 0.0, 0.0, 'ground')
            if ch == '~':
                yw0 = cym + (-D[j] / 2 + CARR[cls[2]] / 2 + SIDE[cls[2]] + QUAY - 1.5)
                yw1 = cym + (D[j] / 2 - CARR[cls[3]] / 2 + -SIDE[cls[3]] - QUAY + 1.5)
                plan.water.append((int(round(X[i] / 2.0)) * 2, int(np.floor(yw0 / 2) * 2), int(round(X[i + 1] / 2.0)) * 2, int(np.ceil(yw1 / 2) * 2), RIVER_Z))
                continue
            rr = np.random.default_rng(int(rng.integers(1, 10**9)))
            blds = []
            if (i, j) == (12, 11):
                blds.append(('stadium', dict(w=float(min(bw - 8, 152)), d=float(min(bd - 8, 118)), seed=1), 0.0, 0.0, 6.0))
            elif (i, j) == (5, 11):
                blds.append(('station_hall', dict(w=120.0, d=64.0, seed=2), 0.0, 0.0, 0.0))
            elif ch in 'CKPF':
                if ch == 'K':
                    blds.append(('arcology', dict(w=76, floors=70, seed=77), 0.0, 0.0, 0.0))
                elif ch == 'P':
                    blds.append(('plaza_gate', dict(w=56, h=70.0, seed=5), 0.0, 0.0, 90.0))
                else:
                    dist_c = np.hypot(bcx - cx0, bcy - cy0)
                    target = (102 if ch == 'F' else 96) - dist_c / 13.0 + float(rr.uniform(-8, 10))
                    arch, a = pick(P_['towers'], bw, bd, target, rr, avoid=recent[-6:])
                    recent.append((arch, a.get('seed')))
                    fw, fd = _footprint(arch, a)
                    rz = 0.0 if (fw <= bw - 2 and fd <= bd - 2) else 90.0
                    blds.append((arch, a, 0.0, 0.0, rz))
            elif ch == 'H':
                # high-rise residential: one slab + one tower + a garage
                arch, a = pick(P_['slabs'], bw * 0.62, bd - 8, 22, rr)
                blds.append((arch, a, -bw * 0.18, 0.0, 0.0 if bw >= bd else 90.0))
                if rr.random() < 0.7:
                    arch, a = pick(P_['towers'], bw * 0.45, bd * 0.5, 52, rr, avoid=recent[-4:])
                    recent.append((arch, a.get('seed')))
                    blds.append((arch, a, bw * 0.27, bd * 0.12, 0.0))
                else:
                    blds.append(('garage', dict(w=44.0, d=32.0, levels=int(rr.integers(4, 8)), seed=int(rr.integers(1, 99))), bw * 0.26, -bd * 0.16, 0.0))
            elif ch == 'E':
                r = rr.random()
                if r < 0.34:
                    arch, a = pick(P_['towers'], bw, bd, 40 + float(rr.uniform(-6, 16)), rr, avoid=recent[-6:])
                    recent.append((arch, a.get('seed')))
                    blds.append((arch, a, 0.0, 0.0, 0.0 if _footprint(arch, a)[0] <= bw - 2 else 90.0))
                elif r < 0.78:
                    arch, a = pick(P_['mids'], bw - 4, bd - 4, 14 + float(rr.uniform(-4, 5)), rr, avoid=recent[-4:])
                    recent.append((arch, a.get('seed')))
                    blds.append((arch, a, 0.0, 0.0, float(rr.choice([0, 90]))))
                else:
                    blds.append(('garage', dict(w=float(rr.choice([48, 52, 56])), d=float(rr.choice([32, 36])), levels=int(rr.integers(5, 9)), seed=int(rr.integers(1, 99))), 0.0, 0.0, float(rr.choice([0, 90]))))
            elif ch == 'W':
                if rr.random() < 0.55:
                    arch, a = pick(P_['mids'], bw - 4, bd - 4, 10 + float(rr.uniform(-2, 8)), rr, avoid=recent[-4:])
                    recent.append((arch, a.get('seed')))
                    blds.append((arch, a, 0.0, 0.0, 0.0))
                elif rr.random() < 0.5:
                    arch, a = pick(P_['slabs'], bw - 4, bd - 4, 18, rr)
                    blds.append((arch, a, 0.0, 0.0, 0.0 if bw >= bd else 90.0))
                else:
                    blds.append(('park_patch', dict(w=float(min(bw - 30, 72)), d=float(min(bd - 30, 60)), seed=int(rr.integers(1, 9999))), 0.0, 0.0, 0.0, 'park'))
            elif ch == 'M':
                ds = (bd - 8.0) / 2.0
                for row in (-1, 1):
                    for col in (-1, 1):
                        arch, a = pick(P_['tens'], bw / 2 - 1, ds - 1.5, int(rr.integers(6, 14)), rr)
                        blds.append((arch, a, col * bw / 4.0, row * (4.0 + ds / 2.0), float(rr.choice([0, 90, 180, 270]))))
            elif ch == 'O':
                # old town: rows of pastel houses + a few tenements
                for k, col in enumerate((-1, 1)):
                    arch, a = pick(P_['rows'], bw - 4, bd * 0.42, 3, rr, key=lambda it: it[1].get('floors', 3))
                    blds.append((arch, a, 0.0, col * bd * 0.24, 0.0 if col > 0 else 180.0))
                if rr.random() < 0.5:
                    arch, a = pick(P_['tens'], bw * 0.5, bd * 0.4, 9, rr)
                    blds.append((arch, a, -bw * 0.22, 0.0, float(rr.choice([0, 90]))))
            elif ch == 'R':
                if rr.random() < 0.5:
                    arch, a = pick(P_['megas'], bw - 4, bd - 4, 32, rr, key=lambda it: it[1]['floors'])
                    blds.append((arch, a, 0.0, 0.0, 0.0))
                else:
                    arch, a = pick(P_['slabs'], bw - 6, bd * 0.45, 20, rr)
                    blds.append((arch, a, 0.0, -bd * 0.22, 0.0))
                    arch2, a2 = pick(P_['slabs'], bw - 6, bd * 0.45, 16, rr)
                    blds.append((arch2, a2, 0.0, bd * 0.24, 180.0))
            elif ch == 'S':
                # suburb: row houses + small garages + green pockets
                if rr.random() < 0.55:
                    for row in (-1, 1):
                        arch, a = pick(P_['rows'], bw - 4, bd * 0.4, 2, rr, key=lambda it: it[1].get('floors', 3))
                        blds.append((arch, a, 0.0, row * bd * 0.26, 0.0 if row > 0 else 180.0))
                else:
                    blds.append(('park_patch', dict(w=float(min(bw - 32, 70)), d=float(min(bd - 32, 56)), seed=int(rr.integers(1, 9999))), 0.0, 0.0, 0.0, 'park'))
                    arch, a = pick(P_['villas'], bw * 0.4, bd * 0.34, 2, rr, key=lambda it: 2)
                    blds.append((arch, a, -bw * 0.26, bd * 0.18, float(rr.uniform(-25, 25))))
            elif ch == 'V':
                blds.append(('park_patch', dict(w=float(min(bw - 30, 78)), d=float(min(bd - 30, 62)), seed=int(rr.integers(1, 9999))), 0.0, 0.0, 0.0, 'park'))
            elif ch == 'Q':
                if rr.random() < 0.55:
                    arch, a = pick(P_['warehouses'], bw - 4, bd - 4, 11, rr, key=lambda it: it[1]['h'])
                    blds.append((arch, a, 0.0, -bd * 0.18 if bd > 70 else 0.0, 0.0))
                    if bd >= 84:
                        arch, a = pick(P_['warehouses'], bw - 4, bd * 0.4, 10, rr, key=lambda it: it[1]['h'])
                        blds.append((arch, a, 0.0, bd * 0.27, 0.0))
                else:
                    blds.append(('container_yard', dict(w=float(min(bw - 4, 80)), d=float(min(bd - 4, 60)), seed=int(rr.integers(1, 99))), 0.0, 0.0, 0.0))
            elif ch == 'I':
                if rr.random() < 0.65:
                    arch, a = pick(P_['warehouses'], bw - 4, bd - 4, 11, rr, key=lambda it: it[1]['h'])
                    blds.append((arch, a, 0.0, -bd * 0.18 if bd > 70 else 0.0, 0.0))
                else:
                    blds.append(('garage', dict(w=float(min(bw - 8, 56)), d=float(min(bd - 8, 40)), levels=int(rr.integers(3, 6)), seed=int(rr.integers(1, 99))), 0.0, 0.0, 0.0))
            elif ch == 'T':
                blds.append(('tank_farm', dict(w=float(bw - 6), d=float(min(bd - 6, 70)), seed=int(rr.integers(1, 99))), 0.0, 0.0, 0.0))
            elif ch == 'X':
                blds.append(('factory', dict(w=float(bw - 4), d=float(min(bd - 4, 70)), seed=int(rr.integers(1, 99))), 0.0, 0.0, 0.0))
            elif ch == 'Y':
                blds.append(('container_yard', dict(w=float(bw - 4), d=float(min(bd - 4, 64)), seed=int(rr.integers(1, 99))), 0.0, 0.0, 0.0))
            for bspec in blds:
                arch, a, dx, dy, rz = bspec[:5]
                btag = bspec[5] if len(bspec) > 5 else 'bld'
                bname = plan.model('b', arch, a, hint=arch)
                plan.place(bname, bcx + dx, bcy + dy, CURB, rz, btag)
                fw, fd = _footprint(arch, a)
                if rz % 180 == 90:
                    fw, fd = fd, fw
                skyblocks.setdefault((i, j), []).append((bcx + dx, bcy + dy, fw / 2, fd / 2, arch, a))
    # ------------------------------------------------------------------ expressways (grid aligned, elevated)
    ew, ns = EXPRESS_EW, EXPRESS_NS
    for i in range(16):
        L = int(round(W[i]))
        m = plan.model('i', 'expressway', dict(L=L, level=ew['level'], seed=i % 3, pier=True), hint='ew')
        plan.place(m, X[i] + W[i] / 2, Y[ew['line']], 0.0, 0.0, 'infra')
    for j in range(14):
        L = int(round(D[j]))
        if j == RIVER_J:
            m = plan.model('i', 'expressway', dict(L=L, level=ns['level'], seed=j % 3, pier=False, river=True), hint='ns-river')
        else:
            m = plan.model('i', 'expressway', dict(L=L, level=ns['level'], seed=j % 3, pier=True), hint='ns')
        plan.place(m, X[ns['line']], Y[j] + D[j] / 2, 0.0, 90.0, 'infra')
    # ------------------------------------------------------------------ river bridges + the road tunnel
    j = RIVER_J
    span = int(round(D[j]))
    water_span = int(round(D[j] - (CARR[YC[j]] / 2 + SIDE[YC[j]] + QUAY) - (CARR[YC[j + 1]] / 2 + SIDE[YC[j + 1]] + QUAY)))
    for line, cls in BRIDGE_LINES.items():
        if line == HERO_BRIDGE_LINE:
            m = plan.model('i', 'bridge_cable', dict(span=span, water=water_span, cls='A', seed=3), hint='hero bridge')
        else:
            m = plan.model('i', 'bridge_girder', dict(span=span, water=water_span, cls=cls, seed=line), hint='bridge %s' % cls)
        plan.place(m, X[line], (Y[j] + Y[j + 1]) / 2, 0.0, 0.0, 'bridge')
    for pt_ in tg['parts']:
        m = plan.model('i', pt_['builder'], pt_['args'], hint='tunnel')
        plan.place(m, tg['x'], pt_['y'], pt_['z'], pt_['rz'], 'tunnel')
    # ------------------------------------------------------------------ curved corridors on the terrain
    # 1. the bayshore parkway: hugs the east coast from the port to the northern bay
    bay = []
    for yq in np.linspace(-1240.0, 820.0, 12):
        xc = float(terrain.coast_x(yq)) - 250.0
        bay.append((xc, float(yq), 2.0 + 4.0 * max(0.0, (float(yq) + 300.0) / 1100.0)))
    lay_corridor(plan, bay, seg_len=92.0, cls='A', tag='road', seed=1)
    # 2. the crest road: climbs from the suburb into the north-west mountains
    crest = [(-620.0, 1080.0, 2.0), (-900.0, 1240.0, 18.0), (-1180.0, 1420.0, 42.0),
             (-1420.0, 1520.0, 70.0), (-1620.0, 1420.0, 92.0), (-1760.0, 1180.0, 104.0)]
    lay_corridor(plan, crest, seg_len=84.0, cls='S', tag='road', seed=2)
    # 3. the airport parkway: south from the industrial belt to the airfield
    airp = [(120.0, -940.0, 1.0), (180.0, -1080.0, 1.6), (120.0, -1210.0, 3.0), (20.0, -1300.0, 3.5)]
    lay_corridor(plan, airp, seg_len=88.0, cls='A', tag='road', seed=0)
    # 4. the harbour service road along the bay
    har = [(-360.0, -1020.0, 1.0), (-100.0, -1120.0, 1.2), (260.0, -1180.0, 1.4), (620.0, -1120.0, 1.6), (860.0, -980.0, 1.8)]
    lay_corridor(plan, har, seg_len=88.0, cls='S', tag='road', seed=1)
    # roundabouts + a ramp interchange where the parkway meets the expressway
    rb = plan.model('i', 'roundabout', dict(r=26.0, cls='S', seed=1), hint='roundabout')
    plan.place(rb, -648.0, 1052.0, 2.0, 0.0, 'road')
    plan.place(rb, 148.0, -912.0, 1.0, 0.0, 'road')
    for k, (r, dz, sx, sy, rz) in enumerate(((110.0, 6.0, 1080.0, -40.0, 250.0), (110.0, -6.0, 1160.0, 60.0, 70.0))):
        m = plan.model('i', 'ramp', dict(L=90.0, r=r, dz=dz, w=8.0, seed=k), hint='ramp')
        plan.place(m, sx, sy, 3.0, rz, 'road')
    # ------------------------------------------------------------------ the Night City Metro (organic closed loop)
    wps = [tuple(w) for w in METRO_WPS]
    Pm = catmull(wps, n=14, closed=True)
    d = np.gradient(Pm, axis=0)
    seg = np.linalg.norm(np.diff(np.vstack([Pm, Pm[:1]]), axis=0), axis=1)
    s_arr = np.concatenate([[0.0], np.cumsum(seg[:-1])])
    total = float(s_arr[-1] + seg[-1])
    cur = np.gradient(d[:, :2], axis=0)
    kappa = (d[:, 0] * cur[:, 1] - d[:, 1] * cur[:, 0]) / np.maximum(np.linalg.norm(d[:, :2], axis=1) ** 3, 1e-6)
    # station s positions (closest sample to each station waypoint)
    stops = []
    for (name, wi, kind) in METRO_STATIONS:
        wp = np.array(wps[wi])
        dd = np.linalg.norm(Pm - wp, axis=1)
        stops.append(dict(name=name, kind=kind, s=float(s_arr[int(np.argmin(dd))]), x=float(wp[0]), y=float(wp[1]), z=float(wp[2])))
    stops.sort(key=lambda t: t['s'])
    # place guideway pieces along the loop
    PIECE = 84.0
    n_pieces = int(round(total / PIECE))
    st_s = [t['s'] for t in stops]
    for k in range(n_pieces):
        t0 = total * k / n_pieces
        t1 = total * (k + 1) / n_pieces
        i0 = int(np.searchsorted(s_arr, t0, 'right') - 1) % len(Pm)
        i1 = int(np.searchsorted(s_arr, t1, 'right') - 1) % len(Pm)
        p0, p1 = Pm[i0], Pm[i1]
        mid = (p0 + p1) / 2
        # stations swallow the pieces under them
        covered = any((min(abs(t0 - ss), abs(t1 - ss)) < PIECE * 0.5) and (abs(((t0 + t1) / 2 - ss + total / 2) % total - total / 2) < PIECE * 0.6) for ss in st_s)
        if covered:
            continue
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        rz = float(np.degrees(np.arctan2(dy, dx)))
        L = float(np.hypot(dx, dy))
        dz = float(p1[2] - p0[2])
        r = _quant_r(float(kappa[(i0 + i1) // 2]))
        z = float((p0[2] + p1[2]) / 2)
        mode = 'tube' if z < -2.0 else ('ground' if z < 4.5 else 'viaduct')
        m = plan.model('i', 'rail_seg', dict(L=round(L, 1), r=r, dz=round(dz, 1), mode=mode, seed=0), hint='metro %s' % mode)
        plan.place(m, float(mid[0]), float(mid[1]), z, rz, 'metro')
    # portals where the guideway dives / surfaces
    for k in range(1, len(Pm)):
        za, zb = Pm[k - 1][2], Pm[k][2]
        if (za + 2.0) * (zb + 2.0) < 0 or (za - 4.5) * (zb - 4.5) < 0:
            p = Pm[k]
            dd = np.gradient(Pm[max(0, k - 2):k + 2], axis=0)
            rz = float(np.degrees(np.arctan2(dd[-1, 1], dd[-1, 0])))
            mp = plan.model('i', 'rail_portal', dict(), hint='metro portal')
            plan.place(mp, float(p[0]), float(p[1]), float(p[2]), rz, 'metro')
    # stations
    for si, t in enumerate(stops):
        i = int(np.argmin(np.linalg.norm(Pm - np.array([t['x'], t['y'], t['z']]), axis=1)))
        dd = np.gradient(Pm[max(0, i - 2):i + 2], axis=0)
        rz = float(np.degrees(np.arctan2(dd[-1, 1], dd[-1, 0])))
        if t['kind'] == 'underground':
            m = plan.model('i', 'rail_station_u', dict(variant=si % 3), hint='metro station %s' % t['name'])
        elif t['kind'] == 'ground':
            m = plan.model('i', 'rail_station_g', dict(variant=si % 3), hint='metro station %s' % t['name'])
        else:
            m = plan.model('i', 'rail_station', dict(variant=si % 3), hint='metro station %s' % t['name'])
        plan.place(m, t['x'], t['y'], t['z'], rz, 'metro')
        t['rz'] = rz
    sig = plan.model('i', 'rail_signal', dict(), hint='metro signal')
    for frac in (0.08, 0.21, 0.36, 0.52, 0.68, 0.84):
        i = int(np.argmin(np.abs(s_arr - total * frac)))
        p = Pm[i]
        dd = np.gradient(Pm[max(0, i - 2):i + 2], axis=0)
        rz = float(np.degrees(np.arctan2(dd[-1, 1], dd[-1, 0])))
        plan.place(sig, float(p[0]) + 4.2 * np.sin(np.radians(rz)), float(p[1]) - 4.2 * np.cos(np.radians(rz)), float(p[2]), rz, 'metro')
    plan.metro = dict(path=[(float(x), float(y), float(z)) for x, y, z in Pm], total=total, stops=stops, dw=6.0, vx=16.0, wps=wps)
    # ------------------------------------------------------------------ landmarks and special zones
    # the port: piers reaching into the bay + a lighthouse on the head
    pier = plan.model('b', 'pier', dict(L=150.0, w=16.0, seed=7), hint='harbour pier')
    plan.place(pier, 1180.0, river_y - 240.0, 0.0, 90.0, 'bld')
    plan.place(pier, 1240.0, river_y - 430.0, 0.0, 72.0, 'bld')
    m = plan.model('b', 'lighthouse', dict(seed=3), hint='lighthouse')
    plan.place(m, float(terrain.coast_x(-1250.0)) - 90.0, -1250.0, float(terrain.land_h(terrain.coast_x(-1250.0) - 90.0, -1250.0)) - 0.32, 0.0, 'bld')
    # hillside villas on the north-east hills (placed on the terrain)
    rng2 = np.random.default_rng(4242)
    for k in range(26):
        hx = float(rng2.uniform(520.0, 1240.0))
        hy = float(rng2.uniform(820.0, 1380.0))
        hz = float(terrain.land_h(hx, hy))
        if hz < 8.0 or float(terrain.land_s(hx, hy)) < 60.0:
            continue
        arch, a = pick(P_['villas'], 26.0, 22.0, 2, rng2, key=lambda it: 2)
        plan.place(plan.model('b', arch, a, hint='hillside villa'), hx, hy, hz - 0.32, float(rng2.uniform(0, 360)), 'bld')
    # the airfield (south outskirts): runway + hangars
    for k in range(3):
        m = plan.model('i', 'runway', dict(L=372.0, seed=9), hint='airport runway')
        plan.place(m, 20.0 + (k - 1) * 372.0 * np.cos(np.radians(8.0)), -1280.0 + (k - 1) * 372.0 * np.sin(np.radians(8.0)), 3.5, 8.0, 'infra')
    hangar = plan.model('b', 'hangar', dict(w=76.0, d=46.0, seed=6), hint='hangar')
    for k in range(3):
        plan.place(hangar, -260.0 + k * 210.0, -1160.0, 3.5, 96.0, 'bld')
    # ------------------------------------------------------------------ sky bridges between neighbouring towers
    sky = []
    for (i, jj), lst in skyblocks.items():
        if (i + 1, jj) in skyblocks and DIST[jj][i] in 'CFE' and DIST[jj][i + 1] in 'CFE':
            for (x0, y0, hw0, hd0, a0, s0) in lst:
                for (x1, y1, hw1, hd1, a1, s1) in skyblocks[(i + 1, jj)]:
                    f0, f1 = s0.get('floors', 0), s1.get('floors', 0)
                    if a0.startswith('tower') and a1.startswith('tower') and min(f0, f1) >= 46 and abs(y0 - y1) < 6:
                        gap = (x1 - hw1) - (x0 + hw0)
                        if 8 < gap < 64:
                            sky.append(((x0 + hw0 - 1.0 + x1 - hw1 + 1.0) / 2, (y0 + y1) / 2, gap + 2.0, min(f0, f1)))
    sky.sort(key=lambda s: -s[3])
    for used, (sx, sy, L, f) in enumerate(sky[:5]):
        z = 40.0 + 3.8 * int(f * 0.35)
        m = plan.model('i', 'skybridge', dict(length=int(round(L)), seed=used), hint='skybridge')
        plan.place(m, sx, sy, z, 0.0, 'sky')
    # ------------------------------------------------------------------ terrain, sea and the distant horizon
    TILE = 470.0   # COL quantisation: model half-size must stay < 255.9
    x0, y0, x1, y1 = X[0] - 1300.0, Y[0] - 1300.0, X[-1] + 1300.0, Y[-1] + 1300.0
    tid = 0
    yy = y0
    while yy < y1 - 1:
        xx = x0
        while xx < x1 - 1:
            cx_t, cy_t = xx + TILE / 2, yy + TILE / 2
            s_corner = max(float(terrain.land_s(xx + dxx, yy + dyy)) for dxx, dyy in ((0, 0), (TILE, 0), (0, TILE), (TILE, TILE)))
            if s_corner > -4.0:      # only tiles that touch land (open sea is the sea_floor model)
                # the tile is centred on its own height range (COL quantisation needs |z| < 255.9)
                gsz = 11
                gx, gy = np.meshgrid(np.linspace(xx, xx + TILE, gsz), np.linspace(yy, yy + TILE, gsz), indexing='ij')
                hh = terrain.land_h(gx, gy)
                zoff = float((hh.min() + hh.max()) / 2.0)
                m = plan.model('g', 'terrain_tile', dict(x0=xx, y0=yy, x1=xx + TILE, y1=yy + TILE, seed=tid, zoff=round(zoff, 1)), hint='terrain')
                plan.place(m, xx + TILE / 2, yy + TILE / 2, zoff - 0.32, 0.0, 'terrain')
                tid += 1
            xx += TILE
        yy += TILE
    # far mountain rings (coarse LOD, no collision)
    for (fx0, fy0, fx1, fy1, sd) in ((-2350.0, 900.0, -1300.0, 2350.0, 1), (-900.0, 1700.0, 1400.0, 2350.0, 2),
                                     (-2350.0, -400.0, -1600.0, 1100.0, 3)):
        m = plan.model('g', 'far_ring', dict(x0=fx0, y0=fy0, x1=fx1, y1=fy1, seed=sd), hint='far mountains')
        plan.place(m, (fx0 + fx1) / 2, (fy0 + fy1) / 2, 119.68, 0.0, 'terrain')
    # sea floor under the bay
    for k, (sx0, sy0, sx1, sy1) in enumerate(((1150.0, -2350.0, 2350.0, -1020.0), (1150.0, -1020.0, 2350.0, 2350.0),
                                              (-2350.0, -2350.0, 1150.0, -1020.0))):
        m = plan.model('g', 'sea_floor', dict(x0=sx0, y0=sy0, x1=sx1, y1=sy1, seed=k), hint='seabed')
        plan.place(m, (sx0 + sx1) / 2, (sy0 + sy1) / 2, -0.32, 0.0, 'terrain')
    # the sea itself (big water rectangles on the even GTA grid; land mesh rises above them)
    # the sea: water coordinates must stay well inside the +-3000 GTA world for any /ncshow here offset
    plan.water.append((-2300, -2300, 2300, -1080, SEA_Z))
    plan.water.append((1080, -1080, 2300, 2300, SEA_Z))
    # distant skyline strips (no collision)
    lw = (X[-1] - X[0]) + 500
    for (side, k, cx, cy, rz, L, sd) in ((('N'), 0, (X[0] + X[-1]) / 2, Y[-1] + 210.0, 0.0, lw, 11), ('N', 1, (X[0] + X[-1]) / 2, Y[-1] + 430.0, 0.0, lw, 12),
                                         ('S', 2, (X[0] + X[-1]) / 2, Y[0] - 260.0, 180.0, lw, 13)):
        m = plan.model('s', 'skyline_strip', dict(L=int(L), seed=sd, rows=2), hint='skyline')
        plan.place(m, cx, cy, 0.0, rz, 'skyline')
    for (rz, xs, tagn, sd) in ((-90.0, X[-1] + 240.0, 'E', 21), (90.0, X[0] - 240.0, 'W', 22)):
        m = plan.model('s', 'skyline_strip', dict(L=int((Y[-1] - Y[0]) + 200), seed=sd, rows=2), hint='skyline')
        plan.place(m, xs, (Y[0] + Y[-1]) / 2, 0.0, rz, 'skyline')
    dome = plan.model('g', 'skydome', dict(), hint='sky dome', name='nc_skydome')
    plan.place(dome, 0.0, 0.0, 350.0, 0.0, 'sky')
    # ------------------------------------------------------------------ named points (stable keys for /ncview)
    st = {t['name']: t for t in stops}
    plan.points = dict(
        spawn=(cx0, cy0 - D[HERO[1]] / 2 + 12.0, CURB + 1.0),
        plaza=(X[8] + 20.0, Y[9] + 40.0, CURB + 1.0),
        avenue=(X[5], cy0 - 200.0, 1.0),
        market=(X[3] + 12.0, Y[10] + 40.0, 1.0),
        quay=(cx0 + 200.0, Y[RIVER_J] + CARR[YC[RIVER_J]] / 2 + SIDE[YC[RIVER_J]] + 4.0, CURB + 1.0),
        bridge=(X[HERO_BRIDGE_LINE], (Y[RIVER_J] + Y[RIVER_J + 1]) / 2, CURB + 1.0),
        expressway=(X[3], Y[ew['line']], ew['level'] + 1.0),
        industrial=(X[3] + 60, Y[3] + 80, 1.0),
        metro_market=(st['MARKET']['x'], st['MARKET']['y'] + 8.5, st['MARKET']['z'] + 1.0),
        metro_union=(st['UNION']['x'], st['UNION']['y'] + 8.5, st['UNION']['z'] + 1.0),
        metro_docks=(st['DOCKS']['x'], st['DOCKS']['y'] + 8.5, st['DOCKS']['z'] + 1.0),
        metro_portal=(900.0, 380.0, -6.0),
        metro_loop=(st['WORKS']['x'] - 60.0, st['WORKS']['y'] - 60.0, st['WORKS']['z'] + 2.0),
        tunnel_in=(tg['x'], tg['y_in'] - 14.0, 1.0),
        tunnel_out=(tg['x'], tg['y_out'] + 14.0, 1.0),
        tunnel_mid=(tg['x'], (tg['y_a'] + tg['y_b']) / 2, tg['z_floor'] + 1.0),
        stadium=(X[12] + W[12] / 2, Y[11] + D[11] / 2, 30.0),
        harbor=(1180.0, river_y - 240.0, 4.0),
        bayshore=(float(terrain.coast_x(-200.0)) - 250.0, -200.0, 6.0),
        heights=(-1010.0, -120.0, 16.0),
        airfield=(20.0, -1280.0, 6.0),
        mountains=(-1620.0, 1420.0, 95.0),
    )
    # ------------------------------------------------------------------ the camera tour
    yr = river_y
    hb = X[HERO_BRIDGE_LINE]
    plan.tour = [
        (X[12], Y[2] - 120.0, 340.0, cx0, cy0, 90.0, 14.0),
        (hb + 160.0, yr - 260.0, 70.0, hb, yr, 45.0, 12.0),
        (hb, yr - 70.0, 7.0, hb, yr + 330.0, 40.0, 14.0),
        (X[5], Y[8] + 20.0, 3.5, X[5], Y[12], 60.0, 12.0),
        (cx0 - 140.0, cy0 - 120.0, 3.0, cx0, cy0, 150.0, 12.0),
        (cx0 + 70.0, cy0 - 30.0, 40.0, cx0, cy0, 140.0, 10.0),
        (X[3], Y[ew['line']], ew['level'] + 3.0, X[11], Y[ew['line']], ew['level'] + 9.0, 14.0),
        (X[3] + 3.0, Y[10] + 6.0, 3.0, X[3] + 3.0, Y[10] + 220.0, 14.0, 14.0),
        (X[9] + 50.0, Y[3] + 30.0, 11.0, X[9] + 50.0, Y[4] + 140.0, 46.0, 12.0),
    ] + tunnel_tour(tg) + [
        (float(terrain.coast_x(-200.0)) - 420.0, -200.0, 26.0, float(terrain.coast_x(-200.0)) + 40.0, -200.0, 2.0, 12.0),
        (st['MARKET']['x'] - 120.0, st['MARKET']['y'] + 26.0, st['MARKET']['z'] + 16.0, st['MARKET']['x'], st['MARKET']['y'], st['MARKET']['z'] + 4.0, 12.0),
        (st['MARKET']['x'] - 34.0, st['MARKET']['y'] + 9.0, st['MARKET']['z'] + 2.6, st['MARKET']['x'] + 44.0, st['MARKET']['y'] + 8.0, st['MARKET']['z'] + 2.2, 11.0),
        (880.0, 380.0, -4.4, 640.0, 480.0, -4.0, 11.0),
        (-1620.0, 1180.0, 120.0, cx0, cy0, 40.0, 10.0),
    ]
    plan.grid = dict(X=X, Y=Y, W=W, D=D)
    plan.hero = (cx0, cy0)
    return plan
