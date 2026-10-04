# Created by: Arena.ai Agent Mode (AI) - NightCity MTA:SA asset pipeline
# registry.py - model name -> geometry: calls the right generator for every model of the plan.
from . import ground, bld, infra, tunnel, skydome


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
    return getattr(infra, b)(**a)
