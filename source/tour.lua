-- Created by: Arena.ai Agent Mode (AI) - NightCity MTA:SA resource
-- ---------------------------------------------------------------------------------------------
-- tour.lua - /nctour : scripted camera flight along NC_TOUR (aerial, river, bridge, avenue, plaza, expressway, market, industrial,
--                      river tunnel).  Space or backspace (or /nctour again) stops it.
--            /ncfree : free camera - W A S D move, mouse looks, Space up, C down, Shift fast, Ctrl slow.  /ncfree again leaves it.
-- Uses the helpers that client.lua publishes in the global table NC.
-- ---------------------------------------------------------------------------------------------
local FOV = 75
local TOUR = { on = false, t0 = 0, held = false }
local FREE = { on = false, x = 0, y = 0, z = 0, yaw = 0, pitch = 0, last = 0, delay = 0, held = false }

local function catmull(p0, p1, p2, p3, t)
    local t2, t3 = t * t, t * t * t
    return 0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3)
end

local function holdPlayer(state)
    state.held = NC.hold() and true or false           -- client.lua may already hold the player until the ground exists
    setElementFrozen(localPlayer, true)
end

local function releasePlayer(state)
    if not state.held then setElementFrozen(localPlayer, false) end
    state.held = false
end

-- ---------------------------------------------------------------------------------------------
-- tour
-- ---------------------------------------------------------------------------------------------
local function tourFrame()
    if not TOUR.on then return end
    local K = NC_TOUR
    local n = #K
    local el = (getTickCount() - TOUR.t0) / 1000
    local j, acc = 1, 0
    while j < n and el >= acc + K[j][7] do
        acc = acc + K[j][7]
        j = j + 1
    end
    if j >= n then NC.stopTour() NC.say("tour finished.") return end
    local t = (el - acc) / K[j][7]
    local a, b, c, d = K[math.max(j - 1, 1)], K[j], K[j + 1], K[math.min(j + 2, n)]
    local ex, ey, ez = catmull(a[1], b[1], c[1], d[1], t), catmull(a[2], b[2], c[2], d[2], t), catmull(a[3], b[3], c[3], d[3], t)
    local tx, ty, tz = catmull(a[4], b[4], c[4], d[4], t), catmull(a[5], b[5], c[5], d[5], t), catmull(a[6], b[6], c[6], d[6], t)
    local wx, wy, wz = NC.toWorld(ex, ey, ez)
    local lx, ly, lz = NC.toWorld(tx, ty, tz)
    setCameraMatrix(wx, wy, wz, lx, ly, lz, 0, FOV)
end

function NC.stopTour()
    if not TOUR.on then return false end
    TOUR.on = false
    removeEventHandler("onClientPreRender", root, tourFrame)
    unbindKey("space", "down", NC.stopTour)
    unbindKey("backspace", "down", NC.stopTour)
    setCameraTarget(localPlayer)
    releasePlayer(TOUR)
    return true
end

local function startTour()
    if not NC.isShown() then NC.say("the city is not shown (/ncshow).") return end
    if FREE.on then NC.stopFree() end
    if #NC_TOUR < 2 then NC.say("this build has no tour path.") return end
    holdPlayer(TOUR)
    TOUR.on = true
    TOUR.t0 = getTickCount()
    addEventHandler("onClientPreRender", root, tourFrame)
    bindKey("space", "down", NC.stopTour)
    bindKey("backspace", "down", NC.stopTour)
    NC.say("camera tour - Space / Backspace (or /nctour) stops it.")
end

addCommandHandler("nctour", function()
    if TOUR.on then NC.stopTour() NC.say("tour stopped.") else startTour() end
end)

-- ---------------------------------------------------------------------------------------------
-- free camera
-- ---------------------------------------------------------------------------------------------
local function freeMouse(_, _, ax, ay)
    if not FREE.on then return end
    if isCursorShowing() or isMainMenuActive() then FREE.delay = 5 return end
    if FREE.delay > 0 then FREE.delay = FREE.delay - 1 return end
    local w, h = guiGetScreenSize()
    FREE.yaw = FREE.yaw + (ax - w / 2) * 0.0035
    FREE.pitch = NC.clamp(FREE.pitch - (ay - h / 2) * 0.0035, -1.5, 1.5)
end

local function freeFrame()
    if not FREE.on then return end
    local now = getTickCount()
    local dt = math.min((now - FREE.last) / 1000, 0.1)
    FREE.last = now
    local speed = 22
    if getKeyState("lshift") then speed = 110 elseif getKeyState("lctrl") then speed = 4 end
    speed = speed * dt
    local cp, sp, cy, sy = math.cos(FREE.pitch), math.sin(FREE.pitch), math.cos(FREE.yaw), math.sin(FREE.yaw)
    local dx, dy, dz = sy * cp, cy * cp, sp                  -- looking direction (yaw 0 = north)
    local rx, ry = cy, -sy                                    -- right
    local mx, my, mz = 0, 0, 0
    if getKeyState("w") then mx, my, mz = mx + dx, my + dy, mz + dz end
    if getKeyState("s") then mx, my, mz = mx - dx, my - dy, mz - dz end
    if getKeyState("d") then mx, my = mx + rx, my + ry end
    if getKeyState("a") then mx, my = mx - rx, my - ry end
    if getKeyState("space") then mz = mz + 1 end
    if getKeyState("c") then mz = mz - 1 end
    FREE.x, FREE.y, FREE.z = FREE.x + mx * speed, FREE.y + my * speed, FREE.z + mz * speed
    setCameraMatrix(FREE.x, FREE.y, FREE.z, FREE.x + dx * 50, FREE.y + dy * 50, FREE.z + dz * 50, 0, FOV)
end

function NC.stopFree()
    if not FREE.on then return false end
    FREE.on = false
    removeEventHandler("onClientPreRender", root, freeFrame)
    removeEventHandler("onClientCursorMove", root, freeMouse)
    setCameraTarget(localPlayer)
    releasePlayer(FREE)
    return true
end

local function startFree()
    if not NC.isShown() then NC.say("the city is not shown (/ncshow).") return end
    if TOUR.on then NC.stopTour() end
    holdPlayer(FREE)
    local cx, cy, cz, lx, ly, lz = getCameraMatrix()
    local dx, dy, dz = lx - cx, ly - cy, lz - cz
    local len = math.sqrt(dx * dx + dy * dy + dz * dz)
    if len < 1e-6 then dx, dy, dz, len = 0, 1, 0, 1 end
    FREE.x, FREE.y, FREE.z = cx, cy, cz
    FREE.yaw = math.atan2(dx, dy)
    FREE.pitch = math.asin(NC.clamp(dz / len, -1, 1))
    FREE.last = getTickCount()
    FREE.delay = 5
    FREE.on = true
    addEventHandler("onClientPreRender", root, freeFrame)
    addEventHandler("onClientCursorMove", root, freeMouse)
    NC.say("free camera - W A S D + mouse, Space up, C down, Shift fast, Ctrl slow.  /ncfree again leaves it.")
end

addCommandHandler("ncfree", function()
    if FREE.on then NC.stopFree() NC.say("free camera off.") else startFree() end
end)

-- the camera must come back whenever the city goes away
local previousOnHide = NC.onHide
NC.onHide = function()
    if previousOnHide then previousOnHide() end
    NC.stopTour()
    NC.stopFree()
end

addEventHandler("onClientResourceStop", resourceRoot, function()
    NC.stopTour()
    NC.stopFree()
end)
