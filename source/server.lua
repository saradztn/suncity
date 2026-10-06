-- Created by: Arena.ai Agent Mode (AI) - NightCity MTA:SA resource
-- ---------------------------------------------------------------------------------------------
-- server.lua - /ncshow drops the whole city high above the map (or /ncshow here on the ground where you stand) and puts you at the
--              spawn point; /nchide removes it; /ncz <m> trims the height; /ncempty keeps vehicles and peds out of it.
--              The city itself (models, objects, water, sounds, shaders) is created client side, see client.lua.
-- ---------------------------------------------------------------------------------------------
local CFG = {
    ADMIN_ONLY = false,
    SKY = { x = 0.0, y = 0.0, z = 900.0 },        -- default anchor: high above the map, so no vanilla terrain, tree or building can touch the city
    SAFE = { 2495.0, -1688.0, 14.0 },             -- where players are sent when the sky city is removed (Grove Street)
    GUARD_MS = 2000,
}
local city = nil            -- { zoff, ax, ay, az }   world position of the city origin
local guard = nil           -- timer of /ncempty

addEvent("nc:request", true)

local function allowed(player)
    if not CFG.ADMIN_ONLY then return true end
    local acc = getPlayerAccount(player)
    if not acc or isGuestAccount(acc) then return false end
    return isObjectInACLGroup("user." .. getAccountName(acc), aclGetGroup("Admin")) and true or false
end

local function sendState(target)
    if city then
        triggerClientEvent(target, "nc:show", resourceRoot, city.zoff, city.ax, city.ay, city.az)
    else
        triggerClientEvent(target, "nc:hide", resourceRoot)
    end
end

-- /ncshow            city high above the map (default, always works, nothing can poke through it)
-- /ncshow here       city on the ground exactly where you stand (use it on flat ground)
-- /ncshow x y z      city origin (street level at its centre) at the given world position
addCommandHandler("ncshow", function(player, _, a1, a2, a3)
    if not allowed(player) then outputChatBox("NightCity: you are not allowed to use this command.", player, 255, 80, 80) return end
    local P = NC_POINTS.spawn
    local ax, ay, az
    local tele = true
    if a1 == "here" then
        local px, py, pz = getElementPosition(player)
        ax, ay, az = px - P[1], py - P[2], pz - P[3]
        tele = false
    elseif tonumber(a1) and tonumber(a2) and tonumber(a3) then
        ax, ay, az = tonumber(a1), tonumber(a2), tonumber(a3)
    else
        ax, ay, az = CFG.SKY.x, CFG.SKY.y, CFG.SKY.z
    end
    city = { zoff = 0, ax = ax, ay = ay, az = az }
    if tele then      -- the spawn point of layout.lua; the client holds the player until the ground collision exists
        setElementPosition(player, ax + P[1], ay + P[2], az + P[3] + 1.0)
        setElementRotation(player, 0, 0, 0)
    end
    sendState(root)
    outputChatBox("Welcome to NightCity.  /nchide removes it, /ncz <m> adjusts the height, /nctour and /ncfree for the camera, /ncfx graphics.", player, 120, 220, 255)
    for _, other in ipairs(getElementsByType("player")) do
        if other ~= player then outputChatBox("NightCity is open: /ncview spawn takes you there.", other, 120, 220, 255) end
    end
end)

addCommandHandler("nchide", function(player)
    if not allowed(player) then outputChatBox("NightCity: you are not allowed to use this command.", player, 255, 80, 80) return end
    if city and city.az > 300 then    -- sky city: nobody may fall 900 m when the ground disappears
        for _, p in ipairs(getElementsByType("player")) do
            local x, y, z = getElementPosition(p)
            if z > 300 and math.abs(x - city.ax) < 900 and math.abs(y - city.ay) < 900 then
                setElementPosition(p, CFG.SAFE[1], CFG.SAFE[2], CFG.SAFE[3])
            end
        end
    end
    city = nil
    sendState(root)
    outputChatBox("NightCity removed.", player, 230, 200, 120)
end)

addCommandHandler("ncz", function(player, _, dz)
    if not allowed(player) then return end
    dz = tonumber(dz)
    if not city or not dz then outputChatBox("Usage: /ncz <metres, e.g. 0.5 or -0.3>  (the city must be shown)", player, 230, 200, 120) return end
    dz = math.max(-8, math.min(8, dz))
    city.zoff = city.zoff + dz
    triggerClientEvent(root, "nc:zoff", resourceRoot, dz)
end)

-- /ncempty on | off | now : the city has no people, vehicles or animals of its own; this keeps it that way when other resources spawn some
local function sweep()
    if not city then return 0 end
    local n = 0
    for _, kind in ipairs({ "vehicle", "ped" }) do
        for _, e in ipairs(getElementsByType(kind)) do
            local x, y, z = getElementPosition(e)
            if math.abs(x - city.ax) < 800 and math.abs(y - city.ay) < 900 and z > city.az - 60 and z < city.az + 500 then
                destroyElement(e)
                n = n + 1
            end
        end
    end
    return n
end

addCommandHandler("ncempty", function(player, _, mode)
    if not allowed(player) then return end
    if mode == "on" then
        if guard and isTimer(guard) then killTimer(guard) end
        guard = setTimer(sweep, CFG.GUARD_MS, 0)
        outputChatBox("NightCity: vehicles and peds are removed from the city volume (/ncempty off to stop).", player, 120, 220, 255)
    elseif mode == "off" then
        if guard and isTimer(guard) then killTimer(guard) end
        guard = nil
        outputChatBox("NightCity: guard off.", player, 230, 200, 120)
    else
        outputChatBox("NightCity: removed " .. sweep() .. " vehicles / peds.  Usage: /ncempty on | off | now", player, 120, 220, 255)
    end
end)

addEventHandler("nc:request", resourceRoot, function()
    if client then sendState(client) end
end)

addEventHandler("onResourceStop", resourceRoot, function()
    if guard and isTimer(guard) then killTimer(guard) end
    guard = nil
    if city and city.az > 300 then
        for _, p in ipairs(getElementsByType("player")) do
            local x, y, z = getElementPosition(p)
            if z > 300 and math.abs(x - city.ax) < 900 and math.abs(y - city.ay) < 900 then
                setElementPosition(p, CFG.SAFE[1], CFG.SAFE[2], CFG.SAFE[3])
            end
        end
    end
end)
