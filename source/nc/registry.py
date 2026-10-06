# Created by: Arena.ai Agent Mode (AI) - NightCity MTA:SA asset pipeline
# registry.py - model name -> geometry: calls the right generator for every model of the plan.
from . import ground, bld, infra, tunnel, skydome, rail


def build_model(plan, name):
    m = plan.models[name]
    b, a = m['builder'], m['args']
    if b == 'cell':
        return ground.build_cell(a)
    if b == 'skydome':
        return skydome.sky_dome()
    if b in bld.ARCH:
        return bld.ARCH[b](**a)
    if b.startswith('tunnel_'):
        return getattr(tunnel, b)(**a)
    if b.startswith('rail_') or b in ('metro', 'metro_door'):
        return getattr(rail, b)(**a)
    if b == 'terrain_tile':
        from . import terrain as T
        return T.tile(**a)
    if b in ('far_ring', 'sea_floor'):
        from . import terrain as T
        return getattr(T, b)(**a)
    from . import roads, terrain
    if hasattr(infra, b):
        return getattr(infra, b)(**a)
    if hasattr(roads, b):
        return getattr(roads, b)(**a)
    if hasattr(terrain, b):
        return getattr(terrain, b)(**a)
    raise AttributeError('no builder for %r' % b)
