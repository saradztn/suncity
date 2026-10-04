-- Created by: Arena.ai Agent Mode (AI) - WetStreets MTA:SA resource (NightCity companion)
-- ---------------------------------------------------------------------------------------
-- env.lua - the environment engine for the VANILLA San Andreas map.
--
-- Same maths and the same look as the NightCity env.lua (shared timecycle keyframes, wetness
-- physics, lightning), but instead of owning the clock and the weather it FOLLOWS the vanilla
-- ones: getTime(), getWeather(), getRainLevel() every tick.  It never changes the vanilla
-- world - it only produces the uniform block the wet.fx / post.fx shaders are fed with.
--
--   * timecycle: keyframed day phases (pre-dawn .. deep night), smooth interpolation of sky /
--     sun / ambient / fog colours - used for lighting the wet streets and the reflection tint
--   * sun / moon: simplified ephemeris (~38 N, late spring) -> gSunDir
--   * vanilla weather id -> cloud cover / wetness target / lightning rate (8 and 16 = rain)
--   * wetness model: the ground soaks fast while it rains and dries slowly afterwards (faster
--     with sun and broken cloud), puddles fill after the film and dry last -> the after-rain look
--   * lightning: multi-strike flashes (gFlash) with a thunder callback while it rains
-- ---------------------------------------------------------------------------------------
WS_ENV = {}

local D2R = math.pi / 180.0

-- ---------------------------------------------------------------------------------------
-- timecycle keyframes (identical values to NightCity - the look is the product)
-- ---------------------------------------------------------------------------------------
local KEYS = {
    { h = 4.6, name = "pre-dawn", zen = { 0.030, 0.045, 0.095 }, hor = { 0.16, 0.13, 0.21 }, sun = { 0.55, 0.55, 0.75 }, sunI = 0.02,
      amb = { 0.035, 0.04, 0.055 }, nightKeep = 1.0, nightGlow = 1.0, exposure = 1.18, mie = 0.35, haze = 0.55, water = { 0.035, 0.075, 0.10 } },
    { h = 5.5, name = "dawn", zen = { 0.075, 0.11, 0.20 }, hor = { 0.52, 0.28, 0.22 }, sun = { 1.0, 0.52, 0.28 }, sunI = 0.22,
      amb = { 0.10, 0.085, 0.10 }, nightKeep = 0.85, nightGlow = 0.85, exposure = 1.12, mie = 0.85, haze = 0.60, water = { 0.10, 0.09, 0.11 } },
    { h = 6.6, name = "sunrise", zen = { 0.16, 0.28, 0.48 }, hor = { 0.85, 0.52, 0.32 }, sun = { 1.0, 0.68, 0.38 }, sunI = 0.55,
      amb = { 0.19, 0.185, 0.21 }, nightKeep = 0.55, nightGlow = 0.45, exposure = 1.05, mie = 0.95, haze = 0.55, water = { 0.14, 0.15, 0.18 } },
    { h = 8.5, name = "morning", zen = { 0.22, 0.40, 0.72 }, hor = { 0.62, 0.66, 0.72 }, sun = { 1.0, 0.94, 0.82 }, sunI = 0.92,
      amb = { 0.30, 0.33, 0.38 }, nightKeep = 0.30, nightGlow = 0.10, exposure = 1.0, mie = 0.55, haze = 0.42, water = { 0.09, 0.15, 0.20 } },
    { h = 12.5, name = "noon", zen = { 0.25, 0.45, 0.82 }, hor = { 0.68, 0.74, 0.80 }, sun = { 1.0, 0.98, 0.92 }, sunI = 1.12,
      amb = { 0.36, 0.40, 0.46 }, nightKeep = 0.22, nightGlow = 0.0, exposure = 0.88, mie = 0.42, haze = 0.36, water = { 0.08, 0.15, 0.21 } },
    { h = 16.5, name = "afternoon", zen = { 0.23, 0.41, 0.74 }, hor = { 0.68, 0.68, 0.70 }, sun = { 1.0, 0.92, 0.76 }, sunI = 0.95,
      amb = { 0.32, 0.33, 0.37 }, nightKeep = 0.28, nightGlow = 0.08, exposure = 1.0, mie = 0.52, haze = 0.42, water = { 0.09, 0.15, 0.20 } },
    { h = 18.3, name = "golden", zen = { 0.20, 0.30, 0.55 }, hor = { 0.92, 0.55, 0.28 }, sun = { 1.0, 0.72, 0.40 }, sunI = 0.68,
      amb = { 0.24, 0.22, 0.24 }, nightKeep = 0.50, nightGlow = 0.35, exposure = 1.06, mie = 1.0, haze = 0.52, water = { 0.13, 0.13, 0.15 } },
    { h = 19.3, name = "sunset", zen = { 0.12, 0.14, 0.30 }, hor = { 0.88, 0.38, 0.24 }, sun = { 1.0, 0.52, 0.28 }, sunI = 0.32,
      amb = { 0.15, 0.12, 0.15 }, nightKeep = 0.75, nightGlow = 0.65, exposure = 1.12, mie = 1.1, haze = 0.60, water = { 0.10, 0.09, 0.11 } },
    { h = 20.2, name = "dusk", zen = { 0.05, 0.06, 0.14 }, hor = { 0.38, 0.20, 0.28 }, sun = { 0.85, 0.55, 0.55 }, sunI = 0.08,
      amb = { 0.07, 0.065, 0.09 }, nightKeep = 0.92, nightGlow = 0.92, exposure = 1.16, mie = 0.65, haze = 0.62, water = { 0.05, 0.07, 0.10 } },
    { h = 21.3, name = "night", zen = { 0.022, 0.032, 0.075 }, hor = { 0.135, 0.10, 0.19 }, sun = { 0.5, 0.5, 0.7 }, sunI = 0.0,
      amb = { 0.032, 0.036, 0.05 }, nightKeep = 1.0, nightGlow = 1.0, exposure = 1.2, mie = 0.3, haze = 0.55, water = { 0.035, 0.075, 0.10 } },
    { h = 2.0, name = "deep night", zen = { 0.016, 0.024, 0.062 }, hor = { 0.115, 0.085, 0.17 }, sun = { 0.5, 0.5, 0.7 }, sunI = 0.0,
      amb = { 0.026, 0.03, 0.042 }, nightKeep = 1.0, nightGlow = 1.0, exposure = 1.22, mie = 0.28, haze = 0.55, water = { 0.03, 0.065, 0.09 } },
}

-- ---------------------------------------------------------------------------------------
-- vanilla weather ids -> cloud cover / wetness target / lightning rate.
-- 0-19 are the GTA:SA weather types; anything else falls back to a clear-ish default.
-- The actual rain level (getRainLevel, server driven) always wins over the preset guess.
-- ---------------------------------------------------------------------------------------
local WX = {
    [0] = { cover = 0.10, wetT = 0.0, flash = 0.0, dim = 1.04 },   -- extrasunny LA
    [1] = { cover = 0.15, wetT = 0.0, flash = 0.0, dim = 1.02 },   -- sunny LA
    [2] = { cover = 0.28, wetT = 0.0, flash = 0.0, dim = 0.98 },   -- extrasunny smog LA
    [3] = { cover = 0.34, wetT = 0.0, flash = 0.0, dim = 0.95 },   -- sunny smog LA
    [4] = { cover = 0.75, wetT = 0.05, flash = 0.0, dim = 0.88 },  -- cloudy LA
    [5] = { cover = 0.20, wetT = 0.0, flash = 0.0, dim = 1.0 },    -- sunny SF
    [6] = { cover = 0.10, wetT = 0.0, flash = 0.0, dim = 1.03 },   -- extrasunny SF
    [7] = { cover = 0.70, wetT = 0.05, flash = 0.0, dim = 0.9 },   -- cloudy SF
    [8] = { cover = 0.95, wetT = 0.95, flash = 1.0, dim = 0.62 },  -- rainy SF
    [9] = { cover = 0.55, wetT = 0.10, flash = 0.0, dim = 0.82 },  -- foggy SF
    [10] = { cover = 0.10, wetT = 0.0, flash = 0.0, dim = 1.04 },  -- sunny vegas
    [11] = { cover = 0.08, wetT = 0.0, flash = 0.0, dim = 1.05 },  -- extrasunny vegas
    [12] = { cover = 0.65, wetT = 0.05, flash = 0.0, dim = 0.9 },  -- cloudy vegas
    [13] = { cover = 0.12, wetT = 0.0, flash = 0.0, dim = 1.03 },  -- extrasunny countryside
    [14] = { cover = 0.20, wetT = 0.0, flash = 0.0, dim = 1.0 },   -- sunny countryside
    [15] = { cover = 0.75, wetT = 0.05, flash = 0.0, dim = 0.88 }, -- cloudy countryside
    [16] = { cover = 0.95, wetT = 0.95, flash = 1.0, dim = 0.62 }, -- rainy countryside
    [17] = { cover = 0.06, wetT = 0.0, flash = 0.0, dim = 1.05 },  -- extrasunny desert
    [18] = { cover = 0.12, wetT = 0.0, flash = 0.0, dim = 1.02 },  -- sunny desert
    [19] = { cover = 0.55, wetT = 0.0, flash = 0.0, dim = 0.85 },  -- sandstorm desert
}
local WX_DEFAULT = { cover = 0.2, wetT = 0.0, flash = 0.0, dim = 1.0 }
WS_ENV.WX = WX

-- ---------------------------------------------------------------------------------------
-- state
-- ---------------------------------------------------------------------------------------
local S = {
    hour = 0.5,                                          -- from getTime()
    wxId = 0,                                            -- from getWeather()
    rainLevel = 0.0,                                     -- from getRainLevel()
    cur = nil,                                           -- eased live weather parameters
    wet = 0.0, puddle = 0.0, wetManual = nil,
    flash = 0.0, flashCd = 8.0, strikes = nil,
    sunEl = 0.0, sunDir = { x = 0, y = 0, z = 1 }, moonDir = { x = 0, y = 0, z = -1 },
    key = nil,
    t = 0,
}
WS_ENV.state = S

-- ---------------------------------------------------------------------------------------
-- helpers
-- ---------------------------------------------------------------------------------------
local function clamp(v, a, b)
    if v < a then return a end
    if v > b then return b end
    return v
end

local function lerp(a, b, t) return a + (b - a) * t end

local function lerp3(a, b, t)
    return { lerp(a[1], b[1], t), lerp(a[2], b[2], t), lerp(a[3], b[3], t) }
end

local function smooth(t)
    return t * t * (3.0 - 2.0 * t)
end

-- solar elevation / azimuth (simplified ephemeris: ~38 N, late spring declination, solar noon at 12:30)
local LAT, DEC = 0.665, 0.31

local function sunPos(hour)
    local H = (hour - 12.5) * math.pi / 12.0
    local sinEl = math.sin(DEC) * math.sin(LAT) + math.cos(DEC) * math.cos(LAT) * math.cos(H)
    sinEl = clamp(sinEl, -1, 1)
    local el = math.asin(sinEl)
    local az = math.atan2(math.sin(H), math.cos(H) * math.sin(LAT) - math.tan(DEC) * math.cos(LAT)) + math.pi
    local ce = math.cos(el)
    return { x = math.sin(az) * ce, y = math.cos(az) * ce, z = math.sin(el) }, el
end

-- sample the timecycle at the given hour (circular, smoothstep between the bracketing keys)
local function sampleKeys(hour)
    local n = #KEYS
    local i2 = 1
    while i2 <= n and KEYS[i2].h <= hour do
        i2 = i2 + 1
    end
    local i1 = i2 - 1
    if i1 < 1 then
        i1 = n
        i2 = 1
    end
    if i2 > n then
        i2 = 1
    end
    local a, b = KEYS[i1], KEYS[i2]
    local h0, h1 = a.h, b.h
    if h1 <= h0 then
        h1 = h1 + 24.0
    end
    local t = smooth(clamp((hour - h0) / math.max(h1 - h0, 0.001), 0, 1))
    return {
        zen = lerp3(a.zen, b.zen, t), hor = lerp3(a.hor, b.hor, t), sun = lerp3(a.sun, b.sun, t),
        amb = lerp3(a.amb, b.amb, t), water = lerp3(a.water, b.water, t),
        sunI = lerp(a.sunI, b.sunI, t), nightKeep = lerp(a.nightKeep, b.nightKeep, t), nightGlow = lerp(a.nightGlow, b.nightGlow, t),
        exposure = lerp(a.exposure, b.exposure, t), mie = lerp(a.mie, b.mie, t), haze = lerp(a.haze, b.haze, t),
    }
end

-- ease every weather parameter toward the vanilla weather (dt seconds)
local function easeWeather(dt)
    local w = WX[S.wxId] or WX_DEFAULT
    local tau = 1.0 - math.exp(-dt / 7.0)                -- ~7 s to settle
    local c = S.cur
    if not c then
        c = {}
        S.cur = c
        for k, v in pairs(w) do
            if type(v) == "number" then
                c[k] = v
            end
        end
    else
        for k, v in pairs(w) do
            if type(v) == "number" then
                c[k] = c[k] + (v - c[k]) * tau
            end
        end
    end
end

-- ---------------------------------------------------------------------------------------
-- wetness / drying model
-- ---------------------------------------------------------------------------------------
local function stepWet(dt)
    local c = S.cur or (WX[S.wxId] or WX_DEFAULT)
    local rain = S.rainLevel
    local target
    if S.wetManual then
        target = S.wetManual
    else
        target = clamp(math.max(c.wetT, rain * 1.15), 0, 1)
    end
    local sunUp = math.max(0, S.sunDir.z)
    local dry = 0.006 + 0.030 * sunUp * (1.0 - 0.65 * c.cover) + 0.004 * (1.0 - c.cover)
    if S.wetManual then
        S.wet = S.wet + (target - S.wet) * math.min(1, dt * 1.5)          -- manual override snaps in about a second
    elseif target > S.wet then
        S.wet = S.wet + (target - S.wet) * math.min(1, dt * (0.22 + 0.45 * rain))
    else
        S.wet = math.max(target, S.wet - dry * dt * 1.7)
    end
    if S.wetManual then
        S.puddle = S.wetManual
    elseif S.wet > 0.5 then
        S.puddle = S.puddle + (math.min(1, (S.wet - 0.5) * 2.2) - S.puddle) * math.min(1, dt * 0.10)
    else
        S.puddle = math.max(0, S.puddle - dry * dt * 0.85)
    end
end

-- ---------------------------------------------------------------------------------------
-- lightning
-- ---------------------------------------------------------------------------------------
function WS_ENV.fireFlash()
    S.strikes = { t0 = S.t, times = { 0.0, 0.12, 0.30 } }
    S.flash = 1.15
    if WS_ENV.onFlash then
        WS_ENV.onFlash(1.0)
    end
end

local function stepFlash(dt)
    local c = S.cur or (WX[S.wxId] or WX_DEFAULT)
    local rate = c.flash
    S.flash = math.max(0, S.flash - dt * 2.6)
    if rate <= 0.01 then
        S.strikes = nil
        S.flashCd = math.max(S.flashCd, 6.0)
        return
    end
    S.flashCd = S.flashCd - dt
    if S.flashCd <= 0 then
        S.flashCd = (4.5 + math.random() * 9.0) / math.max(rate, 0.05)
        WS_ENV.fireFlash()
    end
    if S.strikes then
        local el = S.t - S.strikes.t0
        local amp = 0.0
        for _, st in ipairs(S.strikes.times) do
            if el >= st then
                amp = math.max(amp, math.exp(-(el - st) * 11.0))
            end
        end
        S.flash = math.max(S.flash, amp * 1.15)
        if el > 1.2 then
            S.strikes = nil
        end
    end
end

-- ---------------------------------------------------------------------------------------
-- tick: read the vanilla clock / weather / rain, then clock, sun, timecycle, wetness, lightning
-- ---------------------------------------------------------------------------------------
function WS_ENV.tick(dt)
    dt = clamp(dt or 0.05, 0, 0.5)
    S.t = S.t + dt

    -- what the vanilla game is doing right now
    local okh, h, m = pcall(getTime)
    if okh and h then
        S.hour = (tonumber(h) or 0) + (tonumber(m) or 0) / 60.0
    end
    local okw, w1 = pcall(getWeather)
    if okw and w1 then
        S.wxId = tonumber(w1) or S.wxId
    end
    local okr, r = pcall(getRainLevel)
    if okr and r then
        S.rainLevel = clamp(tonumber(r) or 0, 0, 1)
    else
        S.rainLevel = (WX[S.wxId] or WX_DEFAULT).wetT          -- old servers: use the preset guess
    end

    -- sun / moon
    local dir, el = sunPos(S.hour)
    S.sunDir = dir
    S.sunEl = el
    S.moonDir = { x = -dir.x, y = -dir.y, z = -dir.z }

    -- timecycle sample
    S.key = sampleKeys(S.hour)

    -- weather parameters (eased) + wetness + lightning
    easeWeather(dt)
    stepWet(dt)
    stepFlash(dt)
end

-- ---------------------------------------------------------------------------------------
-- uniforms for the shaders (same field names as the NightCity contract)
-- ---------------------------------------------------------------------------------------
function WS_ENV.uniforms()
    local k = S.key
    local c = S.cur or (WX[S.wxId] or WX_DEFAULT)
    local night = clamp(-S.sunDir.z * 6.0 + 0.55, 0, 1)
    local rays = (S.sunEl > 0.02) and (0.55 + 0.45 * k.mie) or 0
    return {
        sunX = S.sunDir.x, sunY = S.sunDir.y, sunZ = S.sunDir.z,
        sunR = k.sun[1], sunG = k.sun[2], sunB = k.sun[3], sunI = k.sunI * (0.35 + 0.65 * c.dim),
        moonX = S.moonDir.x, moonY = S.moonDir.y, moonZ = S.moonDir.z,
        ambR = k.amb[1] * c.dim, ambG = k.amb[2] * c.dim, ambB = k.amb[3] * c.dim,
        nightKeep = k.nightKeep, nightGlow = k.nightGlow, night = night,
        zenR = k.zen[1] * c.dim, zenG = k.zen[2] * c.dim, zenB = k.zen[3] * c.dim,
        horR = k.hor[1] * c.dim, horG = k.hor[2] * c.dim, horB = k.hor[3] * c.dim,
        fogR = k.hor[1] * c.dim, fogG = k.hor[2] * c.dim, fogB = k.hor[3] * c.dim,
        fogNear = 220, fogFar = 900,
        cover = c.cover, cloudDark = (1.0 - 0.5 * c.cover) * (0.55 + 0.45 * c.dim),
        windX = 6.0, windY = 2.0,
        flash = S.flash, quality = 2, dim = c.dim,
        wet = S.wet, puddle = S.puddle, exposure = k.exposure, haze = k.haze * (0.8 + 0.3 * c.cover), mie = k.mie,
        waterR = k.water[1] * c.dim, waterG = k.water[2] * c.dim, waterB = k.water[3] * c.dim,
        rayStrength = rays,
        time = S.t,
    }
end

function WS_ENV.setWet(v)
    S.wetManual = v
end

function WS_ENV.status()
    local c = S.cur or (WX[S.wxId] or WX_DEFAULT)
    return string.format("time %02d:%02d  weather %d  rain %.2f  wet %.2f / puddle %.2f  flash %.2f",
        math.floor(S.hour), math.floor((S.hour % 1) * 60), S.wxId, S.rainLevel, S.wet, S.puddle, S.flash)
end

-- boot: evaluate the first state so the shaders get sane values before the first tick
WS_ENV.tick(0.0)
