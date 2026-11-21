# Changelog

Todos los cambios notables de **Jiny** (exclusivo para WoW Classic Forever `_forever_`, Interface `16001`) se documentan en este archivo.

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
