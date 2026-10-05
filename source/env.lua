-- Created by: Arena.ai Agent Mode (AI) - NightCity MTA:SA resource
-- ---------------------------------------------------------------------------------------
-- env.lua - the environment engine: time of day, sun / moon, weather, surface wetness, lightning, quality.
-- client.lua drives it every frame (NC_ENV.tick + NC_ENV.apply) and pushes NC_ENV.uniforms() into the shaders.
--
--   * timecycle: keyframed day phases (pre-dawn, sunrise, morning, noon, afternoon, golden hour, sunset, dusk,
--     night) with smooth interpolation of sky / sun / ambient / fog / water colours, exposure and night glow
--   * sun: real solar elevation / azimuth (simplified ephemeris, ~38 N, late spring) -> gSunDir for the shaders,
--     warm low sun vs. neutral noon comes from the timecycle sun colour
--   * weather presets: clear, fair, cloudy, overcast, lightrain, rain, storm, fog, mist, afterrain - each with
--     cloud cover, rain, wetness target, fog / far clip, dimming, wind, god-ray strength and lightning rate;
--     every parameter eases toward the target (no hard switches)
--   * wetness model: the ground soaks fast while it rains and dries slowly afterwards (faster with sun and
--     broken cloud), puddles fill after the film and dry last -> the "after rain" look
--   * lightning: multi-strike flashes (gFlash) with a thunder callback, only in rain / storm
--   * quality: LOW / MEDIUM / HIGH / ULTRA (shader feature uniform, billboard budget, god rays)
--
-- Technical limits (documented on purpose): no dynamic shadows and no true reflections exist in MTA:SA / DX9 -
-- the sun term is a wrapped diffuse approximation, wet reflections are screen-space, sun rays are screen-space
-- radial scattering.  The vanilla sky gradient / sun / moon are only the fallback for /ncfx 0 and the GTA water.
-- ---------------------------------------------------------------------------------------
NC_ENV = {}

local D2R = math.pi / 180.0

-- ---------------------------------------------------------------------------------------
-- quality presets
-- ---------------------------------------------------------------------------------------
local QUALITY = {
    low = { q = 0, sprites = 150, rays = 0.0, name = "LOW" },
    medium = { q = 1, sprites = 240, rays = 0.55, name = "MEDIUM" },
    high = { q = 2, sprites = 340, rays = 1.0, name = "HIGH" },
    ultra = { q = 3, sprites = 420, rays = 1.35, name = "ULTRA" },
}
NC_ENV.QUALITY = QUALITY

-- ---------------------------------------------------------------------------------------
-- timecycle keyframes: hour -> sky / sun / ambient / fog / water / exposure
-- colours are 0..1 floats (setSkyGradient gets them x 255)
-- ---------------------------------------------------------------------------------------
local KEYS = {
    { h = 4.6, name = "pre-dawn", zen = { 0.030, 0.045, 0.095 }, hor = { 0.16, 0.13, 0.21 }, sun = { 0.55, 0.55, 0.75 }, sunI = 0.02,
      amb = { 0.035, 0.04, 0.055 }, nightKeep = 1.0, nightGlow = 1.0, exposure = 1.18, mie = 0.35, haze = 0.55, water = { 0.035, 0.075, 0.10 } },
    { h = 5.5, name = "dawn", zen = { 0.075, 0.11, 0.20 }, hor = { 0.52, 0.28, 0.22 }, sun = { 1.0, 0.52, 0.28 }, sunI = 0.22,
      amb = { 0.10, 0.085, 0.10 }, nightKeep = 0.85, nightGlow = 0.85, exposure = 1.05, mie = 0.85, haze = 0.60, water = { 0.10, 0.09, 0.11 } },
    { h = 6.6, name = "sunrise", zen = { 0.16, 0.28, 0.48 }, hor = { 0.85, 0.52, 0.32 }, sun = { 1.0, 0.68, 0.38 }, sunI = 0.55,
      amb = { 0.19, 0.185, 0.21 }, nightKeep = 0.55, nightGlow = 0.45, exposure = 0.98, mie = 0.95, haze = 0.55, water = { 0.14, 0.15, 0.18 } },
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
-- weather presets.  fog / far are absolute GTA distances (the shader haze follows gFogColor),
-- wetT is the wetness the weather wants, flash is the lightning rate multiplier, rays the
-- sun-ray strength multiplier.
-- ---------------------------------------------------------------------------------------
local WEATHERS = {
    clear = { cover = 0.12, rain = 0.0, wetT = 0.0, fog = 850, far = 2400, dim = 0.97, wind = 3.0, rays = 1.0, flash = 0.0, cloudDark = 0.95, wx = 0 },
    fair = { cover = 0.35, rain = 0.0, wetT = 0.0, fog = 720, far = 2100, dim = 0.95, wind = 4.0, rays = 0.85, flash = 0.0, cloudDark = 0.88, wx = 1 },
    cloudy = { cover = 0.65, rain = 0.0, wetT = 0.0, fog = 620, far = 1900, dim = 0.92, wind = 5.5, rays = 0.55, flash = 0.0, cloudDark = 0.72, wx = 2 },
    overcast = { cover = 0.92, rain = 0.0, wetT = 0.05, fog = 520, far = 1600, dim = 0.78, wind = 6.0, rays = 0.22, flash = 0.0, cloudDark = 0.52, wx = 3 },
    lightrain = { cover = 0.85, rain = 0.35, wetT = 0.55, fog = 480, far = 1500, dim = 0.72, wind = 7.0, rays = 0.1, flash = 0.0, cloudDark = 0.45, wx = 8 },
    rain = { cover = 0.95, rain = 0.8, wetT = 0.92, fog = 420, far = 1350, dim = 0.62, wind = 8.5, rays = 0.05, flash = 0.15, cloudDark = 0.38, wx = 8 },
    storm = { cover = 1.0, rain = 1.0, wetT = 1.0, fog = 380, far = 1200, dim = 0.52, wind = 12.0, rays = 0.0, flash = 1.0, cloudDark = 0.28, wx = 8 },
    fog = { cover = 0.5, rain = 0.0, wetT = 0.1, fog = 110, far = 700, dim = 0.8, wind = 2.0, rays = 0.15, flash = 0.0, cloudDark = 0.62, wx = 9 },
    mist = { cover = 0.42, rain = 0.0, wetT = 0.15, fog = 260, far = 1100, dim = 0.88, wind = 2.5, rays = 0.35, flash = 0.0, cloudDark = 0.68, wx = 9 },
    afterrain = { cover = 0.42, rain = 0.05, wetT = 0.55, fog = 700, far = 2200, dim = 0.96, wind = 4.5, rays = 1.25, flash = 0.0, cloudDark = 0.8, wx = 2 },
}
NC_ENV.WEATHERS = WEATHERS
local WORDER = { "clear", "fair", "cloudy", "overcast", "lightrain", "rain", "storm", "fog", "mist", "afterrain" }
NC_ENV.WORDER = WORDER

-- ---------------------------------------------------------------------------------------
-- state
-- ---------------------------------------------------------------------------------------
local S = {
    hour = 0.5, minute = 30, cycle = 0,                    -- clock (cycle = in-game hours per real minute, 0 = frozen)
    weather = "storm",                                     -- preset name
    cur = nil,                                             -- eased live parameters
    wet = 1.0, puddle = 1.0, wetManual = nil, rainManual = nil,
    flash = 0.0, flashCd = 8.0, strikes = nil,
    quality = "high", q = QUALITY.high,
    sunEl = 0.0, sunDir = { x = 0, y = 0, z = 1 }, moonDir = { x = 0, y = 0, z = -1 },
    key = nil,                                             -- sampled timecycle
    vanillaSun = false,                                    -- /ncfx 0: show the vanilla sun / moon discs
    t = 0, applied = -10,
}
NC_ENV.state = S

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

-- ease every weather parameter toward its preset (dt seconds)
local function easeWeather(dt)
    local w = WEATHERS[S.weather] or WEATHERS.storm
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
    local c = S.cur or WEATHERS[S.weather]
    local rain = S.rainManual or c.rain
    local target
    if S.wetManual then
        target = S.wetManual
    else
        target = clamp(S.rainManual and (rain * 1.15) or c.wetT, 0, 1)
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
function NC_ENV.fireFlash()
    S.strikes = { t0 = S.t, times = { 0.0, 0.12, 0.30 } }
    S.flash = 1.15
    if NC_ENV.onFlash then
        NC_ENV.onFlash(1.0)
    end
end

local function stepFlash(dt)
    local c = S.cur or WEATHERS[S.weather]
    local rate = c.flash * (S.quality == "low" and 0.5 or 1.0)
    S.flash = math.max(0, S.flash - dt * 2.6)
    if rate <= 0.01 then
        S.strikes = nil
        S.flashCd = math.max(S.flashCd, 6.0)
        return
    end
    S.flashCd = S.flashCd - dt
    if S.flashCd <= 0 then
        S.flashCd = (4.5 + math.random() * 9.0) / math.max(rate, 0.05)
        NC_ENV.fireFlash()
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
-- uniforms for the shaders (client.lua pushes these into every active shader)
-- ---------------------------------------------------------------------------------------
function NC_ENV.uniforms()
    local k = S.key
    local c = S.cur or WEATHERS[S.weather]
    local w = WEATHERS[S.weather]
    local q = S.q
    local night = clamp(-S.sunDir.z * 6.0 + 0.55, 0, 1)
    local rays = (w.rays or 0) * q.rays
    return {
        sunX = S.sunDir.x, sunY = S.sunDir.y, sunZ = S.sunDir.z,
        sunR = k.sun[1], sunG = k.sun[2], sunB = k.sun[3], sunI = k.sunI * (0.35 + 0.65 * c.dim),
        moonX = S.moonDir.x, moonY = S.moonDir.y, moonZ = S.moonDir.z,
        ambR = k.amb[1] * c.dim, ambG = k.amb[2] * c.dim, ambB = k.amb[3] * c.dim,
        nightKeep = k.nightKeep, nightGlow = k.nightGlow, night = night,
        zenR = k.zen[1] * c.dim, zenG = k.zen[2] * c.dim, zenB = k.zen[3] * c.dim,
        horR = k.hor[1] * c.dim, horG = k.hor[2] * c.dim, horB = k.hor[3] * c.dim,
        fogR = k.hor[1] * c.dim, fogG = k.hor[2] * c.dim, fogB = k.hor[3] * c.dim,
        fogNear = c.fog * 0.45, fogFar = c.fog * 1.35,
        cover = c.cover, cloudDark = c.cloudDark * (0.55 + 0.45 * c.dim),
        windX = 0.6 * c.wind, windY = 0.2 * c.wind,
        flash = S.flash, quality = q.q, dim = c.dim,
        wet = S.wet, puddle = S.puddle, exposure = k.exposure, haze = k.haze * (0.8 + 0.3 * c.cover), mie = k.mie,
        waterR = k.water[1] * c.dim, waterG = k.water[2] * c.dim, waterB = k.water[3] * c.dim,
        rayStrength = rays,
        time = S.t,
    }
end

-- ---------------------------------------------------------------------------------------
-- vanilla world (GTA sky gradient / fog / clock / rain): the fallback look and what the GTA water reflects
-- ---------------------------------------------------------------------------------------
function NC_ENV.apply()
    local k = S.key
    local c = S.cur or WEATHERS[S.weather]
    local w = WEATHERS[S.weather]
    local rain = S.rainManual or c.rain
    local h, m = math.floor(S.hour), math.floor((S.hour % 1) * 60)
    pcall(setTime, h, m)
    if S.wxApplied ~= w.wx then
        S.wxApplied = w.wx
        pcall(setWeatherBlended, w.wx, 4000)
    end
    pcall(setSkyGradient,
        math.floor(clamp(k.zen[1] * c.dim, 0, 1) * 255 + 0.5), math.floor(clamp(k.zen[2] * c.dim, 0, 1) * 255 + 0.5), math.floor(clamp(k.zen[3] * c.dim, 0, 1) * 255 + 0.5),
        math.floor(clamp(k.hor[1] * c.dim, 0, 1) * 255 + 0.5), math.floor(clamp(k.hor[2] * c.dim, 0, 1) * 255 + 0.5), math.floor(clamp(k.hor[3] * c.dim, 0, 1) * 255 + 0.5))
    pcall(setFogDistance, c.fog)
    pcall(setFarClipDistance, c.far)
    pcall(setHeatHaze, 0)
    pcall(setWindVelocity, 0.6 * c.wind / 12.0, 0.2 * c.wind / 12.0, 0.0)
    pcall(setRainLevel, (NC_ENV.tunnel and 0 or rain))
    -- lighting of dynamically created elements (peds / vehicles) and of map objects: GTA's default
    -- timecycle fights the NightCity look and goes near-black at high sun (the vertical surfaces get
    -- no directional light at noon).  MTA 1.6 setWorldProperty lets us drive the exact terms from the
    -- same timecycle the shaders use - pcall keeps older clients safe.
    local dirI = k.sunI * (0.35 + 0.65 * c.dim)
    pcall(setWorldProperty, "AmbientColor",
        math.floor(clamp(k.amb[1] * c.dim, 0, 1) * 255), math.floor(clamp(k.amb[2] * c.dim, 0, 1) * 255), math.floor(clamp(k.amb[3] * c.dim, 0, 1) * 255))
    pcall(setWorldProperty, "AmbientObjColor",
        math.floor(clamp(k.amb[1] * c.dim * 1.25, 0, 1) * 255 + 16), math.floor(clamp(k.amb[2] * c.dim * 1.25, 0, 1) * 255 + 16), math.floor(clamp(k.amb[3] * c.dim * 1.25, 0, 1) * 255 + 16))
    pcall(setWorldProperty, "DirectionalColor",
        math.floor(clamp(k.sun[1], 0, 1) * 255), math.floor(clamp(k.sun[2], 0, 1) * 255), math.floor(clamp(k.sun[3], 0, 1) * 255))
    pcall(setWorldProperty, "Illumination", math.max(0, dirI))
    if S.vanillaSun then
        pcall(setSunSize, math.floor(k.sunI * 16 + 0.5))
        pcall(setSunColor, math.floor(clamp(k.sun[1], 0, 1) * 255), math.floor(clamp(k.sun[2], 0, 1) * 255), math.floor(clamp(k.sun[3], 0, 1) * 255))
        pcall(setMoonSize, 2)
    else
        pcall(setSunSize, 0)
    end
    local wr, wg, wb = k.water[1] * c.dim, k.water[2] * c.dim, k.water[3] * c.dim
    pcall(setWaterColor, math.floor(clamp(wr * 2.2, 0, 1) * 255), math.floor(clamp(wg * 2.2, 0, 1) * 255), math.floor(clamp(wb * 2.2, 0, 1) * 255), 232)
end

-- ---------------------------------------------------------------------------------------
-- tick: clock, sun, timecycle, weather easing, wetness, lightning
-- ---------------------------------------------------------------------------------------
function NC_ENV.tick(dt)
    dt = clamp(dt or 0.05, 0, 0.5)
    S.t = S.t + dt
    if S.cycle ~= 0 then
        S.hour = (S.hour + dt / 60.0 * S.cycle) % 24.0
    end
    S.sunDir, S.sunEl = sunPos(S.hour)
    S.moonDir = sunPos((S.hour + 12.0) % 24.0)
    S.key = sampleKeys(S.hour)
    easeWeather(dt)
    stepWet(dt)
    stepFlash(dt)
end

-- ---------------------------------------------------------------------------------------
-- controls
-- ---------------------------------------------------------------------------------------
function NC_ENV.setClock(hour, minute)
    S.hour = (clamp(tonumber(hour) or 0, 0, 23.999) + (tonumber(minute) or 0) / 60.0) % 24.0
    S.sunDir, S.sunEl = sunPos(S.hour)
    S.key = sampleKeys(S.hour)
end

function NC_ENV.setWeather(name)
    if not WEATHERS[name] then
        return false
    end
    S.weather = name
    S.wxApplied = nil
    return true
end

function NC_ENV.setQuality(name)
    local q = QUALITY[name]
    if not q then
        return false
    end
    S.quality = name
    S.q = q
    return true
end

function NC_ENV.setWet(v)
    S.wetManual = v
end

function NC_ENV.setRain(v)
    S.rainManual = v
end

function NC_ENV.setCycle(v)
    S.cycle = clamp(tonumber(v) or 0, 0, 240)
end

function NC_ENV.status()
    local c = S.cur or WEATHERS[S.weather]
    return string.format("time %02d:%02d (%s)  weather %s  sun %+.1f deg  wet %.2f / puddle %.2f  rain %.2f  flash %.2f  quality %s  cycle %.1f h/min",
        math.floor(S.hour), math.floor((S.hour % 1) * 60), (S.key and "timecycle" or "-"), S.weather, S.sunEl / D2R, S.wet, S.puddle,
        S.rainManual or c.rain, S.flash, S.q.name, S.cycle)
end

-- boot: evaluate the first state so the shaders get sane values before the first tick.
-- NC_ENV.apply() is intentionally NOT called here: the vanilla world must stay untouched until the city is shown.
NC_ENV.tick(0.0)
