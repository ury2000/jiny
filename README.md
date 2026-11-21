# Jiny v0.4 — Asistente In-Game para WoW Classic Forever

**Jiny** es un addon asistente diseñado **exclusivamente** para **World of Warcraft Classic Forever** (`_forever_`, Vanilla `1.15.x`, `## Interface: 16001`). No ofrece ni contempla soporte para otras expansiones o clientes.

> *Powered by Gemini & Local AI* — **Jiny v0.4 (Estable Forever)** integra la interfaz Lua del juego (con temas **Pergamino Clásico** y **DarkGlass**) junto a un **Companion local en Python** equipado con **Base de Conocimiento RAG de Classic Era 1.15.x**, **proveedores unificados** (**Gemini `gemini-3.8-flash` API Key**, **OAuth 2.0 PKCE / Vertex AI** y **Ollama local**) y **salidas modulares opcionales** (**Audio TTS** y **Overlay ligero**).

---

## Los 7 Pilares Fundamentales

1. **Identidad Intelectual**: Diseño visual propio de Azeroth con estética editorial, doble tema (`ParchmentLight` / `DarkGlass`) y emblema estelar original (`JinyIcon`), sin plantillas ni texturas genéricas de Blizzard.
2. **Seguridad y Privacidad**: 100% ToS-safe, sin inyección en memoria/DirectX, sin automatización prohibida; el transporte usa auto-susurro oculto y el Companion filtra estrictamente `Logs\WoWChatLog.txt` sin leer chats privados ni exponer credenciales en Lua.
3. **Usabilidad & i18n**: Interfaz clara, legible y multilingüe con soporte sincronizado en **Español (`ES`)**, **Inglés (`EN`)** e **Italiano (`IT`)**, además de detección automática.
4. **Simplicidad**: Ventana compacta con botones de acceso rápido (`Tema`, `Idioma`, `Sincronizar`, `Limpiar`, `Enviar`), bloques interactivos de macros/código y comandos slash intuitivos.
5. **Rendimiento**: Arquitectura ligera en Lua y almacenamiento local SQLite FTS5 (`BM25`) en el Companion sin latencia añadida en el cliente de WoW.
6. **Interoperabilidad**: Interfaz unificada de proveedores (`LLMProvider`) compatible con AI Studio API Key (`google-genai` `gemini-3.8-flash` Interactions API), OAuth 2.0 (`PKCE S256`) y modelos locales Ollama (`/api/chat`), más salidas opcionales desacopladas (`TTS` y `Overlay`).
7. **Disponibilidad**: Enfoque estricto en **WoW Classic Forever** (`_forever_`, `## Interface: 16001`, Vanilla `1.15.x`) con validación automática, suite de pruebas offline y despliegue reproducible.

---

## Novedades de v0.3 y v0.4

### Fase 3 (`v0.3`) — Base de Conocimiento RAG Classic Era (`1.15.x`)
- **Índice local SQLite FTS5 (`companion/rag_schema.py`, `companion/rag_store.py`)**: Almacena misiones, monstruos/PNJs, objetos y mazmorras de Classic Era `1.15.x` (`companion/data/classic_era_seed.json`) con coordenadas `(x, y)`, niveles mínimos/recomendados y porcentajes de *drop*.
- **Frontera estricta Classic Forever**: Rechaza términos, zonas, niveles (`> 60` para jugador) o URLs fuera de Classic Era `1.15.x`.
- **Fundamentación anti-alucinaciones (`companion/prompts.py`)**: Inyecta el bloque `[CLASSIC_ERA_CONTEXT]` en el proveedor activo (`API Key`, `OAuth 2.0` u `Ollama`) y abstiene cuando no existe coincidencia verificada (`NO_LOCAL_RAG_MATCH` / `NON_CLASSIC_SCOPE`).
- **Actualizador opcional Wowhead Classic (`companion/wowhead_scraper.py`)**: Parseo restringido exclusivamente a `https://www.wowhead.com/classic/...`.

### Fase 4 (`v0.4`) — Estable Forever, Temas, Auth Extendida y Salidas Modulares
- **Modo Oscuro `DarkGlass` (`Jiny/Themes.lua`, `Jiny/UI.lua`, `Jiny/Core.lua`)**: Alternable en vivo con el botón de tema en la barra superior o mediante `/jiny theme [light|dark]`, con contraste verificado WCAG 2.1 y textos localizados en `ES`, `EN` e `IT`.
- **Proveedores Unificados (`companion/providers.py`, `companion/oauth.py`)**:
  - `gemini_api_key`: Google AI Studio (`google-genai` `gemini-3.8-flash` Interactions API).
  - `gemini_oauth`: Flujo OAuth 2.0 PKCE (`S256`) con refresco automático en `companion/oauth_token.json` (ignorado por Git) y soporte Bearer REST o Vertex AI.
  - `ollama`: Modelos locales vía `/api/chat` usando biblioteca estándar (`urllib.request`) sin dependencias externas adicionales.
- **Audio TTS opcional (`companion/tts.py`)**: Cola asíncrona no bloqueante que limpia códigos de color/macros de WoW (`NullTTSBackend`, `WindowsSAPIBackend` o `Pyttsx3Backend` opcional).
- **Overlay ligero opcional (`companion/overlay.py`)**: Ventana flotante desacoplada sincronizada con `DarkGlass` / `ParchmentLight` (`TkOverlayBackend` con respaldo automático `HeadlessOverlayBackend` en entornos sin pantalla).

---

## Comandos Slash In-Game

| Comando | Descripción |
| :--- | :--- |
| `/jiny` | Abre o cierra la ventana principal de Jiny. |
| `/jiny <pregunta>` | Envía una consulta directa a Jiny. |
| `/jiny theme [light\|dark]` | Alterna o selecciona entre `ParchmentLight` y `DarkGlass`. |
| `/jiny sync` | Recarga la UI (`/reload`) para cargar las respuestas del Companion en la ventana Lua. |
| `/jiny mode <companion\|mock>` | Cambia entre el modo real con Companion y el modo demo local. |
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

## Instalación Manual del Addon

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

## Ejecutar el Companion (`v0.4`)

1. Instala las dependencias en Python 3.10+:
   ```powershell
   py -m pip install -r jiny\requirements.txt
   ```
2. Configura tus preferencias copiando `jiny\companion\config.example.json` a `jiny\companion\config.json` (ignorado por Git) o usando variables de entorno:
   - **AI Studio API Key**: `GEMINI_API_KEY` (proveedor `gemini_api_key`).
   - **OAuth 2.0**: `JINY_PROVIDER=gemini_oauth`, `JINY_OAUTH_CLIENT_ID` (y opcionalmente `JINY_VERTEXAI=true`, `JINY_GCP_PROJECT`) ejecutando primero `py -m companion.main --oauth-login`.
   - **Ollama Local**: `JINY_PROVIDER=ollama`, `JINY_OLLAMA_BASE_URL=http://127.0.0.1:11434`, `JINY_OLLAMA_MODEL=llama3.1:8b`.
3. Comprueba estado, proveedor, RAG, TTS y Overlay:
   ```powershell
   py -m companion.main --status
   ```
4. Operaciones RAG locales (100% offline):
   ```powershell
   py -m companion.main --rag-stats
   py -m companion.main --rag-rebuild
   py -m companion.main --rag-query "Ironfoe" --rag-type item --rag-top-k 2
   ```
5. Inicia el *listener* en tiempo real mientras juegas en WoW Classic Forever:
   ```powershell
   py -m companion.main --watch
   py -m companion.main --watch --provider ollama --tts --overlay --overlay-theme DarkGlass
   ```
6. Consulta puntual desde CLI (con `--dry-run` opcional o `--no-rag` para desactivar RAG):
   ```powershell
   py -m companion.main --ask "¿Dónde cae Ironfoe?" --lang esES --dry-run
   ```

---

## Validación y Pruebas Offline

```powershell
py .\tools\check_addon.py
py .\tools\test_companion.py
py -m unittest discover -s tools -p "test_*.py" -v
```

---

## Regeneración de Recursos (Opcional)

El icono `Jiny/Assets/JinyIcon.tga` (64×64, 32 bits BGRA sin compresión) puede regenerarse en cualquier momento con Python 3 (solo biblioteca estándar):

```powershell
py jiny\tools\make_icon.py
```
