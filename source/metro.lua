-- Created by: Arena.ai Agent Mode (AI) - NightCity MTA:SA resource
-- -------------------------------------------------------------------------------------------
-- metro.lua - the rideable Night City Metro.  The train is the VANILLA GTA:SA consist
--             (model 538 "streak" engine + three 570 "streakc" carriages) - nothing is
--             modelled by us.  It circulates a closed loop for ever (clockwise: the north
--             straight eastbound through the lit tunnel and the three stations MARKET /
--             UNION / DOCKS, then the east turn, the south return line and the west turn).
--             Automatic station dwells; press E next to / under the train to ride on the
--             roof of a carriage - press E again to step out.  /ncmetro teleports to MARKET.
--             Uses the helpers client.lua publishes in the global table NC.
-- -------------------------------------------------------------------------------------------
local ACC = 1.2            -- m/s^2 while motoring
local BRK = 1.4            -- m/s^2 while braking
local CAR_GAP = 23.5       -- centre to centre between cars
local CARS = { 538, 570, 570, 570 }   -- vanilla GTA:SA train models
local ROOF_Z = 3.2         -- rider height above the rail top (carriage roof)
local RIDE_XMAX = 8.0

local M = {
    on = false, s = 0.0, v = 0.0, targetS = 0.0, dwell = 0.0,
    cars = nil, riding = false, rideCar = 1, last = 0.0,
}

local G = {}               -- loop geometry (filled from NC_METRO)

local function buildGeom()
    local t = NC_METRO
    G.x0, G.x1, G.y, G.ys, G.r = t.x0, t.x1, t.y, t.ys, t.r
    G.z = t.z
    G.ym = (t.y + t.ys) / 2
    G.l1 = t.x1 - t.x0                              -- north straight (eastbound)
    G.la = math.pi * t.r                            -- east turn
    G.l2 = G.l1                                     -- south straight (westbound)
    G.lb = G.la                                     -- west turn
    G.total = 2 * (G.l1 + G.la)
    G.stops = {}                                    -- loop distance of every station call
    for i = 1, #t.stops do
        G.stops[i] = t.stops[i] - t.x0
    end
end

-- position + travel direction at loop distance s (forward is +y at rz 0)
local function pathAt(s)
    s = s % G.total
    if s < G.l1 then
        return G.x0 + s, G.y, 1.0, 0.0
    elseif s < G.l1 + G.la then
        local phi = math.pi / 2 - (s - G.l1) / G.r
        return G.x1 + G.r * math.cos(phi), G.ym + G.r * math.sin(phi), math.sin(phi), -math.cos(phi)
    elseif s < G.l1 + G.la + G.l2 then
        return G.x1 - (s - G.l1 - G.la), G.ys, -1.0, 0.0
    else
        local phi = -math.pi / 2 - (s - G.l1 - G.la - G.l2) / G.r
        return G.x0 + G.r * math.cos(phi), G.ym + G.r * math.sin(phi), math.sin(phi), -math.cos(phi)
    end
end

local function say(msg) if NC and NC.say then NC.say(msg) end end

-- next station call strictly ahead of cur (stations repeat every lap)
local function nextStop(cur)
    for lap = 0, 4 do
        for i = 1, #G.stops do
            local s = G.stops[i] + lap * G.total
            if s > cur + 0.5 then return s end
        end
    end
    return cur + G.total
end

local function placeCars()
    if not M.cars then return end
    for i, veh in ipairs(M.cars) do
        if isElement(veh) then
            local x, y, dx, dy = pathAt(M.s - (i - 1) * CAR_GAP)
            setElementPosition(veh, NC.toWorld(x, y, G.z))
            setElementRotation(veh, 0, 0, math.deg(math.atan2(-dx, dy)))
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
    if not (M.on and M.cars) then return end
    local now = getTickCount()
    local dt = (now - M.last) / 1000
    M.last = now
    if dt > 0.1 then dt = 0.1 end
    if dt <= 0 then return end

    local vmax = NC_METRO.vx or 16.0
    if M.dwell > 0 then
        M.dwell = M.dwell - dt
    else
        local d = M.targetS - M.s
        local ad = math.abs(d)
        local vpeak = math.min(vmax, math.sqrt(math.max(0.0, 2 * ad * ACC * BRK / (ACC + BRK))))
        if M.v * M.v / (2 * BRK) >= ad - 0.25 then
            M.v = math.max(0.0, M.v - BRK * dt)                 -- braking distance reached
        else
            M.v = math.min(vpeak, M.v + ACC * dt)
        end
        if M.v * dt >= ad or (M.v <= 0.0 and ad < 1.0) then     -- land exactly on the call point
            M.s = M.targetS
            M.v = 0.0
            M.dwell = NC_METRO.dw or 6.0
            M.targetS = nextStop(M.s)
        else
            M.s = M.s + M.v * dt
        end
    end

    placeCars()

    if M.riding and M.cars[M.rideCar] and isElement(M.cars[M.rideCar]) then
        local x, y = pathAt(M.s - (M.rideCar - 1) * CAR_GAP)
        setElementPosition(localPlayer, NC.toWorld(x, y, G.z + ROOF_Z))
    end
end

local function toggleRide()
    if not (M.on and M.cars) then return end
    if M.riding then
        releaseRider()
        local x, y = pathAt(M.s - (M.rideCar - 1) * CAR_GAP)
        -- step out onto the platform when standing at a station, else onto the track deck
        local outY, outZ = G.y + 2.6, 0.06
        if M.dwell > 0 then
            outY, outZ = G.y + 8.5, 1.02
        end
        setElementPosition(localPlayer, NC.toWorld(x, outY, G.z + outZ))
        say("left the metro.")
        return
    end
    -- board: the player must be near the consist (anywhere along it)
    local px, py, pz = NC.toCity(getElementPosition(localPlayer))
    for i = 1, #M.cars do
        local x, y = pathAt(M.s - (i - 1) * CAR_GAP)
        local dx, dy, dz = px - x, py - y, pz - G.z
        if math.abs(dx) < 12.0 and math.abs(dy) < 8.0 and dz > -2.5 and dz < 5.5 then
            if NC.stopTour then NC.stopTour() end
            M.riding = true
            M.rideCar = i
            setElementFrozen(localPlayer, true)
            setElementPosition(localPlayer, NC.toWorld(x, y, G.z + ROOF_Z))
            say("aboard the Night City Metro - press E to leave.")
            return
        end
    end
end

local function destroyCars()
    if M.cars then
        for _, veh in ipairs(M.cars) do
            if isElement(veh) then destroyElement(veh) end
        end
    end
    M.cars = nil
end

local function start()
    if M.on or not NC_METRO then return end
    buildGeom()
    -- the consist: vanilla GTA:SA train models, frozen (the driver moves them every frame)
    M.cars = {}
    for i, model in ipairs(CARS) do
        local x, y, dx, dy = pathAt(150.0 - (i - 1) * CAR_GAP)   -- start inside the west tunnel
        local wx, wy, wz = NC.toWorld(x, y, G.z)
        local veh = createVehicle(model, wx, wy, wz, 0, 0, math.deg(math.atan2(-dx, dy)))
        if veh then
            setElementFrozen(veh, true)
            pcall(setVehicleDamageProof, veh, true)
            pcall(setVehicleLocked, veh, true)
            pcall(setVehicleEngineState, veh, false)
            setElementCollisionsEnabled(veh, true)
            M.cars[#M.cars + 1] = veh
        end
    end
    if #M.cars == 0 then M.cars = nil say("metro: could not create the train.") return end
    M.on = true
    M.s = 150.0
    M.v = 0.0
    M.dwell = 0.0
    M.targetS = nextStop(M.s)
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
    destroyCars()
end

NC.onHide = function()
    stop()
end

NC.onShow = function()
    start()
end

NC_METRO_RT = M          -- introspection for the test harness (M.on while the driver runs)

addCommandHandler("ncmetro", function()
    if not (NC and NC.isShown()) then return say("show the city first (/ncshow).") end
    if M.riding then toggleRide() end
    setElementPosition(localPlayer, NC.toWorld(NC_METRO.stops[1], NC_METRO.y + 8.5, NC_METRO.z + 1.02))
    say("Night City Metro: press E near the train to ride.")
end)
