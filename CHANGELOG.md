# Changelog

Todos los cambios notables de **Jiny** (exclusivo para WoW Classic Forever `_forever_`, Vanilla `1.15.x`, Interface `16001`) se documentan en este archivo.

## [0.4.0] - 2026-11-21

### Añadido (Fase 4 — Jiny Estable Forever, Temas, Auth Extendida y Salidas Modulares)
- **Tema Oscuro `DarkGlass` e i18n sincronizado (`Jiny/Themes.lua`, `Jiny/UI.lua`, `Jiny/Core.lua`, `Jiny/Locales/*.lua`)**:
  - Activación de `DarkGlass` junto a `ParchmentLight` con cambio dinámico desde el botón de cabecera y el comando `/jiny theme [light|dark]`.
  - Contraste verificado WCAG 2.1 (`>= 4.5:1` en todos los pares), diseño responsive seguro en `MIN_WIDTH = 320` y pie actualizado a `v0.4 • Forever` en `ES`, `EN` e `IT`.
  - Sincronización de las 51 claves de idioma en `enUS.lua`, `esES.lua`, `itIT.lua` y `tools/check_addon.py` (`Jiny.toc` versión `0.4.0`, `Interface: 16001`).
- **Interfaz Unificada de Proveedores y Auth Extendida (`companion/providers.py`, `companion/oauth.py`)**:
  - `LLMProvider`, `ProviderError` y fábrica `create_provider()` con alias normalizados (`gemini_api_key`, `gemini_oauth`, `ollama`).
  - `GeminiOAuthProvider`: autenticación OAuth 2.0 PKCE (`S256`) en servidor local loopback, persistencia atómica en `companion/oauth_token.json` (ignorado por Git), refresco automático y transporte Bearer REST / Vertex AI.
  - `OllamaProvider`: cliente local `/api/chat` y `/api/tags` basado en `urllib.request` con historial de sesión y manejo seguro de errores.
- **Salidas Modulares Opcionales (`companion/tts.py`, `companion/overlay.py`)**:
  - `TTSManager`: cola asíncrona no bloqueante, saneamiento de etiquetas `[JINY_MACRO]` y códigos de color WoW, con `NullTTSBackend`, `WindowsSAPIBackend` (aislado por entorno) y `Pyttsx3Backend` opcional.
  - `OverlayManager`: ventana ligera opcional con temas `DarkGlass` / `ParchmentLight` (`TkOverlayBackend` con cierre seguro y respaldo automático `HeadlessOverlayBackend` ante entornos sin interfaz gráfica).
- **Integración y Endurecimiento (`companion/config.py`, `companion/main.py`, `tools/test_v04.py`, `tools/test_integration.py`)**:
  - Flags CLI combinados (`--provider`, `--oauth-login`, `--tts`/`--no-tts`, `--overlay`/`--no-overlay`, `--overlay-theme`) junto a los flags RAG de v0.3.
  - Validación estricta de valores numéricos no finitos (`inf`, `-inf`, `nan`) y cadenas inválidas en configuración y variables de entorno.
  - Pruebas offline combinadas (`tools/test_v04.py` y `tools/test_integration.py`).

## [0.3.0] - 2026-11-21

### Añadido (Fase 3 — Base de Conocimiento RAG Classic Era `1.15.x`)
- **Esquema y Frontera Classic Forever (`companion/rag_schema.py`)**:
  - Modelos normalizados para misiones, monstruos/PNJs, objetos y mazmorras de Classic Era `1.15.x` (`QuestRecord`, `MobRecord`, `ItemRecord`, `DungeonRecord`) con validación estricta de coordenadas (`0..100`), niveles (`<= 60` jugador), porcentajes de *drop* (`0..100%`) y rechazo explícito de términos o URLs fuera de Classic Era (`ClassicScopeError`).
- **Semilla Verificada y Almacén SQLite FTS5 (`companion/data/classic_era_seed.json`, `companion/rag_store.py`)**:
  - 52 registros verificados de Kalimdor y Reinos del Este con alias multilingües (`EN`/`ES`/`IT`), índice FTS5 (`unicode61 remove_diacritics 2`) ponderado con `BM25`, expansión bilingüe y guardia contra falsos positivos por palabras genéricas.
- **Actualizador Opcional Wowhead Classic (`companion/wowhead_scraper.py`)**:
  - Ingesta restringida a `https://www.wowhead.com/classic/...` con `fetcher` inyectable para pruebas offline.
- **Fundamentación Anti-Alucinaciones y CLI (`companion/prompts.py`, `companion/main.py`, `tools/test_rag.py`)**:
  - Bloque `[CLASSIC_ERA_CONTEXT]` (`NO_LOCAL_RAG_MATCH`, `NON_CLASSIC_SCOPE`) inyectado en el flujo de respuestas del Companion (`--ask` y `--watch`) y comandos `--rag-rebuild`, `--rag-stats`, `--rag-query`, `--no-rag`, `--rag-type` y `--rag-top-k`.

## [0.2.0] - 2026-11-21

### Añadido (Fase 2 — Companion & Gemini API)
- **Bloques estilizados de Macros y Código (`Jiny/UI.lua` + `companion/prompts.py`)**:
  - Detección de token `[JINY_MACRO name="..."]` emitido por Gemini y fallback para bloques Markdown/macros clásicas (`#showtooltip`, `/cast`, `/use`).
  - Renderizado de cajas visuales estilizadas en pergamino con marco distintivo y tipografía clara.
  - Enlace interactivo **`[📋 Copiar Macro]`** con ventana emergente de copiado rápido (`Ctrl + C`) y selección automática.
  - Botón nativo **`[⚡ Crear Macro en WoW]`** que invoca `CreateMacro(...)` de Blizzard para registrar o actualizar la macro directamente en el panel `/macro` del juego.
- **Transporte en vivo (`Jiny/Transport.lua` y `Jiny/CompanionData.lua`)**:
  - Canal de salida no invasivo mediante auto-susurro oculto por filtro (`[JINY_Q#reqId#locale]`), activación y vaciado instantáneo de `LoggingChat` hacia `Logs\WoWChatLog.txt` y respaldo en `JinyDB.outbox`.
  - Botón **Sincronizar** y comando `/jiny sync` para recargar y mostrar respuestas nuevas del Companion en el historial Lua sin duplicados (`JinyDB.processedIds`).
  - Selector de modo `/jiny mode <companion|mock>` para alternar entre Gemini real y demo local.
- **Companion Python (`companion/`)**:
  - `log_reader.py`: lectura incremental por offset de bytes sobre `WoWChatLog.txt` con filtro estricto de privacidad (ignora chats normales/hermandad/susurros ajenos) y deduplicación por `reqId`.
  - `gemini_client.py` + `prompts.py`: integración oficial con `google-genai` (`client.interactions.create` + `previous_interaction_id`) usando `gemini-3.8-flash` y *System Prompt* exclusivo de WoW Classic Forever (1.15.x) en ES/EN/IT.
  - `lua_writer.py`: escritura atómica (`.tmp` + `os.replace`) de `CompanionData.lua` en UTF-8 sin BOM.
  - `main.py`: CLI con `--watch`, `--ask`, `--status` y `--dry-run`.
- **Calidad y pruebas**: Suite `tools/test_companion.py` (`unittest`) y actualización de `tools/check_addon.py` para 36 claves de locale.

## [0.1.0] - 2026-11-21

### Añadido (Fase 1)
- **UI Lua — Pergamino Clásico (Light)**: Ventana principal in-game para WoW Classic Forever con diseño editorial en pergamino clásico, barra de título, área de historial y caja de entrada.
- **Theme Engine**: Motor de temas desacoplado con soporte inicial para `Pergamino Clásico (Light)` y arquitectura preparada para añadir *Dark Mode* en futuras versiones.
- **Internacionalización (i18n)**: Soporte completo para **Español (`ES`)**, **Inglés (`EN`)** e **Italiano (`IT`)**, con selección automática (`auto`) o manual mediante `/jiny lang <auto|en|es|it>`.
- **Modo demo local**: Flujo de conversación interactivo in-game sin dependencias externas mientras llega la integración con el Companion (*Powered by Gemini & Local AI*) en v0.2.
- **Tipografía y Escalado HiDPI (Estilo TSM)**:
  - Nueva tipografía nítida para historial y entrada (`Friz Quadrata` 14px con sutil sombra y espaciado de línea de 3px para máxima legibilidad sobre pergamino).
  - Escalado dinámico HiDPI al mantener **Shift + arrastrar la esquina inferior derecha** con vista previa en tooltip en vivo (`HiDPI Scale: 1.25x`), persistido en `JinyDB`.
  - Clic derecho en la esquina inferior derecha para restablecer posición, tamaño y escala.
  - Nuevo comando `/jiny scale <0.65-2.5|reset>`.
- **Comandos Slash**: Implementación de `/jiny`, `/jiny help`, `/jiny lang <auto|en|es|it>`, `/jiny scale <valor|reset>`, `/jiny reset` y `/jiny clear`.
- **Iconografía original**: Diseño vectorial `Jiny/Assets/JinyIcon.svg` (gema estelar de 4 puntas) y textura `Jiny/Assets/JinyIcon.tga` (64×64, 32-bit BGRA sin compresión) generada mediante `tools/make_icon.py`.
- **Herramientas de despliegue y documentación**: Script interactivo `tools/deploy.ps1` con confirmación y `robocopy`, junto con `README.md` y `CHANGELOG.md`.
