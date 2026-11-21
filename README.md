# Jiny v0.1 — Asistente In-Game para WoW Classic Forever

**Jiny** es un addon asistente diseñado **exclusivamente** para **World of Warcraft Classic Forever** (`_forever_`, Interface `16001`). No ofrece ni contempla soporte para otras expansiones o clientes.

> *Powered by Gemini & Local AI* — En **v0.1 (Fase 1)** Jiny funciona como interfaz visual in-game en **modo demo local** con respuestas simuladas y estado persistente. La conexión externa con el Companion de IA llegará en la versión **v0.2**.

---

## Los 7 Pilares Fundamentales

1. **Identidad Intelectual**: Diseño visual propio de Azeroth con estética editorial y emblema estelar original (`JinyIcon`), alejado de interfaces genéricas.
2. **Seguridad y Privacidad**: Sin automatización prohibida, sin lectura intrusiva ni envío de datos fuera del cliente en v0.1; todo ocurre de forma segura dentro de la API permitida de WoW.
3. **Usabilidad & i18n**: Interfaz clara, legible y multilingüe de serie con soporte completo en **Español (`ES`)**, **Inglés (`EN`)** e **Italiano (`IT`)**, además de detección automática.
4. **Simplicidad**: Flujo directo mediante una ventana compacta, historial de conversación limpio y comandos slash intuitivos sin configuraciones abrumadoras.
5. **Rendimiento**: Arquitectura ligera en Lua pensada para no penalizar los FPS ni la memoria durante sesiones largas en Azeroth.
6. **Interoperabilidad**: Estructura preparada desde la base (`SavedVariables`, motor de temas y locales desacoplados) para integrarse en v0.2 con el servicio Companion de Gemini y modelos locales.
7. **Disponibilidad**: Enfoque estricto en el cliente Classic Forever (`_forever_`, `## Interface: 16001`) con instalación reproducible y herramientas locales de despliegue y generación de recursos.

---

## Características de la v0.1

- **Tema visual**: `Pergamino Clásico (Light)` como tema inicial, construido sobre un motor de temas preparado para incorporar *Dark Mode* en versiones posteriores.
- **Idiomas soportados**: `ES` (Español), `EN` (English), `IT` (Italiano) y modo `auto` según el idioma del cliente.
- **Modo demo local**: Permite probar la ventana del asistente, el historial y las interacciones básicas directamente dentro del juego sin requerir servicios externos activos.
- **Iconografía original**: Emblema de gema estelar de 4 puntas en formato vectorial (`Jiny/Assets/JinyIcon.svg`) y textura TGA de 64×64 píxeles (`Jiny/Assets/JinyIcon.tga`).

---

## Comandos Slash

| Comando | Descripción |
| :--- | :--- |
| `/jiny` | Abre o cierra la ventana principal de Jiny. |
| `/jiny help` | Muestra la lista de comandos disponibles en el chat. |
| `/jiny lang <auto\|en\|es\|it>` | Cambia el idioma de la interfaz (`auto`, `en`, `es` o `it`). |
| `/jiny scale <0.65-2.5\|reset>` | Ajusta o restablece la escala HiDPI de la ventana. |
| `/jiny reset` | Restaura posición, tamaño y escala por defecto de la ventana. |
| `/jiny clear` | Limpia el historial de mensajes mostrado en la sesión actual. |

> **Escalado HiDPI (Estilo TradeSkillMaster):**
> - **Arrastrar esquina inferior derecha:** Redimensiona ancho y alto.
> - **Shift + Arrastrar esquina inferior derecha:** Escala la ventana completa suavemente (texto, caja de entrada, botones y marco en alta resolución) mostrando el tooltip con el factor de escala (ej. `1.25x`).
> - **Clic derecho en la esquina inferior derecha:** Restablece posición, tamaño y escala al valor original.

---

## Instalación Manual

Puedes instalar Jiny en tu cliente **WoW Classic Forever** (`_forever_`) de dos formas:

### Opción 1: Script de despliegue (PowerShell)

Desde la carpeta `jiny`, ejecuta:

```powershell
.\tools\deploy.ps1
```

El script mostrará las rutas de origen y destino y solicitará confirmación antes de sincronizar la carpeta `Jiny` en `_forever_\Interface\AddOns\Jiny` mediante `robocopy /MIR`. Para omitir la confirmación interactiva, añade `-Force`:

```powershell
.\tools\deploy.ps1 -Force
```

### Opción 2: Copia manual

1. Copia la carpeta `jiny\Jiny` completa.
2. Pégala dentro de `_forever_\Interface\AddOns\Jiny` (de modo que `Jiny.toc` quede en `_forever_\Interface\AddOns\Jiny\Jiny.toc`).
3. Inicia WoW Classic Forever o ejecuta `/reload` si ya estás dentro del juego.

---

## Regeneración de Recursos (Opcional)

El icono `Jiny/Assets/JinyIcon.tga` (64×64, 32 bits BGRA sin compresión) puede regenerarse en cualquier momento con Python 3 (solo biblioteca estándar):

```powershell
py jiny\tools\make_icon.py
```
