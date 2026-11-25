local ADDON, ns = ...

local MAX_HISTORY = 50

local DB_DEFAULTS = {
    dbVersion = 1,
    locale = "auto",
    theme = "ParchmentLight",
    point = nil,
    size = { 420, 300 },
    scale = 1.0,
    shown = false,
    mode = "companion",
    outbox = {},
    processedIds = {},
    history = {},
}

local LANG_MAP = {
    auto = "auto",
    en = "enUS",
    enus = "enUS",
    es = "esES",
    eses = "esES",
    esmx = "esES",
    it = "itIT",
    itit = "itIT",
}

local function Trim(str)
    if type(str) ~= "string" then
        return ""
    end
    return (str:gsub("^%s+", ""):gsub("%s+$", ""))
end

local function CopyTable(src)
    local out = {}
    for k, v in pairs(src) do
        if type(v) == "table" then
            out[k] = CopyTable(v)
        else
            out[k] = v
        end
    end
    return out
end

local function MergeDefaults(dst, defaults)
    for k, v in pairs(defaults) do
        if dst[k] == nil then
            if type(v) == "table" then
                dst[k] = CopyTable(v)
            else
                dst[k] = v
            end
        elseif type(v) == "table" and type(dst[k]) ~= "table" then
            dst[k] = CopyTable(v)
        end
    end
end

local function PrintChat(text)
    if DEFAULT_CHAT_FRAME and DEFAULT_CHAT_FRAME.AddMessage then
        local label = (ns.L and ns.L.LABEL_JINY) or "Jiny"
        DEFAULT_CHAT_FRAME:AddMessage("|cff2b6cb0[" .. label .. "]|r " .. tostring(text or ""))
    end
end

function ns.AddHistory(who, text)
    if not ns.db then
        return
    end
    if type(ns.db.history) ~= "table" then
        ns.db.history = {}
    end
    table.insert(ns.db.history, {
        who = who,
        text = text,
        t = time(),
    })
    while #ns.db.history > MAX_HISTORY do
        table.remove(ns.db.history, 1)
    end
end

local function RemoveOutboxId(reqId)
    if not ns.db or type(ns.db.outbox) ~= "table" then
        return
    end
    for i = #ns.db.outbox, 1, -1 do
        local entry = ns.db.outbox[i]
        if type(entry) == "table" and entry.id == reqId then
            table.remove(ns.db.outbox, i)
        end
    end
end

function ns.IngestCompanionReplies()
    if not ns.db or not ns.CompanionData or type(ns.CompanionData.replies) ~= "table" then
        return
    end
    if type(ns.db.processedIds) ~= "table" then
        ns.db.processedIds = {}
    end

    -- Limpiar consultas de outbox que hayan quedado huerfanas (mas de 5 min)
    if type(ns.db.outbox) == "table" then
        local now = time()
        for i = #ns.db.outbox, 1, -1 do
            local outItem = ns.db.outbox[i]
            if type(outItem) == "table" and outItem.t and (now - outItem.t) > 300 then
                table.remove(ns.db.outbox, i)
            end
        end
    end

    local importedAny = false
    for _, item in ipairs(ns.CompanionData.replies) do
        if type(item) == "table" and item.id and item.a and not ns.db.processedIds[item.id] then
            if item.q and tostring(item.q) ~= "" then
                ns.AddHistory("user", tostring(item.q))
            end
            ns.AddHistory("jiny", tostring(item.a))
            ns.db.processedIds[item.id] = true
            RemoveOutboxId(item.id)
            importedAny = true
        end
    end

    if importedAny and ns.UI and type(ns.UI.RenderHistory) == "function" and ns.UI.frame then
        ns.UI:RenderHistory()
        if type(ns.UI.UpdateStatus) == "function" then
            ns.UI:UpdateStatus()
        end
    end
end

function ns.SyncCompanion()
    if ns.db and ns.UI and ns.UI.frame and ns.UI.frame:IsShown() then
        ns.db.shown = true
    end
    if type(ReloadUI) == "function" then
        ReloadUI()
    end
end

local eventFrame = CreateFrame("Frame")
eventFrame:RegisterEvent("ADDON_LOADED")
eventFrame:RegisterEvent("PLAYER_LOGIN")
eventFrame:RegisterEvent("PLAYER_ENTERING_WORLD")
eventFrame:SetScript("OnEvent", function(_, event, arg1)
    if event == "ADDON_LOADED" and arg1 == ADDON then
        JinyDB = JinyDB or {}
        MergeDefaults(JinyDB, DB_DEFAULTS)
        ns.db = JinyDB
        if ns.Themes and type(ns.Themes.Resolve) == "function" then
            ns.db.theme = ns.Themes:Resolve(ns.db.theme) or ns.Themes.default or "ParchmentLight"
        elseif type(ns.db.theme) ~= "string" or ns.db.theme == "" then
            ns.db.theme = "ParchmentLight"
        end
        if ns.Locale and type(ns.Locale.Set) == "function" then
            ns.Locale.Set(ns.db.locale)
        end
    elseif event == "PLAYER_LOGIN" then
        ns.IngestCompanionReplies()
        if ns.Transport and type(ns.Transport.Init) == "function" then
            ns.Transport:Init()
        end
        if ns.UI and type(ns.UI.Create) == "function" then
            ns.UI:Create()
            if ns.db and ns.db.shown then
                ns.UI:Show()
            end
        end
    elseif event == "PLAYER_ENTERING_WORLD" then
        if ns.Transport and type(ns.Transport.Init) == "function" then
            ns.Transport:Init()
        end
    end
end)

SLASH_JINY1 = "/jiny"
SlashCmdList["JINY"] = function(msg)
    local trimmed = Trim(msg)
    if trimmed == "" then
        ns.UI:Toggle()
        return
    end

    local cmd, rest = trimmed:match("^(%S+)%s*(.*)$")
    local lowerCmd = cmd and cmd:lower() or ""

    if lowerCmd == "help" then
        PrintChat(ns.L.HELP_HEADER)
        PrintChat(ns.L.HELP_TOGGLE)
        PrintChat(ns.L.HELP_ASK)
        PrintChat(ns.L.HELP_LANG)
        PrintChat(ns.L.HELP_THEME)
        PrintChat(ns.L.HELP_SCALE)
        PrintChat(ns.L.HELP_SYNC)
        PrintChat(ns.L.HELP_MODE)
        PrintChat(ns.L.HELP_RESET)
        PrintChat(ns.L.HELP_CLEAR)
    elseif lowerCmd == "sync" then
        ns.SyncCompanion()
    elseif lowerCmd == "mode" then
        local arg = Trim(rest):lower()
        if arg == "companion" or arg == "mock" then
            if ns.db then
                ns.db.mode = arg
            end
            if ns.Transport and type(ns.Transport.Init) == "function" then
                ns.Transport:Init()
            end
            if ns.UI and type(ns.UI.UpdateStatus) == "function" then
                ns.UI:UpdateStatus()
            end
            local changedMsg = ns.L.MODE_CHANGED:format(arg)
            PrintChat(changedMsg)
            if ns.UI.frame and ns.UI.frame:IsShown() then
                ns.UI:AddMessage("system", changedMsg)
            end
        else
            PrintChat(ns.L.HELP_MODE)
        end
    elseif lowerCmd == "lang" then
        local arg = Trim(rest):lower()
        local mapped = LANG_MAP[arg]
        if mapped then
            if ns.Locale and type(ns.Locale.Set) == "function" then
                ns.Locale.Set(mapped)
            elseif ns.db then
                ns.db.locale = mapped
            end
            ns.UI:Refresh()
            local changedMsg = ns.L.LANG_CHANGED:format(ns.L["LANG_" .. mapped])
            PrintChat(changedMsg)
            if ns.UI.frame and ns.UI.frame:IsShown() then
                ns.UI:AddMessage("system", changedMsg)
            end
        else
            PrintChat(ns.L.HELP_LANG)
        end
    elseif lowerCmd == "theme" then
        local arg = Trim(rest):lower()
        local targetTheme = nil
        if arg == "toggle" then
            if ns.Themes and type(ns.Themes.Next) == "function" then
                targetTheme = ns.Themes:Next(ns.db and ns.db.theme)
            else
                local cur = (ns.db and ns.db.theme) or "ParchmentLight"
                targetTheme = (cur == "DarkGlass") and "ParchmentLight" or "DarkGlass"
            end
        elseif ns.Themes and type(ns.Themes.Resolve) == "function" then
            targetTheme = ns.Themes:Resolve(arg)
        end

        if targetTheme then
            if ns.UI and type(ns.UI.SetTheme) == "function" then
                targetTheme = ns.UI:SetTheme(targetTheme) or targetTheme
            elseif ns.db then
                ns.db.theme = targetTheme
            end
            local themeLabel = (ns.L and ns.L["THEME_" .. targetTheme]) or targetTheme
            local changedMsg = ns.L.THEME_CHANGED:format(themeLabel)
            PrintChat(changedMsg)
            if ns.UI and ns.UI.frame and ns.UI.frame:IsShown() then
                ns.UI:AddMessage("system", changedMsg)
            end
        else
            PrintChat(ns.L.HELP_THEME)
        end
    elseif lowerCmd == "scale" then
        local arg = Trim(rest):lower()
        if arg == "reset" then
            if ns.UI and type(ns.UI.SetScale) == "function" then
                ns.UI:SetScale(1.0)
            elseif ns.db then
                ns.db.scale = 1.0
            end
            PrintChat(ns.L.SCALE_RESET)
            if ns.UI.frame and ns.UI.frame:IsShown() then
                ns.UI:AddMessage("system", ns.L.SCALE_RESET)
            end
        else
            local num = tonumber(arg)
            if num and num >= 0.65 and num <= 2.5 then
                if ns.UI and type(ns.UI.SetScale) == "function" then
                    ns.UI:SetScale(num)
                elseif ns.db then
                    ns.db.scale = num
                end
                local changedMsg = ns.L.SCALE_CHANGED:format(string.format("%.2f", num))
                PrintChat(changedMsg)
                if ns.UI.frame and ns.UI.frame:IsShown() then
                    ns.UI:AddMessage("system", changedMsg)
                end
            else
                PrintChat(ns.L.HELP_SCALE)
            end
        end
    elseif lowerCmd == "reset" then
        ns.UI:ResetPosition()
        PrintChat(ns.L.POSITION_RESET)
        if ns.UI.frame and ns.UI.frame:IsShown() then
            ns.UI:AddMessage("system", ns.L.POSITION_RESET)
        end
    elseif lowerCmd == "clear" then
        if ns.db then
            ns.db.history = {}
            ns.db.outbox = {}
        end
        ns.UI:Clear()
        ns.UI:UpdateStatus()
        PrintChat(ns.L.HISTORY_CLEARED)
        if ns.UI.frame and ns.UI.frame:IsShown() then
            ns.UI:AddMessage("system", ns.L.HISTORY_CLEARED)
        end
    else
        PrintChat("⚡ Transmitiendo a Jiny Desktop en tiempo real...")
        ns.UI:Show()
        ns.UI:Ask(trimmed)
    end
end
