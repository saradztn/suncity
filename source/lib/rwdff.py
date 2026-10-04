# Created by: Arena.ai Agent Mode (AI) - Park MTA:SA asset pipeline
# -----------------------------------------------------------------------------
# rwdff.py - RenderWare 3.6.0.3 (GTA San Andreas, 0x1803FFFF) DFF clump writer.
#
# Layout (identical to what the GTA SA / MTA:SA loader expects):
#   Clump
#     Struct(numAtomics, 0 lights, 0 cameras)
#     FrameList  -> Struct + one Extension{Frame name 0x253F2FE} per frame
#     GeometryList -> Struct + Geometry*
#         Geometry -> Struct(flags, tris, verts, 1 morph target [sphere, verts, normals])
#                     MaterialList -> Struct + Material* (Texture + Extension{MatFX env-map})
#                     Extension{ BinMesh PLG 0x50E, Extra Vert Colour 0x253F2F9 }
#     Atomic* -> Struct(frame, geometry, flags=5, 0) + Extension{MatFX enable}
#     Extension
# -----------------------------------------------------------------------------
import struct
import numpy as np

RW_VERSION = 0x1803FFFF            # 3.6.0.3 (San Andreas)

ID_STRUCT, ID_STRING, ID_EXT, ID_TEXTURE, ID_MATERIAL, ID_MATLIST = 0x01, 0x02, 0x03, 0x06, 0x07, 0x08
ID_FRAMELIST, ID_GEOMETRY, ID_CLUMP, ID_ATOMIC, ID_GEOLIST = 0x0E, 0x0F, 0x10, 0x14, 0x1A
ID_MATFX, ID_BINMESH, ID_FRAMENAME, ID_NIGHTCOL = 0x120, 0x50E, 0x253F2FE, 0x253F2F9

FLAG_POSITIONS, FLAG_TEXTURED, FLAG_PRELIT, FLAG_NORMALS, FLAG_LIGHT, FLAG_MODULATE = 0x02, 0x04, 0x08, 0x10, 0x20, 0x40


def chunk(cid, payload, ver=RW_VERSION):
    return struct.pack('<III', cid, len(payload), ver) + payload


def struct_chunk(payload):
    return chunk(ID_STRUCT, payload)


def ext(payload=b''):
    return chunk(ID_EXT, payload)


def string_chunk(s):
    b = s.encode('ascii') + b'\0'
    b += b'\0' * ((-len(b)) % 4)
    return chunk(ID_STRING, b)


def texture_chunk(name, filter_mode=0x06, addressing=0x11):
    st = struct_chunk(struct.pack('<I', filter_mode | (addressing << 8)))
    return chunk(ID_TEXTURE, st + string_chunk(name) + string_chunk('') + ext())


def matfx_env(texname, coef):
    pl = struct.pack('<II', 2, 2)                              # material fx type = env map, effect slot 0 = env map
    pl += struct.pack('<fII', coef, 0, 1)                       # coefficient, use frame-buffer alpha, has texture
    pl += texture_chunk(texname)
    pl += struct.pack('<I', 0)                                  # effect slot 1 = none
    return chunk(ID_MATFX, pl)


def material_chunk(m):
    """m: dict(tex, color(rgba), env(coef), env_tex, surface=(amb,spec,diff))"""
    amb, spec, dif = m.get('surface', (1.0, 0.0, 1.0))
    r, g, b, a = m.get('color', (255, 255, 255, 255))
    st = struct.pack('<IBBBBIIfff', 0, r, g, b, a, 0, 1 if m.get('tex') else 0, amb, spec, dif)
    body = struct_chunk(st)
    if m.get('tex'):
        body += texture_chunk(m['tex'])
    e = matfx_env(m['env_tex'], m['env']) if m.get('env', 0) > 0 else b''
    body += ext(e)
    return chunk(ID_MATERIAL, body)


def geometry_chunk(g, materials):
    """g: dict(pos Nx3, nrm Nx3, uv Nx2, tris Mx3 int, tri_mat M int, prelit Nx4 uint8, night Nx4 uint8)"""
    pos = np.asarray(g['pos'], np.float32)
    nrm = np.asarray(g['nrm'], np.float32)
    uv = np.asarray(g['uv'], np.float32)
    tris = np.asarray(g['tris'], np.int64)
    tmat = np.asarray(g['tri_mat'], np.int64)
    n, mT = len(pos), len(tris)
    assert n < 65536, 'vertex count exceeds 16-bit index range'
    has_pre = g.get('prelit') is not None     # None -> no vertex colours: lit dynamically by the game (like weapons/peds)
    dyn = g.get('dyn_light', not has_pre)       # prelit (baked) geometry: no dynamic RW lighting on top of the baked colours
    flags = FLAG_POSITIONS | FLAG_TEXTURED | (FLAG_PRELIT if has_pre else 0) | FLAG_NORMALS | (FLAG_LIGHT if dyn else 0) | FLAG_MODULATE | (1 << 16)
    d = struct.pack('<IIII', flags, mT, n, 1)
    if has_pre:
        d += np.asarray(g['prelit'], np.uint8).tobytes()
    d += uv.astype('<f4').tobytes()
    t = np.zeros((mT, 4), '<u2')
    # RW stores faces as [v2, v1, material, v3] of the CCW triangle (v1, v2, v3)
    t[:, 0] = tris[:, 1]
    t[:, 1] = tris[:, 0]
    t[:, 2] = tmat
    t[:, 3] = tris[:, 2]
    d += t.tobytes()
    lo, hi = pos.min(0), pos.max(0)
    c = (lo + hi) / 2
    rad = float(np.linalg.norm(pos - c, axis=1).max())
    d += struct.pack('<ffffII', c[0], c[1], c[2], rad, 1, 1)
    d += pos.astype('<f4').tobytes() + nrm.astype('<f4').tobytes()
    geo = struct_chunk(d)
    # material list
    ml = struct.pack('<I', len(materials)) + struct.pack('<%di' % len(materials), *([-1] * len(materials)))
    mlc = struct_chunk(ml) + b''.join(material_chunk(m) for m in materials)
    geo += chunk(ID_MATLIST, mlc)
    # extension: bin mesh (triangle lists grouped by material) + night colours
    bm = b''
    nm = 0
    tot = 0
    for mi in range(len(materials)):
        sel = np.nonzero(tmat == mi)[0]
        if len(sel) == 0:
            continue
        idx = tris[sel].reshape(-1)
        bm += struct.pack('<II', len(idx), mi) + idx.astype('<u4').tobytes()
        nm += 1
        tot += len(idx)
    ex = chunk(ID_BINMESH, struct.pack('<III', 0, nm, tot) + bm)
    if g.get('night') is not None:
        ex += chunk(ID_NIGHTCOL, struct.pack('<I', 1) + np.asarray(g['night'], np.uint8).tobytes())
    geo += ext(ex)
    return chunk(ID_GEOMETRY, geo)


def build_clump(frames, geoms, atomics, materials_per_geom):
    """frames: list of dict(name, pos(3), parent)
    geoms: list of geometry dicts; atomics: list of (frame_index, geometry_index, uses_matfx)"""
    out = struct_chunk(struct.pack('<III', len(atomics), 0, 0))
    fl = struct.pack('<I', len(frames))
    for f in frames:
        fl += struct.pack('<9f', 1, 0, 0, 0, 1, 0, 0, 0, 1)
        fl += struct.pack('<3f', *f['pos'])
        fl += struct.pack('<iI', f['parent'], 0x00020003)
    fl = struct_chunk(fl)
    for f in frames:
        fl += ext(chunk(ID_FRAMENAME, f['name'].encode('ascii')))
    out += chunk(ID_FRAMELIST, fl)
    gl = struct_chunk(struct.pack('<I', len(geoms)))
    for g, mats in zip(geoms, materials_per_geom):
        gl += geometry_chunk(g, mats)
    out += chunk(ID_GEOLIST, gl)
    for fi, gi, fx in atomics:
        a = struct_chunk(struct.pack('<IIII', fi, gi, 0x5, 0))
        a += ext(chunk(ID_MATFX, struct.pack('<I', 1)) if fx else b'')
        out += chunk(ID_ATOMIC, a)
    out += ext()
    return chunk(ID_CLUMP, out)
