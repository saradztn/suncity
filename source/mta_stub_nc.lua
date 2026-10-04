-- Created by: Arena.ai Agent Mode (AI) - strict headless MTA:SA API model used by mta_lua_test_nc.py (it runs the REAL client / server Lua)
-- Strict on purpose: unknown globals raise, every API call validates its argument count and types like MTA's CScriptArgReader,
-- elements die when destroyed, models must be requested -> TXD -> COL -> DFF before an object may use them, events must be added
-- before they are handled / triggered remotely, command handlers get the real MTA argument lists (client: name, args; server: player, name, args).
math.atan2 = math.atan2 or function(y, x) return math.atan(y, x) end

T = { now = 0, timers = {}, elems = {}, chat = {}, log = {}, files = {}, textures = {}, fxvars = {}, keys = {}, binds = {},
      nextModel = 20000, models = {}, nmodels = 0, freed = 0, maxModels = nil, shaderMode = "ok", groundHit = true,
      world = {}, calls = {}, hour = 12, minute = 0, weather = 0, draws = 0, lines3d = 0, camset = 0,
      vanilla = { waterclear256 = true },
      cam = { 0, 0, 0, 0, 1, 0, 0, 70 }, camTarget = nil, vehicles = {}, peds = {}, handlerErrors = {} }

local function count(name) T.calls[name] = (T.calls[name] or 0) + 1 end
local function note(msg) T.log[#T.log + 1] = msg end

-- ------------------------------------------------------------------------------------------------------ elements
local function newEl(kind, props, parent)
    local e = props or {}
    e.kind, e.alive, e.isel, e.parent = kind, true, true, parent
    T.elems[#T.elems + 1] = e
    return e
end
local root = newEl("root")
local resourceRoot = newEl("resourceRoot", {}, root)
local PLAYER = newEl("player", { x = 100, y = 200, z = 20, rx = 0, ry = 0, rz = 0, vx = 0, vy = 0, vz = 0, frozen = false }, root)
T.player = PLAYER
T.root, T.resourceRoot = root, resourceRoot
function T.alive(kind) local n = 0 for _, e in ipairs(T.elems) do if e.kind == kind and e.alive then n = n + 1 end end return n end
function T.created(kind) local n = 0 for _, e in ipairs(T.elems) do if e.kind == kind then n = n + 1 end end return n end

local function isChild(e, anc)
    while e do
        if e == anc then return true end
        e = e.parent
    end
    return false
end

-- ------------------------------------------------------------------------------------------------------ strict wrappers
local TYPES = {
    n = function(v) return type(v) == "number" and v == v and v ~= math.huge and v ~= -math.huge end,
    s = function(v) return type(v) == "string" end,
    b = function(v) return type(v) == "boolean" end,
    f = function(v) return type(v) == "function" end,
    e = function(v) return type(v) == "table" and v.isel == true and v.alive == true end,
    t = function(v) return type(v) == "table" and v.kind == "timer" end,
    a = function(v) return true end,
}
local NAMES = { n = "number", s = "string", b = "boolean", f = "function", e = "element", t = "timer", a = "any" }

local function parseSpec(spec)
    local req, opt, vararg, optional = {}, {}, false, false
    spec = spec:gsub("%s", "")
    for ch in spec:gmatch(".") do
        if ch == "|" then optional = true
        elseif ch == "*" then vararg = true
        elseif optional then opt[#opt + 1] = ch
        else req[#req + 1] = ch end
    end
    return req, opt, vararg
end

local function def(env, name, spec, fn)
    local req, opt, vararg = parseSpec(spec)
    env[name] = function(...)
        local n = select("#", ...)
        local args = { ... }
        count(name)
        for i = 1, #req do
            if not TYPES[req[i]](args[i]) then
                error(string.format("Bad argument @ '%s' [Expected %s at argument %d, got %s]", name, NAMES[req[i]], i, type(args[i])), 2)
            end
        end
        for i = 1, #opt do
            local v = args[#req + i]
            if v ~= nil and not TYPES[opt[i]](v) then
                error(string.format("Bad argument @ '%s' [Expected %s at argument %d, got %s]", name, NAMES[opt[i]], #req + i, type(v)), 2)
            end
        end
        if not vararg and n > #req + #opt then
            error(string.format("Bad argument @ '%s' [too many arguments: %d given, at most %d]", name, n, #req + #opt), 2)
        end
        return fn(...)
    end
end

local LUA_GLOBALS = { "assert", "error", "getmetatable", "ipairs", "next", "pairs", "pcall", "rawequal", "rawget", "rawset", "select", "setmetatable",
                      "tonumber", "tostring", "type", "unpack", "xpcall", "loadstring", "math", "string", "table", "_VERSION", "collectgarbage" }
local function makeEnv(side)
    local env = { side = side, handlers = {}, cmds = {}, events = {}, binds = {} }
    for _, k in ipairs(LUA_GLOBALS) do env[k] = _G[k] end
    env.os = { clock = os.clock, date = os.date, difftime = os.difftime, time = os.time }
    env._G = env
    setmetatable(env, { __index = function(_, k) error("attempt to use undefined global '" .. tostring(k) .. "' (" .. side .. ")", 2) end })
    env.root, env.resourceRoot = root, resourceRoot
    return env
end
local C, Sv = makeEnv("client"), makeEnv("server")
C.localPlayer = PLAYER
T.C, T.S = C, Sv

local BUILTIN_C = { onClientRender = 1, onClientPreRender = 1, onClientHUDRender = 1, onClientResourceStart = 1, onClientResourceStop = 1, onClientCursorMove = 1 }
local BUILTIN_S = { onResourceStart = 1, onResourceStop = 1 }

local function eventKnown(env, name)
    return (env.side == "client" and BUILTIN_C[name]) or (env.side == "server" and BUILTIN_S[name]) or env.events[name] ~= nil
end

-- ------------------------------------------------------------------------------------------------------ events + commands (both sides)
local function bothDef(name, spec, fn) def(C, name, spec, fn) def(Sv, name, spec, fn) end

local function fire(env, name, src, ...)
    local list = env.handlers[name]
    if not list then return 0 end
    local copy = {}
    for i, h in ipairs(list) do copy[i] = h end
    local n = 0
    local savedSource = rawget(env, "source")
    for _, h in ipairs(copy) do
        if h.alive and (h.el == src or isChild(src, h.el)) then
            rawset(env, "source", src)
            local ok, err = pcall(h.fn, ...)
            if not ok then T.handlerErrors[#T.handlerErrors + 1] = name .. ": " .. tostring(err) end
            n = n + 1
        end
    end
    rawset(env, "source", savedSource)
    return n
end
T.fire = fire

for _, env in ipairs({ C, Sv }) do
    def(env, "addEvent", "s|b", function(name, remote) env.events[name] = remote and true or false return true end)
    def(env, "addEventHandler", "se f|bs", function(name, el, fn)
        if not eventKnown(env, name) then error("addEventHandler: event '" .. name .. "' was never added (" .. env.side .. ")", 2) end
        env.handlers[name] = env.handlers[name] or {}
        for _, h in ipairs(env.handlers[name]) do
            if h.fn == fn and h.el == el and h.alive then return false end        -- MTA refuses duplicate handler registrations
        end
        table.insert(env.handlers[name], { el = el, fn = fn, alive = true })
        return true
    end)
    def(env, "removeEventHandler", "sef", function(name, el, fn)
        local l = env.handlers[name] or {}
        for i = #l, 1, -1 do
            if l[i].fn == fn and l[i].el == el then l[i].alive = false table.remove(l, i) return true end
        end
        return false
    end)
    def(env, "addCommandHandler", "sf|bb", function(name, fn) env.cmds[name] = fn return true end)
end
function T.cmd(side, name, ...)
    local env = side == "client" and C or Sv
    local fn = env.cmds[name]
    if not fn then error("no command handler /" .. name .. " on the " .. side) end
    if side == "client" then return fn(name, ...) end          -- client: (commandName, arg1, ...)
    return fn(PLAYER, name, ...)                                -- server: (player, commandName, arg1, ...)
end
function T.hasCmd(side, name) return (side == "client" and C or Sv).cmds[name] ~= nil end
function T.handlerCount(side, ev) local l = (side == "client" and C or Sv).handlers[ev] or {} return #l end

-- ------------------------------------------------------------------------------------------------------ timers
for _, env in ipairs({ C, Sv }) do
    def(env, "setTimer", "fnn*", function(fn, ms, times)
        if ms < 50 then error("Bad argument @ 'setTimer' [Interval is below 50]", 2) end
        local t = { kind = "timer", fn = fn, ms = ms, n = times, nxt = T.now + ms, alive = true, side = env.side }
        T.timers[#T.timers + 1] = t
        return t
    end)
    def(env, "killTimer", "t", function(t) t.alive = false return true end)
    def(env, "isTimer", "a", function(t) return type(t) == "table" and t.kind == "timer" and t.alive == true end)
end
function T.advance(ms)
    local stop = T.now + ms
    while true do
        local best
        for _, t in ipairs(T.timers) do
            if t.alive and t.nxt <= stop and (not best or t.nxt < best.nxt) then best = t end
        end
        if not best then break end
        T.now = best.nxt
        if best.n == 1 then best.alive = false else best.nxt = best.nxt + best.ms end
        local ok, err = pcall(best.fn)
        if not ok then T.handlerErrors[#T.handlerErrors + 1] = "timer(" .. best.side .. "): " .. tostring(err) end
        if best.n and best.n > 1 then best.n = best.n - 1 end
    end
    T.now = stop
end
function T.liveTimers(side) local n = 0 for _, t in ipairs(T.timers) do if t.alive and (not side or t.side == side) then n = n + 1 end end return n end
function T.frame(ms)
    T.advance(ms)
    fire(C, "onClientPreRender", root, ms / 1000)
    fire(C, "onClientRender", root)
    fire(C, "onClientHUDRender", root)
end
bothDef("getTickCount", "", function() return math.floor(T.now) end)

-- ------------------------------------------------------------------------------------------------------ shared element api
bothDef("isElement", "a", function(e) return type(e) == "table" and e.isel == true and e.alive == true end)
bothDef("destroyElement", "e", function(e)
    if e == root or e == resourceRoot or e == PLAYER then return false end
    e.alive = false
    return true
end)
bothDef("getElementPosition", "e", function(e) return e.x or 0, e.y or 0, e.z or 0 end)
bothDef("setElementPosition", "enn n|b", function(e, x, y, z) e.x, e.y, e.z = x, y, z return true end)
bothDef("setElementRotation", "enn n|s", function(e, rx, ry, rz) e.rx, e.ry, e.rz = rx, ry, rz return true end)
bothDef("setElementFrozen", "eb", function(e, f) e.frozen = f return true end)
bothDef("setElementDimension", "en", function(e, d) e.dim = d return true end)
bothDef("getElementsByType", "s|eb", function(t)
    if t == "player" then return { PLAYER } end
    if t == "vehicle" then local l = {} for _, e in ipairs(T.vehicles) do if e.alive then l[#l + 1] = e end end return l end
    if t == "ped" then local l = {} for _, e in ipairs(T.peds) do if e.alive then l[#l + 1] = e end end return l end
    return {}
end)

-- ------------------------------------------------------------------------------------------------------ client api
def(C, "outputChatBox", "s|nnnb", function(m) T.chat[#T.chat + 1] = m return true end)
def(C, "outputDebugString", "s|nnnn", function(m, level) T.log[#T.log + 1] = "dbg:" .. m return true end)
def(C, "tocolor", "nnn|n", function(r, g, b, a)
    for _, v in ipairs({ r, g, b, a or 255 }) do if v < -1 or v > 256 then error("tocolor: component out of range " .. v, 2) end end
    return 1
end)
def(C, "guiGetScreenSize", "", function() return 1920, 1080 end)
def(C, "isCursorShowing", "", function() return false end)
def(C, "isMainMenuActive", "", function() return false end)
def(C, "getKeyState", "s", function(k) return T.keys[k] == true end)
def(C, "bindKey", "ssf*", function(k, st, fn) T.binds[k .. ":" .. st] = fn return true end)
def(C, "unbindKey", "ss|f", function(k, st) local had = T.binds[k .. ":" .. st] ~= nil T.binds[k .. ":" .. st] = nil return had end)
def(C, "triggerServerEvent", "se*", function(name, src, ...)
    if Sv.events[name] ~= true then error("triggerServerEvent: '" .. name .. "' is not a remote-triggerable event on the server", 2) end
    rawset(Sv, "client", PLAYER)
    fire(Sv, name, src, ...)
    rawset(Sv, "client", nil)
    return true
end)
function T.press(k) local f = T.binds[k .. ":down"] if f then f(k, "down") return true end return false end

-- cameras
def(C, "getCameraMatrix", "", function() return T.cam[1], T.cam[2], T.cam[3], T.cam[4], T.cam[5], T.cam[6], T.cam[7], T.cam[8] end)
def(C, "setCameraMatrix", "nnnnnn|nn", function(x, y, z, lx, ly, lz, roll, fov)
    T.cam = { x, y, z, lx, ly, lz, roll or 0, fov or 70 }
    T.camTarget = nil
    T.camset = T.camset + 1
    return true
end)
def(C, "setCameraTarget", "e|e", function(e) T.camTarget = e return true end)
def(C, "setElementVelocity", "enn n", function(e, x, y, z) e.vx, e.vy, e.vz = x, y, z return true end)
def(C, "setElementCollisionsEnabled", "eb", function(e, b) e.collisions = b return true end)

-- models
def(C, "engineRequestModel", "s|n", function(kind, parent)
    if kind ~= "object" then error("engineRequestModel: this resource must only allocate 'object' models, got " .. kind, 2) end
    if T.maxModels and T.nmodels >= T.maxModels then return false end
    T.nextModel = T.nextModel + 1
    T.models[T.nextModel] = { txd = false, col = false, dff = false, order = "" }
    T.nmodels = T.nmodels + 1
    return T.nextModel
end)
def(C, "engineFreeModel", "n", function(id)
    if not T.models[id] then error("engineFreeModel: model " .. id .. " is not allocated (double free?)", 2) end
    T.models[id] = nil
    T.nmodels = T.nmodels - 1
    T.freed = T.freed + 1
    return true
end)
local function loader(kind) return function(path)
    if not T.files[path] then note("missing file: " .. path) return false end
    return newEl(kind, { path = path }, resourceRoot)
end end
def(C, "engineLoadTXD", "s|b", loader("txd"))
def(C, "engineLoadDFF", "s", loader("dff"))
def(C, "engineLoadCOL", "s", loader("col"))
def(C, "engineImportTXD", "en", function(txd, id)
    local m = T.models[id]
    if txd.kind ~= "txd" or not m then error("engineImportTXD: bad txd or unknown model", 2) end
    if m.dff then error("engineImportTXD must run before engineReplaceModel", 2) end
    m.txd = true
    return true
end)
def(C, "engineReplaceCOL", "en", function(col, id)
    local m = T.models[id]
    if col.kind ~= "col" or not m then error("engineReplaceCOL: bad col or unknown model", 2) end
    m.col = true
    return true
end)
def(C, "engineReplaceModel", "en|b", function(dff, id)
    local m = T.models[id]
    if dff.kind ~= "dff" or not m then error("engineReplaceModel: bad dff or unknown model", 2) end
    m.dff = true
    return true
end)
def(C, "engineSetModelLODDistance", "nn|b", function(id, d)
    if not T.models[id] then error("engineSetModelLODDistance: unknown model " .. id, 2) end
    if d <= 0 then return false end
    T.models[id].lod = d
    return true
end)
def(C, "createObject", "nnnn|nnnb", function(model, x, y, z, rx, ry, rz)
    local m = T.models[model]
    if not m then return false end
    if not (m.txd and m.col and m.dff) then error("createObject: model " .. model .. " is not completely loaded (txd/col/dff)", 2) end
    return newEl("object", { model = model, x = x, y = y, z = z, rx = rx or 0, ry = ry or 0, rz = rz or 0, frozen = false, collisions = true }, resourceRoot)
end)

-- water
def(C, "createWater", "nnnnnnnnn|nnn", function(...)
    local a = { ... }
    for i = 1, #a do
        if i % 3 ~= 0 then
            if a[i] ~= math.floor(a[i]) or a[i] % 2 ~= 0 then note("water coordinate not an even integer: " .. a[i]) return false end
        end
        if math.abs(a[i]) > 3000 then note("water coordinate outside +-3000: " .. a[i]) return false end
    end
    if #a ~= 12 then error("createWater: this resource must create quads", 2) end
    return newEl("water", { z = a[3], x = a[1], y = a[2] }, resourceRoot)
end)
def(C, "setWaterLevel", "en|bbb", function(w, z) if w.kind ~= "water" then error("setWaterLevel: not a water", 2) end w.z = z return true end)
def(C, "setWaterColor", "nnn|n", function() T.world.waterColor = true return true end)
def(C, "resetWaterColor", "", function() T.world.waterColor = false return true end)

-- sound
local function soundEl(path, loop, x, y, z)
    if not T.files[path] then note("missing sound file: " .. path) return false end
    return newEl("sound", { path = path, loop = loop == true, vol = 1, x = x, y = y, z = z }, resourceRoot)
end
def(C, "playSound", "s|bb", function(p, loop) return soundEl(p, loop) end)
def(C, "playSound3D", "snnn|b", function(p, x, y, z, loop) return soundEl(p, loop, x, y, z) end)
def(C, "setSoundVolume", "en", function(s, v)
    if s.kind ~= "sound" then error("setSoundVolume: not a sound", 2) end
    if v < 0 or v > 1 then error("setSoundVolume: volume out of range " .. v, 2) end
    s.vol = v
    return true
end)
def(C, "setSoundMinDistance", "en", function(s, d) if d <= 0 then error("min distance", 2) end s.minD = d return true end)
def(C, "setSoundMaxDistance", "en", function(s, d) if d <= 0 then error("max distance", 2) end s.maxD = d return true end)

-- dx / shaders
def(C, "dxCreateTexture", "s|sbs", function(path)
    if not T.files[path] then note("missing texture file: " .. path) return false end
    return newEl("texture", { path = path }, resourceRoot)
end)
def(C, "dxCreateShader", "s|nnbs", function(path)
    if not T.files[path] then note("missing shader file: " .. path) return false, "file not found" end
    if T.shaderMode == "fail" then return false, "compile error (test)" end
    local e = newEl("shader", { path = path, values = {}, textures = {} }, resourceRoot)
    return e, (T.shaderMode == "fallback") and "fallback" or "tec0"
end)
def(C, "dxCreateScreenSource", "nn", function(w, h)
    if w < 1 or h < 1 then error("dxCreateScreenSource: bad size", 2) end
    return newEl("screensource", { w = w, h = h, updates = 0 }, resourceRoot)
end)
def(C, "dxUpdateScreenSource", "e|b", function(s) if s.kind ~= "screensource" then error("not a screen source", 2) end s.updates = s.updates + 1 return true end)
def(C, "dxSetShaderValue", "es*", function(sh, name, ...)
    if sh.kind ~= "shader" then error("dxSetShaderValue: not a shader", 2) end
    local vars = T.fxvars[sh.path]
    if not (vars and vars[name]) then error("dxSetShaderValue: shader " .. sh.path .. " has no variable '" .. name .. "'", 2) end
    local v = { ... }
    if #v == 0 then error("dxSetShaderValue: no value", 2) end
    for _, x in ipairs(v) do
        if not (type(x) == "number" or type(x) == "boolean" or (type(x) == "table" and x.isel == true and x.alive == true)) then
            error("dxSetShaderValue: bad value for " .. name, 2)
        end
    end
    sh.values[name] = v
    return true
end)
def(C, "dxDrawImage", "nnnne|nnnnb", function(x, y, w, h, img) T.draws = T.draws + 1 T.lastImage = img return true end)
def(C, "dxDrawMaterialLine3D", "nnnnnnen|nbnnn", function(x1, y1, z1, x2, y2, z2, mat, width, color, post, fx, fy, fz)
    if mat.kind ~= "texture" then error("dxDrawMaterialLine3D: material must be a texture", 2) end
    if width <= 0 then error("dxDrawMaterialLine3D: width must be > 0", 2) end
    T.lines3d = T.lines3d + 1
    return true
end)
def(C, "engineApplyShaderToWorldTexture", "es|eb", function(sh, name)
    if sh.kind ~= "shader" then error("not a shader", 2) end
    if not (T.textures[name] or T.vanilla[name]) then error("engineApplyShaderToWorldTexture: no texture named '" .. name .. "' in any TXD of this resource", 2) end
    sh.textures[name] = true
    return true
end)
def(C, "engineRemoveShaderFromWorldTexture", "es|e", function(sh, name)
    if not (T.textures[name] or T.vanilla[name]) then error("engineRemoveShaderFromWorldTexture: no texture named '" .. name .. "'", 2) end
    sh.textures[name] = nil
    return true
end)

-- world, weather, sky
local function rangeCheck(name, v, lo, hi) if v < lo or v > hi then error(name .. ": value out of range " .. v, 3) end end
def(C, "setWeather", "n", function(w) rangeCheck("setWeather", w, 0, 255) T.weather = w return true end)
def(C, "setWeatherBlended", "n|n", function(w, ms) rangeCheck("setWeatherBlended", w, 0, 255) T.weather = w T.world.weatherBlend = ms or 50 return true end)
def(C, "getWeather", "", function() return T.weather, T.weather end)
def(C, "setTime", "nn", function(h, m) rangeCheck("setTime hour", h, 0, 23) rangeCheck("setTime minute", m, 0, 59) T.hour, T.minute = h, m return true end)
def(C, "getTime", "", function() return T.hour, T.minute end)
def(C, "setMinuteDuration", "n", function(ms) rangeCheck("setMinuteDuration", ms, 0, 2147483647) T.world.minute = ms return true end)
def(C, "setSkyGradient", "nnnnnn", function(a, b, c, d, e, f)
    for _, v in ipairs({ a, b, c, d, e, f }) do rangeCheck("setSkyGradient", v, 0, 255) end
    T.world.sky = { a, b, c, d, e, f } T.world.skyCalls = (T.world.skyCalls or 0) + 1
    return true
end)
def(C, "resetSkyGradient", "", function() T.world.sky = nil return true end)
def(C, "setFogDistance", "n", function(d) rangeCheck("setFogDistance", d, 0, 10000) T.world.fog = d return true end)
def(C, "resetFogDistance", "", function() T.world.fog = nil return true end)
def(C, "setFarClipDistance", "n", function(d) rangeCheck("setFarClipDistance", d, 5, 20000) T.world.far = d return true end)
def(C, "resetFarClipDistance", "", function() T.world.far = nil return true end)
def(C, "setRainLevel", "n", function(l) rangeCheck("setRainLevel", l, 0, 1) T.world.rain = l return true end)
def(C, "resetRainLevel", "", function() T.world.rain = nil return true end)
def(C, "setWindVelocity", "nnn", function(x, y, z) T.world.wind = { x, y, z } return true end)
def(C, "resetWindVelocity", "", function() T.world.wind = nil return true end)
def(C, "setHeatHaze", "n|nnnnnnb", function(i) T.world.haze = i return true end)
def(C, "resetHeatHaze", "", function() T.world.haze = nil return true end)
def(C, "setSunSize", "n", function(s) T.world.sun = s return true end)
def(C, "resetSunSize", "", function() T.world.sun = nil return true end)
def(C, "setSunColor", "nnn", function(r, g, b)
    for _, v in ipairs({ r, g, b }) do rangeCheck("setSunColor", v, 0, 255) end
    T.world.sunColor = { r, g, b }
    return true
end)
def(C, "resetSunColor", "", function() T.world.sunColor = nil return true end)
def(C, "setMoonSize", "n", function(s) rangeCheck("setMoonSize", s, 0, 5) T.world.moon = s return true end)
def(C, "resetMoonSize", "", function() T.world.moon = nil return true end)
def(C, "setCloudsEnabled", "b", function(b) T.world.clouds = b return true end)
def(C, "setBirdsEnabled", "b", function(b) T.world.birds = b return true end)
def(C, "setOcclusionsEnabled", "b", function(b) T.world.occlusions = b return true end)
def(C, "setAmbientSoundEnabled", "sb", function(kind, b)
    if kind ~= "general" and kind ~= "gunfire" then error("setAmbientSoundEnabled: bad type " .. kind, 2) end
    T.world["ambient_" .. kind] = b
    return true
end)
def(C, "processLineOfSight", "nnnnnn|bbbbbbbbebb", function(x1, y1, z1, x2, y2, z2)
    if T.groundHit then return true, x1, y1, (z1 + z2) / 2, nil end
    return false
end)

-- ------------------------------------------------------------------------------------------------------ server api
def(Sv, "outputChatBox", "se|nnnb", function(m) T.chat[#T.chat + 1] = "S:" .. m return true end)
def(Sv, "triggerClientEvent", "ese*", function(target, name, src, ...)
    if C.events[name] ~= true then error("triggerClientEvent: '" .. name .. "' is not a remote-triggerable event on the client", 2) end
    T.log[#T.log + 1] = "toClient:" .. name
    fire(C, name, src, ...)
    return true
end)
def(Sv, "getPlayerAccount", "e", function() return { kind = "account", name = "tester" } end)
def(Sv, "isGuestAccount", "a", function() return false end)
def(Sv, "getAccountName", "a", function() return "tester" end)
def(Sv, "isObjectInACLGroup", "sa", function() return T.aclAdmin ~= false end)
def(Sv, "aclGetGroup", "s", function(n) return { kind = "aclgroup", name = n } end)
function T.addVehicle(x, y, z) local v = newEl("vehicle", { x = x, y = y, z = z }, resourceRoot) T.vehicles[#T.vehicles + 1] = v return v end
function T.addPed(x, y, z) local p = newEl("ped", { x = x, y = y, z = z }, resourceRoot) T.peds[#T.peds + 1] = p return p end

-- ------------------------------------------------------------------------------------------------------ test helpers
function T.load(side, chunkname, src)
    local env = side == "client" and C or Sv
    local fn, err = loadstring(src, chunkname)
    if not fn then error(err) end
    setfenv(fn, env)
    return fn()
end
function T.fireClient(ev, src, ...) return fire(C, ev, src or resourceRoot, ...) end
function T.fireServer(ev, src, ...) rawset(Sv, "client", PLAYER) local n = fire(Sv, ev, src or resourceRoot, ...) rawset(Sv, "client", nil) return n end
function T.setKey(k, down) T.keys[k] = down and true or false end
function T.elements(kind) local l = {} for _, e in ipairs(T.elems) do if e.kind == kind and e.alive then l[#l + 1] = e end end return l end
function T.world_get(k) return T.world[k] end
function T.chatCount() return #T.chat end
function T.lastChat() return T.chat[#T.chat] or "" end
function T.logHas(sub) for _, l in ipairs(T.log) do if l:find(sub, 1, true) then return true end end return false end
function T.errors() return T.handlerErrors end
function T.sounds(sub) local l = {} for _, e in ipairs(T.elems) do if e.kind == "sound" and e.alive and e.path:find(sub, 1, true) then l[#l + 1] = e end end return l end
function T.globalOf(side, name) return rawget(side == "client" and C or Sv, name) end

function T.setCam(x, y, z, lx, ly, lz) T.cam = { x, y, z, lx or x, ly or (y + 1), lz or z, 0, 70 } end
function T.elementProp(e, k) return e[k] end
function T.objectsFrozen() local n = 0 for _, e in ipairs(T.elems) do if e.kind == "object" and e.alive and e.frozen then n = n + 1 end end return n end
function T.objectsNoCollision() local n = 0 for _, e in ipairs(T.elems) do if e.kind == "object" and e.alive and e.collisions == false then n = n + 1 end end return n end
function T.modelsComplete() local n = 0 for _, m in pairs(T.models) do if m.txd and m.col and m.dff then n = n + 1 end end return n end
function T.firstObject() for _, e in ipairs(T.elems) do if e.kind == "object" and e.alive then return e end end end
function T.objectsAt(x, y, z, eps)
    local out = {}
    for _, e in ipairs(T.elems) do
        if e.kind == "object" and e.alive and math.abs(e.x - x) < (eps or 1e-6) and math.abs(e.y - y) < (eps or 1e-6) and math.abs(e.z - z) < (eps or 1e-6) then
            out[#out + 1] = e
        end
    end
    return out
end
function T.shaderOf(path, n)
    local k = 0
    for _, e in ipairs(T.elems) do
        if e.kind == "shader" and e.alive and e.path == path then
            k = k + 1
            if k == (n or 1) then return e end
        end
    end
end
function T.shaderCount(path)
    local k = 0
    for _, e in ipairs(T.elems) do
        if e.kind == "shader" and e.alive and e.path == path then k = k + 1 end
    end
    return k
end
function T.shaderValue(path, name, i, n) local sh = T.shaderOf(path, n) return sh and sh.values[name] and sh.values[name][i or 1] end
function T.shaderTextures(path, n) local sh = T.shaderOf(path, n) local k = 0 if sh then for _ in pairs(sh.textures) do k = k + 1 end end return k end
function T.shaderTexturesTotal(path)
    local k = 0
    for _, e in ipairs(T.elems) do
        if e.kind == "shader" and e.alive and e.path == path then
            for _ in pairs(e.textures) do k = k + 1 end
        end
    end
    return k
end
function T.screenUpdates() local n = 0 for _, e in ipairs(T.elems) do if e.kind == "screensource" and e.alive then n = n + e.updates end end return n end
function T.chatContains(sub) for _, l in ipairs(T.chat) do if l:find(sub, 1, true) then return true end end return false end
function T.resetCounters() T.lines3d = 0 T.draws = 0 T.camset = 0 end
function T.destroyedCount(kind) local n = 0 for _, e in ipairs(T.elems) do if e.kind == kind and not e.alive then n = n + 1 end end return n end
function T.same(a, b) return rawequal(a, b) end
function T.camIsPlayer() return rawequal(T.camTarget, PLAYER) end
