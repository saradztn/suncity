# Created by: Arena.ai Agent Mode (AI) - NightCity MTA:SA asset pipeline
# -----------------------------------------------------------------------------
# rail.py - the rideable Night City Metro: rolling stock, guideway and stations.
#           The line runs east-west at y = 55 over the river's north edge, rail
#           top at z = 13.  Models are authored with the origin ON the rail top.
#           Builders return (M, C, meta(kind='metro'|'rail', dist, amb)).
# -----------------------------------------------------------------------------
import numpy as np

from .mb import Mesh, Col
from .texsign import metro_sign_uv

MAT = 'nc_metal_dark'
MAT2 = 'nc_metal_light'
CON = 'nc_concrete_dark'
GL = 'nc_glass_a'
RED = 'nc_light_red'
WARM = 'nc_light_warm'
SIGN = 'nc_metro_sign'
ML = 'nc_metal_light'

CAR_L = 25.0            # body length (nose to nose)
CAR_W = 2.9             # body half-width is W2 below
W2 = 1.45
FLOOR_Z = 1.05          # interior floor
SKIRT_Z = 1.62          # red skirt stripe centre
WIN_TOP = 3.42
ROOF_Z = 3.98
DOOR_W = 1.46
DOOR_X = (-8.05, -2.68, 2.68, 8.05)


def _uv_rect(rect):
    u0, v0, u1, v1 = rect
    return ((u0, v0), (u1, v0), (u1, v1), (u0, v1))


def _logo_uv():
    return _uv_rect(metro_sign_uv(0))


def _sign_uv(i):
    # atlas cells 1..3 -> MARKET / UNION / DOCKS (cell 0 is the logo)
    return _uv_rect(metro_sign_uv(i + 1))


def _mirror(uv):
    (a, b), (c, d), (e, f), (g, h) = uv
    return ((c, b), (a, b), (a, h), (c, h))


def _plate(M, x0, y0, z0, x1, y1, z1, mat, emis=0.0, tile=1.0):
    M.box((x0, y0, z0), (x1, y1, z1), mat, tile=(tile, tile), emis=emis)


def _board(M, x, y0, z0, y1, z1, uv, emis=1.2):
    """sign board on a plane x = const, facing +x.  Seen from +x the +y axis is screen-left,
    so the u order is flipped here to keep the text readable."""
    P = np.array([[[(x, y0, z0), (x, y1, z0), (x, y1, z1), (x, y0, z1)]]], np.float32)
    M.quads(P, SIGN, np.array([[uv[1], uv[0], uv[3], uv[2]]], np.float32), emis)


def _nose_board(M, sx, sy, x_near, x_far, z0, z1):
    """destination board on the nose side; face normal = sy (u grows with x seen from +y)."""
    P = [[(x_far - sx * 0.42, sy * (W2 - 0.34), z0), (x_near + sx * 0.35, sy * (W2 - 0.34), z0),
          (x_near + sx * 0.35, sy * (W2 - 0.34), z1), (x_far - sx * 0.42, sy * (W2 - 0.34), z1)]]
    uv = _logo_uv()
    if sy < 0:
        uv = _mirror(uv)
    M.quads(np.array([P], np.float32), SIGN, np.array([[uv[0], uv[1], uv[2], uv[3]]], np.float32), 1.45)


def _tunnel_profile(r=5.8, zc=1.9, fl=-1.25, n_arc=14):
    """arch cross-section (y, z): left floor -> left springing -> over the top -> right floor."""
    pts = [(-r, fl), (-r, zc)]
    for k in range(n_arc + 1):
        th = np.pi - k * np.pi / n_arc
        pts.append((r * np.cos(th), zc + r * np.sin(th)))
    pts.append((r, fl))
    return np.array(pts, np.float64)


def _shell(M, prof, x0, x1, mat, tile=(4.0, 2.0), outward=False, emis=0.0):
    """extrude the (y,z) profile along x with quads CCW seen from inside (or outside)."""
    K = len(prof)
    seg = np.linalg.norm(np.diff(prof, axis=0), axis=1)
    v = np.concatenate([[0.0], np.cumsum(seg)]) / tile[1]
    P = np.zeros((K - 1, 4, 3), np.float64)
    UV = np.zeros((K - 1, 4, 2), np.float64)
    for i in range(K - 1):
        (ya, za), (yb, zb) = prof[i], prof[i + 1]
        if not outward:
            P[i] = [(x0, ya, za), (x0, yb, zb), (x1, yb, zb), (x1, ya, za)]
        else:
            P[i] = [(x0, yb, zb), (x0, ya, za), (x1, ya, za), (x1, yb, zb)]
        UV[i] = [(x0 / tile[0], v[i]), (x0 / tile[0], v[i + 1]), (x1 / tile[0], v[i + 1]), (x1 / tile[0], v[i])]
    M.quads(P, mat, UV, emis)


def metro_door():
    """sliding door leaf (1.35 x 2.05), origin at the leaf centre (the runtime slides it)."""
    M, C = Mesh(), Col()
    w, h = 1.35, 2.30
    x0, x1 = -w / 2, w / 2
    M.box((x0, -0.03, 0.0), (x1, 0.03, h), MAT2, tile=(0.9, 1.4), emis=0.06)
    M.box((x0, -0.035, 0.32), (x1, 0.035, 0.46), RED, tile=(0.9, 0.2), emis=0.30)     # red stripe
    # window (a little proud of the leaf so it reads as glass)
    M.box((x0 + 0.13, -0.05, 0.78), (x1 - 0.13, 0.05, 1.92), GL, tile=(1.0, 1.2), emis=0.22)
    M.box((x0 + 0.08, -0.02, 1.88), (x1 - 0.08, 0.02, 1.99), MAT, tile=(1.0, 0.15))
    C.box((x0, -0.04, 0.0), (x1, 0.04, h))
    return M, C, dict(kind='metro', dist=900.0, amb=1.0)


def metro():
    """one 25 m metro car: silver body, red skirt + roof stripe, lit window band,
    open door bays at DOOR_X (the runtime attaches the sliding leaves), twin noses
    with the NIGHT CITY METRO board and a full interior (benches, poles, handrails)."""
    M, C = Mesh(), Col()
    x0, x1 = -CAR_L / 2, CAR_L / 2
    nose = 1.4
    body_a, body_b = x0 + nose, x1 - nose

    # ---------------------------------------------------------------- chassis
    M.box((x0 + 0.2, -W2 + 0.10, 0.28), (x1 - 0.2, W2 - 0.10, FLOOR_Z + 0.06), MAT, tile=(2.2, 1.2))
    for sy in (-1.0, 1.0):                                 # red skirt stripes
        M.box((x0 + 0.25, sy * (W2 - 0.17), SKIRT_Z - 0.11), (x1 - 0.25, sy * (W2 + 0.01), SKIRT_Z + 0.11),
              RED, tile=(2.2, 0.22), emis=0.22)
    M.box((x0 + 0.35, -W2 + 0.30, 3.62), (x1 - 0.35, W2 - 0.30, 3.78), RED, tile=(2.0, 0.22), emis=0.16)

    # ------------------------------------------------------------- body shell
    for sy in (-1.0, 1.0):
        yl, yr = sy * W2, sy * (W2 - 0.16)
        (y0_, y1_) = (yl, yr) if sy > 0 else (yr, yl)
        for dx in DOOR_X:                                  # pillars between the bays
            _plate(M, dx - DOOR_W / 2 - 0.34, y0_, 0.30, dx - DOOR_W / 2, y1_, 3.86, MAT2, 0.06, 0.8)
            _plate(M, dx + DOOR_W / 2, y0_, 0.30, dx + DOOR_W / 2 + 0.34, y1_, 3.86, MAT2, 0.06, 0.8)
        # continuous header above the bays
        _plate(M, body_a, y0_, 3.34, body_b, y0_ + (yr - yl), 3.86, MAT2, 0.06, 1.2)
        # solid sill + lit window band between the door bays (the bays stay open for the leaves)
        gaps = [(-1e9, DOOR_X[0]), (DOOR_X[0], DOOR_X[1]), (DOOR_X[1], DOOR_X[2]), (DOOR_X[2], DOOR_X[3]), (DOOR_X[3], 1e9)]
        for (ga, gb) in gaps:
            xa = max(ga + DOOR_W / 2, body_a)
            xb = min(gb - DOOR_W / 2, body_b)
            if xb - xa < 0.2:
                continue
            _plate(M, xa, y0_, 0.30, xb, y0_ + (yr - yl), 1.68, MAT2, 0.06, 1.2)
            _plate(M, xa, y0_, 1.68, xb, y0_ + (yr - yl), 3.34, GL, 0.34, 1.4)
            # window mullions
            n = max(1, int(round((xb - xa) / 1.55)))
            for k in range(1, n):
                xm = xa + (xb - xa) * k / n
                _plate(M, xm - 0.045, y0_, 1.68, xm + 0.045, y0_ + (yr - yl), 3.34, MAT, 0.02, 0.4)
    # roof
    M.box((x0 + 0.30, -W2 + 0.22, 3.86), (x1 - 0.30, W2 - 0.22, ROOF_Z), MAT2, tile=(2.2, 0.9))
    M.box((x0 + 1.2, -0.95, ROOF_Z), (x1 - 1.2, 0.95, ROOF_Z + 0.13), MAT, tile=(2.0, 0.8))

    # ------------------------------------------------------------------ noses
    for sx in (-1.0, 1.0):
        xb = x0 if sx < 0 else x1                       # far end
        xs = x0 + nose if sx < 0 else x1 - nose         # body joint
        inset = 0.30
        # nose shell steps
        xa_, xb_ = sorted((xb - sx * inset, xs + sx * 0.35))
        _plate(M, xa_, -W2 + inset + 0.12, 0.30, xb_, W2 - inset - 0.12, 3.86, MAT2, 0.06, 0.8)
        xa2, xb2 = sorted((xb - sx * inset * 2.1, xs + sx * 0.15))
        _plate(M, xa2, -W2 + inset * 2.1 + 0.12, 0.30, xb2, W2 - inset * 2.1 - 0.12, 3.86, MAT2, 0.06, 0.8)
        # red nose stripe + dark visor band
        xa3, xb3 = sorted((xb - sx * inset * 2.1, xs + sx * 0.28))
        _plate(M, xa3, -W2 + inset * 1.6, SKIRT_Z - 0.11, xb3, W2 - inset * 1.6, SKIRT_Z + 0.11, RED, 0.24, 0.3)
        _plate(M, xa3, -W2 + inset * 1.9, 2.86, xb3, W2 - inset * 1.9, 3.24, MAT, 0.04, 0.6)
        # headlights
        for sy in (-1.0, 1.0):
            M.box((xb - sx * 0.34, sy * (W2 - inset * 1.6) - 0.16, 2.38), (xb - sx * 0.02, sy * (W2 - inset * 1.6) + 0.16, 2.62),
                  WARM, tile=(0.3, 0.3), emis=1.1)
        # roof cap
        xa4, xb4 = sorted((xb - sx * inset, xs + sx * 0.55))
        M.box((xa4, -W2 + inset, 3.86), (xb4, W2 - inset, ROOF_Z + 0.06), MAT2, tile=(1.2, 0.9))
        _nose_board(M, sx, 1.0, xs, xb, 3.18, 3.72)
        _nose_board(M, sx, -1.0, xs, xb, 3.18, 3.72)

    # --------------------------------------------------------------- interior
    M.box((-body_a + 2.0, -W2 + 0.16, FLOOR_Z - 0.06), (body_b - 2.0, W2 - 0.16, FLOOR_Z), MAT2, tile=(1.6, 1.2))
    M.box((-body_a + 2.2, -W2 + 0.20, FLOOR_Z - 0.075), (body_b - 2.2, W2 - 0.20, FLOOR_Z - 0.06), RED, tile=(1.6, 1.2), emis=0.14)
    # ceiling light strips
    for sy in (-1.0, 1.0):
        M.box((-body_a + 1.2, sy * (W2 - 0.42) - 0.10, 3.58), (body_b - 1.2, sy * (W2 - 0.42) + 0.10, 3.66),
              WARM, tile=(2.0, 0.16), emis=1.15)
    # side benches (long, over the wheel bays)
    for sy in (-1.0, 1.0):
        for (ba, bb) in ((-body_a + 2.2, DOOR_X[1] - 0.95), (DOOR_X[1] + 0.95, DOOR_X[2] - 0.95),
                         (DOOR_X[2] + 0.95, body_b - 2.2)):
            _plate(M, ba, sy * (W2 - 0.52), FLOOR_Z, bb, sy * (W2 - 0.14), FLOOR_Z + 0.44, RED, 0.16, 0.7)
            _plate(M, ba, sy * (W2 - 0.20), FLOOR_Z + 0.44, bb, sy * (W2 - 0.13), FLOOR_Z + 1.06, MAT2, 0.04, 0.7)
    # grab poles + handrails
    for px in (-6.36, -0.0, 6.36):
        M.cyl((px, 0.0), 0.035, FLOOR_Z, 3.58, 8, ML, tile=(0.4, 1.2), smooth=True)
    for sy in (-1.0, 1.0):
        _plate(M, -body_a + 1.2, sy * (W2 - 0.38) - 0.03, 3.42, body_b - 1.2, sy * (W2 - 0.38) + 0.03, 3.48,
               ML, 0.30, 1.2)
    # end walls (leaving the nose doors open)
    for sx in (-1.0, 1.0):
        xe = -body_a + 0.06 if sx < 0 else body_b - 0.06
        _plate(M, xe, -W2 + 0.16, FLOOR_Z, xe + sx * 0.12, W2 - 0.16, 3.58, MAT2, 0.05, 0.9)

    # --------------------------------------------------------------- bogies
    for bx in (-8.6, 8.6):
        M.box((bx - 1.8, -W2 + 0.35, 0.10), (bx + 1.8, W2 - 0.35, 0.62), MAT, tile=(1.4, 0.8))
        for sy in (-1.0, 1.0):
            for dx in (-1.15, 1.15):
                M.box((bx + dx - 0.52, sy * (W2 - 0.52), 0.06), (bx + dx + 0.52, sy * (W2 - 0.22), 0.58), MAT,
                      tile=(0.8, 0.6))
    # lights on the underframe
    for lx in (-11.2, -5.6, 0.0, 5.6, 11.2):
        M.light((lx, 0.0, 1.25), (1.0, 0.88, 0.70), 0.55, 10.0)

    C.box((x0, -W2, 0.30), (x1, W2, ROOF_Z))
    C.box((x0 + 0.4, -W2 + 0.3, 0.0), (x1 - 0.4, W2 - 0.3, 0.35))
    return M, C, dict(kind='metro', dist=1600.0, amb=1.0)


def rail_deck():
    """12 m guideway deck segment (origin at rail-top level)."""
    M, C = Mesh(), Col()
    M.box((-6.0, -3.9, -1.25), (6.0, 3.9, -0.02), MAT, tile=(3.0, 2.0))
    M.box((-6.0, -3.95, -1.35), (6.0, 3.95, -1.22), CON, tile=(3.0, 2.0))
    for sy in (-1.0, 1.0):
        M.box((-6.0, sy * (3.95) - 0.16, -0.28), (6.0, sy * (3.95) + 0.16, -0.02), RED, tile=(3.0, 0.3), emis=0.12)
        M.box((-6.0, sy * (3.9) - 0.30, -0.02), (6.0, sy * (3.9) + 0.30, 0.04), MAT2, tile=(3.0, 0.5))
        # railing
        for rx in np.linspace(-5.4, 5.4, 6):
            M.box((rx - 0.05, sy * 4.12 - 0.05, 0.02), (rx + 0.05, sy * 4.12 + 0.05, 1.02), RED, tile=(0.2, 0.6), emis=0.10)
        M.box((-6.0, sy * 4.12 - 0.055, 0.94), (6.0, sy * 4.12 + 0.055, 1.05), RED, tile=(3.0, 0.16), emis=0.12)
        M.box((-6.0, sy * 4.12 - 0.045, 0.52), (6.0, sy * 4.12 + 0.045, 0.60), RED, tile=(3.0, 0.12), emis=0.10)
    # running rails + power rail
    for sy in (-1.0, 1.0):
        M.box((-6.0, sy * 1.10 - 0.07, -0.02), (6.0, sy * 1.10 + 0.07, 0.10), MAT2, tile=(3.0, 0.2))
        M.box((-6.0, sy * 0.72 - 0.05, -0.02), (6.0, sy * 0.72 + 0.05, 0.05), MAT, tile=(3.0, 0.2))
    C.box((-6.0, -4.15, -1.35), (6.0, 4.15, -0.02))
    for sy in (-1.0, 1.0):
        C.box((-6.0, sy * 4.12 - 0.08, -0.02), (6.0, sy * 4.12 + 0.08, 1.05))
    return M, C, dict(kind='rail', dist=1800.0, amb=1.0)


def rail_pylon():
    """support pier (placed at z = -13, the deck underside)."""
    M, C = Mesh(), Col()
    M.box((-2.4, -1.6, -1.15), (2.4, 1.6, -0.65), CON, tile=(2.0, 1.6))
    M.box((-1.35, -1.05, -11.8), (1.35, 1.05, -1.15), CON, tile=(1.6, 4.0))
    M.box((-2.1, -1.35, -13.0), (2.1, 1.35, -11.8), CON, tile=(1.8, 1.2))
    M.box((-1.5, -1.15, -12.0), (1.5, 1.15, -11.8), RED, tile=(1.6, 0.25), emis=0.12)
    C.box((-2.2, -1.5, -13.0), (2.2, 1.5, -0.65))
    return M, C, dict(kind='rail', dist=1800.0, amb=1.0)


def rail_tube():
    """12 m tunnel shell: horseshoe arch, tiled lining, wall light strips, service walkways."""
    M, C = Mesh(), Col()
    prof = _tunnel_profile(5.8, 1.9, -1.25)
    _shell(M, prof, -6.0, 6.0, CON, tile=(4.0, 2.2), outward=False, emis=0.02)
    # wall light strips (emissive, facing the track)
    for sy in (-1.0, 1.0):
        M.box((-6.0, sy * 5.72 - 0.10, -0.62), (6.0, sy * 5.72 + 0.10, 1.72), WARM, tile=(4.0, 1.2), emis=1.05)
    # crown light strip
    M.box((-6.0, -1.15, 7.52), (6.0, 1.15, 7.62), WARM, tile=(4.0, 1.0), emis=0.95)
    # service walkways + cable channel
    for sy in (-1.0, 1.0):
        w0, w1 = sorted((sy * 5.75, sy * 4.0))
        M.box((-6.0, w0, -1.25), (6.0, w1, -0.45), MAT, tile=(4.0, 1.2))
        M.box((-6.0, sy * 4.05 - 0.12, -1.25), (6.0, sy * 4.05 + 0.12, -0.45), MAT2, tile=(4.0, 0.6), emis=0.04)
    M.box((-6.0, -5.8, -1.28), (6.0, 5.8, -1.24), MAT, tile=(4.0, 3.0))
    # shell collisions: side walls + crown
    for sy in (-1.0, 1.0):
        C.box((-6.0, sy * 5.8 - 0.35, -1.3), (6.0, sy * 5.8 + 0.35, 2.0))
    C.box((-6.0, -5.8, 6.6), (6.0, 5.8, 7.8))
    return M, C, dict(kind='rail', dist=2200.0, amb=1.0)


def rail_portal():
    """tunnel portal: concrete collar ring around the arch mouth, spandrel face,
    the NIGHT CITY METRO board on a pediment above the arch, red signal heads."""
    M, C = Mesh(), Col()
    prof_in = _tunnel_profile(5.8, 1.9, -1.25)
    prof_out = _tunnel_profile(6.5, 1.9, -1.35)
    # spandrel face (annulus between mouth and collar), seen from +x
    K = len(prof_in)
    P = np.zeros((K - 1, 4, 3), np.float64)
    UV = np.zeros((K - 1, 4, 2), np.float64)
    for i in range(K - 1):
        (ya, za), (yb, zb) = prof_in[i], prof_in[i + 1]
        (Ya, Za), (Yb, Zb) = prof_out[i], prof_out[i + 1]
        P[i] = [(0.02, ya, za), (0.02, yb, zb), (0.02, Yb, Zb), (0.02, Ya, Za)]
        UV[i] = [(ya * 0.4, za * 0.4), (yb * 0.4, zb * 0.4), (Yb * 0.4, Zb * 0.4), (Ya * 0.4, Za * 0.4)]
    M.quads(P, CON, UV, 0.03)
    # collar shell (outward facing) + its end rim
    _shell(M, prof_out, -0.02, 1.45, CON, tile=(2.2, 2.4), outward=True, emis=0.02)
    K2 = len(prof_out)
    P2 = np.zeros((K2 - 1, 4, 3), np.float64)
    for i in range(K2 - 1):
        (ya, za), (yb, zb) = prof_out[i], prof_out[i + 1]
        P2[i] = [(1.45, yb, zb), (1.45, ya, za), (1.32, ya, za), (1.32, yb, zb)]
    M.quads(P2, CON, np.zeros((K2 - 1, 4, 2)) + 0.4, 0.03)
    # pediment + the sign board above the arch
    M.box((-0.25, -5.05, 8.35), (1.75, 5.05, 9.85), CON, tile=(2.0, 1.4))
    M.box((-0.45, -5.35, 9.85), (1.95, 5.35, 10.15), CON, tile=(2.2, 0.5))
    _board(M, 1.78, -4.55, 8.55, 4.55, 9.62, _logo_uv(), 1.35)
    # red signal heads on the collar
    for sy in (-1.0, 1.0):
        M.box((1.42, sy * 5.55 - 0.42, 2.05), (1.62, sy * 5.55 + 0.42, 3.05), MAT, tile=(0.4, 0.6))
        M.cyl((1.68, sy * 5.55), 0.30, 2.55, 2.55, 12, RED, tile=(0.6, 0.6), smooth=True, rx=0.16, ry=0.30)
        M.cyl((1.68, sy * 5.55), 0.22, 2.55, 2.55, 12, RED, tile=(0.5, 0.5), smooth=True, rx=0.10, ry=0.22, emis=1.2)
    # wing walls
    for sy in (-1.0, 1.0):
        M.box((-0.15, sy * 6.5 - 0.9, -1.35), (1.55, sy * 6.5 + 0.9, 3.35), CON, tile=(1.6, 2.2))
        M.box((-0.15, sy * 6.5 - 1.05, 3.35), (1.55, sy * 6.5 + 1.05, 3.75), CON, tile=(1.6, 0.6))
    C.box((-0.15, -7.4, -1.35), (1.6, -5.6, 3.8))
    C.box((-0.15, 5.6, -1.35), (1.6, 7.4, 3.8))
    C.box((-0.3, -5.4, 8.3), (1.8, 5.4, 10.2))
    return M, C, dict(kind='rail', dist=2200.0, amb=1.0)


def rail_station(variant=0):
    """80 m station (local y = 0 on the track, origin on the rail top): twin platforms with
    level boarding at z = 0.98, canopy on slim columns, red railings, name totems and
    stairs down to the street on the north (land) side.  variant 0/1/2 = MARKET/UNION/DOCKS."""
    M, C = Mesh(), Col()
    L = 80.0
    idx = variant % 3

    # ------------------------------------------------------------ platforms
    for side in (-1.0, 1.0):
        ya, yb = sorted((side * 4.6, side * 12.4))
        M.box((-L / 2, ya, -0.45), (L / 2, yb, 0.92), CON, tile=(6.0, 2.6))
        M.box((-L / 2, ya, 0.92), (L / 2, yb, 0.98), MAT2, tile=(6.0, 2.6), emis=0.05)
        # yellow warning strip along the boarding edge
        e0, e1 = sorted((side * 4.6, side * 5.15))
        M.box((-L / 2 + 1.0, e0, 0.985), (L / 2 - 1.0, e1, 1.02), WARM, tile=(6.0, 0.4), emis=0.55)
        # red railing along the back edge
        b0, b1 = sorted((side * 12.05, side * 12.4))
        for rx in np.linspace(-L / 2 + 2.0, L / 2 - 2.0, 11):
            M.box((rx - 0.07, b0, 0.98), (rx + 0.07, b1, 2.18), RED, tile=(0.3, 1.0), emis=0.10)
        M.box((-L / 2 + 1.0, b0, 2.08), (L / 2 - 1.0, b1, 2.22), RED, tile=(6.0, 0.2), emis=0.12)
        M.box((-L / 2 + 1.0, b0, 1.52), (L / 2 - 1.0, b1, 1.62), RED, tile=(6.0, 0.15), emis=0.10)
        # canopy on slim columns
        cy = side * 8.5
        for cx in np.linspace(-L / 2 + 6.0, L / 2 - 6.0, 6):
            M.cyl((cx, cy), 0.15, 0.98, 3.86, 8, MAT2, tile=(0.6, 1.6), smooth=True)
        M.box((-L / 2 + 3.0, ya + 0.4, 3.86), (L / 2 - 3.0, yb - 0.4, 4.12), MAT2, tile=(6.0, 1.8))
        M.box((-L / 2 + 3.0, ya + 0.4, 4.12), (L / 2 - 3.0, yb - 0.4, 4.22), RED, tile=(6.0, 1.8), emis=0.12)
        # canopy underside lights
        for cx in np.linspace(-L / 2 + 10.0, L / 2 - 10.0, 5):
            M.box((cx - 1.4, cy - 0.22, 3.80), (cx + 1.4, cy + 0.22, 3.86), WARM, tile=(1.6, 0.3), emis=1.15)
        # benches
        for bx in (-L / 2 + 16.0, -4.0, L / 2 - 16.0):
            M.box((bx - 1.7, cy - 0.42, 1.10), (bx + 1.7, cy + 0.42, 1.42), RED, tile=(1.2, 0.6), emis=0.10)
            M.box((bx - 1.7, cy - 0.42, 1.42), (bx + 1.7, cy - 0.34, 1.98), MAT2, tile=(1.2, 0.5), emis=0.04)
        # platform support columns down to the ground / river bed
        for cx in np.linspace(-L / 2 + 12.0, L / 2 - 12.0, 5):
            M.cyl((cx, cy), 0.85, -12.9, -0.45, 10, CON, tile=(1.4, 4.0), smooth=True)
            M.cyl((cx, cy), 1.15, -13.0, -12.2, 10, CON, tile=(1.6, 0.6), smooth=True)

    # --------------------------------------- stairs (land side only) + name totems
    for side in (1.0,):
        yc = side * 11.6
        for sx in (-1.0, 1.0):
            xst = sx * 40.5
            # stair run: 20 steps from platform z 0.98 down to z 0
            for k in range(20):
                z = 0.98 - (k + 1) * 0.049
                y0 = yc - side * 4.4 + side * k * 0.44
                y1 = y0 + side * 0.46
                a, b = sorted((y0, y1))
                M.box((xst - 3.2, a, z), (xst + 3.2, b, z + 0.055), CON, tile=(1.6, 0.4))
            # stringer walls + railing
            for sx2 in (-1.0, 1.0):
                M.box((xst + sx2 * 3.2 - 0.18, yc - side * 4.6, -0.05), (xst + sx2 * 3.2 + 0.18, yc + side * 4.6, 1.15),
                      CON, tile=(0.6, 1.6))
                M.box((xst + sx2 * 3.2 - 0.10, yc - side * 4.6, 1.15), (xst + sx2 * 3.2 + 0.10, yc + side * 4.6, 2.15),
                      RED, tile=(0.3, 1.2), emis=0.10)
            # totem with the station name
            ty = yc - side * 6.2
            M.cyl((xst, ty), 0.16, 0.0, 4.6, 8, MAT, tile=(0.6, 1.8), smooth=True)
            M.box((xst - 1.55, ty - 0.16, 3.15), (xst + 1.55, ty + 0.16, 4.42), MAT, tile=(1.4, 1.0))
            # sign face on the +x side of the totem box (visible along the platform)
            _board(M, xst + 1.58, ty - 1.25, 3.28, ty + 1.25, 4.30, _sign_uv(idx), 1.20)

    # station name plate on the outer platform walls (both sides)
    for side in (-1.0, 1.0):
        yf = side * 12.85
        uv = _sign_uv(idx)
        P = np.array([[[( -3.2, yf - side * 0.06, 1.35), (3.2, yf - side * 0.06, 1.35),
                        (3.2, yf - side * 0.06, 2.35), (-3.2, yf - side * 0.06, 2.35)]]], np.float32)
        uvar = np.array([[uv[0], uv[1], uv[2], uv[3]]], np.float32)
        M.quads(P, SIGN, uvar, 1.15)
    # platform-edge lights
    for side in (-1.0, 1.0):
        for lx in np.linspace(-L / 2 + 8.0, L / 2 - 8.0, 6):
            M.light((lx, side * 6.6, 3.2), (1.0, 0.86, 0.62), 0.75, 14.0)

    C.box((-L / 2, -12.6, -0.5), (L / 2, -4.4, 0.98))
    C.box((-L / 2, 4.4, -0.5), (L / 2, 12.6, 0.98))
    for sx in (-1.0, 1.0):
        xst = sx * 40.5
        C.box((xst - 3.4, 6.8, -0.2), (xst + 3.4, 16.4, 1.2))
    return M, C, dict(kind='rail', dist=2200.0, amb=1.0)


def rail_buffer():
    """track buffer stop at the east end."""
    M, C = Mesh(), Col()
    M.box((-1.2, -2.6, -0.02), (1.2, 2.6, 1.15), MAT, tile=(1.4, 1.6))
    M.box((-1.35, -2.75, 1.15), (1.35, 2.75, 1.45), RED, tile=(1.4, 0.4), emis=0.30)
    for sy in (-1.0, 1.0):
        M.box((-1.5, sy * 1.10 - 0.14, 0.10), (1.5, sy * 1.10 + 0.14, 0.62), MAT2, tile=(1.4, 0.3))
    M.cyl((0.0, 0.0), 0.42, 1.45, 1.75, 12, RED, tile=(0.8, 0.4), smooth=True, emis=0.8)
    C.box((-1.4, -2.8, -0.1), (1.4, 2.8, 1.5))
    return M, C, dict(kind='rail', dist=1200.0, amb=1.0)


def rail_signal():
    """trackside signal mast with red lamps."""
    M, C = Mesh(), Col()
    M.cyl((0.0, 0.0), 0.12, 0.0, 4.2, 8, MAT, tile=(0.5, 1.6), smooth=True)
    M.box((-0.35, -0.35, 4.2), (0.35, 0.35, 5.6), MAT, tile=(0.5, 0.8))
    for z in (4.55, 5.25):
        M.cyl((0.0, -0.38), 0.22, z, z, 10, RED, tile=(0.5, 0.5), smooth=True, rx=0.12, ry=0.22, emis=1.1)
    M.box((-0.55, -0.55, -0.02), (0.55, 0.55, 0.25), CON, tile=(0.6, 0.4))
    C.box((-0.3, -0.3, 0.0), (0.3, 0.3, 5.6))
    return M, C, dict(kind='rail', dist=1200.0, amb=1.0)
