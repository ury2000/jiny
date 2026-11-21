local ADDON, ns = ...

local Mock = {}
ns.Mock = Mock

function Mock:Reply(question, callback)
    if type(callback) ~= "function" then
        return
    end
    local safeQuestion = tostring(question or "")
    C_Timer.After(0.4, function()
        local template = (ns.L and ns.L.MOCK_REPLY) or "%s"
        callback(template:format(safeQuestion))
    end)
end

ns.Transport = {
    Send = function(question, cb)
        ns.Mock:Reply(question, cb)
    end,
}
