-- Created by: Arena.ai Agent Mode (AI) - WetStreets MTA:SA resource (NightCity companion)
-- ---------------------------------------------------------------------------------------
-- wetstreets.lua - rain wetness + cinematic grade for the VANILLA San Andreas map.
--
-- The NightCity street look as a standalone resource: wet.fx (screen-space reflections, puddles,
-- rain ripples, sun glints, night emissive) applied to the stock GTA:SA road / pavement textures,
-- plus the post.fx cinematic grade (filmic tone, god rays, vignette, grain).  The environment
-- (env.lua) FOLLOWS the vanilla clock / weather / rain level - this resource never changes them.
--
--   /wetfx [0|1|2]        graphics mode: off / grade only / wet streets + grade (cycled)
--   /wetlevel <0..1|auto> manual wetness (auto = follow the weather)
--   /wetflash             fire a lightning strike (visible in the wet reflections)
--   /wetinfo              status + how many vanilla textures each group captured
-- ---------------------------------------------------------------------------------------
local WS = {
    mode = 0,                -- 0 off, 1 grade only, 2 wet streets + grade
    gain = 1.0,
    groups = {},             -- { name, sh, patterns }
    post = nil,
    src = nil, w = 0, h = 0,
    on = false,              -- HUD handler attached
    tech = {},
    pushLast = 0,
}

-- ---------------------------------------------------------------------------------------
-- material groups: vanilla texture patterns -> wet behaviour (NightCity's NC_SURFACES groups)
-- engineApplyShaderToWorldTexture matches these with '*' wildcards; extend freely.
-- ---------------------------------------------------------------------------------------
local GROUPS = {
    { name = "road", wet = 1.00, refl = 1.00, spec = 0.70, gloss = 26, rings = 1, emis = 0.15,
      patterns = { "*road*", "*tar*", "*hiway*", "*freeway*", "*cross*" } },
    { name = "pavement", wet = 0.65, refl = 0.45, spec = 0.35, gloss = 18, rings = 1, emis = 0.25,
      patterns = { "*pave*", "*sidewalk*", "*walk*", "*kerb*", "*curb*", "*step*" } },
    { name = "concrete", wet = 0.55, refl = 0.35, spec = 0.30, gloss = 22, rings = 0, emis = 0.25,
      patterns = { "*conc*", "*floor*", "*slab*", "*plaza*", "*deck*" } },
    { name = "metal", wet = 0.85, refl = 0.75, spec = 1.15, gloss = 64, rings = 0, emis = 0.10,
      patterns = { "*steel*", "*metal*", "*grate*", "*manhole*", "*bridge*" } },
}
WS.groups = GROUPS                       -- the working list (g.sh added per group)

-- ---------------------------------------------------------------------------------------
-- tiny helpers
-- ---------------------------------------------------------------------------------------
local function say(msg, r, g, b)
    outputChatBox("[WetStreets] #ffffff" .. msg, r or 80, g or 200, b or 255, true)
end

local function dbg(msg)
    outputDebugString("WetStreets: " .. msg, 2)
end

local function clamp(v, a, b)
    if v < a then return a end
    if v > b then return b end
    return v
end

-- ---------------------------------------------------------------------------------------
-- uniform push (same contract as NightCity): slow values on a 0.12 s cadence, gTime + gFlash
-- every frame
-- ---------------------------------------------------------------------------------------
local function pushOne(sh, U)
    if not (sh and isElement(sh)) then return end
    dxSetShaderValue(sh, "gSunDir", U.sunX, U.sunY, U.sunZ)
    dxSetShaderValue(sh, "gSunColor", U.sunR, U.sunG, U.sunB)
    dxSetShaderValue(sh, "gSunI", U.sunI)
    dxSetShaderValue(sh, "gMoonDir", U.moonX, U.moonY, U.moonZ)
    dxSetShaderValue(sh, "gAmbient", U.ambR, U.ambG, U.ambB)
    dxSetShaderValue(sh, "gNightKeep", U.nightKeep)
    dxSetShaderValue(sh, "gNightGlow", U.nightGlow)
    dxSetShaderValue(sh, "gNight", U.night)
    dxSetShaderValue(sh, "gZenith", U.zenR, U.zenG, U.zenB)
    dxSetShaderValue(sh, "gHorizon", U.horR, U.horG, U.horB)
    dxSetShaderValue(sh, "gFogColor", U.fogR, U.fogG, U.fogB)
    dxSetShaderValue(sh, "gFogRange", U.fogNear, U.fogFar)
    dxSetShaderValue(sh, "gCloudCover", U.cover)
    dxSetShaderValue(sh, "gCloudDark", U.cloudDark)
    dxSetShaderValue(sh, "gWind", U.windX, U.windY)
    dxSetShaderValue(sh, "gQuality", U.quality)
    dxSetShaderValue(sh, "gDim", U.dim)
    dxSetShaderValue(sh, "gWet", U.wet)
    dxSetShaderValue(sh, "gPuddle", U.puddle)
    dxSetShaderValue(sh, "gExposure", U.exposure)
end

local function pushFast(sh, U)
    if not (sh and isElement(sh)) then return end
    dxSetShaderValue(sh, "gTime", U.time)
    dxSetShaderValue(sh, "gFlash", U.flash)
end

local function pushFastAll(U)
    for _, g in ipairs(WS.groups) do
        pushFast(g.sh, U)
    end
    pushFast(WS.post, U)
end

local function pushUniforms(U)
    for _, g in ipairs(WS.groups) do
        pushOne(g.sh, U)
    end
    pushOne(WS.post, U)
    -- post extras: the sun's screen position drives the god rays
    if WS.post and isElement(WS.post) then
        local cx, cy, cz = getCameraMatrix()
        local sx, sy = getScreenFromWorldPosition(cx + U.sunX * 400, cy + U.sunY * 400, cz + U.sunZ * 400, 0.25, false)
        if sx and sy then
            dxSetShaderValue(WS.post, "gSunScreen", sx, sy)
            dxSetShaderValue(WS.post, "gRayStrength", U.rayStrength)
        else
            dxSetShaderValue(WS.post, "gRayStrength", 0)
        end
    end
end

-- ---------------------------------------------------------------------------------------
-- shaders
-- ---------------------------------------------------------------------------------------
local fxFrame                                       -- forward declaration (referenced by fxStop / fxSet below)

local function surfacesOff()
    for _, g in ipairs(WS.groups) do
        if g.sh and isElement(g.sh) then
            for _, pat in ipairs(g.patterns) do
                engineRemoveShaderFromWorldTexture(g.sh, pat)
            end
            destroyElement(g.sh)
        end
        g.sh = nil
    end
end

local function surfacesOn()
    local n = 0
    for _, g in ipairs(WS.groups) do
        if not g.sh then
            local sh, tech = dxCreateShader("wet.fx")
            if sh then
                if tech == "fallback" then
                    dbg("wet.fx: shader model 3 is not available - wet streets disabled")
                    destroyElement(sh)
                else
                    g.sh = sh
                    WS.tech[g.name] = tech
                    dxSetShaderValue(sh, "gMatWet", g.wet)
                    dxSetShaderValue(sh, "gMatRefl", g.refl)
                    dxSetShaderValue(sh, "gMatSpec", g.spec)
                    dxSetShaderValue(sh, "gMatGloss", g.gloss)
                    dxSetShaderValue(sh, "gMatRings", g.rings)
                    dxSetShaderValue(sh, "gMatEmis", g.emis)
                    if WS.src then
                        dxSetShaderValue(sh, "gScreen", WS.src)
                    end
                    for _, pat in ipairs(g.patterns) do
                        engineApplyShaderToWorldTexture(sh, pat)
                    end
                    n = n + 1
                end
            else
                dbg("wet.fx (" .. g.name .. "): " .. tostring(tech))
            end
        else
            n = n + 1
        end
    end
    return n
end

local function postOn()
    if WS.post then return true end
    local sh, tech = dxCreateShader("post.fx")
    if not sh then dbg("post.fx: " .. tostring(tech)) return false end
    if tech == "fallback" then
        dbg("post.fx: shader model 3 is not available - grade disabled")
        destroyElement(sh)
        return false
    end
    WS.post = sh
    WS.tech.post = tech
    if WS.src then
        dxSetShaderValue(WS.post, "ScreenTexture", WS.src)
    end
    return true
end

local function postOff()
    if WS.post and isElement(WS.post) then destroyElement(WS.post) end
    WS.post = nil
end

local function fxStop()
    if WS.on then removeEventHandler("onClientHUDRender", root, fxFrame) end
    WS.on = false
    surfacesOff()
    postOff()
    if WS.src and isElement(WS.src) then destroyElement(WS.src) end
    WS.src = nil
end

fxFrame = function()
    if not WS.src or not isElement(WS.src) then return end
    dxUpdateScreenSource(WS.src, true)      -- capture NOW, before the grade pass: without 'true' the source
    if WS.post and isElement(WS.post) then  -- holds last frame's output and every frame re-grades it
        dxDrawImage(0, 0, WS.w, WS.h, WS.post)
    end
end

local function fxSet(mode)
    if mode == 0 then fxStop() return 0 end
    if not WS.src then
        local sw, sh = guiGetScreenSize()
        WS.w, WS.h = sw, sh
        WS.src = dxCreateScreenSource(sw, sh)
        if not WS.src then return 0 end
    end
    local okPost = postOn()
    local nSurf = 0
    if mode >= 2 then
        nSurf = surfacesOn()
    else
        surfacesOff()
    end
    if not (okPost or nSurf > 0) then fxStop() return 0 end
    if not WS.on then addEventHandler("onClientHUDRender", root, fxFrame) WS.on = true end
    WS.mode = (nSurf > 0 and mode >= 2) and 2 or (okPost and 1 or 0)
    pushUniforms(WS_ENV.uniforms())
    return WS.mode
end

-- ---------------------------------------------------------------------------------------
-- environment frame: clock / weather / wetness / lightning + uniform push
-- ---------------------------------------------------------------------------------------
local function envFrame()
    local now = getTickCount() / 1000
    local dt = now - (WS.lastTick or now)
    WS.lastTick = now
    WS_ENV.tick(dt)
    local U = WS_ENV.uniforms()
    pushFastAll(U)                                   -- every frame: rain-ring time + lightning flash
    if now - (WS.pushLast or 0) > 0.12 or U.flash > 0.01 then
        WS.pushLast = now
        pushUniforms(U)
    end
end

-- ---------------------------------------------------------------------------------------
-- lightning: shader flash + a brief whitening of the vanilla sky (restored after 240 ms),
-- thunder from thunder.wav if the user dropped one into the resource folder
-- ---------------------------------------------------------------------------------------
local flashTimers = {}

WS_ENV.onFlash = function(strength)
    pcall(setSkyGradient, 150, 155, 175, 170, 175, 195)
    flashTimers[#flashTimers + 1] = setTimer(function()
        pcall(resetSkyGradient)
    end, 240, 1)
    if fileExists("thunder.wav") then
        flashTimers[#flashTimers + 1] = setTimer(function()
            local s = playSound("thunder.wav")
            if s then setSoundVolume(s, 0.55 * strength) end
        end, math.random(700, 3200), 1)
    end
end

-- ---------------------------------------------------------------------------------------
-- commands
-- ---------------------------------------------------------------------------------------
addCommandHandler("wetfx", function(_, arg)
    local want = tonumber(arg)
    if want == nil then want = (WS.mode + 1) % 3 end
    want = clamp(math.floor(want), 0, 2)
    local got = fxSet(want)
    if got == want then
        say("graphics: " .. ({ [0] = "OFF (plain)", [1] = "cinematic grade", [2] = "wet streets + cinematic grade" })[got] .. "   (/wetfx 0|1|2)")
    elseif want > 0 and got == 0 then
        say("this graphics setup could not compile the shaders - running without them.", 255, 150, 120)
    else
        say("some shaders could not be compiled here, running a reduced set.", 255, 190, 120)
    end
end)

addCommandHandler("wetlevel", function(_, arg)
    if arg == "auto" then
        WS_ENV.setWet(nil)
        say("wetness: driven by the weather again")
        return
    end
    local v = tonumber(arg)
    if not v then say("usage: /wetlevel <0 .. 1 | auto>   (now " .. (WS_ENV.state.wetManual and string.format("%.2f", WS_ENV.state.wetManual) or "auto (weather)") .. ")") return end
    WS_ENV.setWet(clamp(v, 0, 1))
    say("wetness " .. string.format("%.2f", WS_ENV.state.wetManual))
end)

addCommandHandler("wetflash", function()
    WS_ENV.fireFlash()
    say("lightning fired.")
end)

addCommandHandler("wetinfo", function()
    say(WS_ENV.status() .. "  mode " .. WS.mode .. "  shaders " .. #WS.groups .. " groups")
    for _, g in ipairs(WS.groups) do
        local n = 0
        for _, pat in ipairs(g.patterns) do
            local names = engineGetVisibleTextureNames(pat)
            if type(names) == "table" then
                n = n + #names
            end
        end
        say(string.format("  %s: %s -> %d visible texture names", g.name, table.concat(g.patterns, " "), n))
    end
end)

-- ---------------------------------------------------------------------------------------
-- boot / stop
-- ---------------------------------------------------------------------------------------
addEventHandler("onClientResourceStart", resourceRoot, function()
    local U = WS_ENV.uniforms()
    pushUniforms(U)
    local got = fxSet(2)
    if got == 2 then
        say("wet streets ready - the vanilla map follows the weather now.  /wetfx /wetlevel /wetinfo")
    elseif got == 1 then
        say("running with the cinematic grade only (the surface shader did not compile).", 255, 190, 120)
    else
        say("this graphics setup could not compile the shaders - running without them.", 255, 150, 120)
    end
    addEventHandler("onClientPreRender", root, envFrame)
end)

addEventHandler("onClientResourceStop", resourceRoot, function()
    removeEventHandler("onClientPreRender", root, envFrame)
    fxStop()
    for _, t in ipairs(flashTimers) do
        if isTimer(t) then killTimer(t) end
    end
    pcall(resetSkyGradient)
end)
