"""Modular, non-blocking Audio TTS output with WoW markup sanitization."""

from __future__ import annotations

from abc import ABC, abstractmethod
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from typing import Any, Callable, Optional

from .config import CompanionConfig

_MACRO_BLOCK_RE = re.compile(
    r"\[JINY_MACRO(?:\s+[^\]]*)?\].*?\[/JINY_MACRO\]",
    flags=re.IGNORECASE | re.DOTALL,
)
_MACRO_STRAY_TAG_RE = re.compile(r"\[/?JINY_MACRO(?:\s+[^\]]*)?\]", flags=re.IGNORECASE)
_CODE_BLOCK_RE = re.compile(r"```[a-zA-Z0-9_-]*.*?```", flags=re.DOTALL)
_HYPERLINK_PREFIX_RE = re.compile(r"\|H[^|]*\|h")
_COLOR_CODE_RE = re.compile(r"\|c[0-9a-fA-F]{8}")
_COLOR_RESET_RE = re.compile(r"\|r")
_WHITESPACE_RE = re.compile(r"\s+")

_SAPI_POWERSHELL_SCRIPT = (
    "Add-Type -AssemblyName System.Speech; "
    "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
    "try { "
    "  $c = switch ($env:JINY_TTS_LOCALE) { 'esES' { 'es-ES' } 'itIT' { 'it-IT' } default { 'en-US' } }; "
    "  try { $s.SelectVoiceByHints([System.Speech.Synthesis.VoiceGender]::NotSet, "
    "    [System.Speech.Synthesis.VoiceAge]::NotSet, 0, "
    "    [System.Globalization.CultureInfo]::GetCultureInfo($c)) } catch {}; "
    "  if ($env:JINY_TTS_RATE -match '^-?\\d+$') { "
    "    $r = [int]$env:JINY_TTS_RATE; if ($r -lt -10) { $r = -10 }; if ($r -gt 10) { $r = 10 }; $s.Rate = $r "
    "  }; "
    "  if ($env:JINY_TTS_VOLUME -match '^\\d+$') { "
    "    $v = [int]$env:JINY_TTS_VOLUME; if ($v -lt 0) { $v = 0 }; if ($v -gt 100) { $v = 100 }; $s.Volume = $v "
    "  }; "
    "  if ($env:JINY_TTS_TEXT) { $s.Speak($env:JINY_TTS_TEXT) } "
    "} finally { $s.Dispose() }"
)


class TTSError(RuntimeError):
    """Raised when a TTS backend fails to synthesize audio."""


def sanitize_tts_text(text: str) -> str:
    """Strip WoW markup, macro tags, and fenced code blocks for clean speech synthesis."""
    if not text:
        return ""
    cleaned = _MACRO_BLOCK_RE.sub(" ", text)
    cleaned = _MACRO_STRAY_TAG_RE.sub(" ", cleaned)
    cleaned = _CODE_BLOCK_RE.sub(" ", cleaned)
    cleaned = cleaned.replace("`", "")
    cleaned = _HYPERLINK_PREFIX_RE.sub("", cleaned)
    cleaned = cleaned.replace("|h", "")
    cleaned = _COLOR_CODE_RE.sub("", cleaned)
    cleaned = _COLOR_RESET_RE.sub("", cleaned)
    return _WHITESPACE_RE.sub(" ", cleaned).strip()


class TTSBackend(ABC):
    """Abstract interface for pluggable TTS engines."""

    name: str

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if this backend can run in the current environment."""

    @abstractmethod
    def speak(self, text: str, locale: str = "esES") -> None:
        """Speak plain text synchronously (invoked from TTSManager worker thread)."""


class NullTTSBackend(TTSBackend):
    """Silent no-op backend used when TTS is disabled or unavailable."""

    name = "null"

    def is_available(self) -> bool:
        return True

    def speak(self, text: str, locale: str = "esES") -> None:
        return


class WindowsSAPIBackend(TTSBackend):
    """Windows System.Speech TTS backend using isolated child environment variables."""

    name = "sapi"

    def __init__(
        self,
        rate: int = 0,
        volume: int = 100,
        runner: Optional[Callable[..., Any]] = None,
        timeout: float = 30.0,
    ) -> None:
        self.rate = max(-10, min(10, int(rate)))
        self.volume = max(0, min(100, int(volume)))
        self._runner = runner or subprocess.run
        self.timeout = max(1.0, float(timeout))

    def is_available(self) -> bool:
        return sys.platform == "win32" and shutil.which("powershell") is not None

    def speak(self, text: str, locale: str = "esES") -> None:
        if not text:
            return
        env = os.environ.copy()
        env["JINY_TTS_TEXT"] = text
        env["JINY_TTS_LOCALE"] = locale or "esES"
        env["JINY_TTS_RATE"] = str(self.rate)
        env["JINY_TTS_VOLUME"] = str(self.volume)
        cmd = [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            _SAPI_POWERSHELL_SCRIPT,
        ]
        try:
            result = self._runner(
                cmd,
                env=env,
                shell=False,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise TTSError(f"Windows SAPI execution failed: {exc}") from exc

        returncode = getattr(result, "returncode", 0)
        if returncode != 0:
            stderr = (getattr(result, "stderr", "") or "").strip()
            raise TTSError(f"Windows SAPI exited with code {returncode}: {stderr}")


class Pyttsx3Backend(TTSBackend):
    """Optional pyttsx3 backend (lazily imported; safe no-op if missing)."""

    name = "pyttsx3"

    def __init__(self, rate: int = 0, volume: int = 100) -> None:
        self.rate = max(-10, min(10, int(rate)))
        self.volume = max(0, min(100, int(volume)))
        self._engine: Any = None

    def _init_engine(self) -> Any:
        if self._engine is not None:
            return self._engine
        try:
            import pyttsx3  # lazy import

            engine = pyttsx3.init()
            try:
                base_rate = engine.getProperty("rate") or 200
                engine.setProperty("rate", max(80, int(base_rate) + (self.rate * 15)))
                engine.setProperty("volume", round(self.volume / 100.0, 2))
            except Exception:
                pass
            self._engine = engine
            return engine
        except Exception:
            return None

    def is_available(self) -> bool:
        return self._init_engine() is not None

    def speak(self, text: str, locale: str = "esES") -> None:
        engine = self._init_engine()
        if engine is None or not text:
            return
        try:
            engine.say(text)
            engine.runAndWait()
        except Exception as exc:
            raise TTSError(f"pyttsx3 playback failed: {exc}") from exc


def create_tts_backend(
    backend_name: str = "auto",
    rate: int = 0,
    volume: int = 100,
) -> TTSBackend:
    """Resolve and construct the requested TTS backend with safe fallback."""
    key = (backend_name or "auto").strip().lower()
    if key in ("null", "none", "off", "disabled"):
        return NullTTSBackend()
    if key == "sapi":
        sapi = WindowsSAPIBackend(rate=rate, volume=volume)
        return sapi if sapi.is_available() else NullTTSBackend()
    if key == "pyttsx3":
        pyttsx = Pyttsx3Backend(rate=rate, volume=volume)
        return pyttsx if pyttsx.is_available() else NullTTSBackend()

    # "auto"
    sapi = WindowsSAPIBackend(rate=rate, volume=volume)
    if sapi.is_available():
        return sapi
    pyttsx = Pyttsx3Backend(rate=rate, volume=volume)
    if pyttsx.is_available():
        return pyttsx
    return NullTTSBackend()


class TTSManager:
    """Non-blocking, toggleable queue-backed TTS coordinator."""

    def __init__(
        self,
        enabled: bool = False,
        backend: Optional[TTSBackend] = None,
        backend_name: str = "auto",
        rate: int = 0,
        volume: int = 100,
        max_queue_size: int = 32,
    ) -> None:
        self.enabled = bool(enabled)
        self._backend_name = (backend_name or "auto").strip().lower()
        self._rate = max(-10, min(10, int(rate)))
        self._volume = max(0, min(100, int(volume)))
        self._explicit_backend = backend is not None
        if backend is not None:
            self._backend: TTSBackend = backend
        elif self.enabled:
            self._backend = create_tts_backend(self._backend_name, rate=self._rate, volume=self._volume)
        else:
            self._backend = NullTTSBackend()

        self._queue: queue.Queue[Optional[tuple[str, str]]] = queue.Queue(maxsize=max(1, int(max_queue_size)))
        self._lock = threading.Lock()
        self._worker: Optional[threading.Thread] = None
        self._closed = False
        self.last_error: Optional[str] = None

    @property
    def backend(self) -> TTSBackend:
        return self._backend

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            self.enabled = bool(enabled)
            if self.enabled and not self._explicit_backend and isinstance(self._backend, NullTTSBackend):
                self._backend = create_tts_backend(self._backend_name, rate=self._rate, volume=self._volume)

    def _ensure_worker(self) -> None:
        with self._lock:
            if self._closed:
                return
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(target=self._run_worker, name="jiny-tts-worker", daemon=True)
                self._worker.start()

    def _run_worker(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                self._queue.task_done()
                break
            text, locale = item
            try:
                self._backend.speak(text, locale=locale)
            except Exception as exc:
                self.last_error = str(exc)
            finally:
                self._queue.task_done()

    def speak(self, text: str, locale: str = "esES") -> bool:
        """Sanitize and enqueue speech asynchronously; never blocks caller."""
        if self._closed or not self.enabled:
            return False
        cleaned = sanitize_tts_text(text)
        if not cleaned:
            return False
        self._ensure_worker()
        try:
            self._queue.put_nowait((cleaned, locale))
            return True
        except queue.Full:
            return False

    def flush(self, timeout: float = 5.0) -> bool:
        """Wait until all currently queued utterances finish playing (up to timeout)."""
        deadline = time.monotonic() + max(0.0, float(timeout))
        with self._queue.all_tasks_done:
            while self._queue.unfinished_tasks > 0:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._queue.all_tasks_done.wait(timeout=remaining)
        return True

    def stop(self, drain: bool = False, timeout: float = 2.0) -> None:
        """Stop the TTS worker cleanly; idempotent."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            worker = self._worker

        if not drain:
            while True:
                try:
                    self._queue.get_nowait()
                    self._queue.task_done()
                except queue.Empty:
                    break

        if worker is not None and worker.is_alive():
            try:
                self._queue.put(None, timeout=0.5)
            except queue.Full:
                pass
            worker.join(timeout=max(0.1, float(timeout)))

    def close(self) -> None:
        self.stop(drain=False)

    def __enter__(self) -> "TTSManager":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    @classmethod
    def from_config(cls, cfg: CompanionConfig) -> "TTSManager":
        return cls(
            enabled=cfg.tts_enabled,
            backend_name=cfg.tts_backend,
            rate=cfg.tts_rate,
            volume=cfg.tts_volume,
        )
