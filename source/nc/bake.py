# Created by: Arena.ai Agent Mode (AI) - NightCity MTA:SA asset pipeline
# -----------------------------------------------------------------------------
# bake.py - flatten a Mesh and bake the night vertex lighting: cool city-glow ambient, local lights (street lamps,
#           signs, shop windows, beacons) with distance falloff, emissive surfaces forced to full brightness.
# The day colour set is identical to the night set (the city lives at midnight; changing the clock must not flip it).
# -----------------------------------------------------------------------------
import numpy as np

AMB = np.array([0.50, 0.54, 0.70])          # moonless, cloud-reflected city glow (vertex colour multiplies the texture)


def flatten(M):
    """-> pos, nrm, uv, tris, tri_mat (index into mats), vertex emis, vertex tint (or -1), mats"""
    mats = M.materials()
    mi = {m: i for i, m in enumerate(mats)}
    pos, nrm, uv, tris, tmat, emis, tint = [], [], [], [], [], [], []
    off = 0
    for p, n, u, t, m, e, tn in M.chunks:
        pos.append(p)
        nrm.append(n)
        uv.append(u)
        tris.append(t + off)
        tmat.append(np.full(len(t), mi[m], np.int64))
        emis.append(np.full(len(p), e))
        tint.append(np.tile(np.array(tn if tn is not None else (-1.0, -1.0, -1.0)), (len(p), 1)))
        off += len(p)
    return (np.concatenate(pos), np.concatenate(nrm), np.concatenate(uv), np.concatenate(tris), np.concatenate(tmat),
            np.concatenate(emis), np.concatenate(tint), mats)


def bake(pos, nrm, emis, tint, lights, ground=False, amb=1.0):
    n = len(pos)
    hemi = 0.62 + 0.38 * (nrm[:, 2] * 0.5 + 0.5)
    col = AMB[None, :] * hemi[:, None] * amb          # amb < 1: enclosed spaces (tunnel tube) get less of the city glow
    # street canyon: surfaces close to the ground are a little darker, high surfaces catch more of the glow
    col *= np.clip(0.80 + 0.20 * np.clip(pos[:, 2] / 30.0, 0, 1), 0.8, 1.0)[:, None]
    for L in lights:
        lp = np.array(L['p'])
        d = lp[None, :] - pos
        dist = np.linalg.norm(d, axis=1)
        r = L['r']
        sel = dist < r
        if not sel.any():
            continue
        dd = d[sel] / np.maximum(dist[sel], 1e-6)[:, None]
        fall = (1.0 - dist[sel] / r) ** 2
        surf = np.clip(np.einsum('ij,ij->i', nrm[sel], dd), 0.0, 1.0) * 0.85 + 0.15
        w = fall * surf * L['i']
        if L['n'] is not None:                                      # directional emitters (signs, lamp heads): cosine lobe
            nl = np.array(L['n'])
            cosang = np.clip(-np.einsum('ij,j->i', dd, nl), 0, 1)
            w = w * (0.25 + 0.75 * cosang ** 0.8)
        col[sel] += w[:, None] * np.array(L['c'])[None, :] * 0.9
    col = np.clip(col, 0, 1)
    tn = np.where(tint[:, :1] < 0, 1.0, tint)
    e = np.clip(emis, 0, 1)[:, None]
    col = col * (1 - e) + tn * e
    return np.clip(col, 0, 1)
