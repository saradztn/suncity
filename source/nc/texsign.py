# Created by: Arena.ai Agent Mode (AI) - NightCity MTA:SA asset pipeline
# -----------------------------------------------------------------------------
# texsign.py - procedural PBR materials, part 2: lit glass curtain walls, punched-window walls, shop fronts,
#              neon sign atlases, digital billboards (ads), LED screens, glow sprites and small emissive lights.
# Everything here is emissive at night: the emission map holds the light (lit rooms, tubes, screens).
# -----------------------------------------------------------------------------
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from lib.noise import smooth
from .texkit import PBR, coords, lerp, rgb, blur, fbm, grain, rect_aa, FONT_B, FONT_R, FONT_M
from .texgen import REG, reg

WARM = rgb(1.00, 0.70, 0.40)
WARM2 = rgb(1.00, 0.82, 0.55)
COOL = rgb(0.74, 0.88, 1.00)
WHITE = rgb(0.95, 0.97, 1.00)
MAGENTA = rgb(1.00, 0.18, 0.62)
CYAN = rgb(0.10, 0.88, 1.00)
TVBLUE = rgb(0.30, 0.46, 1.00)
AMBER = rgb(1.00, 0.52, 0.10)
LIME = rgb(0.55, 1.00, 0.25)
VIOLET = rgb(0.55, 0.32, 1.00)
RED = rgb(1.00, 0.12, 0.12)
NEONS = [MAGENTA, CYAN, AMBER, LIME, RED, VIOLET, rgb(0.75, 0.88, 1.0), rgb(1.0, 0.35, 0.2)]
# room light colours (much less saturated than the neon): warm tungsten / LED, cool office white, a little TV blue
W_WARM = rgb(1.00, 0.74, 0.46)
W_WARM2 = rgb(1.00, 0.86, 0.64)
W_COOL = rgb(0.80, 0.89, 1.00)
W_WHITE = rgb(0.96, 0.97, 1.00)
W_TV = rgb(0.52, 0.62, 1.00)
W_MAG = rgb(0.95, 0.42, 0.78)
W_CYA = rgb(0.42, 0.88, 0.96)
W_AMB = rgb(1.00, 0.62, 0.28)


# ---------------------------------------------------------------------------------------------
# curtain wall / punched window facades
# ---------------------------------------------------------------------------------------------
def _pick(rng, pal):
    """pal: list of (colour, weight)"""
    wts = np.array([p[1] for p in pal], np.float64)
    return pal[rng.choice(len(pal), p=wts / wts.sum())][0]


def _facade(h, w, seed, bays, floors, lit, pal, glass, frame, spandrel, wall=None, win=(0.07, 0.04, 0.80), row_corr=0.0, led=None,
            brightness=(0.45, 1.0), spacing_rough=0.07, fins=None, grime=0.5, interior=1.0):
    """win=(mullion, top, bottom) fractions of a cell; wall=None -> glass curtain wall, else colour of the wall around punched windows"""
    rng = np.random.default_rng(seed)
    cw, ch = w // bays, h // floors
    alb = np.zeros((h, w, 3), np.float32)
    em = np.zeros((h, w, 3), np.float32)
    rough = np.zeros((h, w), np.float32)
    metal = np.zeros((h, w), np.float32)
    hgt = np.zeros((h, w), np.float32)
    u1 = (np.arange(cw, dtype=np.float32) + 0.5) / cw
    v1 = (np.arange(ch, dtype=np.float32) + 0.5) / ch
    U, V = np.meshgrid(u1, v1)
    mw, top, bot = win
    row_on = rng.random(floors) < lit
    for fy in range(floors):
        for bx in range(bays):
            sl = (slice(fy * ch, (fy + 1) * ch), slice(bx * cw, (bx + 1) * cw))
            gcov = rect_aa(U, V, mw, top, 1 - mw, bot, 1.0 / cw, 1.0 / ch)
            if wall is None:
                spn = np.clip((V - bot) / (1.0 / ch) + 0.5, 0, 1) * np.clip(1 - (V - 0.995) / (1.0 / ch), 0, 1)
                spn = spn * (1 - gcov)
                fr = np.clip(1 - gcov - spn, 0, 1)
                a = fr[..., None] * np.asarray(frame, np.float32) + spn[..., None] * np.asarray(spandrel, np.float32)
                met = fr * 0.9 + spn * 0.55
                rg = fr * 0.38 + spn * 0.14
                hh = fr * 0.8
            else:
                a = (1 - gcov)[..., None] * np.asarray(wall, np.float32)
                met = np.zeros_like(gcov)
                rg = (1 - gcov) * 0.8
                hh = (1 - gcov) * 0.0 + gcov * -0.8
                # sill + lintel shading
                sill = np.clip(1 - np.abs(V - (bot + 0.02)) / 0.02, 0, 1) * (U > mw * 0.8) * (U < 1 - mw * 0.8)
                a = a * (1 - 0.3 * sill[..., None])
                fr = np.clip(1 - gcov, 0, 1)
            # --- window content
            gv = np.clip((V - top) / max(bot - top, 1e-3), 0, 1)           # 0 top .. 1 bottom of the glass
            on_p = lit if row_corr <= 0 else (0.88 if row_on[fy] else 0.07)
            is_on = rng.random() < on_p
            refl = (0.012 + 0.06 * gv ** 1.6)[..., None] * glass_tint(glass, rng)
            gl = np.asarray(glass, np.float32)[None, None, :] + refl
            e = np.zeros((ch, cw, 3), np.float32)
            if is_on:
                c = _pick(rng, pal)
                bri = float(np.clip(np.exp(rng.normal(np.log(0.5 * (brightness[0] + brightness[1])) - 0.15, 0.5)), brightness[0] * 0.6, brightness[1]))
                prof = (0.55 + 0.45 * (1 - gv)) * interior + (1 - interior)          # ceiling light: brighter at the top
                prof = prof * (1 - 0.38 * (2 * U - 1) ** 2) * (0.92 + 0.08 * np.sin(U * 37.0 + V * 5.0 + rng.uniform(0, 6)))
                prof = prof + 0.55 * np.exp(-((V - top - 0.025) / 0.022) ** 2) * (1 - 0.5 * np.abs(2 * U - 1))
                if rng.random() < 0.40:                                               # blinds (venetian stripes, partly closed)
                    closed = rng.uniform(0.15, 0.7)
                    bl = (np.sin(gv * 55.0) > -0.35).astype(np.float32)
                    prof = prof * np.where(gv < closed, 0.35 + 0.5 * bl, 1.0)
                if rng.random() < 0.55:                                               # furniture silhouettes
                    for _ in range(rng.integers(1, 3)):
                        fx0 = rng.uniform(0.1, 0.7)
                        fw = rng.uniform(0.15, 0.4)
                        fh = rng.uniform(0.2, 0.45)
                        m = rect_aa(U, V, mw + fx0 * (1 - 2 * mw), bot - fh * (bot - top), mw + (fx0 + fw) * (1 - 2 * mw), bot, 1.0 / cw)
                        prof = prof * (1 - 0.75 * m)
                if rng.random() < 0.28:                                               # curtain panel
                    side = rng.random() < 0.5
                    cx0, cx1 = (mw, mw + 0.28 * (1 - 2 * mw)) if side else (1 - mw - 0.28 * (1 - 2 * mw), 1 - mw)
                    m = rect_aa(U, V, cx0, top, cx1, bot, 1.0 / cw)
                    fold = 0.65 + 0.35 * np.sin(U * 90.0)
                    prof = prof * (1 - m * (1 - 0.4 * fold))
                e = gcov[..., None] * (c * bri)[None, None, :] * prof[..., None]
                gl = gl + 0.04 * e
            else:
                # standby LED / faint reflection streak
                if rng.random() < 0.10:
                    sx, sy = rng.uniform(0.2, 0.8), rng.uniform(bot - 0.15, bot - 0.03)
                    m = np.exp(-(((U - sx) ** 2 + (V - sy) ** 2) / 0.0004))
                    e = (gcov * m)[..., None] * rgb(1.0, 0.1, 0.1) * 0.6
            a = a + gcov[..., None] * gl
            rg = rg + gcov * (spacing_rough + 0.03 * rng.random())
            hh = hh
            alb[sl] = a
            em[sl] = e
            rough[sl] = rg
            metal[sl] = met
            hgt[sl] = hh
    # LED lines / fins
    if led is not None:
        kind, col, every = led
        X, Y = coords(h, w)
        if kind == 'floor':      # emissive horizontal strip on the spandrel top every `every` floors
            for fy in range(0, floors, every):
                y0 = (fy + bot + 0.02) / floors
                m = rect_aa(X, Y, 0, y0, 1, y0 + 0.07 / floors, 1.0 / w, 1.0 / h)
                em += m[..., None] * np.asarray(col, np.float32) * 0.9
        elif kind == 'mullion':  # vertical glowing lines on the mullions
            for bx in range(0, bays, every):
                x0 = bx / bays
                m = rect_aa(X, Y, x0 - 0.006, 0, x0 + 0.006, 1, 1.0 / w, 1.0 / h)
                em += m[..., None] * np.asarray(col, np.float32) * 0.8
                alb = lerp(alb, np.asarray(col, np.float32) * 0.5, m[..., None] * 0.6)
    # global grime: vertical rain streaks and dirt
    from scipy import ndimage as ndi
    st = ndi.gaussian_filter(np.random.default_rng(seed + 9).standard_normal((h, w)).astype(np.float32), (h / 5.0, 0.8), mode='wrap')
    st = smooth(0.6, 2.4, st / (st.std() + 1e-9))
    alb = alb * (1 - grime * 0.22 * st[..., None])
    rough = rough + grime * 0.10 * st
    n = fbm(h, w, seed + 10, 2.2)
    alb = alb * (1 + 0.06 * n[..., None])
    return PBR(alb, rough, metal, hgt, em)


def glass_tint(glass, rng):
    g = np.asarray(glass, np.float32)
    t = g / max(g.max(), 1e-3)
    return (0.6 + 0.8 * t)[None, None, :]


# (name, bays, floors, lit, palette, glass, frame, spandrel, kwargs)
GLASS = {
    'nc_glass_a': dict(lit=0.34, row_corr=1.0, pal=[(W_COOL, 5), (W_WHITE, 3), (W_WARM2, 2)], glass=(0.014, 0.022, 0.034), frame=(0.07, 0.075, 0.085), spandrel=(0.035, 0.04, 0.05)),
    'nc_glass_b': dict(lit=0.52, pal=[(W_WARM, 6), (W_WARM2, 4), (W_TV, 0.7), (W_MAG, 0.2), (W_CYA, 0.2), (W_COOL, 1)], glass=(0.018, 0.020, 0.026), frame=(0.06, 0.06, 0.065), spandrel=(0.05, 0.045, 0.045)),
    'nc_glass_c': dict(lit=0.30, row_corr=1.0, pal=[(W_CYA, 3), (W_WHITE, 3), (W_COOL, 2)], glass=(0.010, 0.032, 0.040), frame=(0.05, 0.08, 0.09), spandrel=(0.02, 0.05, 0.06), led=('floor', CYAN, 4)),
    'nc_glass_d': dict(lit=0.22, pal=[(W_WARM2, 5), (W_AMB, 2), (W_WARM, 2)], glass=(0.050, 0.034, 0.020), frame=(0.10, 0.075, 0.045), spandrel=(0.07, 0.05, 0.03)),
    'nc_glass_e': dict(lit=0.92, pal=[(W_COOL, 4), (W_WHITE, 3), (W_CYA, 0.6), (W_TV, 0.6)], glass=(0.012, 0.016, 0.026), frame=(0.06, 0.065, 0.075), spandrel=(0.03, 0.035, 0.045), brightness=(0.10, 0.80)),
    'nc_glass_f': dict(lit=0.14, pal=[(W_WHITE, 5), (W_COOL, 2), (W_MAG, 0.4)], glass=(0.006, 0.007, 0.010), frame=(0.04, 0.04, 0.05), spandrel=(0.015, 0.015, 0.02), led=('mullion', MAGENTA, 2)),
    'nc_glass_g': dict(lit=0.60, pal=[(W_AMB, 3), (W_WARM, 4), (W_WARM2, 3), (W_MAG, 0.3)], glass=(0.022, 0.018, 0.016), frame=(0.20, 0.19, 0.17), spandrel=(0.10, 0.09, 0.08)),
    'nc_glass_h': dict(lit=0.45, row_corr=1.0, pal=[(W_COOL, 3), (W_WARM2, 3), (W_WHITE, 3)], glass=(0.020, 0.022, 0.028), frame=(0.12, 0.12, 0.13), spandrel=(0.06, 0.065, 0.07), led=('floor', MAGENTA, 8)),
}
for _i, (_n, _p) in enumerate(GLASS.items()):
    def _mk(n=_n, p=_p, i=_i):
        def fn(h, w, seed):
            kw = dict(p)
            return _facade(h, w, seed + 2000 + 37 * i, 4, 8, kw.pop('lit'), kw.pop('pal'), kw.pop('glass'), kw.pop('frame'), kw.pop('spandrel'), **kw)
        return fn
    REG[_n] = dict(fn=_mk(), w=512, h=1024, fmt='DXT1')

# punched-window walls (dark masonry / precast concrete with lit rooms)
WALLS = {
    'nc_wall_tenement_a': dict(wall=(0.115, 0.075, 0.085), lit=0.55, pal=[(W_WARM, 6), (W_WARM2, 4), (W_TV, 1.2), (W_MAG, 0.5), (W_CYA, 0.4)], win=(0.20, 0.17, 0.80)),
    'nc_wall_tenement_b': dict(wall=(0.070, 0.105, 0.115), lit=0.50, pal=[(W_WARM2, 5), (W_CYA, 1), (W_AMB, 2), (W_WHITE, 2)], win=(0.18, 0.15, 0.82)),
    'nc_wall_brutal': dict(wall=(0.22, 0.22, 0.225), lit=0.48, pal=[(W_WARM, 4), (W_COOL, 4), (W_WARM2, 2)], win=(0.06, 0.30, 0.66)),
}
for _i, (_n, _p) in enumerate(WALLS.items()):
    def _mk2(n=_n, p=_p, i=_i):
        def fn(h, w, seed):
            kw = dict(p)
            return _facade(h, w, seed + 2400 + 41 * i, 4, 4, kw.pop('lit'), kw.pop('pal'), (0.016, 0.02, 0.03), (0.06, 0.06, 0.07), (0.05, 0.05, 0.05),
                           wall=kw.pop('wall'), grime=1.0, **kw)
        return fn
    REG[_n] = dict(fn=_mk2(), w=512, h=512, fmt='DXT1')


# ---------------------------------------------------------------------------------------------
# shop fronts (12.8 m x 6.4 m: glass shop windows below, illuminated fascia above)
# ---------------------------------------------------------------------------------------------
WORDS = ['NOVA', 'BAR', 'HOTEL', '24H', 'NOODLE', 'CLUB', 'ARCADE', 'SYNTH', 'NEXUS', 'ORBIT', 'AURA', 'HYPER', 'KAIJU', 'MEGA', 'LOTUS', 'VOLT', 'HALO',
         'ZEN', 'DRAGON', 'MOTEL', 'SAKE', 'PHARMA', 'PIXEL', 'VIBE', 'NEON', 'CYBER', 'RAMEN', 'TECH', 'GRID', 'ECHO', 'LUX', 'AXIS']


def _storefront(h, w, seed, kind):
    rng = np.random.default_rng(seed)
    alb = np.zeros((h, w, 3), np.float32) + 0.05
    em = np.zeros((h, w, 3), np.float32)
    rough = np.full((h, w), 0.5, np.float32)
    metal = np.zeros((h, w), np.float32)
    hgt = np.zeros((h, w), np.float32)
    X, Y = coords(h, w)
    bays = 4
    cw = w // bays
    pals = {'retail': [(W_WARM2, 4), (W_COOL, 3), (W_WHITE, 3)], 'club': [(W_MAG, 3), (W_CYA, 2), (W_WARM2, 3), (W_TV, 2)], 'food': [(W_WARM, 5), (W_AMB, 3), (W_WARM2, 3)]}[kind]
    fascia_h = 0.30
    for b in range(bays):
        x0 = b / bays
        c = _pick(rng, pals)
        # shop window opening
        win = rect_aa(X, Y, x0 + 0.018, fascia_h + 0.07, x0 + 1 / bays - 0.018, 0.965, 1.0 / w, 1.0 / h)
        # interior: bright back wall, shelves, product colour dots
        inner = (0.45 + 0.55 * (1 - np.clip((Y - fascia_h) / (1 - fascia_h), 0, 1)) ** 0.7)
        shelf = np.zeros_like(Y)
        for k in range(3):
            sy = fascia_h + 0.13 + k * 0.17
            shelf += rect_aa(X, Y, x0 + 0.03, sy, x0 + 1 / bays - 0.03, sy + 0.012, 1.0 / w, 1.0 / h)
        items = np.zeros_like(Y)
        for _ in range(rng.integers(6, 14)):
            ix = rng.uniform(x0 + 0.04, x0 + 1 / bays - 0.05)
            iy = rng.uniform(fascia_h + 0.10, 0.9)
            items += np.exp(-(((X - ix) ** 2 * 1.0 + (Y - iy) ** 2 * 2.0) / 0.00006))
        ecol = (c * 0.8 + 0.2)[None, None, :]
        e = win[..., None] * ecol * (inner * (1 - 0.6 * np.clip(shelf, 0, 1)))[..., None] * rng.uniform(0.55, 1.0)
        e = e + (win * np.clip(items, 0, 1))[..., None] * _pick(rng, [(MAGENTA, 1), (CYAN, 1), (AMBER, 1), (WHITE, 1)]) * 0.8
        em += e
        alb = lerp(alb, rgb(0.02, 0.025, 0.03), win[..., None])
        # door (every second bay) frame
        if b % 2 == 1:
            dm = rect_aa(X, Y, x0 + 0.045, fascia_h + 0.12, x0 + 0.095, 0.965, 1.0 / w, 1.0 / h)
            alb = lerp(alb, rgb(0.08, 0.08, 0.09), dm[..., None])
        # fascia sign panel (backlit)
        fm = rect_aa(X, Y, x0 + 0.012, 0.045, x0 + 1 / bays - 0.012, fascia_h - 0.02, 1.0 / w, 1.0 / h)
        sc = _pick(rng, [(MAGENTA, 3), (CYAN, 3), (AMBER, 2), (LIME, 1), (WHITE, 2), (RED, 1)])
        im = Image.new('L', (cw, int(h * (fascia_h - 0.065))), 0)
        d = ImageDraw.Draw(im)
        txt = WORDS[rng.integers(len(WORDS))]
        fs = int(im.size[1] * 0.62)
        f = ImageFont.truetype(FONT_B, fs)
        while d.textlength(txt, font=f) > im.size[0] * 0.90 and fs > 8:
            fs -= 2
            f = ImageFont.truetype(FONT_B, fs)
        d.text((im.size[0] / 2, im.size[1] / 2), txt, font=f, fill=255, anchor='mm')
        tm = np.zeros((h, w), np.float32)
        y0p = int(h * 0.055)
        tm[y0p:y0p + im.size[1], b * cw:(b + 1) * cw] = np.asarray(im, np.float32) / 255.0
        tm = np.clip(tm + 0.5 * blur(tm, 1.2, wrap=False), 0, 1)
        em += fm[..., None] * (0.10 * sc[None, None, :] + tm[..., None] * sc[None, None, :] * 1.1)
        alb = lerp(alb, rgb(0.03, 0.03, 0.04), fm[..., None] * 0.9)
    # pilasters / frame
    pil = np.zeros_like(Y)
    for b in range(bays + 1):
        pil += rect_aa(X, Y, b / bays - 0.014, 0.0, b / bays + 0.014, 1.0, 1.0 / w, 1.0 / h)
    alb = lerp(alb, rgb(0.07, 0.07, 0.08), np.clip(pil, 0, 1)[..., None])
    metal = np.clip(pil, 0, 1) * 0.8
    rough = rough - 0.15 * np.clip(pil, 0, 1)
    return PBR(alb, rough, metal, hgt, em)


for _i, _k in enumerate(('retail', 'club', 'food')):
    def _mk3(k=_k, i=_i):
        return lambda h, w, seed: _storefront(h, w, seed + 3000 + 53 * i, k)
    REG['nc_shop_' + _k] = dict(fn=_mk3(), w=512, h=256, fmt='DXT1')


# ---------------------------------------------------------------------------------------------
# neon sign atlases
# ---------------------------------------------------------------------------------------------
def _glyph(d, box, rng, col, wd):
    """pseudo kanji: 6-9 random strokes on a 5x5 lattice inside box"""
    x0, y0, x1, y1 = box
    lat = lambda i, j: (x0 + (x1 - x0) * i / 4.0, y0 + (y1 - y0) * j / 4.0)
    for _ in range(rng.integers(5, 9)):
        t = rng.integers(4)
        i, j = rng.integers(0, 5, 2)
        if t == 0:
            a, b = lat(i, j), lat(min(4, i + rng.integers(1, 4)), j)
        elif t == 1:
            a, b = lat(i, j), lat(i, min(4, j + rng.integers(1, 4)))
        elif t == 2:
            a, b = lat(i, j), lat(min(4, i + rng.integers(1, 3)), min(4, j + rng.integers(1, 3)))
        else:
            a = lat(i, j)
            b = lat(max(0, i - rng.integers(1, 3)), min(4, j + rng.integers(1, 3)))
        d.line([a, b], fill=255, width=wd)
    if rng.random() < 0.5:
        b0 = lat(rng.integers(0, 2), rng.integers(0, 2))
        b1 = lat(rng.integers(3, 5), rng.integers(3, 5))
        d.rectangle([b0, b1], outline=255, width=wd)


_AR = None


def _arabic(txt):
    global _AR
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(txt))
    except Exception:
        return None


ARABIC = ['مدينة الليل', 'مفتوح ٢٤', 'مطعم', 'فندق', 'نيون', 'قهوة']


def _neon_cell(cw, ch, rng, vertical):
    S = 2
    mask = Image.new('L', (cw * S, ch * S), 0)
    d = ImageDraw.Draw(mask)
    wd = max(2, int(min(cw, ch) * 0.045 * S))
    pad = int(min(cw, ch) * 0.12 * S)
    col = NEONS[rng.integers(len(NEONS))]
    col2 = NEONS[rng.integers(len(NEONS))]
    style = rng.integers(5)
    frame = Image.new('L', (cw * S, ch * S), 0)
    df = ImageDraw.Draw(frame)
    df.rounded_rectangle([pad // 2, pad // 2, cw * S - pad // 2, ch * S - pad // 2], radius=pad, outline=255, width=wd)
    use_frame = rng.random() < 0.7
    if vertical:
        if style in (0, 1, 2):          # stack of glyphs
            n = rng.integers(3, 5)
            for k in range(n):
                s = (ch * S - 2 * pad) / n
                _glyph(d, (cw * S * 0.22, pad + k * s + s * 0.1, cw * S * 0.78, pad + (k + 1) * s - s * 0.1), rng, col, wd)
        else:                            # stacked latin letters
            txt = WORDS[rng.integers(len(WORDS))][:5]
            f = ImageFont.truetype(FONT_B, int(min(cw * S * 0.6, (ch * S - 2 * pad) / len(txt) * 0.9)))
            for k, chh in enumerate(txt):
                d.text((cw * S / 2, pad + (k + 0.5) * (ch * S - 2 * pad) / len(txt)), chh, font=f, fill=255, anchor='mm')
    else:
        if style == 0:
            txt = WORDS[rng.integers(len(WORDS))]
            f = ImageFont.truetype(FONT_B, int(ch * S * 0.52))
            d.text((cw * S / 2, ch * S / 2), txt, font=f, fill=255, anchor='mm')
        elif style == 1:
            n = rng.integers(2, 4)
            for k in range(n):
                s = (cw * S - 2 * pad) / n
                _glyph(d, (pad + k * s + s * 0.1, ch * S * 0.2, pad + (k + 1) * s - s * 0.1, ch * S * 0.8), rng, col, wd)
        elif style == 2:
            txt = WORDS[rng.integers(len(WORDS))]
            f = ImageFont.truetype(FONT_B, int(ch * S * 0.34))
            d.text((cw * S * 0.40, ch * S / 2), txt, font=f, fill=255, anchor='mm')
            _glyph(d, (cw * S * 0.74, ch * S * 0.2, cw * S * 0.92, ch * S * 0.8), rng, col, wd)
        elif style == 3:
            ar = _arabic(ARABIC[rng.integers(len(ARABIC))])
            if ar:
                f = ImageFont.truetype(FONT_B, int(ch * S * 0.46))
                d.text((cw * S / 2, ch * S / 2), ar, font=f, fill=255, anchor='mm')
            else:
                txt = WORDS[rng.integers(len(WORDS))]
                d.text((cw * S / 2, ch * S / 2), txt, font=ImageFont.truetype(FONT_B, int(ch * S * 0.5)), fill=255, anchor='mm')
        else:
            txt = WORDS[rng.integers(len(WORDS))]
            d.text((cw * S / 2, ch * S * 0.34), txt, font=ImageFont.truetype(FONT_B, int(ch * S * 0.36)), fill=255, anchor='mm')
            d.line([(pad, ch * S * 0.66), (cw * S - pad, ch * S * 0.66)], fill=255, width=wd)
            d.text((cw * S / 2, ch * S * 0.82), 'OPEN' if rng.random() < 0.5 else '24H', font=ImageFont.truetype(FONT_M, int(ch * S * 0.2)), fill=255, anchor='mm')
    m1 = np.asarray(mask.resize((cw, ch), Image.LANCZOS), np.float32) / 255.0
    m2 = np.asarray(frame.resize((cw, ch), Image.LANCZOS), np.float32) / 255.0 * (1.0 if use_frame else 0.0)
    return m1, m2, col, col2


def _neon_atlas(h, w, seed, vertical):
    rng = np.random.default_rng(seed)
    cols, rows = (8, 4) if vertical else (4, 8)
    cw, ch = w // cols, h // rows
    alb = np.zeros((h, w, 3), np.float32) + 0.012
    em = np.zeros((h, w, 3), np.float32)
    for r in range(rows):
        for c in range(cols):
            m1, m2, col, col2 = _neon_cell(cw, ch, rng, vertical)
            sl = (slice(r * ch, (r + 1) * ch), slice(c * cw, (c + 1) * cw))
            tube = np.clip(m1 + m2, 0, 1)
            core = blur(tube, 0.8, wrap=False)
            glow1 = blur(tube, max(2.0, ch / 28.0), wrap=False)
            glow2 = blur(tube, max(5.0, ch / 9.0), wrap=False)
            colmap = (m1[..., None] * col[None, None, :] + m2[..., None] * col2[None, None, :]) / np.maximum(tube[..., None], 1e-3)
            colmap = np.where(tube[..., None] > 0.02, colmap, col[None, None, :])
            hot = np.clip(core * 1.4 - 0.4, 0, 1)[..., None]
            e = colmap * (core[..., None] * 1.0 + glow1[..., None] * 0.9 + glow2[..., None] * 0.45)
            e = lerp(e, np.array([1, 1, 1], np.float32) * (core[..., None] * 1.1), hot * 0.6)
            board = np.zeros((ch, cw, 3), np.float32) + rng.uniform(0.01, 0.03)
            a = board + tube[..., None] * 0.10 * colmap
            alb[sl] = a
            em[sl] = e
            # outer border of the cell stays black so atlas bleeding is harmless
            edge = 2
            em[sl][:edge] = 0
            em[sl][-edge:] = 0
            em[sl][:, :edge] = 0
            em[sl][:, -edge:] = 0
    return PBR(alb, np.full((h, w), 0.35, np.float32), None, None, em)


REG['nc_neon_h'] = dict(fn=lambda h, w, seed: _neon_atlas(h, w, seed + 4000, False), w=1024, h=1024, fmt='DXT1')
REG['nc_neon_v'] = dict(fn=lambda h, w, seed: _neon_atlas(h, w, seed + 4100, True), w=1024, h=1024, fmt='DXT1')
NEON_ATLAS = {'h': (4, 8), 'v': (8, 4)}      # (columns, rows) -> 32 signs each


def atlas_uv(kind, idx, pad=0.004):
    cols, rows = NEON_ATLAS[kind]
    idx = idx % (cols * rows)
    c, r = idx % cols, idx // cols
    return (c / cols + pad, r / rows + pad, (c + 1) / cols - pad, (r + 1) / rows - pad)


# ---------------------------------------------------------------------------------------------
# billboards (ads) + LED screens
# ---------------------------------------------------------------------------------------------
BRANDS = ['AURA', 'NEXUS', 'VOLT', 'ORBIT', 'HALO', 'ZENITH', 'KAIROS', 'LUMEN', 'PULSE', 'AXIOM', 'NOVA', 'ARC']
TAGS = ['THE FUTURE IS NOW', 'LIVE BEYOND LIMITS', 'POWER YOUR NIGHT', 'SEE EVERYTHING', 'BE THE SIGNAL', 'FEEL THE CITY', 'NEXT GENERATION', 'ZERO LATENCY']


def _ad(cw, ch, rng):
    S = 1
    c1 = NEONS[rng.integers(len(NEONS))] * rng.uniform(0.25, 0.55)
    c2 = NEONS[rng.integers(len(NEONS))] * rng.uniform(0.6, 1.0)
    X, Y = np.meshgrid(np.linspace(0, 1, cw, dtype=np.float32), np.linspace(0, 1, ch, dtype=np.float32))
    ang = rng.uniform(0, np.pi)
    t = np.clip(X * np.cos(ang) + Y * np.sin(ang), 0, 1)
    t = (t - t.min()) / (t.max() - t.min() + 1e-6)
    img = c1[None, None, :] * (1 - t[..., None]) + c2[None, None, :] * t[..., None]
    # bokeh discs / big shapes
    for _ in range(rng.integers(6, 14)):
        cx, cy, r = rng.random(), rng.random(), rng.uniform(0.04, 0.22)
        m = np.clip((r - np.sqrt(((X - cx) * cw / ch) ** 2 + (Y - cy) ** 2)) / 0.01 + 0.5, 0, 1)
        img = img + m[..., None] * NEONS[rng.integers(len(NEONS))][None, None, :] * rng.uniform(0.05, 0.22)
    # diagonal bars
    if rng.random() < 0.6:
        bw = rng.uniform(0.03, 0.09)
        for k in range(rng.integers(2, 5)):
            off = rng.uniform(0, 1)
            m = np.clip((bw - np.abs((X * 0.8 + Y * 0.6) % 1.0 - off)) / 0.006 + 0.5, 0, 1)
            img = img + m[..., None] * WHITE[None, None, :] * 0.12
    im = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    side = rng.random() < 0.5
    bx = cw * (0.28 if side else 0.72)
    # product: glossy capsule / ring / device
    kind = rng.integers(3)
    if kind == 0:
        d.rounded_rectangle([bx - cw * 0.08, ch * 0.16, bx + cw * 0.08, ch * 0.84], radius=int(cw * 0.08), fill=(235, 240, 250))
        d.rounded_rectangle([bx - cw * 0.05, ch * 0.20, bx - cw * 0.02, ch * 0.78], radius=int(cw * 0.03), fill=(255, 255, 255))
    elif kind == 1:
        d.ellipse([bx - ch * 0.34, ch * 0.16, bx + ch * 0.34, ch * 0.84], outline=(250, 250, 255), width=int(ch * 0.07))
        d.ellipse([bx - ch * 0.16, ch * 0.34, bx + ch * 0.16, ch * 0.66], fill=(250, 250, 255))
    else:
        d.rounded_rectangle([bx - cw * 0.11, ch * 0.14, bx + cw * 0.11, ch * 0.86], radius=int(cw * 0.025), fill=(20, 22, 30), outline=(235, 240, 250), width=int(cw * 0.008))
        d.rounded_rectangle([bx - cw * 0.095, ch * 0.18, bx + cw * 0.095, ch * 0.82], radius=int(cw * 0.02), fill=tuple(int(255 * x) for x in c2))
    tx = cw * (0.70 if side else 0.30)
    brand = BRANDS[rng.integers(len(BRANDS))]
    fs = int(ch * 0.26)
    bf = ImageFont.truetype(FONT_B, fs)
    while d.textlength(brand, font=bf) > cw * 0.40 and fs > 8:
        fs -= 2
        bf = ImageFont.truetype(FONT_B, fs)
    d.text((tx, ch * 0.40), brand, font=bf, fill=(255, 255, 255), anchor='mm')
    tag = TAGS[rng.integers(len(TAGS))]
    tfs = int(ch * 0.075)
    tf = ImageFont.truetype(FONT_R, tfs)
    while d.textlength(tag, font=tf) > cw * 0.40 and tfs > 6:
        tfs -= 1
        tf = ImageFont.truetype(FONT_R, tfs)
    d.text((tx, ch * 0.64), tag, font=tf, fill=(235, 240, 255), anchor='mm')
    d.rectangle([tx - cw * 0.16, ch * 0.75, tx + cw * 0.16, ch * 0.77], fill=(255, 255, 255))
    out = np.asarray(im, np.float32) / 255.0
    # scan lines + pixel grid hint
    out = out * (0.92 + 0.08 * (np.arange(ch)[:, None, None] % 3 != 0))
    return out


def _ads(h, w, seed):
    rng = np.random.default_rng(seed)
    cols, rows = 2, 4
    cw, ch = w // cols, h // rows
    img = np.zeros((h, w, 3), np.float32)
    for r in range(rows):
        for c in range(cols):
            img[r * ch:(r + 1) * ch, c * cw:(c + 1) * cw] = _ad(cw, ch, rng)
    em = img ** 2.2 * 1.0
    return PBR(img * 0.12, np.full((h, w), 0.2, np.float32), None, None, em * 1.0)


REG['nc_ads'] = dict(fn=lambda h, w, seed: _ads(h, w, seed + 5000), w=1024, h=1024, fmt='DXT1')
AD_CELLS = (2, 4)


def ad_uv(idx, pad=0.003):
    cols, rows = AD_CELLS
    idx = idx % (cols * rows)
    c, r = idx % cols, idx // cols
    return (c / cols + pad, r / rows + pad, (c + 1) / cols - pad, (r + 1) / rows - pad)


def _led(h, w, seed):
    rng = np.random.default_rng(seed)
    cells = 2
    cw, ch = w // cells, h // cells
    em = np.zeros((h, w, 3), np.float32)
    pitch = max(4, cw // 64)
    for r in range(cells):
        for c in range(cells):
            X, Y = np.meshgrid(np.linspace(0, 1, 64, dtype=np.float32), np.linspace(0, 1, 64, dtype=np.float32))
            kind = (r * cells + c)
            p1, p2, p3 = rng.uniform(0, 6.28, 3)
            if kind == 0:      # plasma waves
                v = np.sin(X * 9 + p1) + np.sin(Y * 7 + p2) + np.sin((X + Y) * 6 + p3)
                col = np.stack([0.5 + 0.5 * np.sin(v + 0), 0.5 + 0.5 * np.sin(v + 2.1), 0.5 + 0.5 * np.sin(v + 4.2)], -1)
            elif kind == 1:    # concentric rings
                rr = np.sqrt((X - 0.5) ** 2 + (Y - 0.5) ** 2)
                v = 0.5 + 0.5 * np.sin(rr * 40)
                col = v[..., None] * CYAN[None, None, :] + (1 - v[..., None]) * MAGENTA[None, None, :] * 0.8
            elif kind == 2:    # digital rain
                v = np.zeros((64, 64), np.float32)
                for x in range(64):
                    y0 = rng.integers(0, 64)
                    L = rng.integers(8, 40)
                    ys = (np.arange(64) - y0) % 64
                    v[:, x] = np.where(ys < L, 1 - ys / L, 0) * rng.uniform(0.5, 1.0)
                col = v[..., None] * LIME[None, None, :]
            else:              # equaliser bars
                v = np.zeros((64, 64), np.float32)
                for x in range(0, 64, 3):
                    hgt = rng.uniform(0.15, 0.95)
                    v[:, x:x + 2] = (Y[:, x:x + 2] > 1 - hgt)
                col = v[..., None] * (AMBER[None, None, :] * (1 - Y[..., None]) + MAGENTA[None, None, :] * Y[..., None])
            big = np.kron(col, np.ones((cw // 64, ch // 64, 1), np.float32)) if cw % 64 == 0 else np.asarray(Image.fromarray((col * 255).astype(np.uint8)).resize((cw, ch), Image.NEAREST), np.float32) / 255
            # LED dot mask
            yy, xx = np.meshgrid(np.arange(ch), np.arange(cw), indexing='ij')
            fx, fy = (xx % (cw // 64)) / (cw // 64) - 0.5, (yy % (ch // 64)) / (ch // 64) - 0.5
            dot = np.clip((0.42 - np.sqrt(fx * fx + fy * fy)) / 0.08 + 0.5, 0, 1)
            em[r * ch:(r + 1) * ch, c * cw:(c + 1) * cw] = big * dot[..., None]
    return PBR(em * 0.06 + 0.01, np.full((h, w), 0.25, np.float32), None, None, em)


REG['nc_led'] = dict(fn=lambda h, w, seed: _led(h, w, seed + 5200), w=512, h=512, fmt='DXT1')
LED_CELLS = 2


def led_uv(idx, pad=0.004):
    c, r = idx % LED_CELLS, (idx // LED_CELLS) % LED_CELLS
    return (c / LED_CELLS + pad, r / LED_CELLS + pad, (c + 1) / LED_CELLS - pad, (r + 1) / LED_CELLS - pad)


# ---------------------------------------------------------------------------------------------
# glow sprites (alpha) and small emissive lights
# ---------------------------------------------------------------------------------------------
@reg('nc_glow', 128, 128, fmt='DXT5')
def glow(h, w, seed):
    X, Y = coords(h, w)
    r = np.sqrt((X - 0.5) ** 2 + (Y - 0.5) ** 2) * 2
    a = np.clip(1 - r, 0, 1) ** 2.4
    core = np.clip(1 - r * 5, 0, 1)
    col = np.ones((h, w, 3), np.float32)
    return PBR(col, None, None, None, col * a[..., None], alpha=np.clip(a + core, 0, 1))


@reg('nc_steam', 256, 256, fmt='DXT5')
def steam(h, w, seed):
    X, Y = coords(h, w)
    n = fbm(h, w, seed + 6000, 2.4)
    r = np.sqrt(((X - 0.5) * 1.0) ** 2 + ((Y - 0.55) * 0.9) ** 2) * 2
    a = np.clip(1 - r, 0, 1) ** 1.2 * np.clip(0.55 + 0.6 * n, 0, 1)
    col = np.ones((h, w, 3), np.float32) * 0.62
    return PBR(col, None, None, None, None, alpha=np.clip(a * 0.9, 0, 1))


def _lightcol(name, col):
    def fn(h, w, seed):
        X, Y = coords(h, w)
        r = np.sqrt((X - 0.5) ** 2 + (Y - 0.5) ** 2) * 2
        c = np.asarray(col, np.float32)[None, None, :] * (1.0 - 0.25 * np.clip(r, 0, 1))[..., None]
        return PBR(c * 0.9, np.full((h, w), 0.3, np.float32), None, None, c)
    REG[name] = dict(fn=fn, w=64, h=64, fmt='DXT1')


# light heads / LED strips: a flat emissive colour (the game diffuse is albedo + emission)
_lightcol('nc_light_white', rgb(0.92, 0.96, 1.0))
_lightcol('nc_light_warm', rgb(1.0, 0.66, 0.30))
_lightcol('nc_light_red', rgb(1.0, 0.05, 0.03))
_lightcol('nc_light_green', rgb(0.2, 1.0, 0.35))
_lightcol('nc_light_amber', rgb(1.0, 0.55, 0.05))
_lightcol('nc_light_cyan', rgb(0.1, 0.9, 1.0))
_lightcol('nc_light_magenta', rgb(1.0, 0.1, 0.6))
_lightcol('nc_strip_cyan', rgb(0.1, 0.9, 1.0))
_lightcol('nc_strip_white', rgb(0.9, 0.95, 1.0))


@reg('nc_ac', 128, 128)
def ac(h, w, seed):
    X, Y = coords(h, w)
    n = fbm(h, w, seed + 7000, 2.0)
    a = np.zeros((h, w, 3), np.float32) + (0.42 + 0.05 * n)[..., None]
    # fan grille: concentric rings + radial bars
    r = np.sqrt((X - 0.5) ** 2 + (Y - 0.5) ** 2)
    ring = np.clip(1 - np.abs(((r * 18) % 1.0) - 0.5) / 0.12, 0, 1) * (r < 0.42)
    a = lerp(a, rgb(0.06, 0.06, 0.07), ((r < 0.44) * 0.85)[..., None])
    a = a + ring[..., None] * 0.30
    a = a * (1 - 0.3 * np.clip(Y - 0.8, 0, 1)[..., None] * 3)
    return PBR(a, 0.5 + 0.1 * n, (r < 0.44) * 0.6, ring * 0.4)


@reg('nc_vent', 128, 128)
def vent(h, w, seed):
    X, Y = coords(h, w)
    sl = np.clip(1 - np.abs(((Y * 10) % 1.0) - 0.5) / 0.25, 0, 1)
    a = np.zeros((h, w, 3), np.float32) + 0.28
    a = lerp(a, rgb(0.03, 0.03, 0.035), sl[..., None] * 0.9)
    return PBR(a, 0.45, 0.8 * np.ones((h, w), np.float32), -sl * 0.7)
