# Created by: Arena.ai Agent Mode (AI) - Park MTA:SA asset pipeline
# -----------------------------------------------------------------------------
# colfile.py - GTA San Andreas COL3 writer (spheres + boxes [+ optional mesh]).
# Header / offsets follow gtamods.com "Collision File": offsets are relative to the
# byte after the FourCC, version 3 header is 120 bytes.
# -----------------------------------------------------------------------------
import struct
import numpy as np


def surface(material=0, flag=0, brightness=0, light=0):
    return struct.pack('<BBBB', material, flag, brightness, light)


def build_col3(name, model_id, spheres, boxes, verts=None, faces=None, bounds=None):
    """spheres: [(cx,cy,cz,r,mat)], boxes: [(minxyz, maxxyz, mat)], verts Nx3 float, faces Mx(a,b,c,mat)"""
    verts = [] if verts is None else verts
    faces = [] if faces is None else faces
    pts = []
    for cx, cy, cz, r, _ in spheres:
        pts += [(cx - r, cy - r, cz - r), (cx + r, cy + r, cz + r)]
    for lo, hi, _ in boxes:
        pts += [tuple(lo), tuple(hi)]
    for v in verts:
        pts.append(tuple(v))
    P = np.array(pts, np.float64)
    lo, hi = P.min(0), P.max(0)
    ctr = (lo + hi) / 2
    rad = 0.0
    for cx, cy, cz, r, _ in spheres:
        rad = max(rad, float(np.linalg.norm(np.array([cx, cy, cz]) - ctr)) + r)
    for l, h_, _ in boxes:
        for cx in (l[0], h_[0]):
            for cy in (l[1], h_[1]):
                for cz in (l[2], h_[2]):
                    rad = max(rad, float(np.linalg.norm(np.array([cx, cy, cz]) - ctr)))
    for v in verts:
        rad = max(rad, float(np.linalg.norm(np.array(v) - ctr)))
    if bounds is not None:                      # explicit bounds (stub COL that must cull like the full model)
        lo, hi = np.array(bounds[0], np.float64), np.array(bounds[1], np.float64)
        ctr = (lo + hi) / 2
        rad = float(np.linalg.norm(hi - ctr))

    body = b''
    off_sph = 120 - 4
    for cx, cy, cz, r, m in spheres:
        body += struct.pack('<ffff', cx, cy, cz, r) + surface(m)
    off_box = off_sph + len(body)
    for l, h_, m in boxes:
        body += struct.pack('<6f', *l, *h_) + surface(m)
    off_vert = off_sph + len(body)
    for v in verts:
        body += struct.pack('<3h', *[int(round(c * 128.0)) for c in v])
    if len(verts) * 6 % 4:
        body += b'\0\0'
    off_face = off_sph + len(body)
    for a, b, c, m in faces:
        body += struct.pack('<HHHBB', a, b, c, m, 0)
    if not spheres:
        off_sph = 0
    if not boxes:
        off_box = 0
    if not verts:
        off_vert = 0
    if not faces:
        off_face = 0
    flags = 0x02 if (spheres or boxes or faces) else 0
    hdr = struct.pack('<4sI', b'COL3', 0)
    hdr += name.encode('ascii')[:21].ljust(22, b'\0')
    hdr += struct.pack('<H', model_id)
    hdr += struct.pack('<10f', *lo, *hi, *ctr, rad)
    hdr += struct.pack('<HHHBB', len(spheres), len(boxes), len(faces), 0, 0)
    hdr += struct.pack('<I', flags)
    hdr += struct.pack('<6I', off_sph, off_box, 0, off_vert, off_face, 0)
    hdr += struct.pack('<III', 0, 0, 0)
    assert len(hdr) == 120, len(hdr)
    data = hdr + body
    return struct.pack('<4sI', b'COL3', len(data) - 8) + data[8:]
