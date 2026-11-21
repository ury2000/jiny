local ADDON, ns = ...

local UI = {}
ns.UI = UI

local FRAME_NAME = "JinyMainFrame"
local DEFAULT_WIDTH = 420
local DEFAULT_HEIGHT = 300
local MIN_WIDTH = 320
local MIN_HEIGHT = 200
local MAX_WIDTH = 900
local MAX_HEIGHT = 700
local DEFAULT_SCALE = 1.0
local MIN_SCALE = 0.65
local MAX_SCALE = 2.5
local WHITE8X8 = "Interface\\Buttons\\WHITE8X8"
local ICON_PATH = "Interface\\AddOns\\Jiny\\Assets\\JinyIcon"

local function GetJinyFonts()
    if not UI.historyFont then
        local baseFont = GameFontNormal:GetFont() or "Fonts\\FRIZQT__.TTF"

        local hFont = CreateFont("JinyHistoryFont")
        hFont:SetFont(baseFont, 14, "")
        hFont:SetShadowOffset(1, -1)
        hFont:SetShadowColor(0, 0, 0, 0.22)
        if hFont.SetSpacing then
            hFont:SetSpacing(3)
        end
        UI.historyFont = hFont

        local iFont = CreateFont("JinyInputFont")
        iFont:SetFont(baseFont, 14, "")
        iFont:SetShadowOffset(1, -1)
        iFont:SetShadowColor(0, 0, 0, 0.15)
        UI.inputFont = iFont
    end
    return UI.historyFont, UI.inputFont
end

local FALLBACK_THEME = {
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
}

local function Trim(str)
    if type(str) ~= "string" then
        return ""
    end
    return (str:gsub("^%s+", ""):gsub("%s+$", ""))
end

local function GetTheme()
    if ns.Themes and type(ns.Themes.Get) == "function" then
        local t = ns.Themes:Get(ns.db and ns.db.theme)
        if type(t) == "table" then
            return t
        end
    end
    return FALLBACK_THEME
end

local function UnpackRGB(color, dr, dg, db)
    if type(color) ~= "table" then
        return dr or 1, dg or 1, db or 1
    end
    local r = color.r ~= nil and color.r or color[1]
    local g = color.g ~= nil and color.g or color[2]
    local b = color.b ~= nil and color.b or color[3]
    return r or dr or 1, g or dg or 1, b or db or 1
end

local function UnpackRGBA(color, dr, dg, db, da)
    local r, g, b = UnpackRGB(color, dr, dg, db)
    local a = da ~= nil and da or 1
    if type(color) == "table" then
        if color.a ~= nil then
            a = color.a
        elseif color[4] ~= nil then
            a = color[4]
        end
    end
    return r, g, b, a
end

local function ColorHex(color)
    if ns.Themes and type(ns.Themes.Hex) == "function" then
        return ns.Themes.Hex(color)
    end
    local r, g, b = UnpackRGB(color, 1, 1, 1)
    return string.format(
        "ff%02x%02x%02x",
        math.floor(r * 255 + 0.5),
        math.floor(g * 255 + 0.5),
        math.floor(b * 255 + 0.5)
    )
end

local function ApplyBackdrop(frame, bgColor, borderColor, edgeSize)
    if not frame or not frame.SetBackdrop then
        return
    end
    local edge = edgeSize or 2
    frame:SetBackdrop({
        bgFile = WHITE8X8,
        edgeFile = WHITE8X8,
        edgeSize = edge,
        insets = { left = edge, right = edge, top = edge, bottom = edge },
    })
    frame:SetBackdropColor(UnpackRGBA(bgColor, 0, 0, 0, 1))
    frame:SetBackdropBorderColor(UnpackRGBA(borderColor, 0.5, 0.5, 0.5, 1))
end

local function RegisterSpecialFrame(name)
    if type(UISpecialFrames) ~= "table" then
        return
    end
    for _, existing in ipairs(UISpecialFrames) do
        if existing == name then
            return
        end
    end
    tinsert(UISpecialFrames, name)
end

local function SaveGeometry(frame)
    if not ns.db or not frame then
        return
    end
    local point, _, relativePoint, x, y = frame:GetPoint(1)
    if point and relativePoint then
        ns.db.point = {
            point,
            relativePoint,
            math.floor((x or 0) + 0.5),
            math.floor((y or 0) + 0.5),
        }
    end
    local w, h = frame:GetSize()
    if w and h then
        ns.db.size = {
            math.floor(w + 0.5),
            math.floor(h + 0.5),
        }
    end
    local scale = frame:GetScale()
    if scale then
        ns.db.scale = math.floor(scale * 100 + 0.5) / 100
    end
end

local function CreateHandButton(parent, fontObject, onClick)
    local btn = CreateFrame("Button", nil, parent, "BackdropTemplate")
    btn.label = btn:CreateFontString(nil, "OVERLAY", fontObject or "GameFontNormalSmall")
    btn.label:SetPoint("CENTER", 0, 0)
    btn.label:SetJustifyH("CENTER")
    btn.isHovered = false

    btn:SetScript("OnEnter", function(self)
        self.isHovered = true
        local t = GetTheme()
        local hover = t.buttonHover or FALLBACK_THEME.buttonHover
        self:SetBackdropColor(UnpackRGBA(hover, 0.58, 0.30, 0.12, 1))
    end)

    btn:SetScript("OnLeave", function(self)
        self.isHovered = false
        local t = GetTheme()
        local bg = t.buttonBg or FALLBACK_THEME.buttonBg
        self:SetBackdropColor(UnpackRGBA(bg, 0.49, 0.25, 0.09, 1))
    end)

    btn:SetScript("OnMouseDown", function(self)
        self.label:SetPoint("CENTER", 1, -1)
    end)

    btn:SetScript("OnMouseUp", function(self)
        self.label:SetPoint("CENTER", 0, 0)
    end)

    btn:SetScript("OnClick", function(self)
        if type(onClick) == "function" then
            onClick(self)
        end
    end)

    return btn
end

-- Snippet storage and macro management
UI.macroSnippets = UI.macroSnippets or {}
local snippetSeq = 0
local function GenSnippetId()
    snippetSeq = snippetSeq + 1
    return tostring(time()) .. "_" .. tostring(snippetSeq)
end

local function FormatMacroBlock(name, body, sid)
    local out = {}
    local macroName = (name and name ~= "") and name or "Macro"
    table.insert(out, "|cffb8860b+--- [ |r|cffffd100" .. macroName .. "|r |cffb8860b] --------------------------------|r")
    table.insert(out, "|cffb8860b| |r|cff3b82f6|Hjinycopy:" .. sid .. "|h[" .. ns.L.BTN_COPY_MACRO .. "]|h|r   |cff10b981|Hjinymacro:" .. sid .. "|h[" .. ns.L.BTN_CREATE_MACRO .. "]|h|r")
    table.insert(out, "|cffb8860b+--------------------------------------------|r")
    for line in body:gmatch("([^\r\n]+)") do
        local trimmed = Trim(line)
        if trimmed ~= "" then
            table.insert(out, "|cffb8860b| |r |cffe6cc80" .. trimmed .. "|r")
        end
    end
    table.insert(out, "|cffb8860b+--------------------------------------------|r")
    return table.concat(out, "\n")
end

local function FormatCodeBlock(lang, body, sid, isMacro)
    local out = {}
    local blockTitle = (lang and lang ~= "") and lang:upper() or (isMacro and "MACRO" or "CODE")
    table.insert(out, "|cff718096+--- [ |r|cffa0aec0" .. blockTitle .. "|r |cff718096] --------------------------------|r")
    if isMacro then
        table.insert(out, "|cff718096| |r|cff3b82f6|Hjinycopy:" .. sid .. "|h[" .. ns.L.BTN_COPY_MACRO .. "]|h|r   |cff10b981|Hjinymacro:" .. sid .. "|h[" .. ns.L.BTN_CREATE_MACRO .. "]|h|r")
    else
        table.insert(out, "|cff718096| |r|cff3b82f6|Hjinycopy:" .. sid .. "|h[" .. ns.L.BTN_COPY_CODE .. "]|h|r")
    end
    table.insert(out, "|cff718096+--------------------------------------------|r")
    for line in body:gmatch("([^\r\n]+)") do
        local trimmed = Trim(line)
        if trimmed ~= "" then
            table.insert(out, "|cff718096| |r |cff81e6d9" .. trimmed .. "|r")
        end
    end
    table.insert(out, "|cff718096+--------------------------------------------|r")
    return table.concat(out, "\n")
end

local function LooksLikeMacro(str)
    if not str then return false end
    if str:find("#showtooltip") or str:find("/cast") or str:find("/use") or str:find("/cancelaura") or str:find("/target") or str:find("/petattack") then
        return true
    end
    return false
end

local function ProcessMessageContent(text)
    if type(text) ~= "string" or text == "" then
        return text
    end

    local processed = text
    local hasMatches = false

    -- 1. Explicit [JINY_MACRO name="..."]...[/JINY_MACRO]
    processed = processed:gsub("%[JINY_MACRO%s*name=\"([^\"]*)\"%]%s*(.-)%s*%[/JINY_MACRO%]", function(name, body)
        hasMatches = true
        local cleanBody = Trim(body)
        local sid = GenSnippetId()
        UI.macroSnippets[sid] = {
            name = (name ~= "" and name) or "Macro",
            body = cleanBody,
            isMacro = true,
        }
        return "\n" .. FormatMacroBlock(name, cleanBody, sid) .. "\n"
    end)

    -- [JINY_MACRO]...[/JINY_MACRO]
    processed = processed:gsub("%[JINY_MACRO%]%s*(.-)%s*%[/JINY_MACRO%]", function(body)
        hasMatches = true
        local cleanBody = Trim(body)
        local sid = GenSnippetId()
        UI.macroSnippets[sid] = {
            name = "Macro",
            body = cleanBody,
            isMacro = true,
        }
        return "\n" .. FormatMacroBlock("Macro", cleanBody, sid) .. "\n"
    end)

    -- 2. Markdown code blocks ```lang ... ```
    processed = processed:gsub("```([a-zA-Z0-9_-]*)\n*(.-)\n*```", function(lang, body)
        hasMatches = true
        local cleanBody = Trim(body)
        local isMacro = LooksLikeMacro(cleanBody)
        local sid = GenSnippetId()
        UI.macroSnippets[sid] = {
            name = isMacro and "Macro" or "Code",
            body = cleanBody,
            isMacro = isMacro,
        }
        if isMacro then
            return "\n" .. FormatMacroBlock("Macro", cleanBody, sid) .. "\n"
        else
            return "\n" .. FormatCodeBlock(lang, cleanBody, sid, false) .. "\n"
        end
    end)

    -- 3. Fallback: raw macro lines (#showtooltip, /cast, etc.)
    if not hasMatches and LooksLikeMacro(processed) then
        local lines = {}
        for line in (processed .. "\n"):gmatch("(.-)\r?\n") do
            table.insert(lines, line)
        end
        local macroBlock = {}
        local inMacro = false
        local finalLines = {}
        for _, l in ipairs(lines) do
            local trimmed = Trim(l)
            if trimmed:find("^#showtooltip") or trimmed:find("^/[a-zA-Z]") then
                inMacro = true
                table.insert(macroBlock, trimmed)
            else
                if inMacro and #macroBlock > 0 then
                    local body = table.concat(macroBlock, "\n")
                    local sid = GenSnippetId()
                    UI.macroSnippets[sid] = {
                        name = "Macro",
                        body = body,
                        isMacro = true,
                    }
                    table.insert(finalLines, FormatMacroBlock("Macro", body, sid))
                    macroBlock = {}
                    inMacro = false
                end
                table.insert(finalLines, l)
            end
        end
        if inMacro and #macroBlock > 0 then
            local body = table.concat(macroBlock, "\n")
            local sid = GenSnippetId()
            UI.macroSnippets[sid] = {
                name = "Macro",
                body = body,
                isMacro = true,
            }
            table.insert(finalLines, FormatMacroBlock("Macro", body, sid))
        end
        processed = table.concat(finalLines, "\n")
    end

    return processed
end

local COPY_DIALOG_NAME = "JinyCopyDialog"

function UI:GetOrCreateCopyDialog()
    if self.copyDialog then
        return self.copyDialog
    end

    local dialog = CreateFrame("Frame", COPY_DIALOG_NAME, UIParent, "BackdropTemplate")
    dialog:SetSize(400, 240)
    dialog:SetPoint("CENTER", UIParent, "CENTER", 0, 40)
    dialog:SetFrameStrata("FULLSCREEN_DIALOG")
    dialog:EnableMouse(true)
    dialog:SetMovable(true)
    dialog:SetClampedToScreen(true)
    dialog:RegisterForDrag("LeftButton")
    dialog:SetScript("OnDragStart", function(f) f:StartMoving() end)
    dialog:SetScript("OnDragStop", function(f) f:StopMovingOrSizing() end)

    RegisterSpecialFrame(COPY_DIALOG_NAME)

    local t = GetTheme()
    local edge = t.edgeSize or 2
    ApplyBackdrop(dialog, t.bg or FALLBACK_THEME.bg, t.border or FALLBACK_THEME.border, edge)

    -- Header
    local header = CreateFrame("Frame", nil, dialog, "BackdropTemplate")
    header:SetPoint("TOPLEFT", dialog, "TOPLEFT", 6, -6)
    header:SetPoint("TOPRIGHT", dialog, "TOPRIGHT", -6, -6)
    header:SetHeight(26)
    header:EnableMouse(true)
    header:RegisterForDrag("LeftButton")
    header:SetScript("OnDragStart", function() dialog:StartMoving() end)
    header:SetScript("OnDragStop", function() dialog:StopMovingOrSizing() end)
    ApplyBackdrop(header, t.headerBg or FALLBACK_THEME.headerBg, t.border or FALLBACK_THEME.border, edge)
    dialog.header = header

    local title = header:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    title:SetPoint("LEFT", header, "LEFT", 8, 0)
    title:SetText(ns.L.MACRO_DIALOG_TITLE)
    title:SetTextColor(UnpackRGB(t.title or FALLBACK_THEME.title, 0.29, 0.15, 0.03))
    dialog.title = title

    local closeBtn = CreateHandButton(header, "GameFontNormal", function()
        dialog:Hide()
    end)
    closeBtn:SetSize(20, 20)
    closeBtn:SetPoint("RIGHT", header, "RIGHT", -4, 0)
    closeBtn.label:SetText("x")
    ApplyBackdrop(closeBtn, t.buttonBg or FALLBACK_THEME.buttonBg, t.buttonBorder or FALLBACK_THEME.buttonBorder, edge)
    closeBtn.label:SetTextColor(UnpackRGB(t.buttonText or FALLBACK_THEME.buttonText, 1, 0.96, 0.82))
    dialog.closeBtn = closeBtn

    -- ScrollFrame + EditBox container
    local editContainer = CreateFrame("Frame", nil, dialog, "BackdropTemplate")
    editContainer:SetPoint("TOPLEFT", header, "BOTTOMLEFT", 0, -6)
    editContainer:SetPoint("BOTTOMRIGHT", dialog, "BOTTOMRIGHT", -6, 38)
    ApplyBackdrop(editContainer, t.inputBg or FALLBACK_THEME.inputBg, t.inputBorder or FALLBACK_THEME.inputBorder, edge)
    dialog.editContainer = editContainer

    local scrollFrame = CreateFrame("ScrollFrame", nil, editContainer)
    scrollFrame:SetPoint("TOPLEFT", editContainer, "TOPLEFT", 6, -6)
    scrollFrame:SetPoint("BOTTOMRIGHT", editContainer, "BOTTOMRIGHT", -6, 6)
    scrollFrame:EnableMouseWheel(true)
    scrollFrame:SetScript("OnMouseWheel", function(sf, delta)
        local current = sf:GetVerticalScroll()
        local maxRange = sf:GetVerticalScrollRange()
        local newScroll = math.max(0, math.min(maxRange, current - (delta * 20)))
        sf:SetVerticalScroll(newScroll)
    end)
    dialog.scrollFrame = scrollFrame

    local _, inputFont = GetJinyFonts()
    local editBox = CreateFrame("EditBox", nil, scrollFrame)
    editBox:SetMultiLine(true)
    editBox:SetAutoFocus(false)
    editBox:SetFontObject(inputFont or "GameFontNormal")
    editBox:SetWidth(370)
    editBox:SetTextColor(UnpackRGB(t.inputText or FALLBACK_THEME.inputText, 0.17, 0.09, 0.03))
    editBox:SetScript("OnEscapePressed", function()
        dialog:Hide()
    end)
    scrollFrame:SetScrollChild(editBox)
    dialog.editBox = editBox

    -- Footer hint
    local hint = dialog:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
    hint:SetPoint("BOTTOMLEFT", dialog, "BOTTOMLEFT", 10, 10)
    hint:SetText(ns.L.MACRO_DIALOG_HINT)
    hint:SetTextColor(UnpackRGB(t.muted or FALLBACK_THEME.muted, 0.42, 0.27, 0.14))
    dialog.hint = hint

    -- Create Macro button
    local createBtn = CreateHandButton(dialog, "GameFontNormalSmall", function()
        if dialog.currentSnippetId then
            UI:CreateInGameMacro(dialog.currentSnippetId)
            dialog:Hide()
        end
    end)
    createBtn:SetHeight(22)
    createBtn:SetPoint("BOTTOMRIGHT", dialog, "BOTTOMRIGHT", -8, 8)
    createBtn.label:SetText(ns.L.BTN_CREATE_MACRO)
    createBtn:SetWidth(math.max(80, math.ceil(createBtn.label:GetStringWidth()) + 16))
    ApplyBackdrop(createBtn, t.buttonBg or FALLBACK_THEME.buttonBg, t.buttonBorder or FALLBACK_THEME.buttonBorder, edge)
    createBtn.label:SetTextColor(UnpackRGB(t.buttonText or FALLBACK_THEME.buttonText, 1, 0.96, 0.82))
    dialog.createBtn = createBtn

    self.copyDialog = dialog
    return dialog
end

function UI:OpenCopyDialog(snippetId)
    local snippet = self.macroSnippets and self.macroSnippets[snippetId]
    if not snippet or not snippet.body then
        return
    end

    local dialog = self:GetOrCreateCopyDialog()
    dialog.currentSnippetId = snippetId
    dialog.editBox:SetText(snippet.body)
    dialog:Show()
    dialog.editBox:SetFocus()
    dialog.editBox:HighlightText()

    if snippet.isMacro then
        dialog.createBtn:Show()
    else
        dialog.createBtn:Hide()
    end
end

function UI:CreateInGameMacro(snippetId)
    local snippet = self.macroSnippets and self.macroSnippets[snippetId]
    if not snippet or not snippet.body then
        return
    end

    if InCombatLockdown and InCombatLockdown() then
        self:AddMessage("system", "|cffff4444[" .. ns.L.LABEL_JINY .. "] " .. ns.L.MACRO_ERR_COMBAT .. "|r")
        return
    end

    local name = snippet.name or "JinyMacro"
    if #name > 16 then
        name = name:sub(1, 16)
    end
    local icon = 134400
    local body = snippet.body
    if #body > 255 then
        body = body:sub(1, 255)
    end

    local existingIndex = GetMacroIndexByName and GetMacroIndexByName(name)
    local macroIndex
    if existingIndex and existingIndex > 0 then
        if EditMacro then
            EditMacro(existingIndex, name, icon, body)
            macroIndex = existingIndex
            local msg = string.format(ns.L.MACRO_UPDATED, name)
            self:AddMessage("system", "|cff10b981[" .. ns.L.LABEL_JINY .. "] " .. msg .. "|r")
        end
    else
        local numGlobal, numChar = 0, 0
        if GetNumMacros then
            numGlobal, numChar = GetNumMacros()
        end
        if numGlobal >= 120 and numChar >= 18 then
            self:AddMessage("system", "|cffff4444[" .. ns.L.LABEL_JINY .. "] " .. ns.L.MACRO_ERR_FULL .. "|r")
            return
        end
        local isPerChar = (numGlobal >= 120)
        if CreateMacro then
            macroIndex = CreateMacro(name, icon, body, isPerChar)
        end
        if macroIndex and macroIndex > 0 then
            local msg = string.format(ns.L.MACRO_CREATED, name)
            self:AddMessage("system", "|cff10b981[" .. ns.L.LABEL_JINY .. "] " .. msg .. "|r")
        else
            self:AddMessage("system", "|cffff4444[" .. ns.L.LABEL_JINY .. "] " .. ns.L.MACRO_ERR_CREATE .. "|r")
        end
    end

    if macroIndex and macroIndex > 0 and PlaySound and SOUNDKIT and SOUNDKIT.IG_MAINMENU_OPEN then
        PlaySound(SOUNDKIT.IG_MAINMENU_OPEN)
    end
end

function UI:UpdateStatus()
    if not self.statusText then
        return
    end
    local t = GetTheme()
    if (self.pendingCount or 0) > 0 then
        self.statusText:SetText(ns.L.STATUS_MOCK)
        self.statusText:SetTextColor(UnpackRGB(t.jinyLabel or t.muted, 0.12, 0.23, 0.54))
    elseif ns.db and type(ns.db.outbox) == "table" and #ns.db.outbox > 0 then
        self.statusText:SetText(ns.L.STATUS_WAITING)
        self.statusText:SetTextColor(UnpackRGB(t.jinyLabel or t.muted, 0.12, 0.23, 0.54))
    else
        self.statusText:SetText(ns.L.STATUS_READY)
        self.statusText:SetTextColor(UnpackRGB(t.muted, 0.42, 0.27, 0.14))
    end
end

function UI:UpdatePlaceholder()
    if not self.editBox or not self.placeholderText then
        return
    end
    self.placeholderText:SetShown(self.editBox:GetText() == "")
end

function UI:Create()
    if self.frame then
        return self.frame
    end

    self.pendingCount = self.pendingCount or 0
    self.buttons = {}

    local frame = CreateFrame("Frame", FRAME_NAME, UIParent, "BackdropTemplate")
    self.frame = frame

    local w, h = DEFAULT_WIDTH, DEFAULT_HEIGHT
    if ns.db and type(ns.db.size) == "table" then
        w = tonumber(ns.db.size[1]) or DEFAULT_WIDTH
        h = tonumber(ns.db.size[2]) or DEFAULT_HEIGHT
    end
    w = math.max(MIN_WIDTH, math.min(MAX_WIDTH, w))
    h = math.max(MIN_HEIGHT, math.min(MAX_HEIGHT, h))
    frame:SetSize(w, h)

    local scale = DEFAULT_SCALE
    if ns.db and ns.db.scale then
        scale = tonumber(ns.db.scale) or DEFAULT_SCALE
    end
    scale = math.max(MIN_SCALE, math.min(MAX_SCALE, scale))
    frame:SetScale(scale)

    if ns.db and type(ns.db.point) == "table" and ns.db.point[1] then
        local pt = ns.db.point
        frame:SetPoint(pt[1], UIParent, pt[2] or pt[1], tonumber(pt[3]) or 0, tonumber(pt[4]) or 0)
    else
        frame:SetPoint("CENTER", UIParent, "CENTER", 0, 0)
    end

    frame:EnableMouse(true)
    frame:SetMovable(true)
    frame:SetResizable(true)
    frame:SetClampedToScreen(true)
    frame:SetFrameStrata("DIALOG")
    if frame.SetResizeBounds then
        frame:SetResizeBounds(MIN_WIDTH, MIN_HEIGHT, MAX_WIDTH, MAX_HEIGHT)
    else
        frame:SetMinResize(MIN_WIDTH, MIN_HEIGHT)
        frame:SetMaxResize(MAX_WIDTH, MAX_HEIGHT)
    end

    -- Hide before hooking OnHide so initial creation does not overwrite ns.db.shown
    frame:Hide()
    frame:SetScript("OnShow", function()
        if ns.db then
            ns.db.shown = true
        end
    end)
    frame:SetScript("OnHide", function()
        if ns.db and (not UIParent or UIParent:IsShown()) then
            ns.db.shown = false
        end
    end)

    RegisterSpecialFrame(FRAME_NAME)

    -- Header
    local header = CreateFrame("Frame", nil, frame, "BackdropTemplate")
    header:SetPoint("TOPLEFT", frame, "TOPLEFT", 8, -8)
    header:SetPoint("TOPRIGHT", frame, "TOPRIGHT", -8, -8)
    header:SetHeight(30)
    header:EnableMouse(true)
    header:RegisterForDrag("LeftButton")
    header:SetScript("OnDragStart", function()
        frame:StartMoving()
    end)
    header:SetScript("OnDragStop", function()
        frame:StopMovingOrSizing()
        SaveGeometry(frame)
    end)
    self.header = header

    local icon = header:CreateTexture(nil, "ARTWORK")
    icon:SetSize(18, 18)
    icon:SetPoint("LEFT", header, "LEFT", 8, 0)
    icon:SetTexture(ICON_PATH)
    self.icon = icon

    local closeBtn = CreateHandButton(header, "GameFontNormal", function()
        UI:Hide()
    end)
    closeBtn:SetSize(22, 22)
    closeBtn:SetPoint("RIGHT", header, "RIGHT", -5, 0)
    closeBtn.label:SetText("×")
    self.closeBtn = closeBtn
    table.insert(self.buttons, closeBtn)

    local titleText = header:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    titleText:SetPoint("LEFT", icon, "RIGHT", 6, 0)
    titleText:SetJustifyH("LEFT")
    self.titleText = titleText

    local statusText = header:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
    statusText:SetPoint("LEFT", titleText, "RIGHT", 8, 0)
    statusText:SetPoint("RIGHT", closeBtn, "LEFT", -8, 0)
    statusText:SetJustifyH("RIGHT")
    statusText:SetWordWrap(false)
    self.statusText = statusText

    -- Footer
    local footer = CreateFrame("Frame", nil, frame)
    footer:SetPoint("BOTTOMLEFT", frame, "BOTTOMLEFT", 8, 8)
    footer:SetPoint("BOTTOMRIGHT", frame, "BOTTOMRIGHT", -8, 8)
    footer:SetHeight(24)
    self.footer = footer

    local clearBtn = CreateHandButton(footer, "GameFontNormalSmall", function()
        if ns.db then
            ns.db.history = {}
            ns.db.outbox = {}
        end
        UI:Clear()
        UI:UpdateStatus()
        UI:AddMessage("system", ns.L.HISTORY_CLEARED)
    end)
    clearBtn:SetHeight(22)
    clearBtn:SetPoint("LEFT", footer, "LEFT", 0, 0)
    self.clearBtn = clearBtn
    table.insert(self.buttons, clearBtn)

    local langBtn = CreateHandButton(footer, "GameFontNormalSmall", function()
        local order = (ns.Locale and ns.Locale.order) or { "auto", "enUS", "esES", "itIT" }
        local current = (ns.db and ns.db.locale) or "auto"
        local nextIdx = 1
        for i, code in ipairs(order) do
            if code == current then
                nextIdx = (i % #order) + 1
                break
            end
        end
        local nextSetting = order[nextIdx] or "auto"
        if ns.Locale and type(ns.Locale.Set) == "function" then
            ns.Locale.Set(nextSetting)
        elseif ns.db then
            ns.db.locale = nextSetting
        end
        UI:Refresh()
        UI:AddMessage("system", ns.L.LANG_CHANGED:format(ns.L["LANG_" .. nextSetting]))
    end)
    langBtn:SetHeight(22)
    langBtn:SetPoint("LEFT", clearBtn, "RIGHT", 6, 0)
    self.langBtn = langBtn
    table.insert(self.buttons, langBtn)

    local syncBtn = CreateHandButton(footer, "GameFontNormalSmall", function()
        if type(ns.SyncCompanion) == "function" then
            ns.SyncCompanion()
        elseif type(ReloadUI) == "function" then
            ReloadUI()
        end
    end)
    syncBtn:SetHeight(22)
    syncBtn:SetPoint("LEFT", langBtn, "RIGHT", 6, 0)
    syncBtn:HookScript("OnEnter", function(selfBtn)
        if GameTooltip then
            GameTooltip:SetOwner(selfBtn, "ANCHOR_TOP")
            GameTooltip:SetText(ns.L.SYNC_TIP)
            GameTooltip:Show()
        end
    end)
    syncBtn:HookScript("OnLeave", function()
        if GameTooltip then
            GameTooltip:Hide()
        end
    end)
    self.syncBtn = syncBtn
    table.insert(self.buttons, syncBtn)

    local footerText = footer:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
    footerText:SetPoint("LEFT", syncBtn, "RIGHT", 8, 0)
    footerText:SetPoint("RIGHT", footer, "RIGHT", -18, 0)
    footerText:SetJustifyH("RIGHT")
    footerText:SetWordWrap(false)
    self.footerText = footerText

    -- Resize grip (bottom-right corner, pure solid WHITE8X8 textures)
    local resizeGrip = CreateFrame("Button", nil, frame)
    resizeGrip:SetSize(16, 16)
    resizeGrip:SetPoint("BOTTOMRIGHT", frame, "BOTTOMRIGHT", -3, 3)
    resizeGrip:SetFrameLevel(frame:GetFrameLevel() + 5)
    resizeGrip:EnableMouse(true)

    local gripBars = {}
    for i = 1, 3 do
        local bar = resizeGrip:CreateTexture(nil, "OVERLAY")
        bar:SetTexture(WHITE8X8)
        local span = i * 4
        bar:SetSize(span, 2)
        bar:SetPoint("BOTTOMRIGHT", resizeGrip, "BOTTOMRIGHT", -1, 1 + (3 - i) * 4)
        table.insert(gripBars, bar)
    end
    self.gripBars = gripBars

    local isResizingOrScaling = false
    local resizeLeft, resizeTop, resizeOffsetX, resizeOffsetY = 0, 0, 0, 0

    local function StopResizeOrScale()
        if not isResizingOrScaling then
            return
        end
        isResizingOrScaling = false
        resizeGrip:SetScript("OnUpdate", nil)
        SaveGeometry(frame)
        if GameTooltip and GameTooltip:GetOwner() == resizeGrip then
            GameTooltip:Hide()
        end
    end

    local function OnResizeUpdate()
        if not IsMouseButtonDown("LeftButton") then
            StopResizeOrScale()
            return
        end

        local cursorX, cursorY = GetCursorPosition()
        local uScale = UIParent:GetEffectiveScale()
        cursorX = cursorX / uScale
        cursorY = cursorY / uScale

        local spanX = cursorX + resizeOffsetX - resizeLeft
        local spanY = resizeTop - (cursorY + resizeOffsetY)

        local currentScale = frame:GetScale() or DEFAULT_SCALE
        local width = frame:GetWidth()
        local height = frame:GetHeight()
        local isScaling = IsShiftKeyDown()

        if isScaling then
            local parentWidth = UIParent:GetWidth()
            local parentHeight = UIParent:GetHeight()
            local targetScale = (spanX / width + spanY / height) / 2
            local newScale = math.max(MIN_SCALE, math.min(MAX_SCALE, targetScale))
            newScale = math.floor(newScale * 100 + 0.5) / 100

            if math.abs(newScale - currentScale) > 0.005 then
                frame:SetScale(newScale)
                if ns.db then
                    ns.db.scale = newScale
                end
                frame:ClearAllPoints()
                frame:SetPoint("TOPLEFT", UIParent, "BOTTOMLEFT", resizeLeft / newScale, resizeTop / newScale)
            end

            if GameTooltip then
                GameTooltip:SetOwner(resizeGrip, "ANCHOR_TOPLEFT")
                GameTooltip:SetText(string.format("HiDPI Scale: %.2fx", newScale), 1, 0.82, 0)
                GameTooltip:Show()
            end
        else
            local newW = math.max(MIN_WIDTH, math.min(MAX_WIDTH, spanX / currentScale))
            local newH = math.max(MIN_HEIGHT, math.min(MAX_HEIGHT, spanY / currentScale))
            frame:SetSize(math.floor(newW + 0.5), math.floor(newH + 0.5))

            if GameTooltip and GameTooltip:GetOwner() == resizeGrip then
                GameTooltip:Hide()
            end
        end
    end

    resizeGrip:SetScript("OnMouseDown", function(_, button)
        if button == "RightButton" then
            UI:ResetPosition()
            return
        end

        if button == "LeftButton" then
            local scale = frame:GetScale() or DEFAULT_SCALE
            local cursorX, cursorY = GetCursorPosition()
            local uScale = UIParent:GetEffectiveScale()
            cursorX = cursorX / uScale
            cursorY = cursorY / uScale

            resizeLeft = frame:GetLeft() * scale
            resizeTop = frame:GetTop() * scale
            resizeOffsetX = (frame:GetRight() * scale) - cursorX
            resizeOffsetY = (frame:GetBottom() * scale) - cursorY

            isResizingOrScaling = true
            if GameTooltip and GameTooltip:GetOwner() == resizeGrip then
                GameTooltip:Hide()
            end
            resizeGrip:SetScript("OnUpdate", OnResizeUpdate)
        end
    end)

    resizeGrip:SetScript("OnMouseUp", function(_, button)
        if button == "LeftButton" then
            StopResizeOrScale()
        end
    end)

    resizeGrip:SetScript("OnEnter", function(selfGrip)
        if isResizingOrScaling then
            return
        end
        if GameTooltip then
            GameTooltip:SetOwner(selfGrip, "ANCHOR_TOPLEFT")
            GameTooltip:SetText(ns.L.RESIZE_TIP)
            GameTooltip:Show()
        end
    end)

    resizeGrip:SetScript("OnLeave", function()
        if isResizingOrScaling then
            return
        end
        if GameTooltip then
            GameTooltip:Hide()
        end
    end)
    self.resizeGrip = resizeGrip

    local historyFont, inputFont = GetJinyFonts()

    -- Input row
    local inputRow = CreateFrame("Frame", nil, frame)
    inputRow:SetPoint("BOTTOMLEFT", footer, "TOPLEFT", 0, 6)
    inputRow:SetPoint("BOTTOMRIGHT", footer, "TOPRIGHT", 0, 6)
    inputRow:SetHeight(28)
    self.inputRow = inputRow

    local sendBtn = CreateHandButton(inputRow, "GameFontNormalSmall", function()
        if UI.editBox then
            local text = UI.editBox:GetText()
            UI.editBox:SetText("")
            UI.editBox:ClearFocus()
            UI:Ask(text)
        end
    end)
    sendBtn:SetHeight(28)
    sendBtn:SetPoint("RIGHT", inputRow, "RIGHT", 0, 0)
    self.sendBtn = sendBtn
    table.insert(self.buttons, sendBtn)

    local inputContainer = CreateFrame("Frame", nil, inputRow, "BackdropTemplate")
    inputContainer:SetPoint("TOPLEFT", inputRow, "TOPLEFT", 0, 0)
    inputContainer:SetPoint("BOTTOMRIGHT", sendBtn, "BOTTOMLEFT", -6, 0)
    self.inputContainer = inputContainer

    local editBox = CreateFrame("EditBox", nil, inputContainer)
    editBox:SetPoint("TOPLEFT", inputContainer, "TOPLEFT", 8, -3)
    editBox:SetPoint("BOTTOMRIGHT", inputContainer, "BOTTOMRIGHT", -8, 3)
    editBox:SetAutoFocus(false)
    editBox:SetFontObject(inputFont)
    editBox:SetMaxLetters(500)
    self.editBox = editBox

    local placeholderText = inputContainer:CreateFontString(nil, "OVERLAY")
    placeholderText:SetFontObject(inputFont)
    placeholderText:SetPoint("LEFT", inputContainer, "LEFT", 8, 0)
    placeholderText:SetPoint("RIGHT", inputContainer, "RIGHT", -8, 0)
    placeholderText:SetJustifyH("LEFT")
    placeholderText:SetWordWrap(false)
    self.placeholderText = placeholderText

    editBox:SetScript("OnTextChanged", function()
        UI:UpdatePlaceholder()
    end)
    editBox:SetScript("OnEnterPressed", function(selfBox)
        local text = selfBox:GetText()
        selfBox:SetText("")
        selfBox:ClearFocus()
        UI:Ask(text)
    end)
    editBox:SetScript("OnEscapePressed", function(selfBox)
        selfBox:ClearFocus()
    end)

    -- History ScrollingMessageFrame
    local historyFrame = CreateFrame("ScrollingMessageFrame", nil, frame)
    historyFrame:SetPoint("TOPLEFT", header, "BOTTOMLEFT", 4, -8)
    historyFrame:SetPoint("BOTTOMRIGHT", inputRow, "TOPRIGHT", -4, 8)
    historyFrame:SetFontObject(historyFont)
    historyFrame:SetFading(false)
    historyFrame:SetMaxLines(200)
    historyFrame:SetJustifyH("LEFT")
    if historyFrame.SetIndentedWordWrap then
        historyFrame:SetIndentedWordWrap(true)
    end
    historyFrame:SetHyperlinksEnabled(true)
    historyFrame:EnableMouseWheel(true)
    historyFrame:SetScript("OnMouseWheel", function(selfHistory, delta)
        if IsShiftKeyDown() then
            if delta > 0 then
                selfHistory:ScrollToTop()
            else
                selfHistory:ScrollToBottom()
            end
        else
            if delta > 0 then
                selfHistory:ScrollUp()
            else
                selfHistory:ScrollDown()
            end
        end
    end)
    historyFrame:SetScript("OnHyperlinkClick", function(selfHistory, link, text, button)
        if type(link) == "string" and link:find("^jinycopy:") then
            local sid = link:sub(10)
            UI:OpenCopyDialog(sid)
        elseif type(link) == "string" and link:find("^jinymacro:") then
            local sid = link:sub(11)
            UI:CreateInGameMacro(sid)
        elseif SetItemRef then
            SetItemRef(link, text, button, selfHistory)
        end
    end)
    self.historyFrame = historyFrame

    self:ApplyTheme()
    self:Refresh()
    self:UpdatePlaceholder()

    if ns.db and type(ns.db.history) == "table" and #ns.db.history > 0 then
        for _, entry in ipairs(ns.db.history) do
            if type(entry) == "table" and entry.text then
                self:AddMessage(entry.who or "jiny", entry.text)
            end
        end
    else
        self:AddMessage("jiny", ns.L.WELCOME)
    end

    return frame
end

function UI:ApplyTheme()
    if not self.frame then
        return
    end
    local t = GetTheme()
    local edge = t.edgeSize or FALLBACK_THEME.edgeSize

    ApplyBackdrop(self.frame, t.bg or FALLBACK_THEME.bg, t.border or FALLBACK_THEME.border, edge)
    ApplyBackdrop(self.header, t.headerBg or FALLBACK_THEME.headerBg, t.border or FALLBACK_THEME.border, edge)
    ApplyBackdrop(self.inputContainer, t.inputBg or FALLBACK_THEME.inputBg, t.inputBorder or FALLBACK_THEME.inputBorder, edge)

    if self.titleText then
        self.titleText:SetTextColor(UnpackRGB(t.title or FALLBACK_THEME.title, 0.29, 0.15, 0.03))
    end
    if self.editBox then
        self.editBox:SetTextColor(UnpackRGB(t.inputText or FALLBACK_THEME.inputText, 0.17, 0.09, 0.03))
    end
    if self.placeholderText then
        self.placeholderText:SetTextColor(UnpackRGB(t.muted or FALLBACK_THEME.muted, 0.42, 0.27, 0.14))
    end
    if self.footerText then
        self.footerText:SetTextColor(UnpackRGB(t.muted or FALLBACK_THEME.muted, 0.42, 0.27, 0.14))
    end

    if self.buttons then
        local btnBg = t.buttonBg or FALLBACK_THEME.buttonBg
        local btnHover = t.buttonHover or FALLBACK_THEME.buttonHover
        local btnBorder = t.buttonBorder or FALLBACK_THEME.buttonBorder
        local btnText = t.buttonText or FALLBACK_THEME.buttonText
        for _, btn in ipairs(self.buttons) do
            local activeBg = btn.isHovered and btnHover or btnBg
            ApplyBackdrop(btn, activeBg, btnBorder, edge)
            if btn.label then
                btn.label:SetTextColor(UnpackRGB(btnText, 1, 0.96, 0.82))
            end
        end
    end

    if self.gripBars then
        local mr, mg, mb, ma = UnpackRGBA(t.muted or FALLBACK_THEME.muted, 0.42, 0.27, 0.14, 0.75)
        for _, bar in ipairs(self.gripBars) do
            bar:SetVertexColor(mr, mg, mb, ma)
        end
    end

    if self.copyDialog then
        ApplyBackdrop(self.copyDialog, t.bg or FALLBACK_THEME.bg, t.border or FALLBACK_THEME.border, edge)
        ApplyBackdrop(self.copyDialog.header, t.headerBg or FALLBACK_THEME.headerBg, t.border or FALLBACK_THEME.border, edge)
        ApplyBackdrop(self.copyDialog.editContainer, t.inputBg or FALLBACK_THEME.inputBg, t.inputBorder or FALLBACK_THEME.inputBorder, edge)
        if self.copyDialog.title then
            self.copyDialog.title:SetTextColor(UnpackRGB(t.title or FALLBACK_THEME.title, 0.29, 0.15, 0.03))
        end
        if self.copyDialog.editBox then
            self.copyDialog.editBox:SetTextColor(UnpackRGB(t.inputText or FALLBACK_THEME.inputText, 0.17, 0.09, 0.03))
        end
        if self.copyDialog.hint then
            self.copyDialog.hint:SetTextColor(UnpackRGB(t.muted or FALLBACK_THEME.muted, 0.42, 0.27, 0.14))
        end
        if self.copyDialog.closeBtn then
            ApplyBackdrop(self.copyDialog.closeBtn, t.buttonBg or FALLBACK_THEME.buttonBg, t.buttonBorder or FALLBACK_THEME.buttonBorder, edge)
            if self.copyDialog.closeBtn.label then
                self.copyDialog.closeBtn.label:SetTextColor(UnpackRGB(t.buttonText or FALLBACK_THEME.buttonText, 1, 0.96, 0.82))
            end
        end
        if self.copyDialog.createBtn then
            ApplyBackdrop(self.copyDialog.createBtn, t.buttonBg or FALLBACK_THEME.buttonBg, t.buttonBorder or FALLBACK_THEME.buttonBorder, edge)
            if self.copyDialog.createBtn.label then
                self.copyDialog.createBtn.label:SetTextColor(UnpackRGB(t.buttonText or FALLBACK_THEME.buttonText, 1, 0.96, 0.82))
            end
        end
    end

    self:UpdateStatus()
end

function UI:Refresh()
    if not self.frame then
        return
    end
    if self.titleText then
        self.titleText:SetText(ns.L.TITLE)
    end
    if self.placeholderText then
        self.placeholderText:SetText(ns.L.INPUT_PLACEHOLDER)
    end
    if self.sendBtn and self.sendBtn.label then
        self.sendBtn.label:SetText(ns.L.BTN_SEND)
        self.sendBtn:SetWidth(math.max(64, math.ceil(self.sendBtn.label:GetStringWidth()) + 20))
    end
    if self.clearBtn and self.clearBtn.label then
        self.clearBtn.label:SetText(ns.L.BTN_CLEAR)
        self.clearBtn:SetWidth(math.max(64, math.ceil(self.clearBtn.label:GetStringWidth()) + 18))
    end
    if self.langBtn and self.langBtn.label then
        local localeKey = "LANG_" .. (ns.db and ns.db.locale or "auto")
        self.langBtn.label:SetText(ns.L.BTN_LANGUAGE .. ": " .. ns.L[localeKey])
        self.langBtn:SetWidth(math.max(104, math.ceil(self.langBtn.label:GetStringWidth()) + 16))
    end
    if self.syncBtn and self.syncBtn.label then
        self.syncBtn.label:SetText(ns.L.BTN_SYNC)
        self.syncBtn:SetWidth(math.max(64, math.ceil(self.syncBtn.label:GetStringWidth()) + 16))
    end
    if self.footerText then
        self.footerText:SetText(ns.L.FOOTER)
    end
    self:UpdateStatus()
end

function UI:Show()
    local frame = self:Create()
    frame:Show()
end

function UI:Hide()
    if self.frame then
        self.frame:Hide()
    elseif ns.db then
        ns.db.shown = false
    end
end

function UI:Toggle()
    local frame = self:Create()
    if frame:IsShown() then
        frame:Hide()
    else
        frame:Show()
    end
end

function UI:Clear()
    if self.historyFrame then
        self.historyFrame:Clear()
    end
end

function UI:ResetPosition()
    if ns.db then
        ns.db.point = nil
        ns.db.size = { DEFAULT_WIDTH, DEFAULT_HEIGHT }
        ns.db.scale = DEFAULT_SCALE
    end
    if self.frame then
        self.frame:SetScale(DEFAULT_SCALE)
        self.frame:ClearAllPoints()
        self.frame:SetPoint("CENTER", UIParent, "CENTER", 0, 0)
        self.frame:SetSize(DEFAULT_WIDTH, DEFAULT_HEIGHT)
    end
end

function UI:SetScale(scale)
    local s = math.max(MIN_SCALE, math.min(MAX_SCALE, tonumber(scale) or DEFAULT_SCALE))
    s = math.floor(s * 100 + 0.5) / 100
    if ns.db then
        ns.db.scale = s
    end
    if self.frame then
        self.frame:SetScale(s)
        SaveGeometry(self.frame)
    end
end

function UI:AddMessage(who, text)
    if not self.historyFrame then
        return
    end
    local msg = tostring(text or "")
    local t = GetTheme()
    local tr, tg, tb = UnpackRGB(t.text or FALLBACK_THEME.text, 0.23, 0.14, 0.06)

    if who == "user" then
        local hex = ColorHex(t.userLabel or FALLBACK_THEME.userLabel)
        local formatted = "|c" .. hex .. "[" .. ns.L.LABEL_YOU .. "]|r " .. msg
        self.historyFrame:AddMessage(formatted, tr, tg, tb)
    elseif who == "jiny" then
        local hex = ColorHex(t.jinyLabel or FALLBACK_THEME.jinyLabel)
        local formatted = ProcessMessageContent(msg)
        local firstLine = true
        for line in (formatted .. "\n"):gmatch("(.-)\r?\n") do
            local lineToRender = (line == "") and " " or line
            if firstLine then
                self.historyFrame:AddMessage("|c" .. hex .. "[" .. ns.L.LABEL_JINY .. "]|r " .. lineToRender, tr, tg, tb)
                firstLine = false
            else
                self.historyFrame:AddMessage(lineToRender, tr, tg, tb)
            end
        end
    else
        local mr, mg, mb = UnpackRGB(t.muted or FALLBACK_THEME.muted, 0.42, 0.27, 0.14)
        for line in (msg .. "\n"):gmatch("(.-)\r?\n") do
            local lineToRender = (line == "") and " " or line
            self.historyFrame:AddMessage(lineToRender, mr, mg, mb)
        end
    end
end

function UI:Ask(text)
    local cleanText = Trim(text)
    if cleanText == "" then
        return
    end
    if not self.frame then
        self:Create()
    end

    self:AddMessage("user", cleanText)
    if type(ns.AddHistory) == "function" then
        ns.AddHistory("user", cleanText)
    end

    self.pendingCount = (self.pendingCount or 0) + 1
    self:UpdateStatus()

    if ns.Transport and type(ns.Transport.Send) == "function" then
        ns.Transport.Send(cleanText, function(reply, meta)
            self.pendingCount = math.max(0, (self.pendingCount or 1) - 1)
            self:UpdateStatus()

            if type(meta) == "table" and meta.queued then
                self:AddMessage("system", ns.L.SENT_TO_COMPANION)
            elseif reply ~= nil then
                local replyText = tostring(reply)
                self:AddMessage("jiny", replyText)
                if type(ns.AddHistory) == "function" then
                    ns.AddHistory("jiny", replyText)
                end
            end
        end)
    else
        self.pendingCount = math.max(0, (self.pendingCount or 1) - 1)
        self:UpdateStatus()
    end
end
