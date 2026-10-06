# Created by: Arena.ai Agent Mode (AI) - static checks of the NightCity Lua files
# -----------------------------------------------------------------------------
# Parses every Lua file of the resource (luaparser), resolves local scopes and lists the GLOBAL names each side uses.  Every global
# must be defined by the resource itself, be part of Lua 5.1, be a predefined MTA global, or be a function that really exists in the
# MTA client / server API (tools/mta_client_funcs.txt, tools/mta_server_funcs.txt, extracted from the mtasa-blue sources).
# Typos and wrong-side calls (e.g. triggerClientEvent in a client script) are errors.
#     python3 mta_lua_static.py
# -----------------------------------------------------------------------------
import os
import re
import sys
from luaparser import ast, astnodes

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, '..', 'resource', 'NightCity')

LUA51 = set('''assert collectgarbage dofile error getfenv getmetatable ipairs load loadfile loadstring module next pairs pcall print rawequal rawget
rawset require select setfenv setmetatable tonumber tostring type unpack xpcall _G _VERSION math string table os io coroutine debug'''.split())
MTA_GLOBALS = set('root resourceRoot localPlayer source client eventName this sourceResource sourceResourceRoot exports'.split())
LIBS = {
    'math': set('abs acos asin atan atan2 ceil cos cosh deg exp floor fmod frexp huge ldexp log log10 max min modf pi pow rad random randomseed sin sinh sqrt tan tanh'.split()),
    'string': set('byte char dump find format gmatch gsub len lower match rep reverse sub upper'.split()),
    'table': set('concat foreach foreachi getn insert maxn remove sort'.split()),
    'os': set('clock date difftime time'.split()),     # MTA exposes only these
}


def names_of(path):
    return [ln.strip() for ln in open(path) if ln.strip()]


CLIENT_API = set(names_of(os.path.join(HERE, 'tools', 'mta_client_funcs.txt')))
SERVER_API = set(names_of(os.path.join(HERE, 'tools', 'mta_server_funcs.txt')))


class Scan:
    def __init__(self):
        self.reads = {}          # global name -> [(file, line)]
        self.defined = set()     # globals assigned / defined by the scripts
        self.lib_uses = []       # (lib, member, file, line)
        self.fields = {}

    def run(self, fname, tree):
        self.fname = fname
        self.block(tree.body, [set()])

    # ------------------------------------------------------------------ scopes
    def declared(self, name, scopes):
        return any(name in s for s in scopes)

    def read(self, node, scopes):
        if self.declared(node.id, scopes):
            return
        self.reads.setdefault(node.id, []).append((self.fname, getattr(node, 'line', 0)))

    def block(self, blk, scopes):
        body = blk.body if hasattr(blk, 'body') and not isinstance(blk, list) else blk
        for st in body:
            self.stmt(st, scopes)

    def stmt(self, st, scopes):
        t = type(st).__name__
        if t == 'LocalAssign':
            for v in st.values:
                self.expr(v, scopes)
            for tg in st.targets:
                scopes[-1].add(tg.id)
        elif t == 'Assign':
            for v in st.values:
                self.expr(v, scopes)
            for tg in st.targets:
                self.target(tg, scopes)
        elif t == 'LocalFunction':
            scopes[-1].add(st.name.id)
            self.func(st.args, st.body, scopes)
        elif t == 'Function':
            self.target(st.name, scopes)
            self.func(st.args, st.body, scopes)
        elif t == 'Method':
            self.expr(st.source, scopes)
            self.func(st.args, st.body, scopes)
        elif t in ('Call', 'Invoke'):
            self.expr(st, scopes)
        elif t == 'Return':
            for v in (st.values if isinstance(st.values, list) else [st.values]):
                self.expr(v, scopes)
        elif t == 'If':
            self.expr(st.test, scopes)
            self.block(st.body, scopes + [set()])
            orelse = st.orelse
            if orelse is not None:
                if type(orelse).__name__ == 'ElseIf':
                    self.stmt(orelse, scopes)
                else:
                    self.block(orelse, scopes + [set()])
        elif t == 'ElseIf':
            self.expr(st.test, scopes)
            self.block(st.body, scopes + [set()])
            if st.orelse is not None:
                if type(st.orelse).__name__ == 'ElseIf':
                    self.stmt(st.orelse, scopes)
                else:
                    self.block(st.orelse, scopes + [set()])
        elif t == 'While':
            self.expr(st.test, scopes)
            self.block(st.body, scopes + [set()])
        elif t == 'Repeat':
            sc = scopes + [set()]
            self.block(st.body, sc)
            self.expr(st.test, sc)
        elif t == 'Fornum':
            for e in (st.start, st.stop, st.step):
                self.expr(e, scopes)
            self.block(st.body, scopes + [{st.target.id}])
        elif t == 'Forin':
            for e in st.iter:
                self.expr(e, scopes)
            self.block(st.body, scopes + [{x.id for x in st.targets}])
        elif t == 'Do':
            self.block(st.body, scopes + [set()])
        elif t in ('Break', 'Goto', 'Label'):
            pass
        else:
            raise RuntimeError('unhandled statement ' + t)

    def func(self, args, body, scopes):
        names = {a.id for a in args if type(a).__name__ == 'Name'}
        self.block(body, scopes + [names])

    def target(self, tg, scopes):
        t = type(tg).__name__
        if t == 'Name':
            if not self.declared(tg.id, scopes):
                self.defined.add(tg.id)
        elif t == 'Index':
            self.expr(tg.value, scopes)
            if tg.notation != astnodes.IndexNotation.DOT:
                self.expr(tg.idx, scopes)
        else:
            raise RuntimeError('unhandled target ' + t)

    def expr(self, e, scopes):
        if e is None or isinstance(e, (int, float, str, bool)):
            return
        t = type(e).__name__
        if t == 'Name':
            self.read(e, scopes)
        elif t in ('Number', 'String', 'Nil', 'TrueExpr', 'FalseExpr', 'Varargs'):
            pass
        elif t == 'Index':
            self.expr(e.value, scopes)
            if e.notation != astnodes.IndexNotation.DOT:
                self.expr(e.idx, scopes)
            elif type(e.value).__name__ == 'Name' and e.value.id in LIBS and not self.declared(e.value.id, scopes):
                self.lib_uses.append((e.value.id, e.idx.id, self.fname, getattr(e, 'line', 0)))
        elif t == 'Call':
            self.expr(e.func, scopes)
            for a in e.args:
                self.expr(a, scopes)
        elif t == 'Invoke':
            self.expr(e.source, scopes)
            for a in e.args:
                self.expr(a, scopes)
        elif t == 'AnonymousFunction':
            self.func(e.args, e.body, scopes)
        elif t == 'Table':
            for f in e.fields:
                if type(f).__name__ == 'Field':
                    if f.between_brackets:
                        self.expr(f.key, scopes)
                    self.expr(f.value, scopes)
                else:
                    self.expr(f, scopes)
        elif t == 'Field':
            self.expr(f.value, scopes)
        elif hasattr(e, 'operand'):                                         # unary operators
            self.expr(e.operand, scopes)
        elif hasattr(e, 'left') and hasattr(e, 'right'):                    # binary operators
            self.expr(e.left, scopes)
            self.expr(e.right, scopes)
        elif t == 'Paren' or hasattr(e, 'expr'):
            self.expr(e.expr, scopes)
        else:
            raise RuntimeError('unhandled expression ' + t)


def check(side_files, api, label):
    scan = Scan()
    for f in side_files:
        scan.run(f, ast.parse(open(os.path.join(RES, f), encoding='utf8').read()))
    problems = []
    for name, uses in sorted(scan.reads.items()):
        if name in scan.defined or name in LUA51 or name in MTA_GLOBALS or name in api:
            continue
        problems.append('%s: undefined global %s used at %s' % (label, name, ', '.join('%s:%s' % u for u in uses[:3])))
    for lib, member, f, line in scan.lib_uses:
        if member not in LIBS[lib]:
            problems.append('%s: %s.%s is not available (Lua 5.1 / MTA) at %s:%d' % (label, lib, member, f, line))
    used_api = sorted(n for n in scan.reads if n in api and n not in scan.defined)
    return problems, used_api, scan


def main():
    bad = []
    client = ['models.lua', 'layout.lua', 'sprites.lua', 'env.lua', 'client.lua', 'tour.lua']
    server = ['layout.lua', 'server.lua']
    for files, api, label in ((client, CLIENT_API, 'client'), (server, SERVER_API, 'server')):
        problems, used, scan = check(files, api, label)
        print('%-6s %d MTA functions used: %s' % (label, len(used), ' '.join(used)))
        for p in problems:
            print('  FAIL', p)
        bad += problems
    # a name that exists only on the other side is an error as well
    print('static check:', 'FAILED' if bad else 'OK')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
