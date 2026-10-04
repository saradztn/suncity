# Created by: Arena.ai Agent Mode (AI) - NightCity MTA:SA asset pipeline
# -----------------------------------------------------------------------------
# mb.py - vectorised mesh builder + collision collector for the procedural city.
#
# Conventions: right handed, X east, Y north, Z up, 1 unit = 1 m.  Triangles are CCW seen from OUTSIDE.
# Materials are plain strings (the texture name); every chunk carries one material and an "emissive" weight
# (0..1) that the lighting bake turns into full-bright vertex colours.
# UV convention (D3D / RenderWare): v grows DOWNWARDS in the image, so a wall uses v = -z / tile and a ground
# quad v = -y / tile (image up = world north).
# -----------------------------------------------------------------------------
import numpy as np

TAU = np.pi * 2


def unit(v):
    v = np.asarray(v, np.float64)
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.maximum(n, 1e-12)


def rotz(a):
    c, s = np.cos(np.radians(a)), np.sin(np.radians(a))
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])


class Mesh:
    """collection of surface chunks: (pos Nx3, nrm Nx3, uv Nx2, tris Mx3, mat str, emis float, tint|None) + point lights"""

    def __init__(self):
        self.chunks = []
        self.lights = []          # dict(p=(x,y,z), c=(r,g,b), i=intensity, r=radius, n=None|(nx,ny,nz))
        self.sprites = []         # dict(p, size, c, kind='glow'|'steam') - camera facing billboards drawn at run time by the client (no alpha models)

    # ------------------------------------------------------------------ raw
    def add(self, pos, nrm, uv, tris, mat, emis=0.0, tint=None):
        pos = np.asarray(pos, np.float64).reshape(-1, 3)
        nrm = np.asarray(nrm, np.float64).reshape(-1, 3)
        uv = np.asarray(uv, np.float64).reshape(-1, 2)
        tris = np.asarray(tris, np.int64).reshape(-1, 3)
        if len(tris) == 0:
            return
        self.chunks.append((pos, nrm, uv, tris, str(mat), float(emis), None if tint is None else tuple(map(float, tint))))

    def light(self, p, c, i=1.0, r=12.0, n=None):
        """point light for the vertex-light bake (nothing is lit at run time: San Andreas objects only have prelit vertex colours)"""
        self.lights.append(dict(p=tuple(map(float, p)), c=tuple(map(float, c)), i=float(i), r=float(r), n=None if n is None else tuple(map(float, n))))

    # ------------------------------------------------------------------ quads
    def quads(self, P, mat, uv=None, emis=0.0, nrm=None, tint=None):
        """P (N,4,3) CCW seen from outside.  uv (N,4,2) or None -> 0..1 (p0 bottom-left)."""
        P = np.asarray(P, np.float64).reshape(-1, 4, 3)
        N = len(P)
        if N == 0:
            return
        if nrm is None:
            n = np.cross(P[:, 1] - P[:, 0], P[:, 3] - P[:, 0])
            ln = np.linalg.norm(n, axis=1, keepdims=True)
            small = ln[:, 0] < 1e-9
            if small.any():           # triangle-shaped quad (two corners coincide): take the normal from the other corners
                alt = (np.cross(P[:, 2] - P[:, 1], P[:, 0] - P[:, 1]) + np.cross(P[:, 3] - P[:, 2], P[:, 1] - P[:, 2])
                       + np.cross(P[:, 0] - P[:, 3], P[:, 2] - P[:, 3]))
                n = np.where(small[:, None], alt, n)
                ln = np.linalg.norm(n, axis=1, keepdims=True)
            n = n / np.maximum(ln, 1e-12)
            nrm = np.repeat(n[:, None, :], 4, axis=1)
        else:
            nrm = np.asarray(nrm, np.float64).reshape(-1, 4, 3)
        if uv is None:
            uv = np.tile(np.array([[0, 1], [1, 1], [1, 0], [0, 0]], np.float64), (N, 1, 1))
        uv = np.asarray(uv, np.float64).reshape(-1, 4, 2)
        base = (np.arange(N) * 4)[:, None, None]
        tr = np.array([[0, 1, 2], [0, 2, 3]], np.int64)[None] + base
        self.add(P.reshape(-1, 3), nrm.reshape(-1, 3), uv.reshape(-1, 2), tr.reshape(-1, 3), mat, emis, tint)

    def quad(self, p0, p1, p2, p3, mat, uv=None, emis=0.0, tile=None, uvoff=(0.0, 0.0), tint=None):
        """one quad.  tile=(tu, tv): world-metre tiling with planar mapping (axis chosen by the normal)"""
        P = np.array([p0, p1, p2, p3], np.float64)
        if tile is not None:
            n = unit(np.cross(P[1] - P[0], P[3] - P[0]))
            uv = self.planar_uv(P, n, tile, uvoff)
        self.quads(P[None], mat, None if uv is None else np.asarray(uv)[None], emis, tint=tint)

    @staticmethod
    def planar_uv(P, n, tile, off=(0.0, 0.0)):
        P = np.asarray(P, np.float64)
        tu, tv = (tile, tile) if np.isscalar(tile) else tile
        ax = int(np.argmax(np.abs(n)))
        if ax == 2:
            a = P[:, 0]
            b = -P[:, 1] if n[2] > 0 else P[:, 1]
        elif ax == 0:
            a = P[:, 1] * (1 if n[0] > 0 else -1)
            b = -P[:, 2]
        else:
            a = P[:, 0] * (-1 if n[1] > 0 else 1)
            b = -P[:, 2]
        return np.stack([a / tu + off[0], b / tv + off[1]], -1)

    def wall(self, a, b, z0, z1, mat, tile=(4.0, 4.0), uoff=0.0, voff=0.0, emis=0.0, uspan=None, flip=False):
        """vertical quad above the 2D segment a->b (outside = right hand side).  u = length / tile_u"""
        a = np.asarray(a, np.float64)[:2]
        b = np.asarray(b, np.float64)[:2]
        L = float(np.linalg.norm(b - a))
        if L < 1e-6 or z1 - z0 < 1e-6:
            return
        tu, tv = tile
        u1 = (L / tu) if uspan is None else uspan
        P = np.array([[a[0], a[1], z0], [b[0], b[1], z0], [b[0], b[1], z1], [a[0], a[1], z1]])
        UV = np.array([[uoff, -z0 / tv + voff], [uoff + u1, -z0 / tv + voff], [uoff + u1, -z1 / tv + voff], [uoff, -z1 / tv + voff]])
        if flip:
            P = P[[1, 0, 3, 2]]
            UV = UV[[1, 0, 3, 2]]
        self.quads(P[None], mat, UV[None], emis)

    def hquad(self, x0, y0, x1, y1, z, mat, tile=(4.0, 4.0), uvoff=(0.0, 0.0), emis=0.0, up=True, uvrect=None):
        """horizontal rectangle (normal up by default), planar uv"""
        tu, tv = tile
        if uvrect is not None:
            ua, va, ub, vb = uvrect
        else:
            ua, ub = x0 / tu + uvoff[0], x1 / tu + uvoff[0]
            va, vb = -y1 / tv + uvoff[1], -y0 / tv + uvoff[1]      # va = top (y1), vb = bottom (y0)
        P = np.array([[x0, y0, z], [x1, y0, z], [x1, y1, z], [x0, y1, z]])
        UV = np.array([[ua, vb], [ub, vb], [ub, va], [ua, va]])
        if not up:
            P = P[[0, 3, 2, 1]]
            UV = UV[[0, 3, 2, 1]]
        self.quads(P[None], mat, UV[None], emis)

    # ------------------------------------------------------------------ solids
    def box(self, lo, hi, mat, tile=(4.0, 4.0), skip=(), emis=0.0, mats=None, uvoff=(0.0, 0.0), uvrects=None):
        """axis aligned box; skip: faces among '+x','-x','+y','-y','+z','-z'; mats: per face material; uvrects: per face (u0,v0,u1,v1)"""
        x0, y0, z0 = lo
        x1, y1, z1 = hi
        if x1 - x0 < 1e-6 or y1 - y0 < 1e-6 or z1 - z0 < 1e-6:
            return
        tu, tv = (tile, tile) if np.isscalar(tile) else tile
        faces = {
            '+x': ([(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)], y0, y1, 'w'),
            '-x': ([(x0, y1, z0), (x0, y0, z0), (x0, y0, z1), (x0, y1, z1)], -y1, -y0, 'w'),
            '+y': ([(x1, y1, z0), (x0, y1, z0), (x0, y1, z1), (x1, y1, z1)], -x1, -x0, 'w'),
            '-y': ([(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)], x0, x1, 'w'),
        }
        for k, (P, s0, s1, _) in faces.items():
            if k in skip:
                continue
            m = mat if mats is None or k not in mats else mats[k]
            if uvrects is not None and k in uvrects:
                ua, va, ub, vb = uvrects[k]
                UV = np.array([[ua, vb], [ub, vb], [ub, va], [ua, va]])
            else:
                UV = np.array([[s0 / tu + uvoff[0], -z0 / tv + uvoff[1]], [s1 / tu + uvoff[0], -z0 / tv + uvoff[1]],
                               [s1 / tu + uvoff[0], -z1 / tv + uvoff[1]], [s0 / tu + uvoff[0], -z1 / tv + uvoff[1]]])
            self.quads(np.array(P)[None], m, UV[None], emis)
        for k, z, up in (('+z', z1, True), ('-z', z0, False)):
            if k in skip:
                continue
            m = mat if mats is None or k not in mats else mats[k]
            if uvrects is not None and k in uvrects:
                self.hquad(x0, y0, x1, y1, z, m, tile, emis=emis, up=up, uvrect=uvrects[k])
            else:
                self.hquad(x0, y0, x1, y1, z, m, tile, uvoff, emis, up)

    def extrude(self, poly, z0, z1, wall_mat, top_mat=None, tile=(4.0, 4.0), bottom_mat=None, emis=0.0, uvoff=(0.0, 0.0),
                smooth=False, wall_emis=None, top_tile=None):
        """prism over a CONVEX polygon (N,2) given CCW.  Walls: u = perimeter / tile_u, v = -z / tile_v."""
        poly = np.asarray(poly, np.float64)
        n = len(poly)
        tu, tv = tile
        we = emis if wall_emis is None else wall_emis
        s = 0.0
        quads, uvs, nrms = [], [], []
        cen = poly.mean(0)
        for i in range(n):
            a, b = poly[i], poly[(i + 1) % n]
            L = float(np.linalg.norm(b - a))
            quads.append([[a[0], a[1], z0], [b[0], b[1], z0], [b[0], b[1], z1], [a[0], a[1], z1]])
            uvs.append([[s / tu + uvoff[0], -z0 / tv + uvoff[1]], [(s + L) / tu + uvoff[0], -z0 / tv + uvoff[1]],
                        [(s + L) / tu + uvoff[0], -z1 / tv + uvoff[1]], [s / tu + uvoff[0], -z1 / tv + uvoff[1]]])
            if smooth:
                na = unit(np.array([a[0] - cen[0], a[1] - cen[1], 0.0]))
                nb = unit(np.array([b[0] - cen[0], b[1] - cen[1], 0.0]))
                nrms.append([na, nb, nb, na])
            s += L
        self.quads(np.array(quads), wall_mat, np.array(uvs), we, nrm=np.array(nrms) if smooth else None)
        tt = top_tile or tile
        if top_mat is not None:
            self.poly([(p[0], p[1], z1) for p in poly], top_mat, tt, emis, up=True)
        if bottom_mat is not None:
            self.poly([(p[0], p[1], z0) for p in poly], bottom_mat, tt, emis, up=False)

    def poly(self, pts, mat, tile=(4.0, 4.0), emis=0.0, up=True, uvoff=(0.0, 0.0)):
        """flat convex horizontal polygon (fan), planar uv; pts CCW seen from above"""
        P = np.asarray(pts, np.float64)
        k = len(P)
        if k < 3:
            return
        tu, tv = tile
        if not up:
            P = P[::-1]
        UV = np.stack([P[:, 0] / tu + uvoff[0], -P[:, 1] / tv + uvoff[1]], -1)
        nr = np.tile(np.array([0, 0, 1.0 if up else -1.0]), (k, 1))
        tr = [[0, i, i + 1] for i in range(1, k - 1)]
        self.add(P, nr, UV, tr, mat, emis)

    def loft(self, poly0, z0, poly1, z1, wall_mat, top_mat=None, tile=(4.0, 4.0), emis=0.0, uvoff=(0.0, 0.0)):
        """frustum between two convex CCW polygons with the same vertex count (flat facets)"""
        p0, p1 = np.asarray(poly0, np.float64), np.asarray(poly1, np.float64)
        n = len(p0)
        tu, tv = tile
        s = 0.0
        quads, uvs = [], []
        h = z1 - z0
        for i in range(n):
            j = (i + 1) % n
            a0, b0, a1, b1 = p0[i], p0[j], p1[i], p1[j]
            L = float(np.linalg.norm(b0 - a0))
            quads.append([[a0[0], a0[1], z0], [b0[0], b0[1], z0], [b1[0], b1[1], z1], [a1[0], a1[1], z1]])
            L1 = float(np.linalg.norm(b1 - a1))
            hh = np.hypot(h, np.linalg.norm((a1 + b1) / 2 - (a0 + b0) / 2))
            uvs.append([[s / tu + uvoff[0], uvoff[1]], [(s + L) / tu + uvoff[0], uvoff[1]],
                        [(s + L) / tu + uvoff[0] - (L - L1) / 2 / tu, -hh / tv + uvoff[1]], [s / tu + uvoff[0] + (L - L1) / 2 / tu, -hh / tv + uvoff[1]]])
            s += L
        self.quads(np.array(quads), wall_mat, np.array(uvs), emis)
        if top_mat is not None:
            self.poly([(p[0], p[1], z1) for p in p1], top_mat, tile, emis, up=True)

    def cyl(self, c, r, z0, z1, n, mat, tile=(4.0, 4.0), top_mat=None, bottom_mat=None, smooth=True, emis=0.0, rx=None, ry=None, theta0=0.0, uvoff=(0.0, 0.0)):
        th = theta0 + np.arange(n) * TAU / n
        rx = r if rx is None else rx
        ry = r if ry is None else ry
        poly = np.stack([c[0] + rx * np.cos(th), c[1] + ry * np.sin(th)], -1)
        self.extrude(poly, z0, z1, mat, top_mat, tile, bottom_mat, emis, uvoff, smooth=smooth)

    def cone(self, c, r0, r1, z0, z1, n, mat, tile=(4.0, 4.0), top_mat=None, emis=0.0, theta0=0.0):
        th = theta0 + np.arange(n) * TAU / n
        p0 = np.stack([c[0] + r0 * np.cos(th), c[1] + r0 * np.sin(th)], -1)
        p1 = np.stack([c[0] + max(r1, 1e-4) * np.cos(th), c[1] + max(r1, 1e-4) * np.sin(th)], -1)
        self.loft(p0, z0, p1, z1, mat, top_mat, tile, emis)

    def tube(self, path, r, n, mat, tile=(2.0, 1.0), caps=True, emis=0.0, smooth=True):
        """round pipe / cable along a polyline (K,3).  u = length / tile_u, v around / tile_v"""
        path = np.asarray(path, np.float64)
        K = len(path)
        if K < 2:
            return
        tang = np.zeros_like(path)
        tang[:-1] += unit(path[1:] - path[:-1])
        tang[1:] += unit(path[1:] - path[:-1])
        tang = unit(tang)
        ref = np.array([0, 0, 1.0])
        rings = []
        for k in range(K):
            t = tang[k]
            a = np.cross(t, ref)
            if np.linalg.norm(a) < 1e-4:
                a = np.cross(t, np.array([1.0, 0, 0]))
            a = unit(a)
            b = unit(np.cross(a, t))
            th = np.arange(n) * TAU / n
            d = np.cos(th)[:, None] * a + np.sin(th)[:, None] * b
            rings.append((path[k] + d * r, d))
        s = 0.0
        quads, nrms, uvs = [], [], []
        av = TAU * r / n / tile[1]
        for k in range(K - 1):
            L = float(np.linalg.norm(path[k + 1] - path[k]))
            P0, D0 = rings[k]
            P1, D1 = rings[k + 1]
            for i in range(n):
                j = (i + 1) % n
                q = [P0[i], P1[i], P1[j], P0[j]]
                nn = [D0[i], D1[i], D1[j], D0[j]]
                uu = [[s / tile[0], i * av], [(s + L) / tile[0], i * av], [(s + L) / tile[0], (i + 1) * av], [s / tile[0], (i + 1) * av]]
                nf = np.cross(q[1] - q[0], q[3] - q[0])
                if np.dot(nf, D0[i] + D0[j]) < 0:                 # make the winding CCW seen from outside
                    perm = [0, 3, 2, 1]
                    q = [q[m] for m in perm]
                    nn = [nn[m] for m in perm]
                    uu = [uu[m] for m in perm]
                quads.append(q)
                nrms.append(nn if smooth else [unit(np.cross(q[1] - q[0], q[3] - q[0]))] * 4)
                uvs.append(uu)
            s += L
        self.quads(np.array(quads), mat, np.array(uvs), emis, nrm=np.array(nrms))
        if caps:
            for k, sgn in ((0, -1), (K - 1, 1)):
                P, D = rings[k]
                c = path[k]
                t = tang[k] * sgn
                tr = []
                for i in range(n):
                    j = (i + 1) % n
                    tri = [c, P[i], P[j]]
                    if np.dot(np.cross(tri[1] - tri[0], tri[2] - tri[0]), t) < 0:
                        tri = [c, P[j], P[i]]
                    tr.append(tri)
                tr = np.array(tr)
                self.add(tr.reshape(-1, 3), np.tile(t, (len(tr) * 3, 1)), np.tile([0.5, 0.5], (len(tr) * 3, 1)), np.arange(len(tr) * 3).reshape(-1, 3), mat, emis)

    def ribbon(self, path, hw, mat, tile_v=8.0, u=(0.0, 1.0), zoff=0.0, emis=0.0, up=True, v0=0.0, uoff_world=None):
        """flat surface strip following a 3D polyline (K,3); half width hw (scalar or K); u across (u0..u1), v along (= length / tile_v)"""
        path = np.asarray(path, np.float64)
        K = len(path)
        hw = np.broadcast_to(np.asarray(hw, np.float64), (K,)).copy()
        tang = np.zeros((K, 2))
        d = path[1:, :2] - path[:-1, :2]
        tang[:-1] += unit(d)
        tang[1:] += unit(d)
        tang = unit(tang)
        left = np.stack([-tang[:, 1], tang[:, 0]], -1)
        Lp = np.concatenate([path[:, :2] + left * hw[:, None], path[:, 2:3] + zoff], 1)
        Rp = np.concatenate([path[:, :2] - left * hw[:, None], path[:, 2:3] + zoff], 1)
        s = np.concatenate([[0], np.cumsum(np.linalg.norm(path[1:] - path[:-1], axis=1))]) / tile_v + v0
        quads, uvs = [], []
        for k in range(K - 1):
            # CCW from above: right-start, right-end, left-end, left-start  (travel direction = +v)
            q = [Rp[k], Rp[k + 1], Lp[k + 1], Lp[k]]
            uv = [[u[1], -s[k]], [u[1], -s[k + 1]], [u[0], -s[k + 1]], [u[0], -s[k]]]
            if not up:
                q = [q[0], q[3], q[2], q[1]]
                uv = [uv[0], uv[3], uv[2], uv[1]]
            quads.append(q)
            uvs.append(uv)
        self.quads(np.array(quads), mat, np.array(uvs), emis)

    # ------------------------------------------------------------------ composition
    def merge(self, sub, pos=(0, 0, 0), rz=0.0, scale=1.0, mirror_x=False):
        """copy `sub` into self rotated about z by rz degrees (CCW from above), scaled, moved to pos"""
        R = rotz(rz)
        pos = np.asarray(pos, np.float64).reshape(-1)
        if pos.size == 2:
            pos = np.append(pos, 0.0)
        for p, n, u, t, mt, e, tn in sub.chunks:
            p2, n2, t2 = p * scale, n, t
            if mirror_x:
                p2 = p2 * np.array([-1, 1, 1.0])
                n2 = n2 * np.array([-1, 1, 1.0])
                t2 = t[:, ::-1]
            self.chunks.append((p2 @ R.T + pos, n2 @ R.T, u, t2, mt, e, tn))
        for L in sub.lights:
            q = np.array(L['p']) * scale
            if mirror_x:
                q = q * np.array([-1, 1, 1.0])
            q = R @ q + pos
            nn = None
            if L['n'] is not None:
                nv = np.array(L['n']) * (np.array([-1, 1, 1.0]) if mirror_x else 1)
                nn = tuple(R @ nv)
            self.lights.append(dict(L, p=tuple(q), n=nn, r=L['r'] * scale))
        for SP in sub.sprites:
            q = np.array(SP['p']) * scale
            if mirror_x:
                q = q * np.array([-1, 1, 1.0])
            q = R @ q + pos
            self.sprites.append(dict(SP, p=tuple(q), size=SP['size'] * scale))

    def wall_strip(self, pts2d, z0, z1, mat, tile=(4.0, 4.0), emis=0.0, uoff=0.0, flip=False):
        """vertical walls along a 2D polyline, outside = right hand side of the travel direction (u continues along it)"""
        pts = np.asarray(pts2d, np.float64)
        s = uoff
        tu, tv = tile
        quads, uvs = [], []
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            L = float(np.linalg.norm(b - a))
            if L < 1e-6:
                continue
            q = [[a[0], a[1], z0], [b[0], b[1], z0], [b[0], b[1], z1], [a[0], a[1], z1]]
            uv = [[s, -z0 / tv], [s + L / tu, -z0 / tv], [s + L / tu, -z1 / tv], [s, -z1 / tv]]
            if flip:
                q = [q[1], q[0], q[3], q[2]]
                uv = [uv[1], uv[0], uv[3], uv[2]]
            quads.append(q)
            uvs.append(uv)
            s += L / tu
        if quads:
            self.quads(np.array(quads), mat, np.array(uvs), emis)
        return s

    def bounds(self):
        P = np.concatenate([c[0] for c in self.chunks])
        return P.min(0), P.max(0)

    def stats(self):
        return sum(len(c[0]) for c in self.chunks), sum(len(c[3]) for c in self.chunks)

    def materials(self):
        return sorted({c[4] for c in self.chunks})


# ---------------------------------------------------------------------------------------------
# collision collector (boxes, oriented prisms, triangle soup)
# ---------------------------------------------------------------------------------------------
class Col:
    def __init__(self):
        self.boxes = []       # (lo, hi)
        self.prisms = []      # (8,3) corner arrays (bottom 4 CCW, top 4 CCW)
        self.tris = []        # (P (n,3), F (m,3), surface)

    def box(self, lo, hi):
        a, b = np.asarray(lo, float), np.asarray(hi, float)
        lo, hi = np.minimum(a, b), np.maximum(a, b)
        if (hi - lo).min() < 1e-4:
            return
        self.boxes.append((tuple(map(float, lo)), tuple(map(float, hi))))

    def slab(self, poly2d, z0, z1):
        """vertical convex prism over a 4-corner polygon (CCW)"""
        P = np.asarray(poly2d, float)
        assert len(P) == 4
        self.prisms.append(np.array([(p[0], p[1], z0) for p in P] + [(p[0], p[1], z1) for p in P]))

    def mesh(self, P, F, surf=0):
        P = np.asarray(P, float)
        F = np.asarray(F, np.int64)
        if len(F):
            self.tris.append((P, F, surf))

    def merge(self, sub, pos=(0, 0, 0), rz=0.0):
        R = rotz(rz)
        pos = np.asarray(pos, float).reshape(-1)
        if pos.size == 2:
            pos = np.append(pos, 0.0)
        quarter = abs(((rz % 90) + 90) % 90) < 1e-6 or abs((rz % 90) - 90) < 1e-6
        for lo, hi in sub.boxes:
            lo, hi = np.array(lo), np.array(hi)
            if quarter:
                a, b = R @ lo + pos, R @ hi + pos
                self.box(np.minimum(a, b), np.maximum(a, b))
            else:
                cs = [R @ np.array([x, y, z]) + pos for z in (lo[2], hi[2]) for x, y in ((lo[0], lo[1]), (hi[0], lo[1]), (hi[0], hi[1]), (lo[0], hi[1]))]
                self.prisms.append(np.array(cs))
        for cc in sub.prisms:
            self.prisms.append(np.asarray(cc) @ R.T + pos)
        for P, F, s in sub.tris:
            self.tris.append((np.asarray(P) @ R.T + pos, F, s))

    def bounds(self):
        pts = []
        for lo, hi in self.boxes:
            pts += [lo, hi]
        for c in self.prisms:
            pts += list(c)
        for P, F, s in self.tris:
            pts += list(P)
        P = np.array(pts)
        return P.min(0), P.max(0)
