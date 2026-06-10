"""`dicton macros` — standalone Qt editor for macros.json.

Decoupled from the daemon: the two processes only meet through macros.json
(the daemon re-reads it on every dictation via an mtime cache), so there is
no IPC, no file-watcher, no restart.

The 🎤 button records a short take and stores the *raw* Whisper
transcription as a spelling — exactly what the daemon will see at match
time. Qt imports stay inside ``run_window`` so importing this module for
its logic (tests, CLI startup) never loads Qt.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid

import httpx
import numpy as np
import sounddevice as sd

from . import macros as macros_mod
from . import stt
from .config import Config
from .macros import Macro, normalize

log = logging.getLogger("dicton")


# ---- pure CRUD helpers (no Qt) ----


def new_macro_id(spelling: str, existing: set[str]) -> str:
    """Stable id from the first spelling (slug), unique among ``existing``."""
    base = normalize(spelling).replace(" ", "-") or uuid.uuid4().hex[:8]
    candidate, n = base, 2
    while candidate in existing:
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def upsert(macros: list[Macro], macro: Macro) -> list[Macro]:
    """Replace the macro with the same id, or append."""
    out = [macro if m.id == macro.id else m for m in macros]
    if macro not in out:
        out.append(macro)
    return out


def remove(macros: list[Macro], macro_id: str) -> list[Macro]:
    return [m for m in macros if m.id != macro_id]


# ---- spelling capture (record → raw Whisper transcription) ----


class Recorder:
    """Short mono capture for a spoken trigger; returns WAV bytes on stop."""

    def __init__(self, sample_rate: int, device: int | None) -> None:
        self._sample_rate = sample_rate
        self._frames: list[np.ndarray] = []
        self._stream = sd.InputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="int16",
            callback=self._on_audio,
            device=device,
        )
        self._stream.start()

    def _on_audio(self, indata: np.ndarray, frames, time_info, status) -> None:  # type: ignore[no-untyped-def]
        self._frames.append(indata[:, 0].copy())

    def stop(self) -> bytes:
        self._stream.stop()
        self._stream.close()
        pcm = np.concatenate(self._frames) if self._frames else np.zeros(0, dtype=np.int16)
        return stt.pcm16_to_wav(pcm, self._sample_rate)


def transcribe_spelling(cfg: Config, wav: bytes) -> str:
    """Blocking STT call returning the raw transcription (no hallucination
    filter, no cleanup) — the spelling must be what Whisper actually emits."""

    async def _go() -> str:
        async with httpx.AsyncClient(http2=True) as client:
            transcript = await stt.transcribe(
                client,
                wav,
                api_key=cfg.groq_api_key,
                model=cfg.stt_model,
                language=cfg.language,
            )
            return transcript.raw_text

    return asyncio.run(_go())


# ---- Qt window ----


def run_window(cfg: Config) -> int:
    from PySide6 import QtCore, QtWidgets

    class MacrosWindow(QtWidgets.QMainWindow):
        _spelling_ready = QtCore.Signal(object, str)

        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle("dicton — Macros")
            self.resize(640, 480)
            self._macros = list(macros_mod.load())
            self._current: Macro | None = None
            self._recorder: Recorder | None = None
            self._rec_button: QtWidgets.QPushButton | None = None
            self._spelling_ready.connect(self._fill_spelling)
            self._build()
            self._refresh_list()

        # -- layout --

        def _build(self) -> None:
            root = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(root)

            top = QtWidgets.QHBoxLayout()
            top.addWidget(QtWidgets.QLabel("<b>Macros</b>"))
            top.addStretch(1)
            new_btn = QtWidgets.QPushButton("+ Nouvelle")
            new_btn.clicked.connect(self._new_macro)
            top.addWidget(new_btn)
            layout.addLayout(top)

            self._list = QtWidgets.QListWidget()
            self._list.currentRowChanged.connect(self._select_row)
            layout.addWidget(self._list, 1)

            editor = QtWidgets.QGroupBox("Édition")
            form = QtWidgets.QVBoxLayout(editor)
            form.addWidget(QtWidgets.QLabel("Déclencheur (ce que tu dis) :"))
            self._spellings_box = QtWidgets.QVBoxLayout()
            form.addLayout(self._spellings_box)
            add_spelling = QtWidgets.QPushButton("+ ajouter une orthographe")
            add_spelling.clicked.connect(lambda: self._add_spelling_row(""))
            form.addWidget(add_spelling)
            form.addWidget(QtWidgets.QLabel("Valeur (insérée verbatim) :"))
            self._value = QtWidgets.QPlainTextEdit()
            form.addWidget(self._value, 1)

            buttons = QtWidgets.QHBoxLayout()
            buttons.addStretch(1)
            save_btn = QtWidgets.QPushButton("Enregistrer")
            save_btn.clicked.connect(self._save_current)
            delete_btn = QtWidgets.QPushButton("Supprimer")
            delete_btn.clicked.connect(self._delete_current)
            buttons.addWidget(save_btn)
            buttons.addWidget(delete_btn)
            form.addLayout(buttons)
            layout.addWidget(editor, 2)

            self.setCentralWidget(root)

        def _add_spelling_row(self, text: str) -> None:
            row = QtWidgets.QHBoxLayout()
            edit = QtWidgets.QLineEdit(text)
            edit.setPlaceholderText("orthographe Whisper du déclencheur")
            mic = QtWidgets.QPushButton("🎤")
            mic.setFixedWidth(36)
            mic.clicked.connect(lambda *, e=edit, b=mic: self._toggle_record(e, b))
            rm = QtWidgets.QPushButton("✕")
            rm.setFixedWidth(28)
            holder = QtWidgets.QWidget()
            holder.setLayout(row)
            rm.clicked.connect(lambda *, h=holder: self._remove_spelling_row(h))
            row.addWidget(edit, 1)
            row.addWidget(mic)
            row.addWidget(rm)
            row.setContentsMargins(0, 0, 0, 0)
            self._spellings_box.addWidget(holder)

        def _remove_spelling_row(self, holder: QtWidgets.QWidget) -> None:
            self._spellings_box.removeWidget(holder)
            holder.deleteLater()

        def _spelling_edits(self) -> list[QtWidgets.QLineEdit]:
            edits: list[QtWidgets.QLineEdit] = []
            for i in range(self._spellings_box.count()):
                holder = self._spellings_box.itemAt(i).widget()
                if holder is not None:
                    edits.extend(holder.findChildren(QtWidgets.QLineEdit))
            return edits

        def _clear_spelling_rows(self) -> None:
            while self._spellings_box.count():
                item = self._spellings_box.takeAt(0)
                w = item.widget()
                if w is not None:
                    w.deleteLater()

        # -- list / editor sync --

        def _refresh_list(self, select_id: str | None = None) -> None:
            self._list.blockSignals(True)
            self._list.clear()
            for m in self._macros:
                preview = m.value.splitlines()[0] if m.value else ""
                if len(preview) > 40:
                    preview = preview[:40] + "…"
                trigger = m.spellings[0] if m.spellings else m.id
                self._list.addItem(f"{trigger}  →  {preview}")
            self._list.blockSignals(False)
            if self._macros:
                ids = [m.id for m in self._macros]
                row = ids.index(select_id) if select_id in ids else 0
                self._list.setCurrentRow(row)
            else:
                self._current = None
                self._clear_spelling_rows()
                self._add_spelling_row("")
                self._value.setPlainText("")

        def _select_row(self, row: int) -> None:
            if not (0 <= row < len(self._macros)):
                return
            self._current = self._macros[row]
            self._clear_spelling_rows()
            for sp in self._current.spellings or [""]:
                self._add_spelling_row(sp)
            self._value.setPlainText(self._current.value)

        # -- actions --

        def _new_macro(self) -> None:
            self._current = None
            self._list.blockSignals(True)
            self._list.setCurrentRow(-1)
            self._list.blockSignals(False)
            self._clear_spelling_rows()
            self._add_spelling_row("")
            self._value.setPlainText("")

        def _save_current(self) -> None:
            spellings = [e.text().strip() for e in self._spelling_edits() if e.text().strip()]
            value = self._value.toPlainText()
            errors, warnings = macros_mod.validate(spellings, value, self._macros, self._current)
            if errors:
                QtWidgets.QMessageBox.warning(self, "Macro invalide", "\n".join(errors))
                return
            if warnings:
                answer = QtWidgets.QMessageBox.question(
                    self,
                    "Orthographe en doublon",
                    "\n".join(warnings) + "\n\nEnregistrer quand même ?",
                )
                if answer != QtWidgets.QMessageBox.StandardButton.Yes:
                    return
            if self._current is None:
                macro_id = new_macro_id(spellings[0], {m.id for m in self._macros})
                self._current = Macro(id=macro_id, spellings=spellings, value=value)
            else:
                self._current.spellings = spellings
                self._current.value = value
            self._macros = upsert(self._macros, self._current)
            macros_mod.save(self._macros)
            self._refresh_list(select_id=self._current.id)

        def _delete_current(self) -> None:
            if self._current is None:
                return
            self._macros = remove(self._macros, self._current.id)
            macros_mod.save(self._macros)
            self._current = None
            self._refresh_list()

        # -- mic capture --

        def _toggle_record(self, edit: QtWidgets.QLineEdit, button: QtWidgets.QPushButton) -> None:
            if self._recorder is None:
                try:
                    self._recorder = Recorder(cfg.sample_rate, cfg.input_device)
                except Exception as exc:  # noqa: BLE001 — surface any device error
                    QtWidgets.QMessageBox.warning(self, "Micro", f"Capture impossible : {exc}")
                    return
                self._rec_button = button
                button.setText("⏹")
                return
            if button is not self._rec_button:
                return  # another row's recording is in progress
            wav = self._recorder.stop()
            self._recorder = None
            button.setText("🎤")
            button.setEnabled(False)

            def work() -> None:
                try:
                    text = transcribe_spelling(cfg, wav)
                except Exception as exc:  # noqa: BLE001 — show the failure, keep the window alive
                    log.warning("spelling transcription failed: %s", exc)
                    text = ""
                self._spelling_ready.emit(edit, text)

            threading.Thread(target=work, daemon=True).start()

        def _fill_spelling(self, edit: object, text: str) -> None:
            for known in self._spelling_edits():
                if known is edit:
                    known.setText(text)
                    break
            if self._rec_button is not None:
                self._rec_button.setEnabled(True)
                self._rec_button = None

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = MacrosWindow()
    window.show()
    return app.exec()
