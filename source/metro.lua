-- Created by: Arena.ai Agent Mode (AI) - NightCity MTA:SA resource
-- -------------------------------------------------------------------------------------------
-- metro.lua - the rideable Night City Metro.  A shuttle train runs the east-west line (NC_METRO)
--             between the west terminus (inside the lit tunnel tube) and the east buffer stop,
--             calling at MARKET / UNION / DOCKS.  Automatic sliding doors open at every stop;
--             press E next to the car (platform or deck) to board - press E again to step out.
--             Uses the helpers client.lua publishes in the global table NC (toWorld / toCity / ...).
-- -------------------------------------------------------------------------------------------
local ACC = 1.2          -- m/s^2 while motoring
local BRK = 1.4          -- m/s^2 while braking
local BAY = { -8.05, -2.68, 2.68, 8.05 }    -- door bay centres along the car (matches nc/rail.py)
local DOOR_Y = 1.47      -- leaf plane offset from the car centre line
local DOOR_Z = 1.05      -- leaf origin on the rail top
local SLIDE = 1.42       -- leaf travel when open (m)
local SLIDE_T = 1.7      -- seconds for a full slide
local CLOSE_LEAD = 2.0   -- doors start closing this long before departure
local RIDE_XMAX = 9.6    -- how far along the car the rider may stand

local M = {
    on = false, x = 0.0, dir = 1, idx = 1, v = 0.0,
    dwell = 0.0, slide = 0.0, slideTarget = 0.0,
    riding = false, rideX = 0.0, last = 0.0,
}

local function stops()
    -- the full call pattern: west terminus, three stations, east terminus
    local t = { NC_METRO.park }
    for i = 1, #NC_METRO.stops do t[#t + 1] = NC_METRO.stops[i] end
    t[#t + 1] = NC_METRO.pend
    return t
end

local function say(msg) if NC and NC.say then NC.say(msg) end end

local function placeTrain()
    if not (NC.train and isElement(NC.train)) then return end
    setElementPosition(NC.train, NC.toWorld(M.x, NC_METRO.y, NC_METRO.z))
    if not NC.doors then return end
    for k = 1, 8 do
        local el = NC.doors[k]
        if el and isElement(el) then
            local bay = BAY[math.floor((k - 1) / 2) + 1]
            local side = (k % 2 == 1) and -1 or 1
            -- each leaf slides toward the middle of the car
            local sgn = (bay < 0) and 1 or -1
            local sx = bay + sgn * M.slide * SLIDE
            setElementPosition(el, NC.toWorld(M.x + sx, NC_METRO.y + side * DOOR_Y, NC_METRO.z + DOOR_Z))
        end
    end
end

local function releaseRider()
    if M.riding then
        M.riding = false
        setElementFrozen(localPlayer, false)
    end
end

local function frame()
    if not (M.on and NC and NC.isShown() and NC.train and isElement(NC.train)) then return end
    local now = getTickCount()
    local dt = (now - M.last) / 1000
    M.last = now
    if dt > 0.1 then dt = 0.1 end
    if dt <= 0 then return end

    local T = stops()
    local vmax = NC_METRO.vx or 16.0
    if M.dwell > 0 then
        -- standing at a stop: doors open, closing again shortly before departure
        M.dwell = M.dwell - dt
        M.slideTarget = (M.dwell > CLOSE_LEAD) and 1.0 or 0.0
        if M.dwell <= 0 then M.dwell = 0 end
    else
        M.slideTarget = 0.0
        local target = T[M.idx + M.dir]
        if not target then
            M.dir = -M.dir
            target = T[M.idx + M.dir]
        end
        local d = target - M.x
        local ad = math.abs(d)
        local vpeak = math.min(vmax, math.sqrt(math.max(0.0, 2 * ad * ACC * BRK / (ACC + BRK))))
        local brake_d = (M.v * M.v) / (2 * BRK)
        if ad <= brake_d + 0.4 then
            M.v = math.max(0.0, M.v - BRK * dt)
        else
            M.v = math.min(vpeak, M.v + ACC * dt)
        end
        M.x = M.x + (d >= 0 and 1 or -1) * M.v * dt
        if ad < 0.35 and M.v < 0.6 then
            M.x = target
            M.v = 0.0
            M.idx = M.idx + M.dir
            M.dwell = NC_METRO.dw or 7.0
        end
    end

    -- door leaves
    local step = dt / SLIDE_T
    if M.slide < M.slideTarget then
        M.slide = math.min(M.slideTarget, M.slide + step)
    elseif M.slide > M.slideTarget then
        M.slide = math.max(M.slideTarget, M.slide - step)
    end

    placeTrain()

    -- the rider travels with the car
    if M.riding then
        setElementPosition(localPlayer, NC.toWorld(M.x + M.rideX, NC_METRO.y, NC_METRO.z + 1.12))
    end
end

local function toggleRide()
    if not (M.on and NC and NC.isShown() and NC.train and isElement(NC.train)) then return end
    if M.riding then
        -- step out: onto the platform when the doors are open at a station, else onto the deck
        releaseRider()
        local sideY, sideZ = 2.9, 0.06
        if M.slide > 0.5 and M.dwell > 0 then
            sideY, sideZ = 8.5, 1.02
        end
        setElementPosition(localPlayer, NC.toWorld(M.x + M.rideX, NC_METRO.y + sideY, NC_METRO.z + sideZ))
        say("left the metro.")
        return
    end
    -- board: the player must be near the car at platform / deck height
    local px, py, pz = NC.toCity(getElementPosition(localPlayer))
    local dx, dy, dz = px - M.x, py - NC_METRO.y, pz - NC_METRO.z
    if math.abs(dx) < 13.5 and math.abs(dy) < 12.5 and math.abs(dz - 1.0) < 3.2 then
        if NC.stopTour then NC.stopTour() end
        M.riding = true
        M.rideX = NC.clamp(dx, -RIDE_XMAX, RIDE_XMAX)
        setElementFrozen(localPlayer, true)
        setElementPosition(localPlayer, NC.toWorld(M.x + M.rideX, NC_METRO.y, NC_METRO.z + 1.12))
        say("aboard the Night City Metro - press E to leave.")
    end
end

local function start()
    if M.on or not (NC_METRO and NC.train and isElement(NC.train)) then return end
    M.on = true
    M.x = NC_METRO.park
    M.dir = 1
    M.idx = 1
    M.v = 0.0
    M.dwell = NC_METRO.dw or 7.0
    M.slide = 0.0
    M.last = getTickCount()
    addEventHandler("onClientPreRender", root, frame)
    bindKey("e", "down", toggleRide)
end

local function stop()
    if not M.on then return end
    M.on = false
    removeEventHandler("onClientPreRender", root, frame)
    unbindKey("e", "down", toggleRide)
    releaseRider()
end

local pollTimer = nil

local function stopPoll()
    if pollTimer then killTimer(pollTimer) pollTimer = nil end
end

-- the train is spawned with the rest of the city: once client.lua reports the build done
-- (NC.onShow) wait for it on a quiet timer - no persistent pre-render handler while idle
local function startPoll()
    if pollTimer then return end
    pollTimer = setTimer(function()
        if M.on then return end
        if NC and NC.isShown() and NC.train and isElement(NC.train) and NC_METRO then
            stopPoll()
            start()
        end
    end, 250, 0)
end

-- client.lua clears NC.train / NC.doors and then calls NC.onHide
NC.onHide = function()
    stop()
    stopPoll()
end

NC.onShow = function()
    startPoll()
end

NC_METRO_RT = M          -- introspection for the test harness (M.on while the driver runs)

addCommandHandler("ncmetro", function()
    if not (NC and NC.isShown()) then return say("show the city first (/ncshow).") end
    if M.riding then toggleRide() end
    -- jump to the MARKET platform
    local s = NC_METRO.stops[1]
    setElementPosition(localPlayer, NC.toWorld(s, NC_METRO.y + 8.5, NC_METRO.z + 1.02))
    say("Night City Metro: press E next to the train to ride.")
end)
