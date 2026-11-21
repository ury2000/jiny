local ADDON, ns = ...

local Locale = {}
local tables = {}

Locale.order = { "auto", "enUS", "esES", "itIT" }

function Locale.Register(code, tbl)
    if type(code) ~= "string" or type(tbl) ~= "table" then
        return
    end
    tables[code] = tbl
end

function Locale.Resolve(setting)
    if setting == "enUS" or setting == "esES" or setting == "itIT" then
        return setting
    end
    local gameLocale = type(GetLocale) == "function" and GetLocale() or "enUS"
    if gameLocale == "esES" or gameLocale == "esMX" then
        return "esES"
    elseif gameLocale == "itIT" then
        return "itIT"
    end
    return "enUS"
end

Locale.current = Locale.Resolve("auto")

local function ResolveKey(_, key)
    local active = tables[Locale.current]
    if active and active[key] ~= nil then
        return active[key]
    end
    local fallback = tables["enUS"]
    if fallback and fallback[key] ~= nil then
        return fallback[key]
    end
    return key
end

ns.L = setmetatable({}, {
    __index = ResolveKey,
})

function Locale.Set(setting)
    local chosen = setting
    if chosen ~= "auto" and chosen ~= "enUS" and chosen ~= "esES" and chosen ~= "itIT" then
        chosen = "auto"
    end
    if ns.db then
        ns.db.locale = chosen
    end
    Locale.current = Locale.Resolve(chosen)
    local mt = getmetatable(ns.L)
    if mt then
        mt.__index = ResolveKey
    end
    return Locale.current
end

ns.Locale = Locale
