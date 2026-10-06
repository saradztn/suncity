-- Created by: Arena.ai Agent Mode (AI) - NightCity MTA:SA resource
-- -------------------------------------------------------------------------------------------
-- metro.lua - the rideable Night City Metro.  The train is the VANILLA GTA:SA consist
--             (model 538 "streak" engine + three 570 "streakc" carriages) - nothing is
--             modelled by us.  It follows the closed organic loop NC_METRO.path (a dense
--             polyline over the city: elevated through the harbour and the western heights,
--             at grade along the bay, underground beneath the CBD and the market) and keeps
--             circulating it for ever with automatic station dwells at every stop.
--             Press E next to / under the train to ride INSIDE a carriage - press E again
--             to step out onto the platform.  /ncmetro teleports to the MARKET station.
--             Uses the helpers client.lua publishes in the global table NC.
-- -------------------------------------------------------------------------------------------
local ACC = 1.2            -- m/s^2 while motoring
local BRK = 1.4            -- m/s^2 while braking
local CAR_GAP = 23.5       -- centre to centre between cars
local CARS = { 538, 570, 570, 570 }   -- vanilla GTA:SA train models
local DECK_Z = 0.15        -- running surface above the path datum (the models' rail top)
local RIDE_Z = 1.05        -- carriage floor: the rider stands INSIDE a car, not on its roof

local M = {
    on = false, s = 0.0, v = 0.0, targetS = 0.0, dwell = 0.0,
    cars = nil, riding = false, rideCar = 1, last = 0.0, lift = 1.15,
}

local G = {}               -- loop geometry (filled from NC_METRO)

local function buildGeom()
    local t = NC_METRO
    G.P = t.path
    G.n = #G.P
    G.cum = { 0.0 }
    local total = 0.0
    for i = 1, G.n do
        local a = G.P[i]
        local b = G.P[i % G.n + 1]
        local dx, dy, dz = b[1] - a[1], b[2] - a[2], b[3] - a[3]
        total = total + math.sqrt(dx * dx + dy * dy + dz * dz)
        G.cum[i + 1] = total
    end
    G.total = total
    G.stops = {}
    for i = 1, #t.stops do
        G.stops[i] = { s = t.stops[i].s, name = t.stops[i].name, kind = t.stops[i].kind }
    end
    table.sort(G.stops, function(a, b) return a.s < b.s end)
end

-- position + travel direction + rail-top z at loop distance s (forward is +y at rz 0)
local function pathAt(s)
    s = s % G.total
    local lo, hi = 1, G.n
    while lo < hi do
        local mid = math.floor((lo + hi) / 2)
        if G.cum[mid + 1] <= s then lo = mid + 1 else hi = mid end
    end
    local i = lo
    local s0 = G.cum[i]
    local t = (s - s0) / math.max(0.01, G.cum[i + 1] - s0)
    local a, b = G.P[i], G.P[i % G.n + 1]
    local dx, dy, dz = b[1] - a[1], b[2] - a[2], b[3] - a[3]
    local l2 = math.sqrt(dx * dx + dy * dy)
    local x = a[1] + dx * t
    local y = a[2] + dy * t
    local z = a[3] + dz * t
    return x, y, dx / l2, dy / l2, z, dz / math.max(0.01, math.sqrt(l2 * l2 + dz * dz))
end

local function say(msg) if NC and NC.say then NC.say(msg) end end

-- next station call strictly ahead of cur (stations repeat every lap)
local function nextStop(cur)
    for lap = 0, 4 do
        for i = 1, #G.stops do
            local s = G.stops[i].s + lap * G.total
            if s > cur + 0.5 then return s end
        end
    end
    return cur + G.total
end

local function placeCars()
    if not M.cars then return end
    for i, veh in ipairs(M.cars) do
        if isElement(veh) then
            local x, y, dx, dy, z, dp = pathAt(M.s - (i - 1) * CAR_GAP)
            setElementPosition(veh, NC.toWorld(x, y, z + DECK_Z + M.lift))
            -- ZXY order: rz = heading, X = local pitch (nose up on a rising grade)
            setElementRotation(veh, -math.deg(math.asin(math.max(-1, math.min(1, dp)))), 0, math.deg(math.atan2(-dx, dy)))
        end
    end
end

-- lift the consist so the model bottom rests exactly on the running surface
local function measureLift(veh)
    local ok, _, _, minZ = pcall(getElementBoundingBox, veh)
    if ok and type(minZ) == "number" and minZ < -0.1 and minZ > -6.0 then
        M.lift = -minZ
    else
        M.lift = 1.15                          -- fallback: typical carriage origin height
    end
end

local function releaseRider()
    if M.riding then
        M.riding = false
        setElementFrozen(localPlayer, false)
        if M.cars then
            for _, v in ipairs(M.cars) do
                if isElement(v) then setElementCollisionsEnabled(v, true) end
            end
        end
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
        local x, y, _, _, z = pathAt(M.s - (M.rideCar - 1) * CAR_GAP)
        setElementPosition(localPlayer, NC.toWorld(x, y, z + RIDE_Z))
    end
end

local function toggleRide()
    if not (M.on and M.cars) then return end
    if M.riding then
        releaseRider()
        local x, y, dx, dy, z = pathAt(M.s - (M.rideCar - 1) * CAR_GAP)
        -- step out to the platform side (left of travel) when dwelling at a station, else onto the deck
        local nx, ny, outZ = -dy, dx, 0.06
        if M.dwell > 0 then
            outZ = 1.02
            nx, ny = -dy * 7.0, dx * 7.0
            setElementPosition(localPlayer, NC.toWorld(x + nx, y + ny, z + outZ))
        else
            setElementPosition(localPlayer, NC.toWorld(x + nx * 3.0, y + ny * 3.0, z + outZ))
        end
        say("left the metro.")
        return
    end
    -- board: the player must be near the consist (anywhere along it)
    local px, py, pz = NC.toCity(getElementPosition(localPlayer))
    for i = 1, #M.cars do
        local x, y, _, _, z = pathAt(M.s - (i - 1) * CAR_GAP)
        local dx, dy, dz = px - x, py - y, pz - z
        if math.abs(dx) < 12.0 and math.abs(dy) < 8.0 and dz > -2.5 and dz < 5.5 then
            if NC.stopTour then NC.stopTour() end
            M.riding = true
            M.rideCar = i
            setElementFrozen(localPlayer, true)
            setElementPosition(localPlayer, NC.toWorld(x, y, z + RIDE_Z))
            for _, v in ipairs(M.cars) do                    -- the camera must not fight the shell
                if isElement(v) then setElementCollisionsEnabled(v, false) end
            end
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
        local x, y, dx, dy, z = pathAt(220.0 - (i - 1) * CAR_GAP)   -- start on the harbour viaduct
        local wx, wy, wz = NC.toWorld(x, y, z + DECK_Z)
        local veh = createVehicle(model, wx, wy, wz, 0, 0, math.deg(math.atan2(-dx, dy)))
        if veh then
            if i == 1 then measureLift(veh) end
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
    M.s = 220.0
    M.v = 0.0
    M.dwell = 0.0
    M.targetS = nextStop(M.s)
    M.last = getTickCount()
    placeCars()
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
    -- the MARKET station platform (plan emits the platform point under this key)
    local p = NC_POINTS and NC_POINTS.metro_market
    if p then
        setElementPosition(localPlayer, NC.toWorld(p[1], p[2], p[3]))
    end
    say("Night City Metro: press E near the train to ride.")
end)
