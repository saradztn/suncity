# Created by: Arena.ai Agent Mode (AI) - NightCity MTA:SA asset pipeline
# textures.py - registry front-end: generate(name, scale) -> PBR, deterministic per name.
import zlib
from . import texgen, texsign, textunnel      # noqa: F401  (importing registers every material)
from .texgen import REG


def seed_of(name):
    return zlib.crc32(name.encode()) % 100000


def generate(name, scale=1):
    sp = REG[name]
    h, w = int(sp['h'] * scale), int(sp['w'] * scale)
    return sp['fn'](h, w, seed_of(name))


def names():
    return sorted(REG)


# surface material class per texture name (see client.lua GROUP_PARAMS and wet.fx):
#   ground   - asphalt / roads / pavements: full wetness, puddles, rain rings, screen-space reflection
#   concrete - structural concrete / tunnel tiles: moderate wetness, weak reflection
#   metal    - metals, containers, plant: glossy sun glints, strong reflection
#   glass    - curtain-wall facades: strong fresnel / reflection, night windows glow
#   wall     - punched-window masonry: subtle wetness, night windows glow strongly
#   neon     - self-lit signs / strips / shops: stays emissive at night
#   sky      - the sky dome (handled by sky.fx, not a surface)
GROUND = {'nc_asphalt', 'nc_alley', 'nc_road_ave', 'nc_road_str', 'nc_road_hwy', 'nc_crosswalk', 'nc_sidewalk', 'nc_plaza', 'nc_curb', 'nc_riverbed'}
CONCRETE = {'nc_concrete', 'nc_concrete_dark', 'nc_pillar', 'nc_deck_under', 'nc_roof', 'nc_tunnel_tile'}
METAL = {'nc_metal_dark', 'nc_metal_light', 'nc_metal_rust', 'nc_steel', 'nc_wall_metal', 'nc_wall_corrug',
         'nc_container_a', 'nc_container_b', 'nc_container_c', 'nc_tank', 'nc_ac', 'nc_vent'}
WALL = {'nc_wall_tenement_a', 'nc_wall_tenement_b', 'nc_wall_brutal'}
NEON = {'nc_ads', 'nc_led', 'nc_neon_h', 'nc_neon_v', 'nc_tunnel_sign', 'nc_shop_retail', 'nc_shop_club', 'nc_shop_food'}


def surface_group(name):
    if name == 'nc_sky_noise':
        return 'sky'
    if name.startswith('nc_glass'):
        return 'glass'
    if name.startswith('nc_light') or name.startswith('nc_strip') or name.startswith('nc_shop') or name.startswith('nc_neon'):
        return 'neon'
    if name in GROUND:
        return 'ground'
    if name in CONCRETE:
        return 'concrete'
    if name in METAL:
        return 'metal'
    if name in WALL:
        return 'wall'
    if name in NEON:
        return 'neon'
    return 'concrete'
