# Created by: Arena.ai Agent Mode (AI) - NightCity MTA:SA asset pipeline
# -----------------------------------------------------------------------------
# texkit.py - helpers for the procedural texture sets (numpy / scipy / PIL).
#
# Every generator returns a PBR set: albedo (sRGB 0..1), roughness, metallic, height, emission (linear colour, 0..1+),
# optional alpha.  All patterns are periodic (FFT noise, wrapped filters) so they tile without seams.
# San Andreas has no PBR pipeline, so only albedo + emission end up in the game (DXT1 diffuse); roughness / metallic /
# height are authoring maps that shape the albedo (cavity AO, wet polish, ...).
# -----------------------------------------------------------------------------
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage as ndi
from lib.noise import fnoise, bnoise, worley, smooth, scratches

# ---------------------------------------------------------------------------------------
# fonts: resolved per platform (Windows / macOS / Linux) - the build must never depend on
# one absolute path.  FONT_B / FONT_R / FONT_M are kind keys for load_font(); every text
# drawing call goes through load_font(), which falls back to the PIL default and never raises.
# ---------------------------------------------------------------------------------------
FONT_B = 'b'   # bold sans   (headings, brands)
FONT_R = 'r'   # regular     (tag lines, small print)
FONT_M = 'm'   # bold mono   (badges like "OPEN" / "24H")

_FONT_FILES = {
    'b': ['DejaVuSans-Bold.ttf', 'DejaVuSans-Bold.otf', 'LiberationSans-Bold.ttf',
          'arialbd.ttf', 'Arial Bold.ttf', 'Arial_Bold.ttf', 'segoeuib.ttf', 'verdanab.ttf',
          'calibrib.ttf', 'tahomabd.ttf', 'NotoSans-Bold.ttf', 'FreeSansBold.ttf'],
    'r': ['DejaVuSans.ttf', 'DejaVuSans.otf', 'LiberationSans-Regular.ttf',
          'arial.ttf', 'Arial.ttf', 'segoeui.ttf', 'verdana.ttf', 'calibri.ttf', 'tahoma.ttf',
          'NotoSans-Regular.ttf', 'FreeSans.ttf'],
    'm': ['DejaVuSansMono-Bold.ttf', 'DejaVuSansMono.ttf', 'LiberationMono-Bold.ttf',
          'consolab.ttf', 'courbd.ttf', 'consola.ttf', 'Menlo.ttc', 'monaco.ttf'],
}


def _font_dirs():
    dirs = []
    windir = os.environ.get('WINDIR') or os.environ.get('SystemRoot')
    if windir:
        dirs.append(os.path.join(windir, 'Fonts'))
    local = os.environ.get('LOCALAPPDATA')
    if local:
        dirs.append(os.path.join(local, 'Microsoft', 'Windows', 'Fonts'))
    dirs += ['/usr/share/fonts', '/usr/share/fonts/truetype', '/usr/share/fonts/truetype/dejavu',
             '/usr/share/fonts/truetype/liberation', '/usr/share/fonts/truetype/noto',
             '/usr/share/fonts/TTF', '/usr/local/share/fonts',
             '/Library/Fonts', '/System/Library/Fonts', '/Library/Fonts/Supplemental',
             os.path.expanduser('~/Library/Fonts')]
    out, seen = [], set()
    for d in dirs:
        d = os.path.normpath(d)
        if d not in seen and os.path.isdir(d):
            seen.add(d)
            out.append(d)
    return out


_FONT_RESOLVED = {}   # kind -> path or None (only resolved once)


def _find_font_path(kind):
    if kind in _FONT_RESOLVED:
        return _FONT_RESOLVED[kind]
    names = [n.lower() for n in _FONT_FILES.get(kind, _FONT_FILES['b'])]
    dirs = _font_dirs()
    found = None
    for name in names:                                    # exact file names first
        for d in dirs:
            p = os.path.join(d, name)
            if os.path.isfile(p):
                found = p
                break
        if found:
            break
    if not found:                                         # then a shallow scan for the same names
        for d in dirs:
            for root, subdirs, files in os.walk(d):
                subdirs[:] = [s for s in subdirs if not s.startswith('.')]
                if root.count(os.sep) - d.count(os.sep) > 2:
                    subdirs.clear()
                    continue
                low = {f.lower(): f for f in files}
                for name in names:
                    if name in low:
                        found = os.path.join(root, low[name])
                        break
                if found:
                    break
            if found:
                break
    if found:
        print('   font %-7s %s' % (kind, found))
    _FONT_RESOLVED[kind] = found
    return found


def load_font(kind, size):
    """PIL font of the given kind ('b' / 'r' / 'm') at pixel size.  Never raises."""
    size = max(6, int(size))
    p = _find_font_path(kind)
    if p:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            pass
    try:
        return ImageFont.load_default(size)      # Pillow >= 10.1: sized default face
    except TypeError:
        return ImageFont.load_default()


class PBR:
    def __init__(self, albedo, rough=None, metal=None, height=None, emit=None, alpha=None):
        h, w = albedo.shape[:2]

        def full(a, default):
            a = np.asarray(default if a is None else a, np.float32)
            return np.broadcast_to(a, (h, w)).copy()
        self.albedo = np.clip(albedo, 0, 1).astype(np.float32)
        self.rough = np.clip(full(rough, 0.6), 0.03, 1)
        self.metal = np.clip(full(metal, 0.0), 0, 1)
        self.height = full(height, 0.0)
        self.emit = (np.zeros((h, w, 3), np.float32) if emit is None else np.maximum(emit, 0)).astype(np.float32)
        self.alpha = None if alpha is None else np.clip(alpha, 0, 1).astype(np.float32)

    @property
    def shape(self):
        return self.albedo.shape[:2]

    def game_rgb(self, emit_gain=1.0, alpha=False):
        """diffuse for the game: albedo + emission, uint8 RGB(A)"""
        c = np.clip(self.albedo + np.minimum(self.emit, 1.5) * emit_gain, 0, 1)
        out = (c * 255 + 0.5).astype(np.uint8)
        if alpha:
            a = np.ones(c.shape[:2], np.float32) if self.alpha is None else self.alpha
            out = np.concatenate([out, (a * 255 + 0.5).astype(np.uint8)[..., None]], -1)
        return out


# ---------------------------------------------------------------------------------------------
def coords(h, w):
    y = (np.arange(h, dtype=np.float32) + 0.5) / h
    x = (np.arange(w, dtype=np.float32) + 0.5) / w
    return np.meshgrid(x, y)          # X, Y   (shape h,w)


def lerp(a, b, t):
    return a + (b - a) * t


def rgb(r, g, b):
    return np.array([r, g, b], np.float32)


def blur(a, sigma, wrap=True):
    if a.ndim == 3:
        return np.stack([ndi.gaussian_filter(a[..., c], sigma, mode='wrap' if wrap else 'nearest') for c in range(a.shape[2])], -1)
    return ndi.gaussian_filter(a, sigma, mode='wrap' if wrap else 'nearest')


def fbm(h, w, seed, beta=2.0):
    return fnoise(h, w, beta, seed).astype(np.float32)


def grain(h, w, seed, sigma=0.6):
    g = np.random.default_rng(seed).standard_normal((h, w)).astype(np.float32)
    if sigma > 0:
        g = ndi.gaussian_filter(g, sigma, mode='wrap')
    return g / (g.std() + 1e-9)


def rect_aa(X, Y, x0, y0, x1, y1, px, py=None):
    """anti aliased rectangle coverage in normalised coordinates (px, py = pixel size in the same units)"""
    py = px if py is None else py
    cx = np.clip((X - x0) / px + 0.5, 0, 1) * np.clip((x1 - X) / px + 0.5, 0, 1)
    cy = np.clip((Y - y0) / py + 0.5, 0, 1) * np.clip((y1 - Y) / py + 0.5, 0, 1)
    return cx * cy


def tile_rep(a, ny, nx):
    return np.tile(a, (ny, nx) + (1,) * (a.ndim - 2))


def height_ao(height, strength=2.0, sigma=3.0):
    """cheap cavity AO from a height map (darkens crevices)"""
    hb = blur(height, sigma)
    return np.clip(1.0 + strength * np.minimum(height - hb, 0.0), 0.4, 1.0)


def srgb2lin(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def lin2srgb(c):
    c = np.clip(c, 0, None)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def draw_text_img(w, h, text, size, fill=(255, 255, 255), font=FONT_B, bg=(0, 0, 0, 0), anchor='mm', xy=None, stroke=0):
    im = Image.new('RGBA', (w, h), bg)
    d = ImageDraw.Draw(im)
    f = load_font(font, size)
    d.text(xy or (w / 2, h / 2), text, font=f, fill=fill, anchor=anchor, stroke_width=stroke, stroke_fill=fill)
    return im
