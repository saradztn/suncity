# Created by: Arena.ai Agent Mode (AI) - Park MTA:SA asset pipeline
# -----------------------------------------------------------------------------
# rwtxd.py - RenderWare texture dictionary writer, D3D9 native textures (GTA SA PC / MTA:SA).
#
# Texture Dictionary (0x16)
#   Struct: uint16 count, uint16 device(9 = D3D9)
#   Texture Native (0x15) *
#       Struct: platform(9) | filter/addressing | name[32] | mask[32] | raster format |
#               d3d format (FourCC) | w | h | depth | levels | raster type(4) | flags
#               then per mip: uint32 size + DXT blocks
#       Extension
#   Extension
# -----------------------------------------------------------------------------
import struct
from .rwdff import chunk, struct_chunk, ext, RW_VERSION

ID_TEXDICT, ID_TEXNATIVE = 0x16, 0x15
RASTER_565, RASTER_1555, RASTER_4444, RASTER_MIPMAP = 0x0200, 0x0100, 0x0300, 0x8000
FOURCC = {'DXT1': 0x31545844, 'DXT3': 0x33545844, 'DXT5': 0x35545844}


def _name32(s):
    b = s.encode('ascii')
    assert len(b) < 32
    return b + b'\0' * (32 - len(b))


def native_texture(name, w, h, fmt, chain, has_alpha=False):
    """chain: list of (w,h,bytes) mip levels, full chain."""
    if fmt == 'DXT1':
        raster = (RASTER_1555 if has_alpha else RASTER_565) | RASTER_MIPMAP
        depth = 16
    else:
        raster = RASTER_4444 | RASTER_MIPMAP
        depth = 32
    flags = 0x08 | (1 if has_alpha else 0)
    st = struct.pack('<II', 9, 0x1106)                   # D3D9, linear-mip-linear, wrap/wrap
    st += _name32(name) + _name32('')
    st += struct.pack('<IIHHBBBB', raster, FOURCC[fmt], w, h, depth, len(chain), 4, flags)
    for lw, lh, data in chain:
        st += struct.pack('<I', len(data)) + data
    return chunk(ID_TEXNATIVE, struct_chunk(st) + ext())


def build_txd(textures):
    """textures: list of dict(name, w, h, fmt, chain, alpha)"""
    out = struct_chunk(struct.pack('<HH', len(textures), 9))
    for t in textures:
        out += native_texture(t['name'], t['w'], t['h'], t['fmt'], t['chain'], t.get('alpha', False))
    out += ext()
    return chunk(ID_TEXDICT, out)
