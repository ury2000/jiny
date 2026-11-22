"""Modular, non-blocking lightweight Overlay window with headless fallback."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import queue
import threading
import time
from typing import Any, Optional

from .config import CompanionConfig

# Exact hex palettes matching Jiny/Themes.lua (ParchmentLight & DarkGlass)
OVERLAY_THEMES: dict[str, dict[str, str]] = {
    "DarkGlass": {
        "bg": "#10141f",
        "border": "#5a6b8c",
        "header_bg": "#0b0e18",
        "title": "#ffd100",
        "text": "#fff4d2",
        "muted": "#94a3b8",
        "jiny_label": "#69ccf0",
        "user_label": "#93c5fd",
        "input_bg": "#070a12",
        "accent": "#2563eb",
    },
    "ParchmentLight": {
        "bg": "#e8d5a8",
        "border": "#7c5329",
        "header_bg": "#d9c08c",
        "title": "#4a2508",
        "text": "#3a2410",
        "muted": "#6b4423",
        "jiny_label": "#1e3a8a",
        "user_label": "#7c2d12",
        "input_bg": "#f8efd8",
        "accent": "#7c3f16",
    },
}


def resolve_overlay_theme(theme_name: Optional[str]) -> str:
    """Resolve theme alias/name to 'DarkGlass' or 'ParchmentLight'."""
    key = (theme_name or "").strip().lower()
    if key in ("parchmentlight", "parchment", "light"):
        return "ParchmentLight"
    if key in ("darkglass", "dark"):
        return "DarkGlass"
    return "DarkGlass"


@dataclass
class OverlayState:
    """Mutable snapshot state managed by OverlayController."""

    status: str = "idle"
    provider: str = ""
    latest_question: str = ""
    latest_reply: str = ""
    last_error: str = ""
    theme: str = "DarkGlass"
    updated_at: float = 0.0


class OverlayController:
    """Thread-safe state controller for the Jiny Companion overlay."""

    def __init__(self, theme: str = "DarkGlass") -> None:
        self._lock = threading.RLock()
        self._state = OverlayState(theme=resolve_overlay_theme(theme), updated_at=time.time())

    def set_status(self, status: str, provider: Optional[str] = None) -> None:
        with self._lock:
            self._state.status = status
            if provider is not None:
                self._state.provider = provider
            self._state.updated_at = time.time()

    def set_question(self, question: str) -> None:
        with self._lock:
            self._state.latest_question = question
            self._state.updated_at = time.time()

    def set_reply(self, question: str, reply: str) -> None:
        with self._lock:
            self._state.latest_question = question
            self._state.latest_reply = reply
            self._state.last_error = ""
            self._state.updated_at = time.time()

    def set_error(self, error: str) -> None:
        with self._lock:
            self._state.status = "error"
            self._state.last_error = error
            self._state.updated_at = time.time()

    def set_theme(self, theme: str) -> None:
        with self._lock:
            self._state.theme = resolve_overlay_theme(theme)
            self._state.updated_at = time.time()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            palette = dict(OVERLAY_THEMES[self._state.theme])
            return {
                "status": self._state.status,
                "provider": self._state.provider,
                "latest_question": self._state.latest_question,
                "latest_reply": self._state.latest_reply,
                "last_error": self._state.last_error,
                "theme": self._state.theme,
                "updated_at": self._state.updated_at,
                "palette": palette,
            }


class OverlayBackend(ABC):
    """Abstract rendering backend for OverlayManager."""

    name: str

    @abstractmethod
    def start(self) -> None:
        """Initialize the overlay surface."""

    @abstractmethod
    def render(self, snapshot: dict[str, Any]) -> None:
        """Render the latest state snapshot."""

    @abstractmethod
    def close(self) -> None:
        """Tear down resources cleanly."""


class HeadlessOverlayBackend(OverlayBackend):
    """In-memory overlay backend with zero GUI/tkinter dependencies."""

    name = "headless"

    def __init__(self) -> None:
        self.started = False
        self.closed = False
        self.snapshots: list[dict[str, Any]] = []
        self.last_snapshot: Optional[dict[str, Any]] = None

    def start(self) -> None:
        self.started = True
        self.closed = False

    def render(self, snapshot: dict[str, Any]) -> None:
        copy = dict(snapshot)
        self.snapshots.append(copy)
        self.last_snapshot = copy

    def close(self) -> None:
        self.closed = True


class TkOverlayBackend(OverlayBackend):
    """Lazy Tkinter overlay window running on its own daemon UI thread."""

    name = "tk"

    def __init__(self, opacity: float = 0.92, always_on_top: bool = True) -> None:
        self.opacity = max(0.3, min(1.0, float(opacity)))
        self.always_on_top = bool(always_on_top)
        self._queue: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=64)
        self._ready_event = threading.Event()
        self._start_error: Optional[BaseException] = None
        self._thread: Optional[threading.Thread] = None
        self._closed = False

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._ready_event.clear()
        self._start_error = None
        self._closed = False
        self._thread = threading.Thread(target=self._ui_main, name="jiny-overlay-tk", daemon=True)
        self._thread.start()
        if not self._ready_event.wait(timeout=3.0):
            raise RuntimeError("Timed out initializing Tk overlay window.")
        if self._start_error is not None:
            raise self._start_error

    def _ui_main(self) -> None:
        try:
            import tkinter as tk  # lazy import ONLY inside UI thread
        except Exception as exc:
            self._start_error = exc
            self._ready_event.set()
            return

        try:
            root = tk.Tk()
            root.title("Jiny Overlay")
            root.geometry("420x280+80+80")
            root.minsize(280, 160)
            try:
                root.attributes("-topmost", self.always_on_top)
                root.attributes("-alpha", self.opacity)
                root.lift()
            except Exception:
                pass

            header = tk.Frame(root, padx=8, pady=6)
            header.pack(fill="x")
            title_var = tk.StringVar(value="Jiny • idle")
            title_lbl = tk.Label(header, textvariable=title_var, anchor="w", font=("Segoe UI", 10, "bold"))
            title_lbl.pack(side="left", fill="x", expand=True)

            body = tk.Text(root, wrap="word", state="disabled", padx=8, pady=6, borderwidth=0)
            body.pack(fill="both", expand=True, padx=6, pady=(0, 6))

            tcl_error = getattr(tk, "TclError", RuntimeError)
            ui_refs: dict[str, Any] = {
                "root": root,
                "header": header,
                "title_var": title_var,
                "title_lbl": title_lbl,
                "body": body,
            }
            del root, header, title_var, title_lbl, body

            def _apply_snapshot(snap: dict[str, Any]) -> None:
                r = ui_refs.get("root")
                h = ui_refs.get("header")
                tv = ui_refs.get("title_var")
                tl = ui_refs.get("title_lbl")
                b = ui_refs.get("body")
                if r is None or h is None or tv is None or tl is None or b is None:
                    return
                pal = snap.get("palette", OVERLAY_THEMES["DarkGlass"])
                r.configure(bg=pal["bg"])
                h.configure(bg=pal["header_bg"])
                provider = snap.get("provider") or "companion"
                tv.set(f"Jiny ({provider}) • {snap.get('status', 'idle')}")
                tl.configure(bg=pal["header_bg"], fg=pal["title"])
                b.configure(bg=pal["input_bg"], fg=pal["text"])

                lines: list[str] = []
                if snap.get("latest_question"):
                    lines.append(f"Q: {snap['latest_question']}")
                if snap.get("latest_reply"):
                    lines.append(f"Jiny: {snap['latest_reply']}")
                if snap.get("last_error"):
                    lines.append(f"Error: {snap['last_error']}")
                if not lines:
                    lines.append("Awaiting Classic Forever queries...")

                b.configure(state="normal")
                b.delete("1.0", "end")
                b.insert("1.0", "\n\n".join(lines))
                b.configure(state="disabled")
                try:
                    r.lift()
                    r.attributes("-topmost", self.always_on_top)
                except Exception:
                    pass

            def _on_close() -> None:
                self._closed = True
                r = ui_refs.get("root")
                if r is None:
                    return
                try:
                    r.quit()
                except Exception:
                    pass
                try:
                    r.destroy()
                except Exception:
                    pass

            ui_refs["root"].protocol("WM_DELETE_WINDOW", _on_close)

            def _poll_queue() -> None:
                r = ui_refs.get("root")
                if r is None:
                    return
                if self._closed:
                    _on_close()
                    return
                try:
                    while True:
                        if self._closed:
                            _on_close()
                            return
                        kind, payload = self._queue.get_nowait()
                        if kind == "close":
                            _on_close()
                            return
                        if kind == "render" and isinstance(payload, dict):
                            try:
                                _apply_snapshot(payload)
                            except (tcl_error, RuntimeError):
                                _on_close()
                                return
                except queue.Empty:
                    pass
                if self._closed:
                    _on_close()
                    return
                try:
                    r.after(100, _poll_queue)
                except (tcl_error, RuntimeError):
                    _on_close()

            self._ready_event.set()
            try:
                ui_refs["root"].after(100, _poll_queue)
                ui_refs["root"].mainloop()
            except (tcl_error, RuntimeError):
                _on_close()
            finally:
                _on_close()
                ui_refs.clear()
        except Exception as exc:
            self._start_error = exc
            self._ready_event.set()

    def render(self, snapshot: dict[str, Any]) -> None:
        if self._closed:
            return
        try:
            self._queue.put_nowait(("render", snapshot))
        except queue.Full:
            pass

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._queue.put_nowait(("close", None))
        except queue.Full:
            pass
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)


class OverlayManager:
    """High-level coordinator with graceful TclError/headless fallback."""

    def __init__(
        self,
        enabled: bool = False,
        theme: str = "DarkGlass",
        opacity: float = 0.92,
        always_on_top: bool = True,
        backend: Optional[OverlayBackend] = None,
        backend_name: str = "auto",
    ) -> None:
        self.enabled = bool(enabled)
        self.opacity = max(0.3, min(1.0, float(opacity)))
        self.always_on_top = bool(always_on_top)
        self._backend_name = (backend_name or "auto").strip().lower()
        self.controller = OverlayController(theme=theme)
        self._injected_backend = backend
        self._backend: OverlayBackend = backend if backend is not None else HeadlessOverlayBackend()
        self.fallback_reason: Optional[str] = None
        self._started = False
        self._closed = False

    @property
    def backend(self) -> OverlayBackend:
        return self._backend

    def start(self) -> OverlayBackend:
        if self._started:
            return self._backend
        self._closed = False
        if self._injected_backend is not None:
            self._backend = self._injected_backend
            self._backend.start()
        elif (not self.enabled) or self._backend_name == "headless":
            self._backend = HeadlessOverlayBackend()
            self._backend.start()
        else:
            tk_backend = TkOverlayBackend(opacity=self.opacity, always_on_top=self.always_on_top)
            try:
                tk_backend.start()
                self._backend = tk_backend
                print("  Overlay  : Activo (ventana flotante en pantalla)")
            except Exception as exc:
                self.fallback_reason = str(exc)
                print(f"  Overlay  : Fallback a headless ({exc})")
                tk_backend.close()
                self._backend = HeadlessOverlayBackend()
                self._backend.start()

        self._started = True
        self._render_current()
        return self._backend

    def _render_current(self) -> None:
        try:
            self._backend.render(self.controller.snapshot())
        except Exception as exc:
            self.fallback_reason = str(exc)

    def update_status(self, status: str, provider: Optional[str] = None) -> None:
        self.controller.set_status(status, provider=provider)
        self._render_current()

    def show_question(self, question: str) -> None:
        self.controller.set_question(question)
        self._render_current()

    def show_reply(self, question: str, reply: str) -> None:
        self.controller.set_reply(question, reply)
        self._render_current()

    def show_error(self, error: str) -> None:
        self.controller.set_error(error)
        self._render_current()

    def set_theme(self, theme: str) -> None:
        self.controller.set_theme(theme)
        self._render_current()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._backend.close()
        except Exception:
            pass

    def __enter__(self) -> "OverlayManager":
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    @classmethod
    def from_config(cls, cfg: CompanionConfig) -> "OverlayManager":
        return cls(
            enabled=cfg.overlay_enabled,
            theme=cfg.overlay_theme,
            opacity=cfg.overlay_opacity,
            always_on_top=cfg.overlay_always_on_top,
        )
