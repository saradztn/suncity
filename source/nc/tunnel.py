# Created by: Arena.ai Agent Mode (AI) - NightCity MTA:SA asset pipeline
# -----------------------------------------------------------------------------
# tunnel.py - the road tunnel (cut-and-cover underpass): open cut ramps with the portal headers (tunnel_open) and the covered tube
#             (tunnel_tube).  Both are built along +y with the local origin in the middle of the part; the plan places them
#             (the second portal with rz = 180).  The road is the 14 m, two + two lane 'S' street carriageway.
#
#   tunnel_open : trench in the street (road ramps down at 10 %), concrete retaining walls, rails on the pavements, sign
#                 gantry, portal header with the green sign; it ends 1.2 m inside the mouth.
#   tunnel_tube : covered box tube.  Interior 14 m x 4.8 m: glazed wall tiles, ceiling ribs, LED luminaires, jet fans,
#                 cable trays, emergency niches, lane control signals.  Nothing is drawn outside the shell (it is buried).
#
# Collision: ramp / floor, walls and roof as sloped prisms.  No vehicles, no people: only the structure.
# -----------------------------------------------------------------------------
import numpy as np
from .mb import Mesh, Col
from . import parts as P

HW = 7.0           # half width of the tunnel (= half of an 'S' street carriageway)
H = 4.8            # clear height, road surface -> ceiling
TR = 1.0           # roof slab thickness
TW = 0.8           # wall / floor slab thickness (collision)
SEG = 4.0          # tessellation step along the tunnel (vertex light resolution)
PANEL = 4.0        # wall tile panel width (nc_tunnel_tile)
LANES = (-5.03, -1.79, 1.79, 5.03)
ROAD = 'nc_road_str'
CURB = 0.16


class Prof:
    """vertical profile: z(y) = s * y (local), arc length measured from y0"""

    def __init__(self, s, y0):
        self.s, self.y0 = float(s), float(y0)
        self.k = float(np.sqrt(1.0 + s * s))

    def z(self, y):
        return self.s * np.asarray(y, float)

    def arc(self, y):
        return (np.asarray(y, float) - self.y0) * self.k


def _split(ya, yb):
    n = max(1, int(round((yb - ya) / SEG)))
    return np.linspace(ya, yb, n + 1)


def _floor(M, Pf, ya, yb):
    xs = np.linspace(-HW, HW, 5)
    ys = _split(ya, yb)
    Q, UV = [], []
    for k in range(len(ys) - 1):
        y0, y1 = ys[k], ys[k + 1]
        v0, v1 = -Pf.arc(y0) / 8.0, -Pf.arc(y1) / 8.0
        for i in range(4):
            xa, xb = xs[i], xs[i + 1]
            Q.append([(xa, y0, Pf.z(y0)), (xb, y0, Pf.z(y0)), (xb, y1, Pf.z(y1)), (xa, y1, Pf.z(y1))])
            UV.append([((xa + HW) / 14.0, v0), ((xb + HW) / 14.0, v0), ((xb + HW) / 14.0, v1), ((xa + HW) / 14.0, v1)])
    M.quads(np.array(Q), ROAD, np.array(UV))


def _ceiling(M, Pf, ya, yb, mat='nc_deck_under'):
    xs = np.linspace(-HW, HW, 5)
    ys = _split(ya, yb)
    Q, UV = [], []
    for k in range(len(ys) - 1):
        y0, y1 = ys[k], ys[k + 1]
        a0, a1 = Pf.arc(y0) / 4.0, Pf.arc(y1) / 4.0
        for i in range(4):
            xa, xb = xs[i], xs[i + 1]
            z0, z1 = Pf.z(y0) + H, Pf.z(y1) + H
            Q.append([(xa, y0, z0), (xa, y1, z1), (xb, y1, z1), (xb, y0, z0)])       # faces down
            UV.append([(xa / 4.0, -a0), (xa / 4.0, -a1), (xb / 4.0, -a1), (xb / 4.0, -a0)])
    M.quads(np.array(Q), mat, np.array(UV))


def _walls(M, Pf, ya, yb, mat, ztop=None, rows=2, tile=None):
    """both side walls, facing the tunnel axis.  ztop None: wall height H above the road (tiles, v = 1 at the road);
    ztop = value: concrete retaining wall up to that constant local z (trench)."""
    ys = _split(ya, yb)
    Q, UV, NR = [], [], []
    for sx in (-1, 1):
        x = sx * HW
        for k in range(len(ys) - 1):
            y0, y1 = ys[k], ys[k + 1]
            r0, r1 = Pf.z(y0), Pf.z(y1)
            for r in range(rows):
                f0, f1 = r / rows, (r + 1) / rows
                if ztop is None:
                    za0, za1, zb0, zb1 = r0 + f0 * H, r1 + f0 * H, r0 + f1 * H, r1 + f1 * H
                else:
                    za0, za1 = r0 + f0 * (ztop - r0), r1 + f0 * (ztop - r1)
                    zb0, zb1 = r0 + f1 * (ztop - r0), r1 + f1 * (ztop - r1)
                if ztop is None:
                    u0, u1 = Pf.arc(y0) / PANEL, Pf.arc(y1) / PANEL
                    va, vb = 1.0 - f0, 1.0 - f1
                    uva = (va, va, vb, vb)
                else:
                    u0, u1 = Pf.arc(y0) / tile[0], Pf.arc(y1) / tile[0]
                    uva = (-za0 / tile[1], -za1 / tile[1], -zb1 / tile[1], -zb0 / tile[1])
                a, b, c, d = (x, y0, za0), (x, y1, za1), (x, y1, zb1), (x, y0, zb0)
                if sx < 0:        # west wall: faces +x
                    Q.append([a, b, c, d])
                    UV.append([(u0, uva[0]), (u1, uva[1]), (u1, uva[2]), (u0, uva[3])])
                    NR.append([(1.0, 0.0, 0.0)] * 4)
                else:             # east wall: faces -x, texture u grows to the right of a viewer looking at the wall (= -y)
                    Q.append([b, a, d, c])
                    UV.append([(-u1, uva[1]), (-u0, uva[0]), (-u0, uva[3]), (-u1, uva[2])])
                    NR.append([(-1.0, 0.0, 0.0)] * 4)
    # explicit normals: the quads at the start of a trench wall have a zero-height edge (degenerate cross product)
    M.quads(np.array(Q), mat, np.array(UV), nrm=np.array(NR))


def _bars(M, Pf, x, ya, yb, dz, w, mat, emis=0.0, step=SEG):
    ys = np.linspace(ya, yb, max(1, int(round((yb - ya) / step))) + 1)
    for k in range(len(ys) - 1):
        y0, y1 = ys[k], ys[k + 1]
        P.bar(M, (x, y0, Pf.z(y0) + dz), (x, y1, Pf.z(y1) + dz), w, mat, tile=(2.0, 1.0), emis=emis)


def _prism(C, x0, x1, ya, yb, Pf, bot, top):
    """sloped collision prism: x in [x0, x1], y in [ya, yb]; bottom / top = road level + bot / top"""
    z = lambda y, off: float(Pf.z(y)) + off
    C.prisms.append(np.array([(x0, ya, z(ya, bot)), (x1, ya, z(ya, bot)), (x1, yb, z(yb, bot)), (x0, yb, z(yb, bot)),
                              (x0, ya, z(ya, top)), (x1, ya, z(ya, top)), (x1, yb, z(yb, top)), (x0, yb, z(yb, top))], float))


def _wall_box(M, sx, d, y0, y1, z0, z1, mat, emis=0.0):
    """box fixed to the side wall (sx = -1 west, +1 east), d metres deep towards the axis; the face on the wall is skipped"""
    xw = sx * HW
    lo, hi = (xw, xw + d) if sx < 0 else (xw - d, xw)
    M.box((lo, y0, z0), (hi, y1, z1), mat, tile=(1, 1), emis=emis, skip=('-x',) if sx < 0 else ('+x',))


# ---------------------------------------------------------------------------------------------
def tunnel_tube(L, dz, variant=0):
    """covered tube of length L along y (centred), road level falling by dz towards +y (dz < 0: descends towards +y)"""
    M, C = Mesh(), Col()
    s = dz / L
    Pf = Prof(s, -L / 2)
    ya, yb = -L / 2, L / 2
    zc = lambda y: Pf.z(y) + H
    _floor(M, Pf, ya, yb)
    _walls(M, Pf, ya, yb, 'nc_tunnel_tile', rows=2)
    _ceiling(M, Pf, ya, yb)
    arc = float(Pf.arc(yb))
    # concrete safety kerbs along both walls
    for sx in (-1, 1):
        _bars(M, Pf, sx * (HW - 0.15), ya, yb, 0.15, 0.30, 'nc_concrete', step=SEG)
    # cable trays and a service pipe on both walls
    for sx in (-1, 1):
        _bars(M, Pf, sx * (HW - 0.12), ya, yb, 3.95, 0.22, 'nc_metal_dark', step=SEG)
        ys = _split(ya, yb)
        for k in range(len(ys) - 1):
            y0, y1 = ys[k], ys[k + 1]
            M.tube(np.array([(sx * (HW - 0.14), y0, Pf.z(y0) + 1.75), (sx * (HW - 0.14), y1, Pf.z(y1) + 1.75)]), 0.07, 8, 'nc_metal_rust', tile=(2.0, 1.0), caps=False)
    # ceiling ribs every 8 m
    nr = max(1, int(round(arc / 8.0)))
    for k in range(nr):
        y = ya + (k + 0.5) * L / nr
        M.box((-HW, y - 0.16, zc(y) - 0.28), (HW, y + 0.16, zc(y)), 'nc_concrete_dark', tile=(3, 3), skip=('+z',))
    # luminaires: two LED tubes + warm accent, regular spacing across the chunk boundaries
    nl = max(1, int(round(arc / 6.2)))
    for k in range(nl):
        y = ya + (k + 0.5) * L / nl
        for sx in (-1, 1):
            P.bar(M, (sx * 3.2, y - 1.9, Pf.z(y - 1.9) + H - 0.09), (sx * 3.2, y + 1.9, Pf.z(y + 1.9) + H - 0.09), 0.14, 'nc_strip_white', emis=1.0)
            M.light((sx * 3.2, y, zc(y) - 0.4), P.COOL, 0.95, 10.5, n=(0, 0, -1))
        if k % 2 == 0:
            M.light((0, y, zc(y) - 0.6), P.WARMW, 0.35, 9.0)
    # jet fans
    if variant in (1, 2):
        for sx in (-1, 1):
            xf = sx * 4.6
            y = 0.0
            M.tube(np.array([(xf, y - 1.5, Pf.z(y - 1.5) + H - 0.72), (xf, y + 1.5, Pf.z(y + 1.5) + H - 0.72)]), 0.44, 12, 'nc_metal_light', tile=(2.0, 1.0), caps=True)
            M.tube(np.array([(xf, y - 1.62, Pf.z(y - 1.62) + H - 0.72), (xf, y - 1.5, Pf.z(y - 1.5) + H - 0.72)]), 0.40, 12, 'nc_metal_dark', tile=(1.0, 1.0), caps=True)
            for yy in (-0.8, 0.8):
                M.box((xf - 0.07, y + yy - 0.07, Pf.z(y + yy) + H - 0.35), (xf + 0.07, y + yy + 0.07, Pf.z(y + yy) + H), 'nc_metal_dark', tile=(1, 1))
            M.light((xf, y - 2.0, zc(y) - 1.0), P.COOL, 0.3, 6.0)
    # emergency niches: SOS post (red), exit sign (green), extinguisher cabinet
    if variant in (0, 2):
        for (sx, y) in ((-1, ya + 0.27 * L), (1, ya + 0.73 * L)):
            r = float(Pf.z(y))
            _wall_box(M, sx, 0.16, y - 0.38, y + 0.38, r + 1.15, r + 1.95, 'nc_light_red', emis=0.85)
            _wall_box(M, sx, 0.16, y - 0.55, y + 0.55, r + 2.45, r + 2.78, 'nc_light_green', emis=1.0)
            _wall_box(M, sx, 0.21, y + 0.75, y + 1.05, r + 0.95, r + 1.55, 'nc_metal_dark')
            M.light((sx * (HW - 0.8), y, r + 1.6), (1.0, 0.1, 0.06), 0.55, 6.0, n=(-sx, 0, 0))
            M.light((sx * (HW - 0.8), y, r + 2.6), (0.15, 1.0, 0.35), 0.5, 6.0, n=(-sx, 0, 0))
    # lane control signals above the lanes
    if variant >= 1:
        y = L * 0.5 - 0.5 if variant == 1 else -L * 0.5 + 8.0
        for i, x in enumerate(LANES):
            amber = (variant == 2 and i == 3)
            M.box((x - 0.46, y - 0.07, zc(y) - 0.92), (x + 0.46, y + 0.07, zc(y) - 0.08), 'nc_metal_dark', tile=(1, 1))
            M.box((x - 0.36, y - 0.09, zc(y) - 0.82), (x + 0.36, y + 0.09, zc(y) - 0.18), 'nc_light_amber' if amber else 'nc_light_green', tile=(1, 1), emis=1.0)
            M.light((x, y - 1.0, zc(y) - 0.6), (1.0, 0.55, 0.05) if amber else (0.2, 1.0, 0.4), 0.45, 7.0, n=(0, -1, 0))
    # ------------------------------------------------------------------ collision: floor, walls, roof
    _prism(C, -HW, HW, ya, yb, Pf, -TW, 0.0)
    _prism(C, -HW - TW, -HW, ya, yb, Pf, -TW, H + TR)
    _prism(C, HW, HW + TW, ya, yb, Pf, -TW, H + TR)
    _prism(C, -HW - TW, HW + TW, ya, yb, Pf, H, H + TR)
    lo = min(Pf.z(ya), Pf.z(yb))
    hi = max(Pf.z(ya), Pf.z(yb))
    return M, C, dict(kind='tunnel', w=2 * (HW + TW), d=float(L), h=float(hi - lo + H + TR), dist=300.0, amb=0.34)


# ---------------------------------------------------------------------------------------------
def tunnel_open(L, pt=1.2, g=0.10):
    """open cut ramp: street level at -y, the road falls with grade g towards +y over L metres, then the portal header (pt m
    deep) closes the cut.  Local origin: middle of the (L + pt) long ramp, local z = 0 = road level there."""
    M, C = Mesh(), Col()
    Lt = L + pt
    s = -g
    Pf = Prof(s, -Lt / 2)
    ya, yb = -Lt / 2, Lt / 2
    yh = yb - pt                                     # front face of the header
    zs = float(Pf.z(ya))                             # street level (local z)
    _floor(M, Pf, ya, yb)
    # trench walls: concrete up to street level (the 0.16 m kerb face belongs to the neighbouring ground cell)
    _walls(M, Pf, ya, yh, 'nc_concrete', ztop=zs, rows=3, tile=(4.0, 4.0))
    # under the header: tiled walls, soffit
    _walls(M, Pf, yh, yb, 'nc_tunnel_tile', rows=2)
    _ceiling(M, Pf, yh, yb, 'nc_concrete_dark')
    # header block: front face (faces -y), underside is the soffit above; the top is the street surface of the ground cell
    zl = float(Pf.z(yh)) + H
    M.quads(np.array([[(-HW, yh, zl), (HW, yh, zl), (HW, yh, zs), (-HW, yh, zs)]]), 'nc_concrete', np.array([[(-HW / 4, -zl / 4), (HW / 4, -zl / 4), (HW / 4, -zs / 4), (-HW / 4, -zs / 4)]]))
    # portal sign on the header front face
    z0, z1 = zl + 0.28, min(zs - 0.12, zl + 1.28)
    P.face(M, (-4.2, yh - 0.02), (4.2, yh - 0.02), z0, z1, 'nc_tunnel_sign', (0.0, 0.0, 1.0, 1.0), emis=0.85)
    M.box((-HW, yh - 0.12, zl), (HW, yh, zl + 0.2), 'nc_metal_dark', tile=(2, 2), skip=('+y', '-z'))
    M.box((-HW, yh - 0.05, zl - 0.04), (HW, yh, zl + 0.06), 'nc_strip_cyan', tile=(1, 1), emis=1.0, skip=('+y', '+z'))
    M.light((0, yh - 3.0, zl + 0.8), (0.55, 1.0, 0.7), 0.9, 14.0, n=(0, 1, 0))
    # LED guide lines along both trench walls
    for sx in (-1, 1):
        _bars(M, Pf, sx * (HW - 0.05), ya + 6.0, yh, 0.95, 0.08, 'nc_strip_cyan', emis=1.0)
    # lights in the cut (sodium from above, cyan wall wash)
    for y in np.arange(ya + 8.0, yh, 12.0):
        M.light((0, y, zs + 3.0), P.SODIUM, 0.75, 17.0)
        for sx in (-1, 1):
            M.light((sx * (HW - 0.6), y, Pf.z(y) + 1.4), P.CYA, 0.5, 9.0, n=(-sx, 0, 0))
    for y in np.arange(yh + 0.6, yb, 1.2):
        M.light((0, y, Pf.z(y) + H - 0.4), P.SODIUM, 0.9, 10.0, n=(0, 0, -1))
    # pavement-edge railings (the pavement is at street level + kerb)
    zp = zs + CURB
    ra, rb = ya + 4.0, yh + 0.2
    for sx in (-1, 1):
        x = sx * (HW + 0.45)
        for y in np.arange(ra, rb, 2.0):
            M.box((x - 0.035, y - 0.035, zp), (x + 0.035, y + 0.035, zp + 1.1), 'nc_metal_dark', tile=(1, 1))
        for zr_ in (1.05, 0.55):
            seg = np.linspace(ra, rb, int(round((rb - ra) / 4.0)) + 1)
            for k in range(len(seg) - 1):
                P.bar(M, (x, seg[k], zp + zr_), (x, seg[k + 1], zp + zr_), 0.06, 'nc_metal_light', tile=(2, 1))
        C.box((x - 0.08, ra, zp), (x + 0.08, rb, zp + 1.1))
    # sign gantry over the approach
    yg = ya + 14.0
    for sx in (-1, 1):
        M.box((sx * (HW + 2.4) - 0.22, yg - 0.22, zp), (sx * (HW + 2.4) + 0.22, yg + 0.22, zp + 7.4), 'nc_steel', tile=(1.0, 3.0))
        C.box((sx * (HW + 2.4) - 0.22, yg - 0.22, zp), (sx * (HW + 2.4) + 0.22, yg + 0.22, zp + 7.4))
    M.box((-(HW + 2.4), yg - 0.3, zp + 7.0), (HW + 2.4, yg + 0.3, zp + 7.5), 'nc_steel', tile=(3.0, 1.0))
    for xc in (-4.6, 4.6):
        P.face(M, (xc - 3.3, yg - 0.32), (xc + 3.3, yg - 0.32), zp + 5.15, zp + 6.95, 'nc_tunnel_sign', (0.0, 0.0, 1.0, 1.0), emis=0.85)
        M.box((xc - 3.4, yg - 0.3, zp + 5.05), (xc + 3.4, yg + 0.3, zp + 7.0), 'nc_metal_dark', tile=(2, 2), skip=('-y',))
        M.light((xc, yg - 3.0, zp + 6.0), (0.55, 1.0, 0.7), 0.8, 13.0, n=(0, 1, 0))
    # lane signals under the header
    yl = yh + 0.6
    for x in LANES:
        M.box((x - 0.42, yl - 0.07, Pf.z(yl) + H - 0.86), (x + 0.42, yl + 0.07, Pf.z(yl) + H - 0.04), 'nc_metal_dark', tile=(1, 1))
        M.box((x - 0.34, yl - 0.09, Pf.z(yl) + H - 0.78), (x + 0.34, yl + 0.09, Pf.z(yl) + H - 0.12), 'nc_light_green', tile=(1, 1), emis=1.0)
    # ------------------------------------------------------------------ collision
    _prism(C, -HW, HW, ya, yb, Pf, -TW, 0.0)
    zlow = float(Pf.z(yb)) - TW
    for sx in (-1, 1):
        a, b = (-HW - TW, -HW) if sx < 0 else (HW, HW + TW)
        C.box((a, ya, zlow), (b, yb, zs))
    C.prisms.append(np.array([(-HW, yh, zl), (HW, yh, zl), (HW, yb, float(Pf.z(yb)) + H), (-HW, yb, float(Pf.z(yb)) + H),
                              (-HW, yh, zs), (HW, yh, zs), (HW, yb, zs), (-HW, yb, zs)], float))
    return M, C, dict(kind='tunnel', w=2 * (HW + 3.0), d=float(Lt), h=float(zs - Pf.z(yb) + 7.5), dist=420.0, amb=1.0)
