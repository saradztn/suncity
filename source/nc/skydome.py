# Created by: Arena.ai Agent Mode (AI) - NightCity MTA:SA asset pipeline
# -----------------------------------------------------------------------------
# skydome.py - the sky dome model: a UV sphere (radius 1, sky.fx places it on the far plane),
# winding + normals face INWARD so it is visible from the centre (the camera).
# The client repositions the object on the camera every frame; the shader ignores the texture
# colour and evaluates the analytic sky / sun / clouds from the view direction (the texture is
# only the tileable noise field the cloud layers sample).
# -----------------------------------------------------------------------------
import numpy as np
from .mb import Mesh, Col


def sky_dome(segs=32, rings=16):
    verts = [(0.0, 0.0, 1.0)]                     # north pole
    uvs = [(0.5, 0.0)]
    for j in range(1, rings):
        phi = np.pi * j / rings
        sp, cp = np.sin(phi), np.cos(phi)
        for i in range(segs):
            th = 2.0 * np.pi * i / segs
            verts.append((float(sp * np.cos(th)), float(sp * np.sin(th)), float(cp)))
            uvs.append((i / segs, j / rings))
    south = len(verts)
    verts.append((0.0, 0.0, -1.0))                # south pole
    uvs.append((0.5, 1.0))
    tris = []
    for i in range(segs):                         # north cap: winding reversed (faces inward)
        tris.append((0, 1 + (i + 1) % segs, 1 + i))
    for j in range(rings - 2):                    # quad bands (winding faces inward)
        r0, r1 = 1 + j * segs, 1 + (j + 1) * segs
        for i in range(segs):
            a, b = r0 + i, r0 + (i + 1) % segs
            c, d = r1 + i, r1 + (i + 1) % segs
            tris.append((a, b, c))
            tris.append((b, d, c))
    r0 = 1 + (rings - 2) * segs                   # south cap
    for i in range(segs):
        tris.append((south, r0 + i, r0 + (i + 1) % segs))
    pos = np.array(verts, np.float64)
    nrm = -pos                                    # inward normals (visible from the centre)
    uv = np.array(uvs, np.float64)
    M, C = Mesh(), Col()
    M.add(pos, nrm, uv, np.array(tris, np.int64), 'nc_sky_noise', emis=1.0)
    return M, C, dict(kind='skydome', nocol=True, dist=400.0, amb=1.0)
