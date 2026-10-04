# Created by: Arena.ai Agent Mode (AI) - headless test of the WetStreets MTA:SA resource (NightCity companion).
# Runs the REAL env.lua / wetstreets.lua (Lua 5.1 via lupa) against the strict API model in mta_stub_nc.lua and drives them through
# resource start / frames / vanilla weather + clock / commands / resource stop, plus failure injection (shader compile failure,
# fallback technique).  Same contract as mta_lua_test_nc.py: it cannot replace a real MTA client, but it catches every logic,
# API-usage, argument-type, ordering and cleanup error that does not depend on the engine itself.
#     python3 mta_lua_test_wet.py
import os
import re
import sys
from lupa import lua51

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.environ.get('NC_WS_RES') or os.path.join(HERE, '..', 'resource', 'WetStreets')

fails = []
passed = [0]


def check(c, msg):
    print('  [%s] %s' % ('PASS' if c else 'FAIL', msg))
    if c:
        passed[0] += 1
    else:
        fails.append(msg)


def rd(f):
    return open(os.path.join(RES, f), encoding='utf8').read()


def fx_vars(path):
    out = set()
    for ln in open(path, encoding='utf8'):
        m = re.match(r'^(float\d?(?:x\d)?|texture|int|bool)\s+(\w+)\s*([(:=;<])', ln)
        if m and m.group(3) != '(':
            out.add(m.group(2))
    return out


META = rd('meta.xml')
META_FILES = re.findall(r'<(?:file|script) src="([^"]+)"', META)
N_PATTERNS = len(re.findall(r'"[*][^"]*"', rd('wetstreets.lua')))
GROUPS = 4


def boot(shader_mode=None):
    lua = lua51.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(open(os.path.join(HERE, 'mta_stub_nc.lua'), encoding='utf8').read())
    T = lua.globals().T
    for f in META_FILES:
        T.files[f] = True
    for f in sorted(f for f in META_FILES if f.endswith('.fx')):
        t = lua.table()
        for v in fx_vars(os.path.join(RES, f)):
            t[v] = True
        T.fxvars[f] = t
    if shader_mode:
        T.shaderMode = shader_mode
    T.load('client', 'env.lua', rd('env.lua'))
    T.load('client', 'wetstreets.lua', rd('wetstreets.lua'))
    return lua, T


def chat(T):
    return [T.chat[i] for i in range(1, int(T.chatCount()) + 1)]


def errors(T):
    e = T.errors()
    return [e[i] for i in range(1, len(e) + 1)]


# =====================================================================================================================================
print('== boot: commands registered, shaders up, vanilla patterns captured ==')
lua, T = boot()
for c in ('wetfx', 'wetlevel', 'wetflash', 'wetinfo'):
    check(T.hasCmd('client', c), 'client command /%s registered' % c)
T.fireClient('onClientResourceStart', T.resourceRoot)
check(not errors(T), 'resource start runs without errors %s' % errors(T)[:2])
check(int(T.alive('shader')) == GROUPS + 1, '%d surface shaders + 1 grade shader alive' % GROUPS)
check(T.shaderOf('post.fx') is not None, 'post.fx grade shader created')
check(int(T.shaderCount('wet.fx')) == GROUPS, 'wet.fx instantiated once per material group')
check(int(T.shaderTexturesTotal('wet.fx')) == N_PATTERNS,
      'every wildcard pattern applied (%d applies over %d patterns)' % (int(T.shaderTexturesTotal('wet.fx')), N_PATTERNS))
for i, (mat, expect) in enumerate(((1, 1.00), (2, 0.65), (3, 0.55), (4, 0.85)), start=1):
    v = T.shaderValue('wet.fx', 'gMatWet', 1, i)
    check(v is not None and abs(float(v) - expect) < 1e-6, 'group %d carries its wetness factor %.2f' % (i, expect))
check(T.shaderValue('wet.fx', 'gScreen', 1, 1) is not None and T.shaderValue('post.fx', 'ScreenTexture') is not None,
      'screen source handed to the reflection and grade shaders')

print('== environment follows the vanilla clock / weather / rain ==')
T.cmd('client', 'wetlevel', 'auto')
T.C.setTime(13, 0)                    # noon -> the low-sun model is not active, sun intensity high
T.C.setWeather(8)                     # rainy SF
T.C.setRainLevel(1.0)
for _ in range(40):                 # 2 s of frames
    T.frame(50)
check(abs(float(T.shaderValue('wet.fx', 'gWet', 1, 1)) - float(T.shaderValue('post.fx', 'gWet'))) < 1e-6,
      'the same wetness reaches every shader')
check(float(T.shaderValue('wet.fx', 'gWet', 1, 1)) > 0.3, 'streets soaked up while it rains (gWet %.2f)' % float(T.shaderValue('wet.fx', 'gWet', 1, 1)))
check(float(T.shaderValue('wet.fx', 'gPuddle', 1, 1)) >= 0 and float(T.shaderValue('wet.fx', 'gSunI', 1, 1)) > 0.2,
      'daytime sun intensity computed from the clock (gSunI %.2f)' % float(T.shaderValue('wet.fx', 'gSunI', 1, 1)))
t0 = float(T.shaderValue('wet.fx', 'gTime', 1, 1))
for _ in range(10):
    T.frame(50)
check(float(T.shaderValue('wet.fx', 'gTime', 1, 1)) > t0, 'rain-ring time advances every frame')
T.C.setTime(22, 30)                   # night: the sun term must go dark, the emissive keep
for _ in range(30):
    T.frame(50)
check(float(T.shaderValue('wet.fx', 'gSunI', 1, 1)) < 0.05 and float(T.shaderValue('wet.fx', 'gNight', 1, 1)) > 0.9,
      'night: sun dark, night factor up')
check(float(T.shaderValue('wet.fx', 'gNightGlow', 1, 1)) > 0.5, 'night emissive glow handed to the shader')

print('== drying: the streets dry slowly after the rain stops ==')
T.C.setTime(13, 0)
T.C.setWeather(0)
T.C.setRainLevel(0.0)
for _ in range(600):                # 30 s of frames
    T.frame(50)
w = float(T.shaderValue('wet.fx', 'gWet', 1, 1))
check(w < 0.5, 'wetness fell back while drying (gWet %.2f after 30 s)' % w)

print('== grade pass: screen source captured every frame with resample ==')
draws0 = int(T.draws)
T.frame(50)
T.frame(50)
check(int(T.draws) > draws0, 'the grade is drawn on the HUD layer')
src = None
i = 1
while T.elems[i] is not None:
    e = T.elems[i]
    if e.kind == 'screensource' and e.alive:
        src = e
        break
    i += 1
check(src is not None and int(src.updates) > 0, 'screen source updated before the grade pass')
check(src is not None and src.resample == True, 'dxUpdateScreenSource called with resample=true (no feedback loop)')

print('== commands ==')
T.cmd('client', 'wetlevel', '0.7')
for _ in range(120):                 # the manual override eases in (~1 s time constant)
    T.frame(50)
check(abs(float(T.shaderValue('wet.fx', 'gWet', 1, 1)) - 0.7) < 1e-4, '/wetlevel 0.7 forces the wetness')
T.cmd('client', 'wetlevel', 'auto')
T.cmd('client', 'wetfx', '0')
check(int(T.alive('shader')) == 0 and int(T.alive('screensource')) == 0, '/wetfx 0 tears every shader and the screen source down')
check(int(T.handlerCount('client', 'onClientHUDRender')) == 0, '/wetfx 0 detaches the HUD pass')
T.cmd('client', 'wetfx', '2')
check(int(T.alive('shader')) == GROUPS + 1 and int(T.shaderTexturesTotal('wet.fx')) == N_PATTERNS, '/wetfx 2 rebuilds everything')
T.cmd('client', 'wetflash')
for _ in range(2):
    T.frame(50)
check(float(T.shaderValue('wet.fx', 'gFlash', 1, 1)) > 0.1, '/wetflash lights the wet mirror (gFlash)')
check(T.world.sky is not None, 'the vanilla sky whitens for the strike')
T.advance(300)
check(T.world.sky is None, 'the sky colours are restored after the flash')
for _ in range(80):
    T.frame(50)
check(float(T.shaderValue('wet.fx', 'gFlash', 1, 1)) < 0.05, 'the flash decays')
nchat = len(chat(T))
T.cmd('client', 'wetinfo')
check(len(chat(T)) > nchat and not errors(T), '/wetinfo prints status without errors')

print('== resource stop: everything released ==')
T.fireClient('onClientResourceStop', T.resourceRoot)
check(int(T.alive('shader')) == 0 and int(T.alive('screensource')) == 0, 'every shader and the screen source destroyed')
check(int(T.handlerCount('client', 'onClientPreRender')) == 0 and int(T.handlerCount('client', 'onClientHUDRender')) == 0,
      'both frame handlers detached')
check(T.world.sky is None, 'no vanilla sky override left behind')
check(not errors(T), 'whole session without a single API / runtime error %s' % errors(T)[:2])

print('== failure injection: compile failure and fallback technique degrade gracefully ==')
for mode in ('fail', 'fallback'):
    lua2, T2 = boot(mode)
    T2.fireClient('onClientResourceStart', T2.resourceRoot)
    check(not errors(T2), 'shader %s: resource still starts cleanly' % mode)
    check(int(T2.alive('shader')) == 0, 'shader %s: nothing half-initialized stays alive' % mode)
    T2.frame(50)
    T2.cmd('client', 'wetinfo')
    check(not errors(T2), 'shader %s: frames and commands keep working' % mode)
    T2.fireClient('onClientResourceStop', T2.resourceRoot)

print('== resource restart: the whole cycle can run twice ==')
lua3, T3 = boot()
T3.fireClient('onClientResourceStart', T3.resourceRoot)
T3.frame(50)
T3.fireClient('onClientResourceStop', T3.resourceRoot)
T3.fireClient('onClientResourceStart', T3.resourceRoot)
check(int(T3.alive('shader')) == GROUPS + 1 and not errors(T3), 'restart rebuilds the full set cleanly')
T3.fireClient('onClientResourceStop', T3.resourceRoot)

print('\n== result: %d passed, %d failed ==' % (passed[0], len(fails)))
for f in fails:
    print('  FAILED:', f)
sys.exit(1 if fails else 0)
