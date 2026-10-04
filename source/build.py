# Created by: Arena.ai Agent Mode (AI) - NightCity MTA:SA asset pipeline
# -----------------------------------------------------------------------------
# build.py - one command build of the complete city:     python3 build.py
#   plan -> models (geometry + baked night vertex light) -> DFF / COL / TXD -> layout / models / sprites .lua -> meta.xml
#   -> audio.  Writes the ready to use MTA:SA resource  ../resource/NightCity/   (copy that folder to the server)
# The hand written scripts / shaders (client.lua, env.lua, tour.lua, server.lua, wet.fx, post.fx, sky.fx, water.fx) live
# here in source/ and are copied into the resource on every build (source/ is the single source of truth).
# Then run validate.py and mta_lua_test_nc.py.
# -----------------------------------------------------------------------------
import json
import os
import shutil
import sys
import time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from nc import plan as PLAN, registry, bake, textures as TX
from nc.texgen import REG
from lib import dxt, rwdff, rwtxd, colfile

OUT = os.path.abspath(os.path.join(HERE, '..'))
RES = os.path.join(OUT, 'resource', 'NightCity')
TXD_OF = {'g': 'ncg', 'b': 'ncb', 'i': 'nci', 's': 'nci'}
ALPHA_MATS = {'nc_glow', 'nc_steam'}
SRC_SCRIPTS = ['client.lua', 'env.lua', 'tour.lua', 'server.lua']
SRC_FX = ['wet.fx', 'post.fx', 'sky.fx', 'water.fx']
WS_SRC = ['meta.xml', 'env.lua', 'wetstreets.lua', 'wet.fx', 'post.fx', 'README.md']


def copy_wetstreets():
    """pack the standalone WetStreets companion resource (source/WetStreets -> resource/WetStreets)."""
    src = os.path.join(HERE, 'WetStreets')
    dst = os.path.join(OUT, 'resource', 'WetStreets')
    os.makedirs(dst, exist_ok=True)
    n = 0
    for f in WS_SRC:
        p = os.path.join(src, f)
        if os.path.isfile(p):
            shutil.copyfile(p, os.path.join(dst, f))
            n += 1
    print('WetStreets: %d files -> %s' % (n, dst))


def weld(pos, nrm, uv, dcol, tris):
    key = np.concatenate([np.round(pos * 1000).astype(np.int64), np.round(nrm * 60).astype(np.int64), np.round(uv * 4000).astype(np.int64), dcol.astype(np.int64)], axis=1)
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    inv = inv.reshape(-1)
    return pos[first], nrm[first], uv[first], dcol[first], inv[tris]


def build_geometry(pos, nrm, uv, tris, tmat, col):
    area = np.linalg.norm(np.cross(pos[tris[:, 1]] - pos[tris[:, 0]], pos[tris[:, 2]] - pos[tris[:, 0]]), axis=1)
    keep = area > 1e-9
    tris, tmat = tris[keep], tmat[keep]
    used, inv = np.unique(tris.reshape(-1), return_inverse=True)
    t2 = inv.reshape(-1, 3)
    c8 = np.concatenate([(col[used] * 255 + 0.5).astype(np.uint8), np.full((len(used), 1), 255, np.uint8)], 1)
    p, n, u, d, t3 = weld(pos[used], nrm[used], uv[used], c8, t2)
    mats = sorted(set(tmat.tolist()))
    remap = {m: i for i, m in enumerate(mats)}
    tm = np.array([remap[m] for m in tmat], np.int64)
    order = np.argsort(tm, kind='stable')
    assert len(p) < 65000, len(p)
    g = dict(pos=p, nrm=n, uv=u, tris=t3[order], tri_mat=tm[order], prelit=d, night=d.copy(), dyn_light=False)
    return g, mats


def build_col(C, name, bounds, nocol=False):
    verts, faces, vmap = [], [], {}

    def vid(p):
        k = tuple(int(round(c * 128)) for c in p)
        if k not in vmap:
            vmap[k] = len(verts)
            verts.append(np.array(k) / 128.0)
        return vmap[k]
    for cc in C.prisms:
        cc = np.asarray(cc, float)
        b, t = cc[:4], cc[4:]
        area = sum(b[i][0] * b[(i + 1) % 4][1] - b[(i + 1) % 4][0] * b[i][1] for i in range(4))
        if area < 0:
            b, t = b[::-1], t[::-1]
        ib = [vid(p) for p in b]
        it = [vid(p) for p in t]
        faces += [(ib[0], ib[2], ib[1], 0), (ib[0], ib[3], ib[2], 0), (it[0], it[1], it[2], 0), (it[0], it[2], it[3], 0)]
        for i in range(4):
            j = (i + 1) % 4
            faces += [(ib[i], ib[j], it[j], 0), (ib[i], it[j], it[i], 0)]
    for P, F, s in C.tris:
        for a, b_, c_ in F:
            ids = [vid(P[q]) for q in (a, b_, c_)]
            if len(set(ids)) == 3:
                faces.append((ids[0], ids[1], ids[2], int(s)))
    boxes = [(lo, hi, 0) for lo, hi in C.boxes]
    if nocol or (not boxes and not faces):
        boxes = [((-0.01, -0.01, -0.02), (0.01, 0.01, 0.0), 0)]
        verts, faces = [], []
    assert len(verts) < 32767 and len(faces) < 65535, (name, len(verts), len(faces))
    V = np.array(verts) if verts else None
    if V is not None:
        assert np.abs(V).max() < 255.9, (name, 'collision vertex outside the int16/128 range')
    # the bounding box / sphere GTA uses to cull collision tests must contain ALL collision geometry (slabs reach below the visible mesh,
    # tunnel walls and roof beyond the visible shell): union of the visible bounds and the collision primitives
    lo_, hi_ = np.array(bounds[0], float), np.array(bounds[1], float)
    for b in boxes:
        lo_, hi_ = np.minimum(lo_, b[0]), np.maximum(hi_, b[1])
    if V is not None:
        lo_, hi_ = np.minimum(lo_, V.min(0)), np.maximum(hi_, V.max(0))
    bounds = (lo_.tolist(), hi_.tolist())
    col = colfile.build_col3(name, 1337, [], boxes, V.tolist() if V is not None else None, faces if faces else None, bounds=bounds)
    return col, len(boxes), len(faces), len(verts)


def mat_chunk(name):
    return dict(tex=name, env=0, color=(255, 255, 255, 255), surface=(1.0, 0.0, 1.0))


def rot(x, y, rz):
    c, s = np.cos(np.radians(rz)), np.sin(np.radians(rz))
    return x * c - y * s, x * s + y * c


def main():
    t0 = time.time()
    copy_wetstreets()
    for d in ('files', 'files/audio', 'files/fx'):
        os.makedirs(os.path.join(RES, d), exist_ok=True)
    for f in os.listdir(os.path.join(RES, 'files')):
        p = os.path.join(RES, 'files', f)
        if os.path.isfile(p):
            os.remove(p)
    for f in SRC_SCRIPTS + SRC_FX:                     # the hand written files always come from source/
        shutil.copyfile(os.path.join(HERE, f), os.path.join(RES, f))
    os.makedirs(os.path.join(HERE, '_work'), exist_ok=True)
    print('[1/6] plan ...')
    plan = PLAN.build_plan()
    print('   %d models, %d placements, %d water rectangles' % (len(plan.models), len(plan.placements), len(plan.water)))
    names = list(plan.models)
    idx = {n: i + 1 for i, n in enumerate(names)}
    print('[2/6] models: geometry + baked night light ...')
    report, files, sprites_local, used_mats = [], [], {}, {}
    glow_stats = 0
    for k, name in enumerate(names):
        M, C, meta = registry.build_model(plan, name)
        pos, nrm, uv, tris, tmat, em, tn, mats = bake.flatten(M)
        col = bake.bake(pos, nrm, em, tn, M.lights, amb=float(meta.get('amb', 1.0)))
        g, used = build_geometry(pos, nrm, uv, tris, tmat, col)
        mnames = [mats[i] for i in used]
        assert not (set(mnames) & ALPHA_MATS), (name, mnames)
        lo, hi = pos.min(0), pos.max(0)
        cat = plan.models[name]['cat']
        used_mats.setdefault(TXD_OF[cat], set()).update(mnames)
        frames = [dict(name=name, pos=(0, 0, 0), parent=-1), dict(name=name + '_a', pos=(0, 0, 0), parent=0)]
        dff = rwdff.build_clump(frames, [g], [(1, 0, False)], [[mat_chunk(m) for m in mnames]])
        open(os.path.join(RES, 'files', name + '.dff'), 'wb').write(dff)
        colb, nb, nf, nv = build_col(C, name, (lo.tolist(), hi.tolist()), nocol=bool(meta.get('nocol')))
        open(os.path.join(RES, 'files', name + '.col'), 'wb').write(colb)
        files += [name + '.dff', name + '.col']
        sprites_local[name] = M.sprites
        plan.models[name].update(meta=meta, txd=TXD_OF[cat])
        report.append(dict(name=name, cat=cat, builder=plan.models[name]['builder'], hint=plan.models[name]['hint'], verts=int(len(g['pos'])), tris=int(len(g['tris'])),
                           materials=mnames, col_boxes=nb, col_faces=nf, dff=len(dff), col=len(colb), height=float(hi[2]), bbox=[lo.round(2).tolist(), hi.round(2).tolist()],
                           lights=len(M.lights), sprites=len(M.sprites), dist=float(meta.get('dist', 500.0))))
        if (k + 1) % 40 == 0:
            print('   %d / %d' % (k + 1, len(names)))
    print('   DFF %.1f MB   COL %.2f MB   %d vertices' % (sum(r['dff'] for r in report) / 1048576, sum(r['col'] for r in report) / 1048576, sum(r['verts'] for r in report)))
    print('[3/6] textures ...')
    txd_info = {}
    for txd, mset in sorted(used_mats.items()):
        lst = []
        for n in sorted(mset):
            p = TX.generate(n, 1)
            im = p.game_rgb()
            h, w = im.shape[:2]
            lst.append(dict(name=n, w=w, h=h, fmt='DXT1', chain=dxt.compress_chain(im, 'DXT1'), alpha=False))
        b = rwtxd.build_txd(lst)
        open(os.path.join(RES, 'files', txd + '.txd'), 'wb').write(b)
        files.append(txd + '.txd')
        txd_info[txd] = dict(bytes=len(b), textures=[(t['name'], t['w'], t['h'], t['fmt']) for t in lst])
        print('   %-4s %2d textures  %.2f MB' % (txd, len(lst), len(b) / 1048576))
    # sprite sheets for the client (PNG with alpha): glow, steam, sky noise
    from PIL import Image
    for n, f in (('nc_glow', 'glow'), ('nc_steam', 'steam'), ('nc_sky_noise', 'sky_noise')):
        p = TX.generate(n, 1)
        a = p.alpha if p.alpha is not None else np.ones(p.albedo.shape[:2], np.float32)
        rgba = np.concatenate([(np.clip(p.albedo, 0, 1) * 255).astype(np.uint8), (np.clip(a, 0, 1) * 255).astype(np.uint8)[..., None]], -1)
        Image.fromarray(rgba, 'RGBA').save(os.path.join(RES, 'files', 'fx', f + '.png'))
        files.append('fx/' + f + '.png')
    print('[4/6] audio ...')
    try:
        from nc import audio
        wavs = audio.make_all(os.path.join(RES, 'files', 'audio'))
    except ImportError:
        wavs = []
    files += ['audio/' + w for w in wavs]
    print('   ', ', '.join(wavs))
    print('[5/6] layout + lua ...')
    hdr = '-- Created by: Arena.ai Agent Mode (AI) - NightCity MTA:SA resource\n-- GENERATED by source/build.py - do not edit by hand\n'
    ml = [hdr + 'NC_MODELS = {', '    -- name, txd, draw distance (m), collision']
    for n in names:
        m = plan.models[n]
        ml.append('    { name = "%s", txd = "%s", dist = %.0f, col = %s },' % (n, m['txd'], m['meta'].get('dist', 500.0), 'false' if m['meta'].get('nocol') else 'true'))
    ml.append('}')
    open(os.path.join(RES, 'models.lua'), 'w').write('\n'.join(ml) + '\n')
    ll = [hdr + '-- city frame: origin = centre of the city, x east, y north, z = street level.  obj = { model index, x, y, z, rz [, tag] }', 'NC_OBJECTS = {']
    sp_rows = []
    for pl in plan.placements:
        ll.append('    { %d, %.2f, %.2f, %.2f, %.1f, "%s" },' % (idx[pl['model']], pl['x'], pl['y'], pl['z'], pl['rz'], pl['tag']))
        for s in sprites_local[pl['model']]:
            x, y = rot(s['p'][0], s['p'][1], pl['rz'])
            sp_rows.append((pl['x'] + x, pl['y'] + y, pl['z'] + s['p'][2], s['size'], s['c'], 1 if s['kind'] == 'glow' else 2))
    ll.append('}')
    ll.append('NC_WATER = {   -- axis aligned rectangles on the even integer grid: x0, y0, x1, y1, z')
    for (x0, y0, x1, y1, z) in plan.water:
        ll.append('    { %d, %d, %d, %d, %.2f },' % (x0, y0, x1, y1, z))
    ll.append('}')
    ll.append('NC_POINTS = {')
    for k, (x, y, z) in plan.points.items():
        ll.append('    %s = { %.1f, %.1f, %.1f },' % (k, x, y, z))
    ll.append('}')
    x0, y0, x1, y1 = plan.extent
    ll.append('NC_EXTENT = { x0 = %.1f, y0 = %.1f, x1 = %.1f, y1 = %.1f }' % (x0, y0, x1, y1))
    tg = plan.tunnel
    ll.append('-- the river road tunnel (x = axis, y0 / y1 = open cut mouths, cov0 / cov1 = covered part, zf = flat road level, hw = half width)')
    ll.append('NC_TUNNEL = { x = %.2f, y0 = %.2f, y1 = %.2f, cov0 = %.2f, cov1 = %.2f, zf = %.2f, hw = %.1f }' % (tg['x'], tg['y_in'], tg['y_out'], tg['y_cov0'], tg['y_cov1'], tg['z_floor'], 7.0))
    surf = {}
    for txdname, mset in used_mats.items():
        for n in mset:
            surf[n] = TX.surface_group(n)
    ll.append('-- texture name -> surface material class: one wet.fx shader instance per class (client.lua GROUP_PARAMS)')
    ll.append('NC_SURFACES = {')
    for n in sorted(surf):
        ll.append('    %s = "%s",' % (n, surf[n]))
    ll.append('}')
    ll.append('NC_TOUR = {   -- camera path: x, y, z (eye), tx, ty, tz (look at), seconds to the next key')
    for (x, y, z, tx, ty, tz, sec) in plan.tour:
        ll.append('    { %.1f, %.1f, %.1f, %.1f, %.1f, %.1f, %.1f },' % (x, y, z, tx, ty, tz, sec))
    ll.append('}')
    open(os.path.join(RES, 'layout.lua'), 'w').write('\n'.join(ll) + '\n')
    sl = [hdr + '-- billboards drawn by the client (dxDrawMaterialLine3D): x, y, z, size, r, g, b, kind (1 glow, 2 steam)', 'NC_SPRITES = {']
    for (x, y, z, size, c, k) in sp_rows:
        sl.append('{%.1f,%.1f,%.1f,%.1f,%.2f,%.2f,%.2f,%d},' % (x, y, z, size, c[0], c[1], c[2], k))
    sl.append('}')
    open(os.path.join(RES, 'sprites.lua'), 'w').write('\n'.join(sl) + '\n')
    print('   %d objects, %d sprites' % (len(plan.placements), len(sp_rows)))
    fx = [f for f in SRC_FX if os.path.exists(os.path.join(RES, f))]
    scripts = [('models.lua', 'client'), ('layout.lua', 'client'), ('sprites.lua', 'client'), ('env.lua', 'client'), ('client.lua', 'client'), ('tour.lua', 'client'),
               ('layout.lua', 'server'), ('server.lua', 'server')]
    mx = ['<!-- Created by: Arena.ai Agent Mode (AI) - NightCity MTA:SA resource -->', '<meta>',
          '    <info author="Arena.ai Agent Mode" name="NightCity" version="2.0.0" type="script"',
          '          description="NightCity - an empty, rain-soaked futuristic megacity with a full day / night and weather system (no people, no vehicles, no animals). Commands: /ncshow /nchide /nctour /ncfree /ncview /ncfx /ncquality /ncweather /nctime /ncdaycycle /ncwet /ncexposure /ncrain /ncz /ncempty /ncenv /ncinfo" />',
          '    <min_mta_version client="1.6.0-9.22676" />', '']
    for s, t in scripts:
        if os.path.exists(os.path.join(RES, s)):
            mx.append('    <script src="%s" type="%s" />' % (s, t))
    mx.append('')
    for f in fx:
        mx.append('    <file src="%s" />' % f)
    mx += ['    <file src="files/%s" />' % f for f in files] + ['</meta>']
    open(os.path.join(RES, 'meta.xml'), 'w').write('\n'.join(mx) + '\n')
    print('[6/6] report ...')
    json.dump(dict(models=report, txd=txd_info, objects=len(plan.placements), sprites=len(sp_rows), seconds=round(time.time() - t0, 1)), open(os.path.join(HERE, '_work', 'build_report.json'), 'w'), indent=1)
    json.dump(dict(files=files, models=names), open(os.path.join(HERE, '_work', 'files.json'), 'w'))
    total = sum(os.path.getsize(os.path.join(RES, 'files', f)) for f in files if os.path.exists(os.path.join(RES, 'files', f)))
    print('resource files: %.1f MB   done in %.1fs' % (total / 1048576, time.time() - t0))


if __name__ == '__main__':
    main()
