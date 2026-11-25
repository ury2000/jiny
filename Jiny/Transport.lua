local ADDON, ns = ...

local Transport = {}
ns.Transport = Transport

local MAX_OUTBOX = 20
local filtersInstalled = false
local flushFrame = nil
local lastWhisperTarget = nil
local lastWhisperTime = 0

local function GetActiveLocale()
    if ns.Locale and ns.Locale.current then
        return ns.Locale.current
    end
    return "enUS"
end

local function GetPlayerWhisperTarget()
    -- En Classic Era nos susurramos siempre al nombre directo del jugador (sin espacios de reino)
    if type(UnitName) == "function" then
        local name = UnitName("player")
        if name and name ~= "" and name ~= UNKNOWNOBJECT then
            return name
        end
    end
    if type(UnitFullName) == "function" then
        local name, realm = UnitFullName("player")
        if name and name ~= "" then
            if realm and realm ~= "" then
                return name .. "-" .. realm:gsub("%s+", "")
            end
            return name
        end
    end
    return nil
end

local function EnableChatLogging()
    if type(LoggingChat) == "function" then
        if not LoggingChat() then
            LoggingChat(true)
        end
    end
end

local function FlushChatLog()
    if type(LoggingChat) == "function" then
        pcall(LoggingChat, false)
        pcall(LoggingChat, true)
    end
end

local function WhisperFilter(_, _, msg)
    if type(msg) == "string" and msg:find("[JINY_Q#", 1, true) then
        return true
    end
    return false
end

local function SystemFilter(_, _, msg)
    if type(msg) == "string" and lastWhisperTarget and (time() - lastWhisperTime) <= 2 then
        local rawShortName = lastWhisperTarget:match("^([^-]+)") or lastWhisperTarget
        if msg:find(lastWhisperTarget, 1, true) or msg:find(rawShortName, 1, true) then
            return true
        end
    end
    return false
end

function Transport:Init()
    if not filtersInstalled then
        local addFilter = (ChatFrameUtil and ChatFrameUtil.AddMessageEventFilter)
            or ChatFrame_AddMessageEventFilter
        if type(addFilter) == "function" then
            addFilter("CHAT_MSG_WHISPER", WhisperFilter)
            addFilter("CHAT_MSG_WHISPER_INFORM", WhisperFilter)
            addFilter("CHAT_MSG_SYSTEM", SystemFilter)
        end
        if not flushFrame and type(CreateFrame) == "function" then
            flushFrame = CreateFrame("Frame")
            flushFrame:RegisterEvent("CHAT_MSG_WHISPER_INFORM")
            flushFrame:SetScript("OnEvent", function(_, _, msg)
                if type(msg) == "string" and msg:find("[JINY_Q#", 1, true) then
                    if C_Timer and type(C_Timer.After) == "function" then
                        C_Timer.After(0.05, FlushChatLog)
                    else
                        FlushChatLog()
                    end
                end
            end)
        end
        filtersInstalled = true
    end

    if ns.db and ns.db.mode == "companion" then
        EnableChatLogging()
    end
end

function Transport.Send(question, callback)
    local mode = (ns.db and ns.db.mode) or "companion"
    if mode == "mock" then
        if ns.Mock and type(ns.Mock.Reply) == "function" then
            ns.Mock:Reply(question, callback)
        end
        return
    end

    local lang = GetActiveLocale()
    local reqId = string.format("%d-%d", time(), math.random(1000, 9999))

    if ns.db then
        if type(ns.db.outbox) ~= "table" then
            ns.db.outbox = {}
        end
        table.insert(ns.db.outbox, {
            id = reqId,
            q = tostring(question or ""),
            lang = lang,
            t = time(),
        })
        while #ns.db.outbox > MAX_OUTBOX do
            table.remove(ns.db.outbox, 1)
        end
    end

    EnableChatLogging()

    local playerName = GetPlayerWhisperTarget()
    local sendChat = (C_ChatInfo and C_ChatInfo.SendChatMessage) or SendChatMessage
    if type(sendChat) == "function" and playerName and playerName ~= "" then
        lastWhisperTarget = playerName
        lastWhisperTime = time()
        local payload = string.format("[JINY_Q#%s#%s] %s", reqId, lang, tostring(question or ""))
        pcall(sendChat, payload, "WHISPER", nil, playerName)
        -- Flush immediately so WoWChatLog.txt on disk receives the line with zero lag
        FlushChatLog()
    end

    if type(callback) == "function" then
        callback(nil, { queued = true, id = reqId })
    end
end
