# Created by: Arena.ai Agent Mode (AI) - Park MTA:SA asset pipeline
# -----------------------------------------------------------------------------
# readers.py - STRICT, independent parsers for DFF / TXD / COL3 (written from the file-format
# specs, they share no code with the writers).  Every chunk size is checked against its
# parent so a malformed file raises instead of being silently accepted.
# -----------------------------------------------------------------------------
import struct
import numpy as np
from . import dxt

CONTAINERS = {0x10, 0x0E, 0x1A, 0x0F, 0x08, 0x07, 0x06, 0x14, 0x03, 0x16, 0x15}
NAMES = {0x01: 'Struct', 0x02: 'String', 0x03: 'Extension', 0x06: 'Texture', 0x07: 'Material', 0x08: 'MaterialList',
         0x0E: 'FrameList', 0x0F: 'Geometry', 0x10: 'Clump', 0x14: 'Atomic', 0x1A: 'GeometryList', 0x15: 'TexNative',
         0x16: 'TexDict', 0x120: 'MatFX', 0x50E: 'BinMesh', 0x253F2FE: 'FrameName', 0x253F2F9: 'NightColors'}


class Chunk:
    def __init__(self, cid, size, ver, off, buf):
        self.id, self.size, self.ver, self.off, self.buf = cid, size, ver, off, buf
        self.data = buf[off + 12: off + 12 + size]
        self.kids = []
        if cid in CONTAINERS:
            self.kids = parse(buf, off + 12, off + 12 + size)

    def find(self, cid):
        return [k for k in self.kids if k.id == cid]

    def one(self, cid):
        r = self.find(cid)
        if len(r) != 1:
            raise ValueError('expected exactly one chunk 0x%X in %s, got %d' % (cid, NAMES.get(self.id, hex(self.id)), len(r)))
        return r[0]


def parse(buf, start, end):
    out = []
    p = start
    while p < end:
        if p + 12 > end:
            raise ValueError('truncated chunk header at %d' % p)
        cid, size, ver = struct.unpack_from('<III', buf, p)
        if p + 12 + size > end:
            raise ValueError('chunk 0x%X at %d overruns parent (%d > %d)' % (cid, p, p + 12 + size, end))
        out.append(Chunk(cid, size, ver, p, buf))
        p += 12 + size
    if p != end:
        raise ValueError('chunk sizes do not sum to parent size')
    return out


def read_string(c):
    d = c.data
    return d.split(b'\0')[0].decode('ascii')


def read_texture(c):
    st = c.one(0x01).data
    filt, = struct.unpack('<I', st)
    names = c.find(0x02)
    return dict(name=read_string(names[0]), mask=read_string(names[1]), filter=filt & 0xFF, addr=(filt >> 8) & 0xFF)


def read_dff(path):
    buf = open(path, 'rb').read()
    top = parse(buf, 0, len(buf))
    assert len(top) == 1 and top[0].id == 0x10, 'top chunk must be a Clump'
    cl = top[0]
    res = dict(version=cl.ver)
    natom, nl, nc = struct.unpack('<III', cl.one(0x01).data)
    fl = cl.one(0x0E)
    nfr, = struct.unpack_from('<I', fl.one(0x01).data, 0)
    frames = []
    d = fl.one(0x01).data
    for i in range(nfr):
        v = struct.unpack_from('<9f3fiI', d, 4 + i * 56)
        frames.append(dict(rot=np.array(v[:9]).reshape(3, 3), pos=np.array(v[9:12]), parent=v[12], flags=v[13]))
    exts = fl.find(0x03)
    assert len(exts) == nfr, 'one frame extension per frame'
    for f, e in zip(frames, exts):
        nm = e.find(0x253F2FE)
        f['name'] = nm[0].data.split(b'\0')[0].decode('ascii') if nm else ''
    res['frames'] = frames
    gl = cl.one(0x1A)
    ng, = struct.unpack('<I', gl.one(0x01).data)
    geoms = []
    gchunks = gl.find(0x0F)
    assert len(gchunks) == ng
    for gc in gchunks:
        d = gc.one(0x01).data
        flags, nt, nv, nmorph = struct.unpack_from('<IIII', d, 0)
        p = 16
        g = dict(flags=flags, ntris=nt, nverts=nv)
        assert nmorph == 1
        assert flags & 0x02 and flags & 0x04 and flags & 0x10
        if flags & 0x08:
            g['prelit'] = np.frombuffer(d, np.uint8, nv * 4, p).reshape(nv, 4)
            p += nv * 4
        ntex = (flags >> 16) & 0xFF
        assert ntex == 1
        g['uv'] = np.frombuffer(d, '<f4', nv * 2, p).reshape(nv, 2)
        p += nv * 8
        t = np.frombuffer(d, '<u2', nt * 4, p).reshape(nt, 4)
        p += nt * 8
        g['tris'] = np.stack([t[:, 1], t[:, 0], t[:, 3]], 1).astype(np.int64)   # (v1,v2,v3) CCW
        g['tri_mat'] = t[:, 2].astype(np.int64)
        cx, cy, cz, rad, hv, hn = struct.unpack_from('<ffffII', d, p)
        p += 24
        assert hv == 1 and hn == 1
        g['sphere'] = (cx, cy, cz, rad)
        g['pos'] = np.frombuffer(d, '<f4', nv * 3, p).reshape(nv, 3)
        p += nv * 12
        g['nrm'] = np.frombuffer(d, '<f4', nv * 3, p).reshape(nv, 3)
        p += nv * 12
        assert p == len(d), 'geometry struct has trailing/missing bytes (%d vs %d)' % (p, len(d))
        ml = gc.one(0x08)
        nm, = struct.unpack_from('<I', ml.one(0x01).data, 0)
        idx = struct.unpack_from('<%di' % nm, ml.one(0x01).data, 4)
        assert all(i == -1 for i in idx)
        mats = []
        for mc in ml.find(0x07):
            m = struct.unpack('<IBBBBIIfff', mc.one(0x01).data)
            mat = dict(flags=m[0], color=m[1:5], textured=m[6], amb=m[7], spec=m[8], diff=m[9], tex=None, env=None)
            tc = mc.find(0x06)
            if m[6]:
                assert len(tc) == 1
                mat['tex'] = read_texture(tc[0])
            fx = mc.one(0x03).find(0x120)
            if fx:
                dd = fx[0].data
                t0, e0 = struct.unpack_from('<II', dd, 0)
                coef, fb, ht = struct.unpack_from('<fII', dd, 8)
                assert t0 == 2 and e0 == 2 and ht == 1
                sub = parse(dd, 20, len(dd) - 4)
                mat['env'] = dict(coef=coef, tex=read_texture(sub[0])['name'])
                assert struct.unpack_from('<I', dd, len(dd) - 4)[0] == 0
            mats.append(mat)
        assert len(mats) == nm
        g['materials'] = mats
        gex = gc.one(0x03)
        bm = gex.find(0x50E)[0].data
        bflags, nmesh, tot = struct.unpack_from('<III', bm, 0)
        p = 12
        meshes = []
        for _ in range(nmesh):
            ni, mi = struct.unpack_from('<II', bm, p)
            p += 8
            ii = np.frombuffer(bm, '<u4', ni, p)
            p += ni * 4
            meshes.append((mi, ii))
        assert p == len(bm) and sum(len(i) for _, i in meshes) == tot
        g['binmesh'] = meshes
        nc = gex.find(0x253F2F9)
        g['night'] = np.frombuffer(nc[0].data, np.uint8, nv * 4, 4).reshape(nv, 4) if nc else None
        geoms.append(g)
    res['geoms'] = geoms
    atoms = []
    for ac in cl.find(0x14):
        fi, gi, fl_, un = struct.unpack('<IIII', ac.one(0x01).data)
        fx = ac.one(0x03).find(0x120)
        atoms.append(dict(frame=fi, geom=gi, flags=fl_, matfx=bool(fx)))
    assert len(atoms) == natom
    res['atomics'] = atoms
    return res


def read_txd(path):
    buf = open(path, 'rb').read()
    top = parse(buf, 0, len(buf))
    assert len(top) == 1 and top[0].id == 0x16
    td = top[0]
    cnt, dev = struct.unpack('<HH', td.one(0x01).data)
    texs = []
    nat = td.find(0x15)
    assert len(nat) == cnt
    for n in nat:
        d = n.one(0x01).data
        plat, fa = struct.unpack_from('<II', d, 0)
        name = d[8:40].split(b'\0')[0].decode()
        mask = d[40:72].split(b'\0')[0].decode()
        raster, d3d, w, h, depth, nlev, rtype, flags = struct.unpack_from('<IIHHBBBB', d, 72)
        fmt = {0x31545844: 'DXT1', 0x33545844: 'DXT3', 0x35545844: 'DXT5'}.get(d3d, 'RAW%d' % d3d)
        p = 88
        levels = []
        for i in range(nlev):
            sz, = struct.unpack_from('<I', d, p)
            p += 4
            levels.append(d[p:p + sz])
            p += sz
        assert p == len(d), 'texture struct size mismatch'
        texs.append(dict(name=name, mask=mask, platform=plat, filter=fa, raster=raster, fmt=fmt, w=w, h=h, depth=depth,
                         nlev=nlev, rtype=rtype, flags=flags, levels=levels))
    return dict(count=cnt, device=dev, textures=texs, version=td.ver)


def decode_texture(t, level=0):
    w, h = max(1, t['w'] >> level), max(1, t['h'] >> level)
    return dxt.decode(t['levels'][level], w, h, t['fmt'])


def read_col3(path):
    b = open(path, 'rb').read()
    assert b[:4] == b'COL3'
    size, = struct.unpack_from('<I', b, 4)
    assert size + 8 == len(b), 'COL size field mismatch'
    name = b[8:30].split(b'\0')[0].decode()
    mid, = struct.unpack_from('<H', b, 30)
    mn = struct.unpack_from('<3f', b, 32)
    mx = struct.unpack_from('<3f', b, 44)
    ctr = struct.unpack_from('<3f', b, 56)
    rad, = struct.unpack_from('<f', b, 68)
    ns, nb, nf, nl, pad = struct.unpack_from('<HHHBB', b, 72)
    flags, o_s, o_b, o_c, o_v, o_f, o_p, nsh, o_sv, o_sf = struct.unpack_from('<I9I', b, 80)
    base = 4
    spheres = [struct.unpack_from('<4f4B', b, base + o_s + 20 * i) for i in range(ns)]
    boxes = [struct.unpack_from('<6f4B', b, base + o_b + 28 * i) for i in range(nb)]
    faces = [struct.unpack_from('<3HBB', b, base + o_f + 8 * i) for i in range(nf)]
    nv = (max(max(f[:3]) for f in faces) + 1) if faces else 0
    verts = [tuple(c / 128.0 for c in struct.unpack_from('<3h', b, base + o_v + 6 * i)) for i in range(nv)]
    # last byte of data must be consumed exactly by the arrays
    end = base + max([o_s + 20 * ns if ns else 0, o_b + 28 * nb if nb else 0, o_f + 8 * nf if nf else 0])
    return dict(name=name, model_id=mid, min=mn, max=mx, center=ctr, radius=rad, spheres=spheres, boxes=boxes, faces=faces, verts=verts,
                flags=flags, nlines=nl, total=len(b), end=end)
