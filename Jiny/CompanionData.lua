local ADDON, ns = ...

ns.CompanionData = {
    updatedAt = 1795295504,
    companionStatus = "online",
    replies = {
        {
            id = "1795294457-6541",
            lang = "esES",
            q = "Necesito una Macro para castear las habilidades de hunter Invocar halcon e arcano[mod:alt]",
            a = "¡Por supuesto! Asumo que te refieres a tu **Aspecto del halcón** y a tu **Disparo arcano**. Con esta macro lanzarás Disparo arcano si mantienes pulsada la tecla Alt, o activarás Aspecto del halcón con una pulsación normal.\n\n[JINY_MACRO name=\"HalconArcano\"]\n#showtooltip\n/cast [mod:alt] Disparo arcano; Aspecto del halcón\n[/JINY_MACRO]\n\nEl comando `#showtooltip` cambiará automáticamente el icono y la descripción en tu barra de acción al pulsar la tecla Alt. Recuerda revisar en tus opciones de interfaz que la tecla Alt no esté asignada a la función de autohechizo si notas que no responde.",
            t = 1795295504,
        },
    },
}
