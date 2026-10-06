# Created by: Arena.ai Agent Mode (AI) - Park MTA:SA asset pipeline
# dxt.py - vectorised DXT1 / DXT5 block encoder + decoder, mip-chain builder, DDS writer.
#
# Encoder: PCA principal-axis end-points -> 565 quantisation -> exhaustive nearest
# palette index per texel (4 colours).  DXT5 alpha: min/max end-points with the
# 8-value interpolation mode.  Block memory order follows the D3D9 specification.
import struct
import numpy as np
from PIL import Image


def _blocks(img):
    h, w, c = img.shape
    b = img.reshape(h // 4, 4, w // 4, 4, c).transpose(0, 2, 1, 3, 4).reshape(-1, 16, c)
    return b


def _to565(c):
    c = np.clip(np.rint(c), 0, 255).astype(np.int32)
    r = (c[..., 0] * 31 + 127) // 255
    g = (c[..., 1] * 63 + 127) // 255
    b = (c[..., 2] * 31 + 127) // 255
    return (r << 11) | (g << 5) | b


def _from565(v):
    r = (v >> 11) & 31
    g = (v >> 5) & 63
    b = v & 31
    r = (r << 3) | (r >> 2)
    g = (g << 2) | (g >> 4)
    b = (b << 3) | (b >> 2)
    return np.stack([r, g, b], -1).astype(np.float32)


def encode_dxt1_blocks(px):
    """px: (N,16,3) float32 0..255 -> (N,8) uint8"""
    N = px.shape[0]
    mean = px.mean(axis=1, keepdims=True)
    d = px - mean
    cov = np.einsum('nki,nkj->nij', d, d) / 16.0
    cov += np.eye(3)[None] * 1e-6
    w, v = np.linalg.eigh(cov)
    axis = v[:, :, -1]                                   # (N,3) principal axis
    t = np.einsum('nki,ni->nk', d, axis)
    tmin = t.min(axis=1)
    tmax = t.max(axis=1)
    # slight inset keeps interior texels from clipping against the end-points
    inset = (tmax - tmin) / 16.0
    ca = mean[:, 0] + axis * (tmin + inset)[:, None]
    cb = mean[:, 0] + axis * (tmax - inset)[:, None]
    qa = _to565(ca)
    qb = _to565(cb)
    swap = qa < qb
    q0 = np.where(swap, qb, qa)
    q1 = np.where(swap, qa, qb)
    same = q0 == q1
    c0 = _from565(q0)
    c1 = _from565(q1)
    pal = np.stack([c0, c1, (2 * c0 + c1) / 3.0, (c0 + 2 * c1) / 3.0], 1)    # (N,4,3)
    dist = ((px[:, :, None, :] - pal[:, None, :, :]) ** 2).sum(-1)           # (N,16,4)
    idx = dist.argmin(-1).astype(np.uint32)
    idx[same] = 0
    bits = np.zeros(N, np.uint32)
    for k in range(16):
        bits |= idx[:, k] << np.uint32(2 * k)
    out = np.zeros((N, 8), np.uint8)
    out[:, 0] = (q0 & 255)
    out[:, 1] = (q0 >> 8) & 255
    out[:, 2] = (q1 & 255)
    out[:, 3] = (q1 >> 8) & 255
    for k in range(4):
        out[:, 4 + k] = (bits >> np.uint32(8 * k)) & 255
    return out


def encode_alpha_blocks(a):
    """a: (N,16) float 0..255 -> (N,8) uint8  (DXT5 interpolated alpha, a0>a1)"""
    N = a.shape[0]
    a0 = np.clip(np.rint(a.max(axis=1)), 0, 255)
    a1 = np.clip(np.rint(a.min(axis=1)), 0, 255)
    same = a0 == a1
    a0 = np.where(same, np.minimum(a0 + 1, 255), a0)
    a1 = np.where(same & (a0 == 255), 254, a1)
    pal = np.zeros((N, 8))
    pal[:, 0] = a0
    pal[:, 1] = a1
    for i in range(1, 7):
        pal[:, 1 + i] = ((7 - i) * a0 + i * a1) / 7.0
    dist = np.abs(a[:, :, None] - pal[:, None, :])
    idx = dist.argmin(-1).astype(np.uint64)
    bits = np.zeros(N, np.uint64)
    for k in range(16):
        bits |= idx[:, k] << np.uint64(3 * k)
    out = np.zeros((N, 8), np.uint8)
    out[:, 0] = a0.astype(np.uint8)
    out[:, 1] = a1.astype(np.uint8)
    for k in range(6):
        out[:, 2 + k] = ((bits >> np.uint64(8 * k)) & np.uint64(255)).astype(np.uint8)
    return out


def encode(img, fmt):
    """img uint8 (H,W,3|4); fmt 'DXT1' | 'DXT5' -> bytes of one mip level"""
    h, w = img.shape[:2]
    assert h % 4 == 0 and w % 4 == 0
    chunks = []
    imgf = img.astype(np.float32)
    B = _blocks(imgf)
    for s in range(0, len(B), 65536):
        blk = B[s:s + 65536]
        if fmt == 'DXT1':
            chunks.append(encode_dxt1_blocks(blk[..., :3]))
        else:
            al = encode_alpha_blocks(blk[..., 3] if blk.shape[-1] > 3 else np.full(blk.shape[:2], 255.0))
            co = encode_dxt1_blocks(blk[..., :3])
            chunks.append(np.concatenate([al, co], axis=1))
    return np.concatenate(chunks).tobytes()


def level_size(w, h, fmt):
    bs = 8 if fmt == 'DXT1' else 16
    return max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * bs


def build_mips(img):
    """full chain down to 1x1 (box filter). img uint8 HxWxC"""
    lv = [img]
    im = img
    while im.shape[0] > 1 or im.shape[1] > 1:
        h, w = max(1, im.shape[0] // 2), max(1, im.shape[1] // 2)
        chans = [np.asarray(Image.fromarray(im[..., c]).resize((w, h), Image.BOX)) for c in range(im.shape[2])]
        im = np.stack(chans, -1)
        lv.append(im)
    return lv


def compress_chain(img, fmt):
    """returns list of (w,h,bytes) for every mip level; sub-4px levels are padded to 4x4 blocks"""
    out = []
    for lvl in build_mips(img):
        h, w = lvl.shape[:2]
        ph, pw = max(4, (h + 3) // 4 * 4), max(4, (w + 3) // 4 * 4)
        if (ph, pw) != (h, w):
            lvl = np.pad(lvl, ((0, ph - h), (0, pw - w), (0, 0)), mode='edge')
        out.append((w, h, encode(lvl, fmt)))
    return out


# ---------------------------------------------------------------------------
# decoder (used by the validator)
# ---------------------------------------------------------------------------
def decode(data, w, h, fmt):
    bs = 8 if fmt == 'DXT1' else 16
    nbx, nby = max(1, (w + 3) // 4), max(1, (h + 3) // 4)
    arr = np.frombuffer(data, np.uint8)[:nbx * nby * bs].reshape(nby * nbx, bs)
    col = arr[:, bs - 8:]
    q0 = col[:, 0].astype(np.int32) | (col[:, 1].astype(np.int32) << 8)
    q1 = col[:, 2].astype(np.int32) | (col[:, 3].astype(np.int32) << 8)
    c0 = _from565(q0)
    c1 = _from565(q1)
    four = (q0 > q1)[:, None]
    p2 = np.where(four, (2 * c0 + c1) / 3.0, (c0 + c1) / 2.0)
    p3 = np.where(four, (c0 + 2 * c1) / 3.0, 0.0)
    pal = np.stack([c0, c1, p2, p3], 1)
    bits = col[:, 4:8].astype(np.uint32)
    bits = bits[:, 0] | (bits[:, 1] << 8) | (bits[:, 2] << 16) | (bits[:, 3] << 24)
    idx = np.stack([(bits >> np.uint32(2 * k)) & 3 for k in range(16)], 1).astype(np.int64)
    rgb = np.take_along_axis(pal, idx[:, :, None], axis=1)                         # (N,16,3)
    out = rgb
    if fmt == 'DXT5':
        al = arr[:, :8]
        a0 = al[:, 0].astype(np.float32)
        a1 = al[:, 1].astype(np.float32)
        ab = np.zeros(len(al), np.uint64)
        for k in range(6):
            ab |= al[:, 2 + k].astype(np.uint64) << np.uint64(8 * k)
        ai = np.stack([(ab >> np.uint64(3 * k)) & np.uint64(7) for k in range(16)], 1).astype(np.int64)
        pa = np.zeros((len(al), 8), np.float32)
        pa[:, 0] = a0
        pa[:, 1] = a1
        gt = a0 > a1
        for i in range(1, 7):
            pa[:, 1 + i] = np.where(gt, ((7 - i) * a0 + i * a1) / 7.0, 0)
        for i in range(1, 5):
            pa[:, 1 + i] = np.where(gt, pa[:, 1 + i], ((5 - i) * a0 + i * a1) / 5.0)
        pa[:, 6] = np.where(gt, pa[:, 6], 0)
        pa[:, 7] = np.where(gt, pa[:, 7], 255)
        alpha = np.take_along_axis(pa, ai, axis=1)
        out = np.concatenate([rgb, alpha[:, :, None]], -1)
    c = out.shape[-1]
    img = out.reshape(nby, nbx, 4, 4, c).transpose(0, 2, 1, 3, 4).reshape(nby * 4, nbx * 4, c)
    return np.clip(np.rint(img[:h, :w]), 0, 255).astype(np.uint8)


# ---------------------------------------------------------------------------
# DDS (for the MTA shader maps)
# ---------------------------------------------------------------------------
def write_dds(path, img, fmt):
    chain = compress_chain(img, fmt)
    h, w = img.shape[:2]
    fourcc = fmt.encode()
    hdr = struct.pack('<4sIIIIIII', b'DDS ', 124, 0x1 | 0x2 | 0x4 | 0x1000 | 0x20000 | 0x80000, h, w, len(chain[0][2]), 0, len(chain))
    hdr += b'\0' * 44
    hdr += struct.pack('<II4sIIIII', 32, 4, fourcc, 0, 0, 0, 0, 0)
    hdr += struct.pack('<IIIII', 0x1000 | 0x400000 | 0x8, 0, 0, 0, 0)
    assert len(hdr) == 128, len(hdr)
    with open(path, 'wb') as f:
        f.write(hdr)
        for _, _, d in chain:
            f.write(d)
    return chain
