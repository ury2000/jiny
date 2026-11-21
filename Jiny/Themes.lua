local ADDON, ns = ...

local Themes = {}
ns.Themes = Themes

Themes.default = "ParchmentLight"

local function clamp01(value, fallback)
    if type(value) ~= "number" then
        return fallback
    end
    if value < 0 then
        return 0
    end
    if value > 1 then
        return 1
    end
    return value
end

Themes.registry = {
    ParchmentLight = {
        bg = { 0.910, 0.835, 0.659, 0.97 },
        border = { 0.486, 0.325, 0.161, 1 },
        headerBg = { 0.851, 0.753, 0.549, 0.98 },
        title = { 0.290, 0.145, 0.031, 1 },
        text = { 0.227, 0.141, 0.063, 1 },
        muted = { 0.420, 0.267, 0.137, 1 },
        jinyLabel = { 0.118, 0.227, 0.541, 1 },
        userLabel = { 0.486, 0.176, 0.071, 1 },
        inputBg = { 0.973, 0.937, 0.847, 1 },
        inputBorder = { 0.624, 0.478, 0.278, 1 },
        inputText = { 0.169, 0.094, 0.031, 1 },
        buttonBg = { 0.486, 0.247, 0.086, 1 },
        buttonBorder = { 0.290, 0.145, 0.031, 1 },
        buttonText = { 1, 0.957, 0.824, 1 },
        buttonHover = { 0.580, 0.302, 0.118, 1 },
        edgeSize = 2,
    },
    DarkGlass = {
        bg = { 0.063, 0.078, 0.122, 0.92 },
        border = { 0.353, 0.420, 0.549, 1 },
        headerBg = { 0.043, 0.055, 0.094, 0.95 },
        title = { 1, 0.820, 0, 1 },
        text = { 1, 0.957, 0.824, 1 },
        muted = { 0.580, 0.639, 0.722, 1 },
        jinyLabel = { 0.412, 0.800, 0.941, 1 },
        userLabel = { 0.576, 0.773, 0.992, 1 },
        inputBg = { 0.027, 0.039, 0.071, 0.9 },
        inputBorder = { 0.220, 0.275, 0.380, 1 },
        inputText = { 1, 0.957, 0.824, 1 },
        buttonBg = { 0.145, 0.388, 0.922, 1 },
        buttonBorder = { 0.231, 0.510, 0.965, 1 },
        buttonText = { 1, 1, 1, 1 },
        buttonHover = { 0.231, 0.510, 0.965, 1 },
        edgeSize = 1,
    },
}

function Themes:Get(name)
    if name and self.registry[name] then
        return self.registry[name]
    end
    return self.registry[self.default]
end

function Themes.Hex(colorTbl)
    if type(colorTbl) ~= "table" then
        return "ffffffff"
    end
    local rRaw = colorTbl[1] ~= nil and colorTbl[1] or colorTbl.r
    local gRaw = colorTbl[2] ~= nil and colorTbl[2] or colorTbl.g
    local bRaw = colorTbl[3] ~= nil and colorTbl[3] or colorTbl.b
    local r = clamp01(rRaw, 1)
    local g = clamp01(gRaw, 1)
    local b = clamp01(bRaw, 1)
    return string.format(
        "ff%02x%02x%02x",
        math.floor(r * 255 + 0.5),
        math.floor(g * 255 + 0.5),
        math.floor(b * 255 + 0.5)
    )
end
