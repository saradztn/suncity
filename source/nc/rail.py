# Created by: Arena.ai Agent Mode (AI) - NightCity MTA:SA asset pipeline
# -----------------------------------------------------------------------------
# rail.py - the Night City Metro infrastructure: guideway (concrete box-girder viaduct),
#           180 degree loop turns, support piers, a lit tunnel tube with an arched portal,
#           three stations and trackside signals.  The TRAIN itself is the vanilla GTA:SA
#           consist (models 538 / 570) - metro.lua creates and drives it, nothing is modelled
#           here.  All rail models are authored with the origin ON the rail top (placed z = 13).
#           Builders return (M, C, meta(kind='metro'|'rail', dist, amb)).
# -----------------------------------------------------------------------------
import numpy as np

from .mb import Mesh, Col
from .texsign import metro_sign_uv

MAT = 'nc_metal_dark'
MAT2 = 'nc_metal_light'
CON = 'nc_concrete_dark'
CONL = 'nc_concrete'
RED = 'nc_light_red'
WARM = 'nc_light_warm'
SIGN = 'nc_metro_sign'

DECK_HW = 3.45           # running-surface half width
DECK_TOP = -0.02         # deck surface below the rail top
GIRD_B = -2.55           # girder soffit
R = 25.0                 # loop turn radius (track centre line)


def _uv_rect(rect):
    u0, v0, u1, v1 = rect
    return ((u0, v0), (u1, v0), (u1, v1), (u0, v1))


def _logo_uv():
    return _uv_rect(metro_sign_uv(0))


def _sign_uv(i):
    # atlas cells 1..3 -> MARKET / UNION / DOCKS (cell 0 is the logo)
    return _uv_rect(metro_sign_uv(i + 1))


def _board(M, x, y0, z0, y1, z1, uv, emis=1.2):
    """sign board on a plane x = const, facing +x.  Seen from +x the +y axis is screen-left,
    so the u order is flipped here to keep the text readable."""
    P = np.array([[[(x, y0, z0), (x, y1, z0), (x, y1, z1), (x, y0, z1)]]], np.float32)
    M.quads(P, SIGN, np.array([[uv[1], uv[0], uv[3], uv[2]]], np.float32), emis)


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


# ---------------------------------------------------------------------------------------------
# guideway
# ---------------------------------------------------------------------------------------------
def _deck_chunk(M, C, L):
    """L metre box-girder deck centred on x = 0 (origin on the rail top).  All concrete and
    dark matte metal - no sky-reflecting light metal on the profile (it read as glowing white
    bands from the street)."""
    x0, x1 = -L / 2, L / 2
    # running surface + the two rails and the conductor rail
    M.box((x0, -DECK_HW, -0.30), (x1, DECK_HW, DECK_TOP), MAT, tile=(3.0, 2.0))
    for sy in (-1.0, 1.0):
        M.box((x0, sy * 1.10 - 0.07, DECK_TOP), (x1, sy * 1.10 + 0.07, 0.09), MAT2, tile=(3.0, 0.2))
        M.box((x0, sy * 0.72 - 0.05, DECK_TOP), (x1, sy * 0.72 + 0.05, 0.04), MAT, tile=(3.0, 0.2))
    # box girder: deep tapered concrete section
    M.box((x0, -DECK_HW, -1.25), (x1, DECK_HW, -0.30), CON, tile=(3.0, 1.2))
    M.box((x0, -2.65, GIRD_B), (x1, 2.65, -1.25), CON, tile=(3.0, 1.4))
    # parapets + red accent stripe
    for sy in (-1.0, 1.0):
        p0, p1 = sorted((sy * DECK_HW, sy * 3.95))
        M.box((x0, p0, -0.30), (x1, p1, 0.85), CON, tile=(3.0, 1.0))
        M.box((x0, sy * 3.97 - 0.06, 0.38), (x1, sy * 3.97 + 0.06, 0.52), RED, tile=(3.0, 0.2), emis=0.12)
        # slim railing: dark posts, red handrail
        for rx in np.linspace(x0 + 0.8, x1 - 0.8, max(2, int(L / 2.2))):
            M.box((rx - 0.045, sy * 3.72 - 0.045, 0.85), (rx + 0.045, sy * 3.72 + 0.045, 1.42), MAT,
                  tile=(0.2, 0.5))
        M.box((x0, sy * 3.72 - 0.055, 1.42), (x1, sy * 3.72 + 0.055, 1.52), RED, tile=(3.0, 0.16), emis=0.10)
        M.box((x0, sy * 3.72 - 0.04, 1.05), (x1, sy * 3.72 + 0.04, 1.11), MAT, tile=(3.0, 0.12))
    # collisions: deck slab + parapets
    C.box((x0, -3.95, GIRD_B), (x1, 3.95, DECK_TOP))
    for sy in (-1.0, 1.0):
        C.box((x0, sy * 3.6 - 0.25, DECK_TOP), (x1, sy * 3.6 + 0.25, 1.52))


def rail_deck(variant=0):
    """48 m straight viaduct span = four 12 m box-girder chunks + two piers (at x = +-12).
    variant 1 has no piers (placed where a bridge deck crosses underneath)."""
    M, C = Mesh(), Col()
    for cx in (-18.0, -6.0, 6.0, 18.0):
        subM, subC = Mesh(), Col()
        _deck_chunk(subM, subC, 12.0)
        M.merge(subM, (cx, 0.0, 0.0), 0.0)
        C.merge(subC, (cx, 0.0, 0.0), 0.0)
    if not variant:
        pierM, pierC, _ = rail_pylon()
        for cx in (-12.0, 12.0):
            M.merge(pierM, (cx, 0.0, 0.0), 0.0)
            C.merge(pierC, (cx, 0.0, 0.0), 0.0)
    return M, C, dict(kind='rail', dist=2600.0, amb=1.0)


def rail_curve():
    """180 degree turn of the closed loop (radius 25 m, origin at the turn centre on the rail
    top).  Built from twelve 15 degree deck chunks around the arc, with three piers."""
    M, C = Mesh(), Col()
    subM, subC = Mesh(), Col()
    chord = 2.0 * (R + 0.12) * np.sin(np.pi / 24.0) + 0.22     # chunk length with a touch of overlap
    _deck_chunk(subM, subC, chord)
    for k in range(12):
        ang = 82.5 - 15.0 * k                                  # chunk centre angles 82.5 .. -82.5
        th = np.radians(ang)
        px, py = R * np.cos(th), R * np.sin(th)
        M.merge(subM, (px, py, 0.0), ang - 90.0)
        C.merge(subC, (px, py, 0.0), ang - 90.0)
    # piers at the quarter points of the arc
    pierM, pierC, _ = rail_pylon()
    for ang in (45.0, 90.0, 135.0):
        th = np.radians(ang)
        M.merge(pierM, (R * np.cos(th), R * np.sin(th), 0.0), 0.0)
        C.merge(pierC, (R * np.cos(th), R * np.sin(th), 0.0), 0.0)
    return M, C, dict(kind='rail', dist=1800.0, amb=1.0)


def rail_pylon():
    """support pier (placed at z = 13 so the cap meets the girder soffit)."""
    M, C = Mesh(), Col()
    M.box((-2.5, -1.8, -3.30), (2.5, 1.8, -2.50), CON, tile=(2.2, 1.2))
    M.box((-1.5, -1.15, -11.9), (1.5, 1.15, -3.30), CON, tile=(1.8, 4.0))
    M.box((-2.2, -1.5, -13.0), (2.2, 1.5, -11.9), CON, tile=(1.9, 1.2))
    M.box((-1.6, -1.25, -12.1), (1.6, 1.25, -11.9), RED, tile=(1.6, 0.25), emis=0.12)
    C.box((-2.3, -1.6, -13.0), (2.3, 1.6, -2.50))
    return M, C, dict(kind='rail', dist=1800.0, amb=1.0)


# ---------------------------------------------------------------------------------------------
# tunnel
# ---------------------------------------------------------------------------------------------
def rail_tube():
    """24 m tunnel shell: horseshoe arch, tiled lining, wall light strips, service walkways."""
    M, C = Mesh(), Col()
    prof = _tunnel_profile(5.8, 1.9, -1.25)
    _shell(M, prof, -12.0, 12.0, CON, tile=(4.0, 2.2), outward=False, emis=0.02)
    for sy in (-1.0, 1.0):
        M.box((-12.0, sy * 5.72 - 0.10, -0.62), (12.0, sy * 5.72 + 0.10, 1.72), WARM, tile=(4.0, 1.2), emis=1.05)
    M.box((-12.0, -1.15, 7.52), (12.0, 1.15, 7.62), WARM, tile=(4.0, 1.0), emis=0.95)
    for sy in (-1.0, 1.0):
        w0, w1 = sorted((sy * 5.75, sy * 4.0))
        M.box((-12.0, w0, -1.25), (12.0, w1, -0.45), MAT, tile=(4.0, 1.2))
        M.box((-12.0, sy * 4.05 - 0.12, -1.25), (12.0, sy * 4.05 + 0.12, -0.45), MAT2, tile=(4.0, 0.6), emis=0.04)
    M.box((-12.0, -5.8, -1.28), (12.0, 5.8, -1.24), MAT, tile=(4.0, 3.0))
    for sy in (-1.0, 1.0):
        C.box((-12.0, sy * 5.8 - 0.35, -1.3), (12.0, sy * 5.8 + 0.35, 2.0))
    C.box((-12.0, -5.8, 6.6), (12.0, 5.8, 7.8))
    return M, C, dict(kind='rail', dist=2600.0, amb=1.0)


def rail_portal():
    """tunnel portal: concrete collar ring around the arch mouth, spandrel face,
    the NIGHT CITY METRO board on a pediment above the arch, red signal heads."""
    M, C = Mesh(), Col()
    prof_in = _tunnel_profile(5.8, 1.9, -1.25)
    prof_out = _tunnel_profile(6.5, 1.9, -1.35)
    K = len(prof_in)
    P = np.zeros((K - 1, 4, 3), np.float64)
    UV = np.zeros((K - 1, 4, 2), np.float64)
    for i in range(K - 1):
        (ya, za), (yb, zb) = prof_in[i], prof_in[i + 1]
        (Ya, Za), (Yb, Zb) = prof_out[i], prof_out[i + 1]
        P[i] = [(0.02, ya, za), (0.02, yb, zb), (0.02, Yb, Zb), (0.02, Ya, Za)]
        UV[i] = [(ya * 0.4, za * 0.4), (yb * 0.4, zb * 0.4), (Yb * 0.4, Zb * 0.4), (Ya * 0.4, Za * 0.4)]
    M.quads(P, CON, UV, 0.03)
    _shell(M, prof_out, -0.02, 1.45, CON, tile=(2.2, 2.4), outward=True, emis=0.02)
    K2 = len(prof_out)
    P2 = np.zeros((K2 - 1, 4, 3), np.float64)
    for i in range(K2 - 1):
        (ya, za), (yb, zb) = prof_out[i], prof_out[i + 1]
        P2[i] = [(1.45, yb, zb), (1.45, ya, za), (1.32, ya, za), (1.32, yb, zb)]
    M.quads(P2, CON, np.zeros((K2 - 1, 4, 2)) + 0.4, 0.03)
    M.box((-0.25, -5.05, 8.35), (1.75, 5.05, 9.85), CON, tile=(2.0, 1.4))
    M.box((-0.45, -5.35, 9.85), (1.95, 5.35, 10.15), CON, tile=(2.2, 0.5))
    _board(M, 1.78, -4.55, 8.55, 4.55, 9.62, _logo_uv(), 1.35)
    for sy in (-1.0, 1.0):
        M.box((1.42, sy * 5.55 - 0.42, 2.05), (1.62, sy * 5.55 + 0.42, 3.05), MAT, tile=(0.4, 0.6))
        M.cyl((1.68, sy * 5.55), 0.30, 2.55, 2.55, 12, RED, tile=(0.6, 0.6), smooth=True, rx=0.16, ry=0.30)
        M.cyl((1.68, sy * 5.55), 0.22, 2.55, 2.55, 12, RED, tile=(0.5, 0.5), smooth=True, rx=0.10, ry=0.22, emis=1.2)
    for sy in (-1.0, 1.0):
        M.box((-0.15, sy * 6.5 - 0.9, -1.35), (1.55, sy * 6.5 + 0.9, 3.35), CON, tile=(1.6, 2.2))
        M.box((-0.15, sy * 6.5 - 1.05, 3.35), (1.55, sy * 6.5 + 1.05, 3.75), CON, tile=(1.6, 0.6))
    C.box((-0.15, -7.4, -1.35), (1.6, -5.6, 3.8))
    C.box((-0.15, 5.6, -1.35), (1.6, 7.4, 3.8))
    C.box((-0.3, -5.4, 8.3), (1.8, 5.4, 10.2))
    return M, C, dict(kind='rail', dist=2200.0, amb=1.0)


# ---------------------------------------------------------------------------------------------
# stations
# ---------------------------------------------------------------------------------------------
def rail_station(variant=0):
    """80 m station (local y = 0 on the track, origin on the rail top): twin platforms with
    level boarding at z = 0.98, concrete canopy on slim columns, red railings, name totems and
    stairs down to the street on the north (land) side.  variant 0/1/2 = MARKET/UNION/DOCKS."""
    M, C = Mesh(), Col()
    L = 80.0
    idx = variant % 3

    for side in (-1.0, 1.0):
        ya, yb = sorted((side * 4.6, side * 12.4))
        M.box((-L / 2, ya, -0.45), (L / 2, yb, 0.92), CON, tile=(6.0, 2.6))
        M.box((-L / 2, ya, 0.92), (L / 2, yb, 0.98), CONL, tile=(6.0, 2.6))
        # yellow warning strip along the boarding edge
        e0, e1 = sorted((side * 4.6, side * 5.15))
        M.box((-L / 2 + 1.0, e0, 0.985), (L / 2 - 1.0, e1, 1.02), WARM, tile=(6.0, 0.4), emis=0.55)
        # red railing along the back edge
        b0, b1 = sorted((side * 12.05, side * 12.4))
        for rx in np.linspace(-L / 2 + 2.0, L / 2 - 2.0, 11):
            M.box((rx - 0.07, b0, 0.98), (rx + 0.07, b1, 2.18), RED, tile=(0.3, 1.0), emis=0.10)
        M.box((-L / 2 + 1.0, b0, 2.08), (L / 2 - 1.0, b1, 2.22), RED, tile=(6.0, 0.2), emis=0.12)
        M.box((-L / 2 + 1.0, b0, 1.52), (L / 2 - 1.0, b1, 1.62), RED, tile=(6.0, 0.15), emis=0.10)
        # concrete canopy on slim columns
        cy = side * 8.5
        for cx in np.linspace(-L / 2 + 6.0, L / 2 - 6.0, 6):
            M.cyl((cx, cy), 0.16, 0.98, 3.86, 8, CON, tile=(0.6, 1.6), smooth=True)
        M.box((-L / 2 + 3.0, ya + 0.4, 3.86), (L / 2 - 3.0, yb - 0.4, 4.12), CON, tile=(6.0, 1.8))
        M.box((-L / 2 + 3.0, ya + 0.4, 4.12), (L / 2 - 3.0, yb - 0.4, 4.22), RED, tile=(6.0, 1.8), emis=0.12)
        for cx in np.linspace(-L / 2 + 10.0, L / 2 - 10.0, 5):
            M.box((cx - 1.4, cy - 0.22, 3.80), (cx + 1.4, cy + 0.22, 3.86), WARM, tile=(1.6, 0.3), emis=1.15)
        # benches
        for bx in (-L / 2 + 16.0, -4.0, L / 2 - 16.0):
            M.box((bx - 1.7, cy - 0.42, 1.10), (bx + 1.7, cy + 0.42, 1.42), RED, tile=(1.2, 0.6), emis=0.10)
            M.box((bx - 1.7, cy - 0.42, 1.42), (bx + 1.7, cy - 0.34, 1.98), MAT, tile=(1.2, 0.5))
        # platform support columns down to the ground / river bed
        for cx in np.linspace(-L / 2 + 12.0, L / 2 - 12.0, 5):
            M.cyl((cx, cy), 0.85, -12.9, -0.45, 10, CON, tile=(1.4, 4.0), smooth=True)
            M.cyl((cx, cy), 1.15, -13.0, -12.2, 10, CON, tile=(1.6, 0.6), smooth=True)

    # --------------------------------------- stairs (land side only) + name totems
    for side in (1.0,):
        yc = side * 11.6
        for sx in (-1.0, 1.0):
            xst = sx * 40.5
            for k in range(20):
                z = 0.98 - (k + 1) * 0.049
                y0 = yc - side * 4.4 + side * k * 0.44
                y1 = y0 + side * 0.46
                a, b = sorted((y0, y1))
                M.box((xst - 3.2, a, z), (xst + 3.2, b, z + 0.055), CON, tile=(1.6, 0.4))
            for sx2 in (-1.0, 1.0):
                M.box((xst + sx2 * 3.2 - 0.18, yc - side * 4.6, -0.05), (xst + sx2 * 3.2 + 0.18, yc + side * 4.6, 1.15),
                      CON, tile=(0.6, 1.6))
                M.box((xst + sx2 * 3.2 - 0.10, yc - side * 4.6, 1.15), (xst + sx2 * 3.2 + 0.10, yc + side * 4.6, 2.15),
                      RED, tile=(0.3, 1.2), emis=0.10)
            # totem with the station name
            ty = yc - side * 6.2
            M.cyl((xst, ty), 0.16, 0.0, 4.6, 8, MAT, tile=(0.6, 1.8), smooth=True)
            M.box((xst - 1.55, ty - 0.16, 3.15), (xst + 1.55, ty + 0.16, 4.42), MAT, tile=(1.4, 1.0))
            _board(M, xst + 1.58, ty - 1.25, 3.28, ty + 1.25, 4.30, _sign_uv(idx), 1.20)

    # station name plate on the outer platform walls (both sides)
    for side in (-1.0, 1.0):
        yf = side * 12.85
        uv = _sign_uv(idx)
        P = np.array([[[( -3.2, yf - side * 0.06, 1.35), (3.2, yf - side * 0.06, 1.35),
                        (3.2, yf - side * 0.06, 2.35), (-3.2, yf - side * 0.06, 2.35)]]], np.float32)
        uvar = np.array([[uv[0], uv[1], uv[2], uv[3]]], np.float32)
        M.quads(P, SIGN, uvar, 1.15)
    for side in (-1.0, 1.0):
        for lx in np.linspace(-L / 2 + 8.0, L / 2 - 8.0, 6):
            M.light((lx, side * 6.6, 3.2), (1.0, 0.86, 0.62), 0.75, 14.0)

    C.box((-L / 2, -12.6, -0.5), (L / 2, -4.4, 0.98))
    C.box((-L / 2, 4.4, -0.5), (L / 2, 12.6, 0.98))
    for sx in (-1.0, 1.0):
        xst = sx * 40.5
        C.box((xst - 3.4, 6.8, -0.2), (xst + 3.4, 16.4, 1.2))
    return M, C, dict(kind='rail', dist=2200.0, amb=1.0)


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
