# Created by: Arena.ai Agent Mode (AI) - NightCity MTA:SA asset pipeline
# -----------------------------------------------------------------------------
# textunnel.py - the two tunnel materials: glazed wall tiles (one panel = 4.0 m along the tunnel x 4.8 m from the road to the
#                ceiling, mapped once from the road up) and the green portal gantry sign.
# -----------------------------------------------------------------------------
import numpy as np
from scipy import ndimage as ndi
from PIL import Image, ImageDraw, ImageFont
from lib.noise import smooth
from .texgen import reg
from .texkit import PBR, coords, lerp, rgb, fbm, grain, FONT_B, FONT_R

PANEL_W = 4.0       # metres of tunnel wall covered by one texture repeat
PANEL_H = 4.8       # metres from the road to the ceiling (the texture is NOT repeated vertically)


def _bar(m, c, wdt, px):
    return np.clip((wdt / 2 - np.abs(m - c)) / px + 0.5, 0, 1)


@reg('nc_tunnel_tile', 512, 512)
def tunnel_tile(h, w, seed):
    X, Y = coords(h, w)
    mx = X * PANEL_W
    mz = (1.0 - Y) * PANEL_H                      # metres above the road surface (bottom of the image = road)
    px, pz = PANEL_W / w, PANEL_H / h
    n1 = fbm(h, w, seed + 1, 2.2)
    n2 = fbm(h, w, seed + 2, 1.3)
    g = grain(h, w, seed + 3, 0.7)
    rng = np.random.default_rng(seed + 4)
    st = ndi.gaussian_filter(rng.standard_normal((h, w)).astype(np.float32), (h * 0.06, 1.0), mode='wrap')
    st = st / (st.std() + 1e-9)
    # glazed tiles 1.0 m x 0.5 m in a running bond (4 tiles per panel, so the pattern is continuous from panel to panel)
    row = np.floor(mz / 0.5)
    mxo = mx + (row % 2) * 0.5
    fx = mxo % 1.0
    fz = mz % 0.5
    joint = np.maximum(np.clip((0.011 - np.minimum(fx, 1.0 - fx)) / px + 0.5, 0, 1),
                       np.clip((0.011 - np.minimum(fz, 0.5 - fz)) / pz + 0.5, 0, 1))
    tid = (np.floor(mxo).astype(np.int64) % 5) + 5 * (row.astype(np.int64) % 12)
    tone = rng.uniform(-0.045, 0.045, 64).astype(np.float32)[tid]
    alb = (rgb(0.60, 0.63, 0.62)[None, None, :] + tone[..., None]) * (1 + 0.05 * n1)[..., None]
    gr = np.exp(-mz / 0.9) * (0.55 + 0.45 * n2)                       # road grime splashes up the wall
    alb = alb * (1 - 0.58 * gr)[..., None]
    soot = smooth(3.8, 4.8, mz) * (0.30 + 0.30 * n1)                    # exhaust soot under the ceiling
    alb = alb * (1 - 0.55 * soot)[..., None]
    alb = alb * (1 + 0.045 * st * smooth(0.6, 3.0, mz))[..., None]     # vertical water / dirt streaks
    alb = alb * (1 - 0.48 * joint)[..., None]
    alb = alb * (1 + 0.025 * g)[..., None]
    # concrete kerb band at the foot of the wall
    kerb = 1 - smooth(0.30, 0.38, mz)
    alb = lerp(alb, rgb(0.17, 0.17, 0.18)[None, None, :] * (1 + 0.15 * g)[..., None], kerb[..., None])
    # retro-reflective guide strip (cyan white) and the shadow line of the cable tray
    band = _bar(mz, 0.60, 0.07, pz)
    alb = lerp(alb, rgb(0.55, 0.80, 0.85)[None, None, :], band[..., None])
    tray = _bar(mz, 3.88, 0.22, pz)
    alb = alb * (1 - 0.60 * tray)[..., None]
    # amber delineator lamps, one per panel (every 4 m)
    d2 = ((mx - 2.0) / 0.10) ** 2 + ((mz - 0.95) / 0.05) ** 2
    lamp = np.exp(-d2)
    halo = np.exp(-(((mx - 2.0) / 0.55) ** 2 + ((mz - 0.95) / 0.38) ** 2)) * 0.10
    amber = rgb(1.0, 0.55, 0.12)
    emit = (lamp * 1.3 + halo)[..., None] * amber[None, None, :] + band[..., None] * rgb(0.06, 0.20, 0.23)[None, None, :]
    rough = 0.28 + 0.35 * gr + 0.10 * n2
    hgt = -0.6 * joint - 0.25 * tray
    return PBR(np.clip(alb, 0, 1), rough, None, hgt, emit)


@reg('nc_tunnel_sign', 512, 128)
def tunnel_sign(h, w, seed):
    im = Image.new('RGB', (w, h), (6, 94, 46))
    d = ImageDraw.Draw(im)
    d.rectangle([2, 2, w - 3, h - 3], outline=(236, 242, 236), width=5)
    # down arrow on the left
    d.polygon([(46, 20), (78, 20), (78, 60), (100, 60), (62, 106), (24, 60), (46, 60)], fill=(240, 246, 240))
    size = 60
    while size > 20:
        f1 = ImageFont.truetype(FONT_B, size)
        if d.textlength('RIVER TUNNEL', font=f1) <= w - 150:
            break
        size -= 2
    d.text((128 + (w - 150) / 2, h * 0.38), 'RIVER TUNNEL', font=f1, fill=(244, 248, 244), anchor='mm')
    f2 = ImageFont.truetype(FONT_R, 21)
    d.text((128 + (w - 150) / 2, h * 0.79), 'LOW BEAM  -  540 m  -  4.5 m', font=f2, fill=(220, 236, 224), anchor='mm')
    a = np.asarray(im, np.float32) / 255.0
    n = fbm(h, w, seed + 7, 2.0)
    a = np.clip(a * (1 + 0.03 * n)[..., None], 0, 1)
    ink = (a.max(axis=2) > 0.80).astype(np.float32)
    emit = ink[..., None] * rgb(0.34, 0.36, 0.34)[None, None, :] + (1 - ink)[..., None] * rgb(0.0, 0.05, 0.02)[None, None, :]
    return PBR(a, 0.35, None, None, emit)
