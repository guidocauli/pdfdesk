# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# Finestra «Traduci PDF»: elenco di file (il documento aperto e/o altri PDF), lingua di partenza (rilevata o scelta),
# lingua di destinazione, nome e cartella dei file tradotti. Il documento aperto, una volta tradotto, si apre in una
# scheda accanto all'originale.
from __future__ import annotations

import os
from typing import Callable, Optional

import pymupdf as fitz
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout,
                               QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QProgressBar,
                               QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout)

from . import translate as T
from .i18n import tr

ENGINE_NAMES = {"local": "Locale (senza internet)", "deepl": "DeepL", "libretranslate": "LibreTranslate"}


def settings():
    from .dialogs import settings as s
    return s()


def engine_from_settings() -> T.Engine:
    s = settings()
    return T.make_engine(str(s.value("translate/engine", "local")), str(s.value("translate/deepl_key", "")),
                         str(s.value("translate/lt_url", "")), str(s.value("translate/lt_key", "")))


def lang_combo(auto: bool, current: str = "") -> QComboBox:
    c = QComboBox()
    if auto:
        c.addItem(tr("Rileva automaticamente"), "")
    for code in sorted(T.LANGS, key=lambda k: T.lang_name(k).lower()):
        if code in T.RTL and not auto:
            continue                                     # destinazione da destra a sinistra: non ancora supportata
        c.addItem(f"{T.lang_name(code)} ({code})", code)
    i = c.findData(current)
    c.setCurrentIndex(max(0, i))
    return c


class TranslateDialog(QDialog):
    """`current`: (percorso o None, funzione che restituisce i byte del documento aperto, titolo) oppure None.
    `on_current_done(percorso_uscita_o_None, byte, resoconto)` viene chiamata quando il documento aperto è tradotto."""

    def __init__(self, parent=None, current: Optional[tuple] = None, files: Optional[list] = None,
                 on_current_done: Optional[Callable] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Traduci PDF"))
        self.setMinimumSize(760, 560)
        self.setAcceptDrops(True)
        self.on_current_done = on_current_done
        self.cancelled = False
        self.running = False
        self.results: list = []                          # (riga, percorso di uscita o None, resoconto o errore)
        s = settings()
        lay = QVBoxLayout(self)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels([tr("Documento"), tr("Lingua"), tr("Stato")])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        lay.addWidget(QLabel(tr("Documenti da tradurre (si possono anche trascinare qui):")))
        lay.addWidget(self.table, 1)
        row = QHBoxLayout()
        self.b_add = QPushButton(tr("Aggiungi PDF…")); self.b_del = QPushButton(tr("Rimuovi"))
        self.b_add.clicked.connect(self._add_dialog); self.b_del.clicked.connect(self._remove)
        row.addWidget(self.b_add); row.addWidget(self.b_del); row.addStretch(1)
        lay.addLayout(row)

        g = QGroupBox(tr("Traduzione")); f = QFormLayout(g)
        self.src = lang_combo(True, "")
        from .i18n import language
        self.dst = lang_combo(False, str(s.value("translate/target", "it" if language().startswith("en") else "en")))
        f.addRow(tr("Da"), self.src); f.addRow(tr("A"), self.dst)
        self.pattern = QLineEdit(str(s.value("translate/pattern", T.DEFAULT_PATTERN)))
        self.pattern.setToolTip(tr("{name} = nome del file originale, {lang} = codice della lingua di destinazione"))
        f.addRow(tr("Nome dei file tradotti"), self.pattern)
        frow = QHBoxLayout()
        self.folder = QLineEdit(str(s.value("translate/folder", "")))
        self.folder.setPlaceholderText(tr("Stessa cartella del file originale"))
        b_folder = QPushButton(tr("Sfoglia…")); b_folder.clicked.connect(self._pick_folder)
        frow.addWidget(self.folder, 1); frow.addWidget(b_folder)
        f.addRow(tr("Cartella"), frow)
        self.minsize = QSpinBox(); self.minsize.setRange(20, 100); self.minsize.setSuffix(" %")
        self.minsize.setValue(int(s.value("translate/min_scale", int(T.MIN_SCALE * 100))))
        self.minsize.setToolTip(tr("Se il testo tradotto non entra nella casella si rimpicciolisce, ma non sotto questa percentuale"))
        f.addRow(tr("Dimensione minima del testo"), self.minsize)
        orow = QHBoxLayout()
        self.o_annots = QCheckBox(tr("Commenti")); self.o_toc = QCheckBox(tr("Segnalibri")); self.o_meta = QCheckBox(tr("Titolo e oggetto"))
        for c, k in ((self.o_annots, "annots"), (self.o_toc, "toc"), (self.o_meta, "meta")):
            c.setChecked(s.value("translate/" + k, True) not in (False, "false", 0, "0")); orow.addWidget(c)
        orow.addStretch(1)
        f.addRow(tr("Traduci anche"), orow)
        eng = str(s.value("translate/engine", "local"))
        self.engine_lbl = QLabel(tr("Motore: {e} — si cambia in Preferenze → Traduzione").format(e=tr(ENGINE_NAMES.get(eng, eng))))
        self.engine_lbl.setWordWrap(True)
        f.addRow("", self.engine_lbl)
        lay.addWidget(g)

        self.status = QLabel(""); self.status.setWordWrap(True)
        self.bar = QProgressBar(); self.bar.setVisible(False)
        lay.addWidget(self.status); lay.addWidget(self.bar)
        brow = QHBoxLayout(); brow.addStretch(1)
        self.b_go = QPushButton(tr("Traduci")); self.b_go.setDefault(True)
        self.b_close = QPushButton(tr("Chiudi"))
        self.b_go.clicked.connect(self.run); self.b_close.clicked.connect(self._close_or_cancel)
        brow.addWidget(self.b_go); brow.addWidget(self.b_close)
        lay.addLayout(brow)

        self.items: list = []                            # dict: path, getter (byte), current (bool), title
        if current is not None:
            path, getter, title = current
            self._append({"path": path, "getter": getter, "current": True, "title": title})
        for p in files or []:
            self.add_file(p)

    # ---------------------------------------------------------------- elenco
    def _append(self, it: dict) -> None:
        self.items.append(it)
        r = self.table.rowCount(); self.table.insertRow(r)
        name = it["title"] + ("  " + tr("(documento aperto)") if it["current"] else "")
        cell = QTableWidgetItem(name); cell.setToolTip(it["path"] or it["title"])
        self.table.setItem(r, 0, cell)
        self.table.setItem(r, 1, QTableWidgetItem(self._detect_label(it)))
        self.table.setItem(r, 2, QTableWidgetItem(tr("In attesa")))

    def _detect_label(self, it: dict) -> str:
        try:
            data = it["getter"]()
            with fitz.open("pdf", data) as d:
                if d.needs_pass:
                    it["lang"] = None; return tr("protetto")
                it["lang"] = T.detect_pdf_language(d)
        except Exception:
            it["lang"] = None
            return "?"
        return T.lang_name(it["lang"]) if it["lang"] else tr("non rilevata")

    def add_file(self, path: str) -> None:
        ap = os.path.abspath(path)
        if any(i["path"] and os.path.abspath(i["path"]) == ap for i in self.items):
            return

        def getter(p=ap):
            with open(p, "rb") as f:
                return f.read()
        self._append({"path": ap, "getter": getter, "current": False, "title": os.path.basename(ap)})

    def _add_dialog(self) -> None:
        start = str(settings().value("lastdir", ""))
        fs, _ = QFileDialog.getOpenFileNames(self, tr("Aggiungi PDF"), start, tr("PDF (*.pdf)"))
        for p in fs:
            self.add_file(p)

    def _remove(self) -> None:
        for r in sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(r); del self.items[r]

    def _pick_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("Cartella dei file tradotti"), self.folder.text() or str(settings().value("lastdir", "")))
        if d:
            self.folder.setText(d)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for u in e.mimeData().urls():
            p = u.toLocalFile()
            if p.lower().endswith(".pdf") and os.path.isfile(p):
                self.add_file(p)

    # ---------------------------------------------------------------- esecuzione
    def _set_state(self, r: int, text: str) -> None:
        self.table.item(r, 2).setText(text)
        QApplication.processEvents()

    def _progress(self, what: str, a: int, b: int) -> bool:
        self.bar.setMaximum(max(1, b)); self.bar.setValue(a)
        self.status.setText(what)
        QApplication.processEvents()
        return not self.cancelled

    def _close_or_cancel(self) -> None:
        if self.running:
            self.cancelled = True
        else:
            self.reject()

    def closeEvent(self, e):
        if self.running:
            self.cancelled = True; e.ignore()
        else:
            super().closeEvent(e)

    def _store(self) -> None:
        s = settings()
        s.setValue("translate/target", self.dst.currentData()); s.setValue("translate/pattern", self.pattern.text().strip() or T.DEFAULT_PATTERN)
        s.setValue("translate/folder", self.folder.text().strip()); s.setValue("translate/min_scale", self.minsize.value())
        s.setValue("translate/annots", self.o_annots.isChecked()); s.setValue("translate/toc", self.o_toc.isChecked())
        s.setValue("translate/meta", self.o_meta.isChecked())

    def _ensure_models(self, engine: T.Engine, pairs: set) -> bool:
        """Motore locale: scarica (dopo conferma) i modelli mancanti per le coppie di lingue richieste."""
        if not isinstance(engine, T.LocalEngine):
            return True
        missing = [p for p in pairs if not engine.ready(*p)]
        if not missing:
            return True
        self.status.setText(tr("Ricerca dei modelli di traduzione…")); QApplication.processEvents()
        try:
            index = T.fetch_index()
            need, seen = [], set()
            for a, b in missing:
                for m in T.models_needed(a, b, index):
                    if (m.src, m.dst) not in seen:
                        seen.add((m.src, m.dst)); need.append(m)
        except T.TranslateError as e:
            QMessageBox.warning(self, tr("Traduci PDF"), str(e)); return False
        names = ", ".join(f"{T.lang_name(m.src)} → {T.lang_name(m.dst)}" for m in need)
        if QMessageBox.question(self, tr("Modelli di traduzione"),
                                tr("Per tradurre senza internet servono i modelli: {n}.\nVerranno scaricati una volta sola "
                                   "(circa 90 MB ciascuno). Continuare?").format(n=names)) != QMessageBox.Yes:
            return False
        for m in need:
            try:
                T.install_model(m, lambda a, b, m=m: self._progress(tr("Scaricamento del modello {a} → {b}").format(
                    a=T.lang_name(m.src), b=T.lang_name(m.dst)), a, b))
            except T.TranslateError as e:
                QMessageBox.warning(self, tr("Traduci PDF"), str(e)); return False
        return True

    def run(self) -> None:
        if not self.items:
            QMessageBox.information(self, tr("Traduci PDF"), tr("Aggiungi almeno un PDF da tradurre.")); return
        dst = self.dst.currentData(); src_sel = self.src.currentData() or None
        engine = engine_from_settings()
        self._store()
        pairs = set()
        for it in self.items:
            src = src_sel or it.get("lang")
            if src and src != dst:
                pairs.add((src, dst))
        self.running = True; self.cancelled = False
        self.b_go.setEnabled(False); self.b_add.setEnabled(False); self.b_del.setEnabled(False)
        self.b_close.setText(tr("Annulla")); self.bar.setVisible(True)
        try:
            if not self._ensure_models(engine, pairs):
                return
            opts = T.Options(min_scale=self.minsize.value() / 100, annotations=self.o_annots.isChecked(),
                             bookmarks=self.o_toc.isChecked(), metadata=self.o_meta.isChecked())
            self.results = []
            for r, it in enumerate(self.items):
                if self.cancelled:
                    break
                self._set_state(r, tr("Traduzione…"))
                src = src_sel or it.get("lang")
                try:
                    if not src:
                        raise T.TranslateError(tr("Lingua non rilevata: sceglila nel campo «Da»"))
                    data, rep = T.translate_document(it["getter"](), src, dst, engine, opts, self._progress)
                    out = None
                    if it["path"]:
                        out = T.output_name(it["path"], dst, self.pattern.text().strip(), self.folder.text().strip())
                        from .compress import write_atomic
                        write_atomic(out, data)
                    if it["current"] and self.on_current_done:
                        self.on_current_done(out, data, rep)
                    self.results.append((r, out, rep))
                    note = tr("Tradotto") + (" — " + tr("da controllare") if rep.overflow or rep.numbers_changed else "")
                    self._set_state(r, note)
                    self.table.item(r, 2).setToolTip((out or "") + "\n" + rep.text())
                except Exception as e:
                    self.results.append((r, None, e))
                    self._set_state(r, tr("Errore"))
                    self.table.item(r, 2).setToolTip(str(e))
                    if isinstance(e, T.TranslateError) and str(e) == tr("Operazione annullata"):
                        break
            self._summary()
        finally:
            self.running = False
            self.b_go.setEnabled(True); self.b_add.setEnabled(True); self.b_del.setEnabled(True)
            self.b_close.setText(tr("Chiudi")); self.bar.setVisible(False)

    def _summary(self) -> None:
        ok = [x for x in self.results if not isinstance(x[2], Exception)]
        bad = [x for x in self.results if isinstance(x[2], Exception)]
        lines = [tr("{n} documenti tradotti, {e} con errori.").format(n=len(ok), e=len(bad))]
        for r, out, rep in ok:
            lines.append(f"\n• {self.items[r]['title']}" + (f" → {os.path.basename(out)}" if out else ""))
            lines.append("   " + rep.text().replace("\n", "\n   "))
        for r, _, e in bad:
            lines.append(f"\n• {self.items[r]['title']}: {e}")
        self.status.setText(lines[0])
        QMessageBox.information(self, tr("Traduci PDF"), "\n".join(lines))
