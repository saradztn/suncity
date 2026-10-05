# Created by: Arena.ai Agent Mode (AI) - structural validation of the NightCity MTA:SA resource (no rendering of any kind)
# -----------------------------------------------------------------------------
# Reads the FINISHED resource files (not the generator) and checks everything that can be checked without a game client:
#   meta.xml vs files on disk, Lua syntax + API names, shaders (lint + optional Slang front-end), TXD / DFF / COL parse and limits,
#   unit normals / winding / duplicate faces / index ranges, materials vs TXD, forbidden names (people, vehicles, animals), layout
#   (indices, bounds, ground cells tile the map without overlap or gap, water, points, tour), the river tunnel (road continuity from
#   part to part, shell faces the axis, cut-outs and collision), budgets (objects, vertices, size).
#     python3 validate.py            structural checks
#     python3 validate.py --lua      ... and the full headless Lua session test (mta_lua_test_nc.py)
#     python3 validate.py --librw    ... and the reference RenderWare loader on every DFF (needs /tmp/librw_check, see tools/)
# Exit code 0 = everything passed.
# -----------------------------------------------------------------------------
import glob
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
import numpy as np
from lupa import lua51

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.environ.get('NC_RES') or os.path.join(HERE, '..', 'resource', 'NightCity')
FILES = os.path.join(RES, 'files')
sys.path.insert(0, HERE)
from lib import readers

fails, warns = [], []
npass = [0]


def check(c, msg):
    if c:
        npass[0] += 1
    else:
        fails.append(msg)
        print('  [FAIL] ' + msg)
    return c


def ok(msg):
    print('  [ ok ] ' + msg)


def warn(msg):
    warns.append(msg)
    print('  [warn] ' + msg)


def section(t):
    print('\n== %s ==' % t)


def rd(f):
    return open(os.path.join(RES, f), encoding='utf8').read()


# ====================================================================================================================================
section('meta.xml')
meta = ET.parse(os.path.join(RES, 'meta.xml')).getroot()
scripts = [(e.get('src'), e.get('type')) for e in meta.findall('script')]
mfiles = [e.get('src') for e in meta.findall('file')]
check(len(set(mfiles)) == len(mfiles), 'no <file> listed twice')
check(all(os.path.exists(os.path.join(RES, f)) for f in mfiles + [s for s, _ in scripts]), 'every listed script / file exists')
on_disk = set()
for root_, _, fs in os.walk(FILES):
    for f in fs:
        on_disk.add(os.path.relpath(os.path.join(root_, f), RES).replace(os.sep, '/'))
on_disk |= {f for f in os.listdir(RES) if f.endswith('.fx')}
check(on_disk == set(mfiles), 'meta.xml lists exactly the files on disk (%d files)' % len(mfiles))
check(('client.lua', 'client') in scripts and ('server.lua', 'server') in scripts and ('tour.lua', 'client') in scripts and ('metro.lua', 'client') in scripts, 'client, metro, tour and server scripts declared')
order = [s for s, t in scripts if t == 'client']
check(order.index('models.lua') < order.index('layout.lua') < order.index('sprites.lua') < order.index('env.lua') < order.index('client.lua') < order.index('metro.lua') < order.index('tour.lua'), 'client script order: data before logic, env before its users, metro / tour after client')
check(meta.find('min_mta_version') is not None and meta.find('min_mta_version').get('client'), 'min_mta_version (client) declared')
lay = rd('layout.lua')
check('NC_METRO' in lay and 'NC_TUNNEL' in lay, 'layout.lua exports NC_METRO and NC_TUNNEL for the runtimes')
check(meta.find('info').get('name') == 'NightCity', 'resource info present')

# ====================================================================================================================================
section('Lua')
L = lua51.LuaRuntime(unpack_returned_tuples=True)
chk = L.eval('function(s, n) local f, e = loadstring(s, n) if f then return true, "" end return false, e end')
for f in sorted({s for s, _ in scripts}):
    good, err = chk(rd(f), f)
    check(good, 'Lua 5.1 syntax of %s %s' % (f, err))
import mta_lua_static
problems = []
for files, api, label in ((['models.lua', 'layout.lua', 'sprites.lua', 'env.lua', 'client.lua', 'metro.lua', 'tour.lua'], mta_lua_static.CLIENT_API, 'client'), (['layout.lua', 'server.lua'], mta_lua_static.SERVER_API, 'server')):
    p, used, _ = mta_lua_static.check(files, api, label)
    problems += p
    ok('%s: %d distinct MTA functions, all exist in the MTA %s API' % (label, len(used), label) if not p else '%s: problems' % label)
check(not problems, 'static Lua check: no undefined globals / wrong-side calls / unknown MTA functions %s' % problems[:3])
check('goto ' not in rd('client.lua') and '//' not in re.sub(r'--.*', '', rd('client.lua')).replace('"//', ''), 'no Lua 5.2+ syntax')

# the data files, loaded for the checks below
env = L.eval('function(src) local e = {} local f = loadstring(src) setfenv(f, e) f() return e end')
D = {}
for f in ('models.lua', 'layout.lua', 'sprites.lua'):
    D.update({k: v for k, v in env(rd(f)).items()})
MODELS = [D['NC_MODELS'][i] for i in range(1, len(D['NC_MODELS']) + 1)]
OBJECTS = [[D['NC_OBJECTS'][i][j] for j in range(1, 7)] for i in range(1, len(D['NC_OBJECTS']) + 1)]
WATER = [[D['NC_WATER'][i][j] for j in range(1, 6)] for i in range(1, len(D['NC_WATER']) + 1)]
POINTS = {k: [v[1], v[2], v[3]] for k, v in D['NC_POINTS'].items()}
EXT = dict(D['NC_EXTENT'].items())
TOUR = [[D['NC_TOUR'][i][j] for j in range(1, 8)] for i in range(1, len(D['NC_TOUR']) + 1)]
TUN = dict(D['NC_TUNNEL'].items())
N_SPRITES = len(D['NC_SPRITES'])
ok('%d models, %d objects, %d water quads, %d points, %d tour keys, %d sprites' % (len(MODELS), len(OBJECTS), len(WATER), len(POINTS), len(TOUR), N_SPRITES))

# ====================================================================================================================================
section('shaders')
HLSL_TYPES = set('float float2 float3 float4 float2x2 float3x3 float4x4 int bool void texture sampler sampler_state struct string technique pass compile return if else for while static const uniform in out inout true false'.split())
HLSL_STATES = set('Texture MinFilter MagFilter MipFilter AddressU AddressV MaxAnisotropy Linear Point Anisotropic None Clamp Wrap VertexShader PixelShader vs_2_0 vs_3_0 ps_2_0 ps_3_0'.split())
INTRINSICS = set('abs acos all any asin atan atan2 ceil clamp clip cos cosh cross ddx ddy degrees determinant distance dot exp exp2 floor fmod frac frexp isfinite isinf isnan ldexp length lerp lit log log10 log2 max min modf mul normalize pow radians reflect refract round rsqrt saturate sign sin sincos sinh smoothstep sqrt step tan tanh tex1D tex2D tex2Dlod tex2Dbias tex3D texCUBE transpose trunc'.split())
SEMANTICS = set('WORLD VIEW PROJECTION WORLDVIEWPROJECTION VIEWPROJECTION WORLDVIEW VIEWINVERSE CAMERAPOSITION CAMERADIRECTION TIME POSITION0 NORMAL0 COLOR0 TEXCOORD0 TEXCOORD1 TEXCOORD2 TEXCOORD3'.split())
FX = {}
for fx in sorted(f for f in os.listdir(RES) if f.endswith('.fx')):
    src = rd(fx)
    code = re.sub(r'/\*.*?\*/', '', re.sub(r'//[^\n]*', '', src), flags=re.S)
    FX[fx] = code
    check(code.count('{') == code.count('}') and code.count('(') == code.count(')'), '%s: balanced braces and parentheses' % fx)
    check(re.search(r'technique\s+tec0', code) is not None and re.search(r'technique\s+fallback', code) is not None, '%s: technique tec0 plus an empty fallback technique' % fx)
    targets = re.findall(r'compile\s+(\w+)\s+(\w+)\(', code)
    funcs = set(re.findall(r'^\s*\w+\s+(\w+)\s*\(', code, re.M))
    check(targets and all(t in ('vs_2_0', 'vs_3_0', 'ps_2_0', 'ps_3_0') and fn in funcs for t, fn in targets), '%s: compile targets %s refer to defined functions' % (fx, targets))
    vs = [t for t, _ in targets if t.startswith('vs')]
    ps = [t for t, _ in targets if t.startswith('ps')]
    check(not vs or (vs[0][3:] == ps[0][3:]), '%s: vertex and pixel shader models match' % fx)
    # declared names
    declared = set(re.findall(r'\b(?:float\d?(?:x\d)?|int|bool|texture|sampler|struct)\s+(\w+)', code))
    declared |= set(re.findall(r'^\s*\w+\s+(\w+)\s*\(', code, re.M))                     # functions
    declared |= set(re.findall(r'\b(?:technique|pass)\s+(\w+)', code))                      # technique / pass names
    declared |= set(re.findall(r'[(,]\s*(?:in\s+|out\s+)?\w+\s+(\w+)\s*(?::\s*\w+)?\s*(?=[,)])', code))       # parameters
    for blk in re.findall(r'struct\s+\w+\s*\{([^}]*)\}', code):
        declared |= set(re.findall(r'\w+\s+(\w+)\s*:', blk))
    toks = re.findall(r'(?<![\w.])([A-Za-z_]\w*)\b', re.sub(r'"[^"]*"', '', re.sub(r'<[^>]*>', '', code)))
    unknown = sorted({t for t in toks if t not in declared and t not in HLSL_TYPES and t not in HLSL_STATES and t not in INTRINSICS and t not in SEMANTICS
                      and not re.match(r'^(float\d?(x\d)?|VSInput|VSOutput|PSInput)$', t) and not re.match(r'^[A-Z][A-Z0-9_]*\d?$', t)})
    check(not unknown, '%s: every identifier is declared, an intrinsic or a keyword %s' % (fx, unknown[:6]))
    for s in re.findall(r'tex2D\s*\(\s*(\w+)', code):
        check(re.search(r'sampler\s+%s\s*=\s*sampler_state' % s, code) is not None, '%s: tex2D uses declared sampler %s' % (fx, s))
    # fxc rejects the two-argument form of atan in older profiles (it is atan2 there) - this broke sky.fx in-game once
    for m in re.finditer(r'\batan\s*\(', code):
        close = code.find(')', m.end())
        seg = code[m.end():close if close > 0 else m.end() + 40]
        check(',' not in seg, '%s: atan() takes one argument - use atan2() for the two-argument form' % fx)
    # ps_2_0 allows only 64 arithmetic slots and MTA compiles EVERY technique when the effect loads:
    # a fat ps_2_0 function kills the whole shader even on shader model 3 cards
    for fn in sorted(set(re.findall(r'compile\s+ps_2_0\s+(\w+)\s*\(', code))):
        i = code.find('float4 %s(' % fn)
        body = code[i:code.find('\n}', i)] if i >= 0 else ''
        heavy = len(re.findall(r'\b(?:pow|sin|cos|tan|asin|acos|atan2?|exp2?|log2?|sqrt|rsq|rcp|normalize|reflect|smoothstep)\s*\(', body))
        if heavy > 12:
            warn('%s: %s (ps_2_0 target) has %d transcendental/geometry calls - keep it under the 64-slot ps_2_0 budget' % (fx, fn, heavy))
        else:
            ok('%s: %s is lean enough for the ps_2_0 target (%d transcendental calls)' % (fx, fn, heavy))
    for sem in re.findall(r':\s*([A-Z]+\d?)\s*[;,)]', code):
        check(sem in SEMANTICS or sem.startswith('COLOR') or sem.startswith('TEXCOORD'), '%s: semantic %s is known' % (fx, sem))
    # shader inputs the script sets must exist
cl = rd('client.lua') + '\n' + rd('env.lua')
fxvars = {fx: set(re.findall(r'^(?:float\d?(?:x\d)?|texture|int|bool)\s+(\w+)\s*[:=;<]', FX[fx], re.M)) for fx in FX}
for var in sorted(set(re.findall(r'dxSetShaderValue\(\s*[\w.]+,\s*"(\w+)"', cl))):
    check(any(var in v for v in fxvars.values()), 'the scripts set the shader variable "%s" which exists in a .fx file' % var)
# vertex output <-> pixel input of wet.fx
m_vs = re.search(r'struct\s+VSOutput\s*\{([^}]*)\}', FX['wet.fx'])
m_ps = re.search(r'struct\s+PSInput\s*\{([^}]*)\}', FX['wet.fx'])
sem_vs = set(re.findall(r':\s*(\w+)\s*;', m_vs.group(1)))
sem_ps = set(re.findall(r':\s*(\w+)\s*;', m_ps.group(1)))
check(sem_ps <= sem_vs, 'wet.fx: every pixel shader input is produced by the vertex shader (%s)' % sorted(sem_ps - sem_vs))
# Slang front-end (type checks the function bodies), optional
try:
    import slangpy
    dev = slangpy.Device(type=slangpy.DeviceType.cpu, enable_debug_layers=False)
    sess = dev.slang_session
    for fx, code in FX.items():
        s = code
        s = re.sub(r'technique\s+\w+\s*\{(?:[^{}]|\{[^{}]*\})*\}', '', s)
        samplers = re.findall(r'sampler\s+(\w+)\s*=\s*sampler_state', s)
        s = re.sub(r'sampler\s+\w+\s*=\s*sampler_state\s*\{[^}]*\}\s*;', '', s)
        s = re.sub(r'texture\s+\w+\s*(?:<[^>]*>)?\s*;', '', s)
        s = re.sub(r'^((?:float\d?(?:x\d)?)\s+\w+)\s*:\s*\w+\s*;', r'\1;', s, flags=re.M)
        s = re.sub(r'tex2D\(\s*(\w+)\s*,', r'T_\1.Sample(S_\1,', s)
        s = ''.join('Texture2D T_%s; SamplerState S_%s;\n' % (n, n) for n in samplers) + s
        try:
            sess.load_module_from_source('fx_' + fx.replace('.', '_'), s)
            check(True, '%s: type-checked by the Slang compiler front-end' % fx)
            ok('%s: type-checked by the Slang compiler front-end (types, intrinsics, swizzles, undeclared names)' % fx)
        except Exception as e:                      # SlangCompileError
            check(False, '%s: Slang front-end rejected the shader: %s' % (fx, str(e)[:400]))
except ImportError:
    warn('slangpy not installed: shader bodies were only linted (pip install slangpy for a real type check)')

# ====================================================================================================================================
section('textures (TXD)')
TXD = {}
for p in sorted(glob.glob(os.path.join(FILES, '*.txd'))):
    t = readers.read_txd(p)
    names = [x['name'] for x in t['textures']]
    TXD[os.path.basename(p)[:-4]] = {x['name']: x for x in t['textures']}
    check(len(set(names)) == len(names), '%s: no duplicate texture names' % os.path.basename(p))
    bad = []
    for x in t['textures']:
        w, h = x['w'], x['h']
        full = int(np.log2(max(w, h))) + 1
        if not (w & (w - 1) == 0 and h & (h - 1) == 0) or x['fmt'] != 'DXT1' or x['nlev'] != full or len(x['name']) > 23:
            bad.append(x['name'])
    check(not bad, '%s: %d textures, power-of-two DXT1 with a full mip chain, names < 24 chars %s' % (os.path.basename(p), len(names), bad[:4]))
    mx = max(max(x['w'], x['h']) for x in t['textures'])
    ok('%s: %d textures, largest %d px, %.2f MB' % (os.path.basename(p), len(names), mx, os.path.getsize(p) / 1048576))
used_tex = set()

# ====================================================================================================================================
section('models (DFF / COL)')
FORBID = set('car cars vehicle vehicles bike bikes bicycle motorbike motorcycle truck trucks bus taxi van ped peds person people human humans man woman men women child '
             'pedestrian crowd animal animals dog dogs cat cats bird birds crow rat rats horse pigeon gull zombie drone drones aircar hovercar skimmer plane helicopter'.split())
tot_v = tot_t = 0
stats = dict(bad_wind=0, zero_n=0, dup_same=0, nan=0, badidx=0, big_uv=0, maxv=0)
col_stats = dict(maxv=0, maxf=0)
BBOX = {}
for i, m in enumerate(MODELS):
    name, txd = m['name'], m['txd']
    d = readers.read_dff(os.path.join(FILES, name + '.dff'))
    g = d['geoms'][0]
    P, N, UV, T, tm = g['pos'].astype(float), g['nrm'].astype(float), g['uv'].astype(float), g['tris'], g['tri_mat']
    mats = [mm['tex']['name'] for mm in g['materials']]
    tot_v += len(P)
    tot_t += len(T)
    stats['maxv'] = max(stats['maxv'], len(P))
    BBOX[name] = (P.min(0), P.max(0))
    used_tex |= {(txd, mt) for mt in mats}
    if len(d['geoms']) != 1 or len(d['atomics']) != 1 or len(P) >= 65000 or len(T) >= 65000:
        check(False, '%s: one geometry, one atomic, < 65000 vertices / triangles (%d / %d)' % (name, len(P), len(T)))
    for mt in mats:
        if mt not in TXD[txd]:
            check(False, '%s: material %s is missing in %s.txd' % (name, mt, txd))
    if set(re.split(r'[_\W]+', name.lower())) & FORBID or any(set(re.split(r'[_\W]+', mt.lower())) & FORBID for mt in mats):
        check(False, '%s: name / material suggests a person, vehicle or animal' % name)
    if not (np.isfinite(P).all() and np.isfinite(N).all() and np.isfinite(UV).all()):
        stats['nan'] += 1
    if T.max() >= len(P) or tm.max() >= len(mats) or T.min() < 0:
        stats['badidx'] += 1
    a, b, c = P[T[:, 0]], P[T[:, 1]], P[T[:, 2]]
    cr = np.cross(b - a, c - a)
    ar = np.linalg.norm(cr, axis=1)
    gn = cr / np.maximum(ar[:, None], 1e-12)
    vn = N[T[:, 0]] + N[T[:, 1]] + N[T[:, 2]]
    stats['bad_wind'] += int(((np.einsum('ij,ij->i', gn, vn) <= 0) & (ar > 1e-9)).sum())
    stats['zero_n'] += int((np.linalg.norm(N, axis=1) < 0.5).sum())
    # same orientation duplicates would z-fight; opposite orientation pairs are the two sides of a thin double sided surface
    Q = np.round(np.stack([a, b, c], 1) * 1000).astype(np.int64)
    seen = {}
    for t in range(len(T)):
        vs = [tuple(q) for q in Q[t]]
        order_ = sorted(range(3), key=lambda j: vs[j])
        par = sum(1 for x in range(3) for y in range(x + 1, 3) if order_[x] > order_[y]) % 2
        key = (tuple(vs[j] for j in order_), par)
        if key in seen:
            stats['dup_same'] += 1
        seen[key] = 1
    stats['big_uv'] += int((np.abs(UV) > 5000).sum())
    # collision
    cp = os.path.join(FILES, name + '.col')
    c3 = readers.read_col3(cp)
    nf, nb = len(c3['faces']), len(c3['boxes'])
    col_stats['maxf'] = max(col_stats['maxf'], nf)
    if not (nf < 65535 and (nb > 0 or nf > 0) and max(abs(v) for v in list(c3['min']) + list(c3['max'])) < 1024):
        check(False, '%s: collision limits (faces %d boxes %d)' % (name, nf, nb))
    if c3['name'] != name:
        check(False, '%s: COL header name is "%s"' % (name, c3['name']))
    cv = np.array(c3['verts']) if c3['verts'] else np.zeros((0, 3))
    cb = np.array([[b[0], b[1], b[2], b[3], b[4], b[5]] for b in c3['boxes']]) if c3['boxes'] else np.zeros((0, 6))
    pts = np.concatenate([cv, cb[:, :3], cb[:, 3:]]) if len(cv) + len(cb) else np.zeros((0, 3))
    if len(pts) and ((pts.min(0) < np.array(c3['min']) - 0.01).any() or (pts.max(0) > np.array(c3['max']) + 0.01).any()):
        check(False, '%s: the COL bounding box does not contain all collision geometry' % name)
check(stats['nan'] == 0, 'all vertex data is finite')
check(stats['badidx'] == 0, 'triangle / material indices are in range')
check(stats['bad_wind'] == 0, 'triangle winding agrees with the vertex normals (%d disagreeing)' % stats['bad_wind'])
check(stats['zero_n'] == 0, 'no zero-length vertex normals (%d)' % stats['zero_n'])
check(stats['dup_same'] == 0, 'no two coincident triangles with the same facing (would z-fight): %d' % stats['dup_same'])
ok('%d models, %d vertices, %d triangles; largest model %d vertices' % (len(MODELS), tot_v, tot_t, stats['maxv']))
allt = {(t, n) for t, d in TXD.items() for n in d}
unused = sorted(allt - used_tex)
check(not unused, 'every texture in every TXD is used by a model of that TXD %s' % unused[:5])
# NC_SURFACES (generated by build.py into layout.lua): one surface class per texture, full coverage
surf = dict(D['NC_SURFACES'].items()) if 'NC_SURFACES' in D else {}
check(bool(surf), 'NC_SURFACES (texture -> surface class) is generated')
groups = set(surf.values())
check(groups <= {'ground', 'concrete', 'metal', 'glass', 'wall', 'neon', 'sky'}, 'surface classes are known %s' % sorted(groups))
alltex = {n for d in TXD.values() for n in d}
check(set(surf) == alltex, 'NC_SURFACES covers every TXD texture exactly (%d surfaces, %d textures) %s' % (len(surf), len(alltex), sorted(set(surf) ^ alltex)[:5]))
wet_names = [n for n, g in surf.items() if g != 'sky']
check(all(any(n in d for d in TXD.values()) for n in wet_names), 'the %d wet-shader textures exist in the TXDs' % len(wet_names))
check(all(n in mf for mf in [set(os.listdir(FILES))] for n in {m['name'] + '.dff' for m in MODELS} | {m['name'] + '.col' for m in MODELS}), 'every model has a .dff and a .col')
check(any(m['name'] == 'nc_skydome' for m in MODELS), 'the sky dome model is part of the plan')

# ====================================================================================================================================
section('layout')
tags = {}
for o in OBJECTS:
    tags[o[5]] = tags.get(o[5], 0) + 1
check(len(OBJECTS) <= 600, '%d objects (MTA streams about 600 ordinary objects at once; limit 600): %s' % (len(OBJECTS), tags))
check(all(1 <= o[0] <= len(MODELS) for o in OBJECTS), 'every object refers to a model')
check({o[0] for o in OBJECTS} == set(range(1, len(MODELS) + 1)), 'every model is placed at least once')
check(all(o[5] in ('ground', 'bld', 'infra', 'bridge', 'sky', 'skyline', 'tunnel', 'metro') for o in OBJECTS), 'object tags are known')
check(len({(o[0], round(o[1], 1), round(o[2], 1), round(o[3], 1)) for o in OBJECTS}) == len(OBJECTS), 'no object is placed twice at the same spot')
check(all(-40 < o[3] < 400 for o in OBJECTS), 'object heights are sane (-40 .. 400 m)')
check(all(abs(o[4] % 90) < 1e-6 or abs(o[4] % 90 - 90) < 1e-6 for o in OBJECTS), 'rotations are multiples of 90 degrees')
x0, y0, x1, y1 = EXT['x0'], EXT['y0'], EXT['x1'], EXT['y1']
inside = [o for o in OBJECTS if o[5] not in ('skyline',)]
check(all(x0 - 20 < o[1] < x1 + 20 and y0 - 20 < o[2] < y1 + 20 for o in inside), 'all non-skyline objects are inside the map extent (%.0f x %.0f m)' % (x1 - x0, y1 - y0))
check(max(abs(o[1]) for o in OBJECTS) < 2500 and max(abs(o[2]) for o in OBJECTS) < 2500, 'everything stays well inside the +-3000 m world limit')
# ground cells: tile without overlap or gap
rects = []
for o in OBJECTS:
    if o[5] != 'ground':
        continue
    lo, hi = BBOX[MODELS[o[0] - 1]['name']]
    assert abs(o[4]) < 1e-9
    rects.append((o[1] + lo[0], o[2] + lo[1], o[1] + hi[0], o[2] + hi[1]))
area = sum((r[2] - r[0]) * (r[3] - r[1]) for r in rects)
ov = 0.0
for i in range(len(rects)):
    for j in range(i + 1, len(rects)):
        a, b = rects[i], rects[j]
        w = min(a[2], b[2]) - max(a[0], b[0])
        h = min(a[3], b[3]) - max(a[1], b[1])
        if w > 1e-3 and h > 1e-3:
            ov += w * h
check(ov < 1.0, 'ground cells do not overlap (%.2f m2)' % ov)
check(abs(area - (x1 - x0) * (y1 - y0)) / ((x1 - x0) * (y1 - y0)) < 1e-3, 'ground cells cover the whole map (%d cells, %.0f of %.0f m2)' % (len(rects), area, (x1 - x0) * (y1 - y0)))
# water
rv = [(w[0], w[1], w[2], w[3]) for w in WATER]
check(all(int(v) == v and v % 2 == 0 for r in rv for v in r), 'water quads on the even integer grid')
check(all(r[0] < r[2] and r[1] < r[3] for r in rv) and all(x0 - 2 <= r[0] and r[2] <= x1 + 2 for r in rv), 'water quads are well formed and inside the map')
ovw = sum(max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1])) for i, a in enumerate(rv) for b in rv[i + 1:])
check(ovw == 0, 'water quads do not overlap')
# points and tour
check({'spawn', 'tunnel_in', 'tunnel_out', 'tunnel_mid'} <= set(POINTS), 'named points: %s' % ' '.join(sorted(POINTS)))
check(all(x0 < p[0] < x1 and y0 < p[1] < y1 for p in POINTS.values()), 'all points are inside the map')
check(len(TOUR) >= 10 and all(k[6] > 0 for k in TOUR), '%d tour keys with positive durations' % len(TOUR))
check(all(x0 - 150 < k[0] < x1 + 150 and y0 - 150 < k[1] < y1 + 150 and -20 < k[2] < 400 for k in TOUR), 'tour keys are inside the map surroundings')

# ====================================================================================================================================
section('road tunnel')
tun_objs = [o for o in OBJECTS if o[5] == 'tunnel']
check(len(tun_objs) == 7, '%d tunnel parts placed (cut, 5 tube chunks, cut)' % len(tun_objs))
rows = []
for o in tun_objs:
    name = MODELS[o[0] - 1]['name']
    d = readers.read_dff(os.path.join(FILES, name + '.dff'))
    g = d['geoms'][0]
    mats = [mm['tex']['name'] for mm in g['materials']]
    P, N, T, tm = g['pos'].astype(float), g['nrm'].astype(float), g['tris'], g['tri_mat']
    cz, sz = np.cos(np.radians(o[4])), np.sin(np.radians(o[4]))
    W = np.stack([P[:, 0] * cz - P[:, 1] * sz + o[1], P[:, 0] * sz + P[:, 1] * cz + o[2], P[:, 2] + o[3]], 1)
    Wn = np.stack([N[:, 0] * cz - N[:, 1] * sz, N[:, 0] * sz + N[:, 1] * cz, N[:, 2]], 1)
    fl = np.isin(tm, [mats.index('nc_road_str')])
    idx = np.unique(T[fl].reshape(-1))
    ys, zs = W[idx, 1], W[idx, 2]
    rows.append((ys.min(), ys.max(), zs[np.isclose(ys, ys.min(), atol=1e-3)].mean(), zs[np.isclose(ys, ys.max(), atol=1e-3)].mean(), name))
    # the interior surfaces face the tunnel axis
    a, b, c = W[T[:, 0]], W[T[:, 1]], W[T[:, 2]]
    gn = np.cross(b - a, c - a)
    gn /= np.maximum(np.linalg.norm(gn, axis=1, keepdims=True), 1e-12)
    cen = (a + b + c) / 3
    if 'nc_tunnel_tile' in mats:
        s = tm == mats.index('nc_tunnel_tile')
        face = gn[s, 0] * (-np.sign(cen[s, 0] - o[1]))
        check(face.min() > 0.99, '%s: tile walls face the tunnel axis' % name)
    check(gn[fl, 2].min() > 0.9, '%s: road faces up' % name)
    if 'nc_deck_under' in mats:
        s = tm == mats.index('nc_deck_under')
        check(gn[s, 2].max() < -0.9, '%s: ceiling faces down' % name)
    check(np.abs(W[:, 0] - o[1]).max() < 10.0, '%s: nothing wider than the street' % name)
rows.sort()
gaps = [(abs(rows[k][0] - rows[k - 1][1]), abs(rows[k][2] - rows[k - 1][3])) for k in range(1, len(rows))]
check(max(g[0] for g in gaps) < 0.01 and max(g[1] for g in gaps) < 0.01, 'the road is continuous from part to part (max gap %.4f m / %.4f m)' % (max(g[0] for g in gaps), max(g[1] for g in gaps)))
check(abs(rows[0][2]) < 0.01 and abs(rows[-1][3]) < 0.01, 'both portals meet street level z = 0')
check(abs(rows[0][0] - TUN['y0']) < 0.01 and abs(rows[-1][1] - TUN['y1']) < 0.01, 'NC_TUNNEL y0 / y1 match the geometry')
zmin = min(r[2] for r in rows)
check(abs(zmin - TUN['zf']) < 0.01, 'flat road level %.2f m below the street' % zmin)
check(zmin + 4.8 + 1.0 <= -0.6 + 1e-6, 'the roof top (%.2f m) is under the 0.6 m thick ground slab of the street above' % (zmin + 4.8 + 1.0))
check(zmin + 4.8 + 1.0 > -3.0, 'the tube is not buried deeper than necessary')
# GTA treats everything below a water polygon as water: no water quad may lie above the tunnel
tx0, tx1 = TUN['x'] - 9.0, TUN['x'] + 9.0
over = [w for w in WATER if w[0] < tx1 and w[2] > tx0 and w[1] < TUN['y1'] and w[3] > TUN['y0']]
check(not over, 'no water polygon above the tunnel (%d overlapping)' % len(over))
# the cut-outs of the ground cells: no road level triangles inside, no slab collision
cells = [o for o in OBJECTS if o[5] == 'ground']
nh = 0
for o in cells:
    name = MODELS[o[0] - 1]['name']
    lo, hi = BBOX[name]
    if abs(o[1] + (lo[0] + hi[0]) / 2 - TUN['x']) > 60 and abs(o[1] - TUN['x']) > 60:
        continue
    for (ya, yb) in ((TUN['y0'], TUN['y0'] + 64.0), (TUN['y1'] - 64.0, TUN['y1'])):
        if not (o[2] + lo[1] < ya and yb < o[2] + hi[1]):
            continue
        for side, (xa, xb) in (('e', (TUN['x'] - 7.0, TUN['x'])), ('w', (TUN['x'], TUN['x'] + 7.0))):
            cell_x0, cell_x1 = o[1] + lo[0], o[1] + hi[0]
            if not (abs(cell_x1 - TUN['x']) < 0.01 if side == 'e' else abs(cell_x0 - TUN['x']) < 0.01):
                continue
            d = readers.read_dff(os.path.join(FILES, name + '.dff'))
            g = d['geoms'][0]
            P, T = g['pos'].astype(float) + np.array([o[1], o[2], o[3]]), g['tris']
            cen = (P[T[:, 0]] + P[T[:, 1]] + P[T[:, 2]]) / 3
            inx = (cen[:, 0] > xa) & (cen[:, 0] < xb)
            iny = (cen[:, 1] > ya + 0.05) & (cen[:, 1] < yb - 0.05)
            n_in = int((inx & iny & (cen[:, 2] < 0.05)).sum())
            check(n_in == 0, '%s: no road-level surface inside the %s trench cut-out (%d)' % (name, side, n_in))
            c3 = readers.read_col3(os.path.join(FILES, name + '.col'))
            cx, cy = (xa + xb) / 2, (ya + yb) / 2
            cover = [b for b in c3['boxes'] if b[0] + o[1] <= cx <= b[3] + o[1] and b[1] + o[2] <= cy <= b[4] + o[2] and b[2] <= -0.3 <= b[5]]
            check(not cover, '%s: no ground collision slab over the %s trench' % (name, side))
            nh += 1
check(nh == 4, 'the four ground cells next to the open cuts were checked (%d)' % nh)
# nothing else may stand in the tunnel corridor (street width 22 m)
clash = []
for o in OBJECTS:
    if o[5] in ('ground', 'tunnel', 'skyline'):
        continue
    lo, hi = BBOX[MODELS[o[0] - 1]['name']]
    r = int(round(o[4] / 90.0)) % 4
    (xa, xb), (ya_, yb_) = ((lo[0], hi[0]), (lo[1], hi[1])) if r in (0, 2) else ((lo[1], hi[1]), (lo[0], hi[0]))
    X0, X1, Y0, Y1 = o[1] + xa, o[1] + xb, o[2] + ya_, o[2] + yb_
    if X0 < TUN['x'] + 11 and X1 > TUN['x'] - 11 and Y0 < TUN['y1'] + 5 and Y1 > TUN['y0'] - 5 and o[3] + lo[2] < 3.0 and o[3] + hi[2] > -8.0:
        # bounding boxes overlap: look at the real vertices (an expressway deck passes high above the street, its piers stand elsewhere)
        g = readers.read_dff(os.path.join(FILES, MODELS[o[0] - 1]['name'] + '.dff'))['geoms'][0]
        Pv = g['pos'].astype(float)
        cz_, sz_ = np.cos(np.radians(o[4])), np.sin(np.radians(o[4]))
        wx = Pv[:, 0] * cz_ - Pv[:, 1] * sz_ + o[1]
        wy = Pv[:, 0] * sz_ + Pv[:, 1] * cz_ + o[2]
        wz = Pv[:, 2] + o[3]
        if ((np.abs(wx - TUN['x']) < 9.0) & (wy > TUN['y0'] - 5) & (wy < TUN['y1'] + 5) & (wz < 3.0) & (wz > -8.0)).any():
            clash.append((MODELS[o[0] - 1]['name'], o[5]))
check(not clash, 'no building or bridge pier stands in the tunnel corridor %s' % clash[:4])

# ====================================================================================================================================
section('collision walk-check (vertical probes against the real COL files)')
# world space collision: boxes -> AABB, triangles (tunnel parts)
BOXES, TRIS = [], []
COLCACHE = {}
for o in OBJECTS:
    if o[5] == 'skyline':
        continue
    name = MODELS[o[0] - 1]['name']
    if name not in COLCACHE:
        COLCACHE[name] = readers.read_col3(os.path.join(FILES, name + '.col'))
    c3 = COLCACHE[name]
    cz_, sz_ = np.cos(np.radians(o[4])), np.sin(np.radians(o[4]))
    for b in c3['boxes']:
        xs = [b[0], b[3]]
        ys = [b[1], b[4]]
        wx = [x * cz_ - y * sz_ + o[1] for x in xs for y in ys]
        wy = [x * sz_ + y * cz_ + o[2] for x in xs for y in ys]
        BOXES.append((min(wx), min(wy), b[2] + o[3], max(wx), max(wy), b[5] + o[3]))
    if c3['faces']:
        V = np.array(c3['verts'])
        W_ = np.stack([V[:, 0] * cz_ - V[:, 1] * sz_ + o[1], V[:, 0] * sz_ + V[:, 1] * cz_ + o[2], V[:, 2] + o[3]], 1)
        for f in c3['faces']:
            TRIS.append(W_[list(f[:3])])
BOXES = np.array(BOXES)
TRIS = np.array(TRIS) if TRIS else np.zeros((0, 3, 3))
tn = np.cross(TRIS[:, 1] - TRIS[:, 0], TRIS[:, 2] - TRIS[:, 0]) if len(TRIS) else np.zeros((0, 3))
up_tris = TRIS[tn[:, 2] > 1e-9] if len(TRIS) else TRIS
ok('%d collision boxes and %d triangles in world space' % (len(BOXES), len(TRIS)))


def ground_z(x, y, z0):
    """highest upward facing collision surface at (x, y) not above z0 (None = nothing there)"""
    best = None
    sel = (BOXES[:, 0] <= x) & (x <= BOXES[:, 3]) & (BOXES[:, 1] <= y) & (y <= BOXES[:, 4]) & (BOXES[:, 5] <= z0 + 1e-6)
    if sel.any():
        best = BOXES[sel, 5].max()
    if len(up_tris):
        a, b, c = up_tris[:, 0], up_tris[:, 1], up_tris[:, 2]
        d = (b[:, 1] - c[:, 1]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 1] - c[:, 1])
        l1 = ((b[:, 1] - c[:, 1]) * (x - c[:, 0]) + (c[:, 0] - b[:, 0]) * (y - c[:, 1])) / d
        l2 = ((c[:, 1] - a[:, 1]) * (x - c[:, 0]) + (a[:, 0] - c[:, 0]) * (y - c[:, 1])) / d
        l3 = 1 - l1 - l2
        inside_ = (l1 >= -1e-9) & (l2 >= -1e-9) & (l3 >= -1e-9)
        if inside_.any():
            zz = (l1 * a[:, 2] + l2 * b[:, 2] + l3 * c[:, 2])[inside_]
            zz = zz[zz <= z0 + 1e-6]
            if len(zz):
                best = zz.max() if best is None else max(best, zz.max())
    return best


def expected_z(x, y):
    if abs(x - TUN['x']) < 6.9:
        for (ya, yb) in ((TUN['y0'], TUN['y0'] + 64.0), (TUN['y1'] - 64.0, TUN['y1'])):
            if ya <= y <= yb:
                t = (y - ya) / 64.0 if ya == TUN['y0'] else (TUN['y1'] - y) / 64.0
                return -6.4 * t
    return 0.0


# street centre lines from the ground cell rectangles (cells run from street centre line to street centre line)
xs_lines = sorted({round(r[0], 1) for r in rects} | {round(r[2], 1) for r in rects})
ys_lines = sorted({round(r[1], 1) for r in rects} | {round(r[3], 1) for r in rects})
bridge_x = sorted({round(o[1], 1) for o in OBJECTS if o[5] == 'bridge'})
water_rects = [(w[0], w[1], w[2], w[3]) for w in WATER]
bank_y = [(min(w[1] for w in WATER) - 14.0, min(w[1] for w in WATER) + 2.0), (max(w[3] for w in WATER) - 2.0, max(w[3] for w in WATER) + 14.0)]   # promenades (0.16 m) along both banks
miss, wrong, n_samples = [], [], 0
for xl_ in xs_lines:
    for off in (0.0, -3.5, 3.5):
        x = xl_ + off
        if x <= x0 + 1 or x >= x1 - 1:
            continue
        for y in np.arange(y0 + 3, y1 - 3, 6.0):
            if any(r[0] <= x <= r[2] and r[1] <= y <= r[3] for r in water_rects) and xl_ not in bridge_x:
                continue                                  # open water between the bridges
            n_samples += 1
            g = ground_z(x, y, 2.0)
            e = expected_z(x, y)
            if g is None:
                miss.append((round(x, 1), round(y, 1)))
            elif abs(g - e) > 0.03 and not (abs(g - 0.16) < 0.03 and any(a_ <= y <= b_ for a_, b_ in bank_y)):
                wrong.append((round(x, 1), round(y, 1), round(g, 3), e))
for yl_ in ys_lines:
    for off in (0.0, -3.5, 3.5):
        y = yl_ + off
        if y <= y0 + 1 or y >= y1 - 1:
            continue
        for x in np.arange(x0 + 3, x1 - 3, 6.0):
            n_samples += 1
            g = ground_z(x, y, 2.0)
            e = expected_z(x, y)
            if g is None:
                miss.append((round(x, 1), round(y, 1)))
            elif abs(g - e) > 0.03 and not (abs(g - 0.16) < 0.03 and any(a_ <= y <= b_ for a_, b_ in bank_y)):
                wrong.append((round(x, 1), round(y, 1), round(g, 3), e))
check(not miss, 'every street sample has walkable collision under it: %d holes of %d samples %s' % (len(miss), n_samples, miss[:4]))
check(not wrong, 'the street collision is at street level (z = 0) everywhere, or follows the trench ramp: %d off %s' % (len(wrong), wrong[:3]))
# kerbs and pavements: scanning sideways from street sample points the collision steps from 0 up to 0.16 exactly once and then stays there
kerb_bad = []
n_kerb = 0
for xl_ in xs_lines[1:-1]:
    for y in np.arange(y0 + 20, y1 - 20, 24.0):
        if any(r[0] <= xl_ <= r[2] and r[1] <= y <= r[3] for r in water_rects) or any(a_ <= y <= b_ for a_, b_ in bank_y):
            continue
        if abs(xl_ - TUN['x']) < 8 and (TUN['y0'] - 2 <= y <= TUN['y0'] + 66 or TUN['y1'] - 66 <= y <= TUN['y1'] + 2):
            continue
        for sd in (-1, 1):
            ds = np.arange(0.0, 20.5, 0.5)
            prof = [ground_z(xl_ + sd * d, y, 2.0) for d in ds]
            n_kerb += 1
            if any(v is None for v in prof[:30]):
                kerb_bad.append(('hole', xl_, round(y, 1), sd))
                continue
            steps = [i for i in range(1, len(prof)) if prof[i] is not None and prof[i - 1] is not None and abs(prof[i] - prof[i - 1]) > 0.03]
            if not steps:
                continue                                                  # a wide avenue: the kerb is beyond the scan
            k = steps[0]
            before = prof[:k]
            after = prof[k:k + 6]                                         # at least 3 m of pavement behind the kerb
            if not (all(abs(v) < 0.03 for v in before) and all(v is not None and abs(v - 0.16) < 0.03 for v in after)):
                kerb_bad.append(('profile', xl_, round(y, 1), sd, [None if v is None else round(v, 2) for v in prof[:20]]))
check(not kerb_bad, 'kerbs: %d sideways scans from the street centre lines are clean (0 -> 0.16 once, no holes) %s' % (n_kerb, kerb_bad[:2]))
# no hole anywhere in the map: a probe from 2 m above ground finds collision under every point of an 8 m grid (river bed included)
holes_g = []
for x in np.arange(x0 + 4, x1 - 4, 8.0):
    for y in np.arange(y0 + 4, y1 - 4, 8.0):
        if ground_z(x, y, 2.0) is None:
            holes_g.append((round(x, 1), round(y, 1)))
check(not holes_g, 'no hole in the ground collision over the whole %d x %d m map (8 m grid): %d holes %s' % (x1 - x0, y1 - y0, len(holes_g), holes_g[:4]))
# the elevated roads: deck collision at deck level along their whole length
express_bad = []
n_ex = 0
ew = [o for o in OBJECTS if o[5] == 'infra' and abs(o[4]) < 1e-6]
ns = [o for o in OBJECTS if o[5] == 'infra' and abs(o[4] - 90) < 1e-6]
for o in ew:
    for dx in np.arange(-30, 30, 7.0):
        for off in (-6.6, 6.6):
            x, y = o[1] + dx, o[2] + off
            if x0 < x < x1:
                n_ex += 1
                g = ground_z(x, y, 14.0)
                if g is None or abs(g - 12.0) > 0.03:
                    express_bad.append(('E-W', round(x, 1), round(y, 1), g))
for o in ns:
    for dy in np.arange(-30, 30, 7.0):
        for off in (-6.6, 6.6):
            x, y = o[1] + off, o[2] + dy
            if y0 < y < y1:
                n_ex += 1
                g = ground_z(x, y, 25.0)
                if g is None or abs(g - 22.0) > 0.03:
                    express_bad.append(('N-S', round(x, 1), round(y, 1), g))
check(not express_bad and n_ex > 200, 'expressway decks are solid at 12 m (east-west) and 22 m (north-south) along their whole length (%d probes, %d off) %s' % (n_ex, len(express_bad), express_bad[:3]))
# the visible ground and its collision agree: points on up-facing road / pavement / bed triangles are found by a probe from just above
rng_ = np.random.default_rng(5)
mismatch, n_vis = [], 0
for o in OBJECTS:
    if o[5] not in ('ground', 'bridge'):
        continue
    d_ = readers.read_dff(os.path.join(FILES, MODELS[o[0] - 1]['name'] + '.dff'))['geoms'][0]
    P_, T_ = d_['pos'].astype(float), d_['tris']
    a_, b_, c_ = P_[T_[:, 0]], P_[T_[:, 1]], P_[T_[:, 2]]
    nrm_ = np.cross(b_ - a_, c_ - a_)
    area_ = np.linalg.norm(nrm_, axis=1) / 2
    zc_ = (a_[:, 2] + b_[:, 2] + c_[:, 2]) / 3
    flat = (nrm_[:, 2] > 0.99 * np.linalg.norm(nrm_, axis=1)) & (np.abs(a_[:, 2] - b_[:, 2]) < 1e-3) & (np.abs(a_[:, 2] - c_[:, 2]) < 1e-3)
    lvl = flat & ((np.abs(zc_ - 0.0) < 0.02) | (np.abs(zc_ - 0.16) < 0.02) | (np.abs(zc_ + 7.0) < 0.02)) & (area_ > 0.5)
    idx = np.where(lvl)[0]
    if len(idx) == 0:
        continue
    pick = rng_.choice(idx, size=min(40, len(idx)), replace=False, p=area_[idx] / area_[idx].sum())
    for t in pick:
        u, v = rng_.random(2)
        if u + v > 1:
            u, v = 1 - u, 1 - v
        pt = a_[t] + u * (b_[t] - a_[t]) + v * (c_[t] - a_[t])
        wx, wy = (pt[0] * np.cos(np.radians(o[4])) - pt[1] * np.sin(np.radians(o[4])) + o[1]), (pt[0] * np.sin(np.radians(o[4])) + pt[1] * np.cos(np.radians(o[4])) + o[2])
        g = ground_z(wx, wy, zc_[t] + 0.2)
        n_vis += 1
        if g is None or abs(g - zc_[t]) > 0.03:
            mismatch.append((MODELS[o[0] - 1]['name'], round(wx, 1), round(wy, 1), round(float(zc_[t]), 2), None if g is None else round(float(g), 3)))
check(not mismatch, 'collision matches the visible ground: %d probes on road / pavement / bed triangles, %d mismatches %s' % (n_vis, len(mismatch), mismatch[:3]))
# buildings are solid: collision reaches a good part of the visible height inside the footprint
weak = []
nb_ = 0
for o in OBJECTS:
    if o[5] != 'bld':
        continue
    lo, hi = BBOX[MODELS[o[0] - 1]['name']]
    r = int(round(o[4] / 90.0)) % 4
    hx, hy = ((hi[0] - lo[0]) / 2, (hi[1] - lo[1]) / 2) if r in (0, 2) else ((hi[1] - lo[1]) / 2, (hi[0] - lo[0]) / 2)
    top = hi[2] + o[3]
    tops = []
    for fx, fy in np.random.default_rng(11).uniform(-0.45, 0.45, (120, 2)):          # random probes (a regular grid can alias with rows of containers)
        g = ground_z(o[1] + fx * hx * 2, o[2] + fy * hy * 2, top + 2.0)
        tops.append(0.0 if g is None else g - o[3])
    nb_ += 1
    h = hi[2]
    # container yards, tank farms etc. are low: demand at least 1.5 m or 30 % of the height, whichever is smaller
    if max(tops) < min(1.5, 0.3 * h):
        weak.append((MODELS[o[0] - 1]['name'], round(max(tops), 1), round(h, 1)))
check(not weak, 'every building has solid collision (%d checked, %d without) %s' % (nb_, len(weak), weak[:4]))
# the reverse direction: wherever there is walkable collision there is also a VISIBLE surface at that height (no invisible ground), and
# the river bed lies under water quads only
cellsz = 8.0
vis = {}
for o in OBJECTS:
    if o[5] in ('skyline', 'sky'):
        continue
    d_ = readers.read_dff(os.path.join(FILES, MODELS[o[0] - 1]['name'] + '.dff'))['geoms'][0]
    P_, T_ = d_['pos'].astype(float), d_['tris']
    cz2, sz2 = np.cos(np.radians(o[4])), np.sin(np.radians(o[4]))
    W_ = np.stack([P_[:, 0] * cz2 - P_[:, 1] * sz2 + o[1], P_[:, 0] * sz2 + P_[:, 1] * cz2 + o[2], P_[:, 2] + o[3]], 1)
    a_, b_, c_ = W_[T_[:, 0]], W_[T_[:, 1]], W_[T_[:, 2]]
    n_ = np.cross(b_ - a_, c_ - a_)
    up_ = (n_[:, 2] > 0.5 * np.linalg.norm(n_, axis=1)) & (np.minimum(np.minimum(a_[:, 2], b_[:, 2]), c_[:, 2]) < 2.0)
    for t in np.where(up_)[0]:
        tri = (a_[t], b_[t], c_[t])
        xs_ = [tri[0][0], tri[1][0], tri[2][0]]
        ys_ = [tri[0][1], tri[1][1], tri[2][1]]
        for gx in range(int(np.floor(min(xs_) / cellsz)), int(np.floor(max(xs_) / cellsz)) + 1):
            for gy in range(int(np.floor(min(ys_) / cellsz)), int(np.floor(max(ys_) / cellsz)) + 1):
                vis.setdefault((gx, gy), []).append(tri)


def visible_zs(x, y):
    out = []
    for (A, B, C_) in vis.get((int(np.floor(x / cellsz)), int(np.floor(y / cellsz))), ()):
        d = (B[1] - C_[1]) * (A[0] - C_[0]) + (C_[0] - B[0]) * (A[1] - C_[1])
        if abs(d) < 1e-12:
            continue
        l1 = ((B[1] - C_[1]) * (x - C_[0]) + (C_[0] - B[0]) * (y - C_[1])) / d
        l2 = ((C_[1] - A[1]) * (x - C_[0]) + (A[0] - C_[0]) * (y - C_[1])) / d
        if l1 >= -1e-9 and l2 >= -1e-9 and 1 - l1 - l2 >= -1e-9:
            out.append(l1 * A[2] + l2 * B[2] + (1 - l1 - l2) * C_[2])
    return out


invisible, unwatered, n_g = [], [], 0
for x in np.arange(x0 + 2.3, x1 - 2, 8.0):
    for y in np.arange(y0 + 2.7, y1 - 2, 8.0):
        g = ground_z(x, y, 2.0)
        if g is None:
            continue
        n_g += 1
        if not any(abs(z - g) < 0.06 for z in visible_zs(x, y)):
            invisible.append((round(x, 1), round(y, 1), round(g, 2)))
        if abs(g + 7.0) < 0.03 and not any(r[0] <= x <= r[2] and r[1] <= y <= r[3] for r in water_rects):
            unwatered.append((round(x, 1), round(y, 1)))
check(not invisible, 'no invisible ground: a visible surface exists under every one of %d walkable probes (%d without) %s' % (n_g, len(invisible), invisible[:4]))
check(not unwatered, 'the whole river bed lies under water quads (%d dry spots) %s' % (len(unwatered), unwatered[:4]))
# the tunnel itself: floor, ceiling and both walls
bad_t = []
prof_y = [TUN['y0'], TUN['cov0'], TUN['cov1'], TUN['y1']]
prof_z = [0.0, TUN['zf'], TUN['zf'], 0.0]
for y in np.arange(TUN['y0'] + 2.0, TUN['y1'] - 2.0, 3.0):
    road = float(np.interp(y, prof_y, prof_z))
    g = ground_z(TUN['x'] + 2.0, y, road + 1.5)
    if g is None or abs(g - road) > 0.03:
        bad_t.append((round(y, 1), g, round(road, 3)))
check(not bad_t, 'a probe from 1.5 m above the road finds the tunnel road at its profile everywhere (%d off) %s' % (len(bad_t), bad_t[:3]))
zc = TUN['zf'] + 4.8
walls = 0
for y in np.arange(TUN['cov0'] + 2.0, TUN['cov1'] - 2.0, 5.0):
    for sx in (-1, 1):
        px_ = TUN['x'] + sx * 7.4
        inside_wall = ((BOXES[:, 0] <= px_) & (px_ <= BOXES[:, 3]) & (BOXES[:, 1] <= y) & (y <= BOXES[:, 4]) & (BOXES[:, 2] <= TUN['zf'] + 2.0) & (TUN['zf'] + 2.0 <= BOXES[:, 5])).any()
        if not inside_wall:
            # walls are prisms (triangles): look for a triangle crossing this point's xz band
            near = [t for t in TRIS if abs(t[:, 0].mean() - px_) < 0.9 and t[:, 1].min() <= y <= t[:, 1].max()]
            inside_wall = len(near) > 0
        walls += 0 if inside_wall else 1
check(walls == 0, 'both tunnel walls are solid along the whole covered part (%d gaps)' % walls)

# ====================================================================================================================================
section('budgets')
tot = sum(os.path.getsize(os.path.join(root_, f)) for root_, _, fs in os.walk(RES) for f in fs)
check(tot < 128 * 1048576, 'resource size %.1f MB (< 128 MB)' % (tot / 1048576))
check(max(os.path.getsize(p) for p in glob.glob(os.path.join(FILES, '*'))) < 20 * 1048576, 'no single file above 20 MB')
check(stats['maxv'] < 30000, 'largest model %d vertices (< 30000: comfortable for streaming)' % stats['maxv'])
sizes = {k: os.path.getsize(os.path.join(FILES, k)) for k in os.listdir(FILES) if os.path.isfile(os.path.join(FILES, k))}
ok('DFF %.1f MB, COL %.2f MB, TXD %.1f MB' % (sum(v for k, v in sizes.items() if k.endswith('.dff')) / 1048576, sum(v for k, v in sizes.items() if k.endswith('.col')) / 1048576,
                                                  sum(v for k, v in sizes.items() if k.endswith('.txd')) / 1048576))
wavs = [f for f in os.listdir(os.path.join(FILES, 'audio'))]
check(len(wavs) >= 7 and all(f.endswith('.wav') for f in wavs), '%d audio files' % len(wavs))
for f in re.findall(r'"(\w+)", (?:true|false), ', cl) + re.findall(r'snd[23]\("(\w+)"', cl):
    pass
snd_used = set(re.findall(r'snd[23]\("(\w+)"', cl))
check(all((f + '.wav') in wavs for f in snd_used), 'every sound the client plays exists (%s)' % ' '.join(sorted(snd_used)))
check(all(os.path.exists(os.path.join(FILES, 'fx', f)) for f in ('glow.png', 'steam.png')), 'glow / steam sprite textures present')

# ====================================================================================================================================
if '--librw' in sys.argv:
    section('reference RenderWare loader (aap/librw)')
    exe = '/tmp/librw_check'
    if not os.path.exists(exe):
        warn('/tmp/librw_check not built: see tools/build_librw_check.sh')
    else:
        bad = 0
        for m in MODELS:
            r = subprocess.run([exe, os.path.join(FILES, m['name'] + '.dff'), os.path.join(FILES, m['txd'] + '.txd')], capture_output=True, text=True)
            if r.returncode != 0 or 'ALL librw CHECKS PASSED' not in r.stdout:
                bad += 1
                print('   ', m['name'], r.stdout[-200:])
        check(bad == 0, 'librw loads all %d DFFs with their TXD' % len(MODELS))
if '--lua' in sys.argv:
    section('headless Lua session test')
    r = subprocess.run([sys.executable, os.path.join(HERE, 'mta_lua_test_nc.py')], capture_output=True, text=True, env=dict(os.environ, NC_RES=RES))
    last = [ln for ln in r.stdout.splitlines() if ln.startswith('== result')]
    check(r.returncode == 0, 'mta_lua_test_nc.py: %s' % (last[0] if last else r.stderr[-300:]))

print('\n== %d checks passed, %d failed, %d warnings ==' % (npass[0], len(fails), len(warns)))
for f in fails:
    print('  FAILED:', f)
sys.exit(1 if fails else 0)
