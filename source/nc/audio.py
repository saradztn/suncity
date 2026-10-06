# Created by: Arena.ai Agent Mode (AI) - NightCity MTA:SA asset pipeline
# -----------------------------------------------------------------------------
# audio.py - synthesised ambience for an empty rainy megacity: rain, ventilation hum, wind between the towers, neon buzz,
#            steam hiss, distant thunder, water drips.  Mono 16-bit 22.05 kHz.  NO traffic, voices or animals (by design).
# Loops are made seamless with an equal power cross-fade of the tail into the head.
# -----------------------------------------------------------------------------
import os
import wave
import numpy as np
from scipy import signal

SR = 22050


def _norm(x, peak=0.85):
    x = x - x.mean()
    return x / max(np.abs(x).max(), 1e-9) * peak


def _loop(x, fade=0.8):
    n = int(fade * SR)
    t = np.linspace(0, np.pi / 2, n)
    head, tail = x[:n].copy(), x[-n:].copy()
    mid = x[n:-n].copy()
    cross = tail * np.cos(t) + head * np.sin(t)
    return np.concatenate([cross, mid])


def _bp(x, lo, hi, order=3):
    sos = signal.butter(order, [lo, hi], btype='band', fs=SR, output='sos')
    return signal.sosfilt(sos, x)


def _lp(x, fc, order=3):
    return signal.sosfilt(signal.butter(order, fc, btype='low', fs=SR, output='sos'), x)


def _hp(x, fc, order=3):
    return signal.sosfilt(signal.butter(order, fc, btype='high', fs=SR, output='sos'), x)


def rain(sec=9.0, seed=1):
    r = np.random.default_rng(seed)
    n = int((sec + 1.6) * SR)
    w = r.standard_normal(n)
    body = _bp(w, 900, 7500) * 0.9 + _hp(r.standard_normal(n), 5000) * 0.25 + _lp(r.standard_normal(n), 400) * 0.35
    # slow gusts + individual drops hitting hard surfaces
    t = np.arange(n) / SR
    body *= 0.85 + 0.15 * np.sin(2 * np.pi * t / 5.3 + 1.0) * np.sin(2 * np.pi * t / 2.7)
    drops = np.zeros(n)
    for _ in range(int(sec * 60)):
        i = int(r.integers(0, n - 400))
        k = np.exp(-np.arange(300) / r.uniform(20, 70)) * r.uniform(0.2, 1.0) * np.sin(np.arange(300) * r.uniform(0.25, 0.7))
        drops[i:i + 300] += k
    return _loop(_norm(body + 0.35 * _hp(drops, 1500)), 0.8)


def hum(sec=8.0, seed=2):
    r = np.random.default_rng(seed)
    n = int((sec + 1.6) * SR)
    t = np.arange(n) / SR
    x = np.zeros(n)
    for f, a in ((50, 1.0), (100, 0.7), (150, 0.35), (200, 0.2), (300, 0.12)):
        x += a * np.sin(2 * np.pi * f * t + r.uniform(0, 6.28)) * (0.85 + 0.15 * np.sin(2 * np.pi * t / r.uniform(3, 7)))
    x += 0.5 * _lp(r.standard_normal(n), 220)                       # ventilation rumble
    x += 0.12 * _bp(r.standard_normal(n), 800, 2500)                # fan whine
    return _loop(_norm(x, 0.7), 0.8)


def wind(sec=10.0, seed=3):
    r = np.random.default_rng(seed)
    n = int((sec + 1.6) * SR)
    w = _bp(r.standard_normal(n), 120, 900, 2)
    t = np.arange(n) / SR
    lfo = 0.55 + 0.45 * np.sin(2 * np.pi * t / 6.1 + 0.7) * np.sin(2 * np.pi * t / 9.3 + 2.0)
    w = w * np.clip(lfo, 0.1, 1) + 0.25 * _bp(r.standard_normal(n), 500, 1500, 2) * np.clip(lfo - 0.3, 0, 1)
    return _loop(_norm(w, 0.7), 0.8)


def buzz(sec=6.0, seed=4):
    r = np.random.default_rng(seed)
    n = int((sec + 1.6) * SR)
    t = np.arange(n) / SR
    x = sum(a * np.sin(2 * np.pi * f * t) for f, a in ((100, 1.0), (200, 0.5), (300, 0.3), (400, 0.18), (700, 0.07)))
    crack = (r.random(n) < 0.0006) * r.standard_normal(n) * 3.0
    crack = _hp(np.convolve(crack, np.exp(-np.arange(200) / 25.0), 'same'), 1500)
    x = x * (0.8 + 0.2 * np.sin(2 * np.pi * t * 0.37)) + 0.8 * crack + 0.06 * _hp(r.standard_normal(n), 3000)
    return _loop(_norm(x, 0.55), 0.8)


def steam(sec=6.0, seed=5):
    r = np.random.default_rng(seed)
    n = int((sec + 1.6) * SR)
    x = _bp(r.standard_normal(n), 2500, 8500) + 0.4 * _bp(r.standard_normal(n), 600, 2000)
    t = np.arange(n) / SR
    x *= 0.75 + 0.25 * np.sin(2 * np.pi * t / 3.1)
    return _loop(_norm(x, 0.6), 0.8)


def thunder(sec=6.0, seed=6):
    r = np.random.default_rng(seed)
    n = int(sec * SR)
    t = np.arange(n) / SR
    base = _lp(r.standard_normal(n), 140, 4)
    env = np.exp(-t / 1.6) * (1 - np.exp(-t / 0.15))
    for k in range(4):
        d = r.uniform(0.3, 3.0)
        env += 0.6 * np.exp(-np.clip(t - d, 0, None) / 1.1) * (t > d) * r.uniform(0.3, 0.8)
    crack = _hp(r.standard_normal(n), 900) * np.exp(-t / 0.08) * 0.5
    x = base * env + crack
    x *= np.minimum(1, (sec - t) / 0.5)
    return _norm(x, 0.9)


def drip(sec=5.0, seed=7):
    r = np.random.default_rng(seed)
    n = int((sec + 1.0) * SR)
    x = np.zeros(n)
    for _ in range(int(sec * 2.2)):
        i = int(r.integers(0, n - 4000))
        f = r.uniform(900, 2400)
        k = np.arange(3500)
        x[i:i + 3500] += np.sin(2 * np.pi * (f + 600 * np.exp(-k / 900.0)) * k / SR) * np.exp(-k / r.uniform(300, 700)) * r.uniform(0.3, 1.0)
    return _loop(_norm(x, 0.6), 0.5)


def write_wav(path, x):
    pcm = (np.clip(x, -1, 1) * 32767).astype('<i2')
    with wave.open(path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def make_all(outdir):
    os.makedirs(outdir, exist_ok=True)
    out = []
    for name, fn in (('rain_loop', rain), ('hum_loop', hum), ('wind_loop', wind), ('buzz_loop', buzz), ('steam_loop', steam), ('thunder', thunder), ('drip_loop', drip)):
        write_wav(os.path.join(outdir, name + '.wav'), fn())
        out.append(name + '.wav')
    return out
