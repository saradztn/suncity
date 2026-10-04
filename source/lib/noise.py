# Created by: Arena.ai Agent Mode (AI) - Park MTA:SA asset pipeline
# -----------------------------------------------------------------------------
# noise.py - procedural noise / scratch helpers used by the castle texture generators (numpy, periodic FFT noise).
#
# The castle textures are baked straight into diffuse (relief + AO included) because San Andreas has no normal maps.
# All patterns are periodic (FFT / wrapped cellular noise) so they tile without seams.
# -----------------------------------------------------------------------------
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

FONT_B = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
FONT_R = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
FONT_M = '/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf'


class Tex:
    def __init__(self, albedo, height, rough, metal, ao):
        self.albedo = np.clip(albedo, 0, 1).astype(np.float32)
        self.height = height.astype(np.float32)
        self.rough = np.clip(rough, 0.04, 1).astype(np.float32)
        self.metal = np.clip(metal, 0, 1).astype(np.float32)
        self.ao = np.clip(ao, 0, 1).astype(np.float32)


# ---------------------------------------------------------------------------
# noise toolbox (all tileable)
# ---------------------------------------------------------------------------
def _norm(a):
    a = a - a.mean()
    return a / (a.std() + 1e-9)


def fnoise(h, w, beta, seed):
    """1/f^beta noise, std = 1"""
    r = np.random.default_rng(seed)
    F = np.fft.rfft2(r.standard_normal((h, w)))
    fy = np.fft.fftfreq(h)[:, None]
    fx = np.fft.rfftfreq(w)[None, :]
    f = np.sqrt(fx * fx + fy * fy)
    f[0, 0] = 1.0
    F = F / (f * max(h, w)) ** (beta / 2.0)
    F[0, 0] = 0
    return _norm(np.fft.irfft2(F, s=(h, w)))


def bnoise(h, w, sx, sy, seed):
    """band-limited (gaussian) noise with correlation lengths sx, sy in pixels, std = 1"""
    r = np.random.default_rng(seed)
    F = np.fft.rfft2(r.standard_normal((h, w)))
    fy = np.fft.fftfreq(h)[:, None] * 2 * np.pi
    fx = np.fft.rfftfreq(w)[None, :] * 2 * np.pi
    F = F * np.exp(-0.5 * ((fx * sx) ** 2 + (fy * sy) ** 2))
    F[0, 0] = 0
    return _norm(np.fft.irfft2(F, s=(h, w)))


def white(h, w, seed):
    return np.random.default_rng(seed).standard_normal((h, w))


def worley(h, w, nx, ny, seed):
    """tileable cellular noise -> (F1, F2, id) with distances in cell units"""
    r = np.random.default_rng(seed)
    pts = r.random((ny, nx, 2))
    ids = r.random((ny, nx))
    X = (np.arange(w) + 0.5)[None, :] / w * nx
    Y = (np.arange(h) + 0.5)[:, None] / h * ny
    cx = np.floor(X).astype(int)
    cy = np.floor(Y).astype(int)
    F1 = np.full((h, w), 9.0)
    F2 = np.full((h, w), 9.0)
    ID = np.zeros((h, w))
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            ccx = cx + dx
            ccy = cy + dy
            px = ccx + pts[ccy % ny, ccx % nx, 0]
            py = ccy + pts[ccy % ny, ccx % nx, 1]
            d = np.sqrt((X - px) ** 2 + (Y - py) ** 2)
            upd = d < F1
            F2 = np.where(upd, F1, np.minimum(F2, d))
            ID = np.where(upd, ids[ccy % ny, ccx % nx], ID)
            F1 = np.where(upd, d, F1)
    return F1, F2, ID


def smooth(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def scratches(h, w, n, lmin, lmax, seed, angle=None, spread=0.3, ss=2, width=1.0):
    """random thin scratches, wrapped; returns 0..1 mask"""
    r = np.random.default_rng(seed)
    im = Image.new('L', (w * ss, h * ss), 0)
    d = ImageDraw.Draw(im)
    for _ in range(n):
        x, y = r.random() * w, r.random() * h
        ang = r.random() * np.pi if angle is None else angle + r.normal(0, spread)
        L = r.uniform(lmin, lmax)
        dx, dy = np.cos(ang) * L, np.sin(ang) * L
        val = int(r.uniform(60, 255))
        for ox in (-w, 0, w):
            for oy in (-h, 0, h):
                d.line([((x + ox) * ss, (y + oy) * ss), ((x + ox + dx) * ss, (y + oy + dy) * ss)], fill=val, width=max(1, int(width * ss)))
    im = im.resize((w, h), Image.BOX)
    return np.asarray(im, np.float32) / 255.0


def normal_from_height(hgt, strength):
    gx = (np.roll(hgt, -1, 1) - np.roll(hgt, 1, 1)) * 0.5
    gy = (np.roll(hgt, -1, 0) - np.roll(hgt, 1, 0)) * 0.5      # d/drow (down)
    nx = -gx * strength
    ny = gy * strength                                          # +Y = image up
    nz = np.ones_like(nx)
    l = np.sqrt(nx * nx + ny * ny + nz * nz)
    return nx / l, ny / l, nz / l


# ---------------------------------------------------------------------------
# bake: Tex -> (diffuse uint8 RGB, normal uint8 RGBA (DXT5nm), orm uint8 RGB)
# ---------------------------------------------------------------------------
def bake(t, nstrength):
    ao = t.ao
    diff = t.albedo * (0.80 + 0.20 * ao[..., None])
    # Game-diffuse lift: authored albedos for black materials (carbon, rubber, plastic) are physically
    # dark (<=12/255), which turns pure black under San Andreas' simple vertex lighting and hides all
    # micro-detail.  Real black rubber/carbon has ~0.04-0.05 linear albedo (~56 sRGB); lift towards it.
    diff = 0.045 + 0.955 * np.power(np.clip(diff, 0, 1), 0.72)
    diffuse = (np.clip(diff, 0, 1) * 255 + 0.5).astype(np.uint8)
    nx, ny, nz = normal_from_height(t.height, nstrength)
    n = np.zeros(t.height.shape + (4,), np.uint8)
    n[..., 0] = 0
    n[..., 1] = ((ny * 0.5 + 0.5) * 255 + 0.5).astype(np.uint8)
    n[..., 2] = 0
    n[..., 3] = ((nx * 0.5 + 0.5) * 255 + 0.5).astype(np.uint8)
    orm = np.stack([ao, t.rough, t.metal], -1)
    orm = (np.clip(orm, 0, 1) * 255 + 0.5).astype(np.uint8)
    return diffuse, n, orm


