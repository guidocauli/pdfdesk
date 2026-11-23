# PDFDesk — Guido Cauli
# ocr_ui.py: finestre dell'OCR.
#   - LanguagesDialog: scarica e toglie le lingue OCR (Preferenze → Scansione e OCR, finestra della scansione e
#     finestra dell'OCR). Su Windows e macOS non serve installare Tesseract: il motore è nel programma.
#   - LangPicker: scelta di una o più lingue fra quelle disponibili.
#   - OcrDialog: «Rendi ricercabile (OCR)» per il documento aperto (sul posto, annullabile, oppure in un nuovo file
#     accanto) e/o per più PDF, salvati con un suffisso scelto (predefinito «_ocr»).
from __future__ import annotations

import os
from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMessageBox, QProgressBar, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from . import ocr
from .i18n import tr


def settings():
    from .dialogs import settings as s
    return s()


def _mb(n: int) -> str:
    return f"{n / 1048576:.1f} MB"


# ====================================================================== lingue
class LanguagesDialog(QDialog):
    """Elenco delle lingue del catalogo: spuntate = da avere. «Applica» scarica quelle nuove e toglie quelle
    deselezionate (solo se scaricate dal programma; quelle di un Tesseract di sistema restano)."""

    def __init__(self, parent=None, preselect: tuple = ()) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Lingue OCR"))
        self.setMinimumSize(520, 560)
        self.cancelled = False
        self.running = False
        lay = QVBoxLayout(self)
        info = QLabel(tr("Il motore OCR è già incluso in PDFDesk: per riconoscere il testo servono solo i dati delle "
                         "lingue, scaricati una volta sola da internet (1–8 MB ciascuna, file verificati). Spunta le "
                         "lingue dei tuoi documenti; più lingue insieme rallentano un poco il riconoscimento."))
        info.setWordWrap(True)
        lay.addWidget(info)
        self.list = QListWidget()
        inst = ocr.installed()
        codes = sorted(set(ocr.CATALOG) | set(inst), key=lambda c: ocr.lang_name(c).lower())
        for c in codes:
            it = QListWidgetItem()
            have = c in inst
            where = ""
            if have and not ocr.is_user_lang(c):
                where = "  — " + tr("dal sistema")
            size = f"  ({_mb(ocr.CATALOG[c][0])})" if c in ocr.CATALOG and not have else ""
            it.setText(f"{ocr.lang_name(c)} [{c}]{size}{where}")
            it.setData(Qt.UserRole, c)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if have or c in preselect else Qt.Unchecked)
            if have and not ocr.is_user_lang(c):
                it.setFlags(it.flags() & ~Qt.ItemIsUserCheckable)    # di sistema: non si toglie da qui
            self.list.addItem(it)
        self.list.itemChanged.connect(self._update)
        lay.addWidget(self.list, 1)
        self.where = QLabel(tr("Cartella: {p}").format(p=ocr.user_dir()))
        self.where.setWordWrap(True); self.where.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.where.setStyleSheet("color: gray")
        lay.addWidget(self.where)
        self.status = QLabel(""); self.status.setWordWrap(True)
        self.bar = QProgressBar(); self.bar.setVisible(False)
        lay.addWidget(self.status); lay.addWidget(self.bar)
        self.bb = QDialogButtonBox(QDialogButtonBox.Apply | QDialogButtonBox.Close)
        self.bb.button(QDialogButtonBox.Apply).setText(tr("Applica"))
        self.bb.button(QDialogButtonBox.Apply).clicked.connect(self.apply)
        self.bb.rejected.connect(self._close)
        lay.addWidget(self.bb)
        self.changed = False
        self._update()

    def _wanted(self) -> tuple[list, list]:
        inst = ocr.installed()
        add, rem = [], []
        for i in range(self.list.count()):
            it = self.list.item(i); c = it.data(Qt.UserRole)
            on = it.checkState() == Qt.Checked
            if on and c not in inst:
                add.append(c)
            elif not on and ocr.is_user_lang(c):
                rem.append(c)
        return add, rem

    def _update(self, *_a) -> None:
        add, rem = self._wanted()
        parts = []
        if add:
            parts.append(tr("da scaricare: {l} ({s})").format(l=", ".join(ocr.lang_name(c) for c in add), s=_mb(ocr.download_size(add))))
        if rem:
            parts.append(tr("da togliere: {l}").format(l=", ".join(ocr.lang_name(c) for c in rem)))
        self.status.setText("; ".join(parts) if parts else tr("Nessuna modifica"))
        self.bb.button(QDialogButtonBox.Apply).setEnabled(bool(add or rem))

    def _progress(self, what: str, a: int, b: int) -> bool:
        self.bar.setMaximum(max(1, b)); self.bar.setValue(min(a, max(1, b)))
        self.status.setText(tr("Scaricamento: {l}").format(l=what))
        QApplication.processEvents()
        return not self.cancelled

    def apply(self) -> bool:
        add, rem = self._wanted()
        for c in rem:
            ocr.remove(c); self.changed = True
        if add:
            self.running = True; self.cancelled = False; self.bar.setVisible(True)
            self.bb.button(QDialogButtonBox.Apply).setEnabled(False)
            self.bb.button(QDialogButtonBox.Close).setText(tr("Annulla"))
            try:
                ocr.download(add, self._progress)
                self.changed = True
            except ocr.OcrError as e:
                if str(e) != tr("Operazione annullata"):
                    QMessageBox.warning(self, tr("Lingue OCR"), str(e))
                self._refresh_marks()
                return False
            finally:
                self.running = False; self.bar.setVisible(False)
                self.bb.button(QDialogButtonBox.Close).setText(tr("Chiudi"))
        self._refresh_marks()
        self.status.setText(tr("Lingue disponibili: {l}").format(l=", ".join(ocr.lang_name(c) for c in ocr.languages()) or "—"))
        return True

    def _refresh_marks(self) -> None:
        inst = ocr.installed()
        self.list.blockSignals(True)
        for i in range(self.list.count()):
            it = self.list.item(i); c = it.data(Qt.UserRole)
            have = c in inst
            where = "  — " + tr("dal sistema") if have and not ocr.is_user_lang(c) else ""
            size = f"  ({_mb(ocr.CATALOG[c][0])})" if c in ocr.CATALOG and not have else ""
            it.setText(f"{ocr.lang_name(c)} [{c}]{size}{where}")
            it.setCheckState(Qt.Checked if have else Qt.Unchecked)
        self.list.blockSignals(False)
        self._update()

    def _close(self) -> None:
        if self.running:
            self.cancelled = True
        else:
            self.accept() if self.changed else self.reject()

    def closeEvent(self, e):
        if self.running:
            self.cancelled = True; e.ignore()
        else:
            super().closeEvent(e)


def ensure_languages(parent, wanted=ocr.DEFAULT_LANGS) -> bool:
    """Se non c'è nessuna lingua OCR propone di scaricare quelle predefinite (italiano e inglese)."""
    if ocr.languages():
        return True
    if not ocr.engine_ok():
        QMessageBox.warning(parent, tr("OCR"), tr("Il motore OCR non è disponibile in questa installazione"))
        return False
    if QMessageBox.question(parent, tr("OCR"), tr("Per l'OCR servono i dati delle lingue. Scaricare ora italiano e inglese "
                                                  "({s})? Altre lingue si aggiungono da Preferenze → Scansione e OCR.")
                            .format(s=_mb(ocr.download_size(wanted)))) != QMessageBox.Yes:
        return False
    dlg = LanguagesDialog(parent, preselect=tuple(wanted))
    dlg.show()
    ok = dlg.apply()
    dlg.close()
    return ok and bool(ocr.languages())


class LangPicker(QWidget):
    """Lingue del documento: caselle di spunta fra quelle disponibili + «Altre lingue…»."""

    def __init__(self, selected: str = "", parent=None) -> None:
        super().__init__(parent)
        v = QVBoxLayout(self); v.setContentsMargins(0, 0, 0, 0)
        self.list = QListWidget(); self.list.setMaximumHeight(130)
        v.addWidget(self.list)
        row = QHBoxLayout()
        self.more = QPushButton(tr("Altre lingue…"))
        self.more.clicked.connect(self._more)
        row.addWidget(self.more); row.addStretch(1)
        v.addLayout(row)
        self.fill(selected)

    def fill(self, selected: str = "") -> None:
        sel = set((selected or self.value() or "+".join(ocr.DEFAULT_LANGS)).split("+"))
        self.list.clear()
        for c in sorted(ocr.languages(), key=lambda c: (c not in sel, ocr.lang_name(c).lower())):   # scelte in cima
            it = QListWidgetItem(f"{ocr.lang_name(c)} [{c}]")
            it.setData(Qt.UserRole, c)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if c in sel else Qt.Unchecked)
            self.list.addItem(it)
        if self.list.count() and not self.value():                 # nessuna delle preferite: la prima
            self.list.item(0).setCheckState(Qt.Checked)

    def value(self) -> str:
        out = []
        for i in range(getattr(self, "list", QListWidget()).count()):
            it = self.list.item(i)
            if it.checkState() == Qt.Checked:
                out.append(it.data(Qt.UserRole))
        # l'ordine conta poco per Tesseract, ma la lingua principale prima: italiano, poi le altre
        return "+".join(sorted(out, key=lambda c: (c != "ita", c != "eng", c)))

    def _more(self) -> None:
        keep = self.value()
        LanguagesDialog(self).exec()
        self.fill(keep)


# ====================================================================== OCR di documenti
class OcrDialog(QDialog):
    """`current`: (percorso o None, PdfDocument aperto, titolo) oppure None.
    `on_current_newfile(percorso, byte)`: chiamata quando il documento aperto è stato riconosciuto e salvato nel
    nuovo file (per aprirlo in una scheda accanto)."""

    def __init__(self, parent=None, current: Optional[tuple] = None, files: Optional[list] = None,
                 on_current_newfile: Optional[Callable] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Rendi ricercabile (OCR)"))
        self.setMinimumSize(760, 560)
        self.setAcceptDrops(True)
        self.on_newfile = on_current_newfile
        self.cancelled = False
        self.running = False
        self.results: list = []
        s = settings()
        lay = QVBoxLayout(self)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels([tr("Documento"), tr("Pagine"), tr("Stato")])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        lay.addWidget(QLabel(tr("Documenti da rendere ricercabili (si possono anche trascinare qui):")))
        lay.addWidget(self.table, 1)
        row = QHBoxLayout()
        self.b_add = QPushButton(tr("Aggiungi PDF…")); self.b_del = QPushButton(tr("Rimuovi"))
        self.b_add.clicked.connect(self._add_dialog); self.b_del.clicked.connect(self._remove)
        row.addWidget(self.b_add); row.addWidget(self.b_del); row.addStretch(1)
        lay.addLayout(row)

        g = QGroupBox(tr("Riconoscimento")); f = QFormLayout(g)
        self.langs = LangPicker(str(s.value("ocr/langs", "+".join(ocr.DEFAULT_LANGS))))
        f.addRow(tr("Lingue"), self.langs)
        self.only_missing = QCheckBox(tr("Solo le pagine senza testo (consigliato)"))
        self.only_missing.setToolTip(tr("Le pagine che contengono già testo selezionabile restano come sono. Togli la spunta "
                                        "per riconoscere anche quelle (utile se il testo esistente è sbagliato o parziale)."))
        self.only_missing.setChecked(s.value("ocr/only_missing", True) not in (False, "false", 0, "0"))
        f.addRow("", self.only_missing)
        self.dpi = QComboBox()
        for d, lab in ((200, tr("200 dpi (più veloce)")), (300, tr("300 dpi (consigliato)")), (400, tr("400 dpi (testi piccoli)"))):
            self.dpi.addItem(lab, d)
        self.dpi.setCurrentIndex(max(0, self.dpi.findData(int(s.value("ocr/dpi", ocr.DEFAULT_DPI)))))
        f.addRow(tr("Risoluzione"), self.dpi)
        lay.addWidget(g)

        g2 = QGroupBox(tr("File di uscita (gli originali non vengono modificati; il documento aperto, una volta "
                          "riconosciuto, si apre in una scheda accanto)")); f2 = QFormLayout(g2)
        self.suffix = QLineEdit(str(s.value("ocr/suffix", ocr.DEFAULT_SUFFIX)))
        self.suffix.setToolTip(tr("Aggiunto al nome di ogni file: «relazione.pdf» → «relazione{s}.pdf»").format(s=ocr.DEFAULT_SUFFIX))
        self.suffix.textChanged.connect(self._example)
        f2.addRow(tr("Suffisso"), self.suffix)
        frow = QHBoxLayout()
        self.folder = QLineEdit(str(s.value("ocr/folder", "")))
        self.folder.setPlaceholderText(tr("Stessa cartella del file originale"))
        b_folder = QPushButton(tr("Sfoglia…")); b_folder.clicked.connect(self._pick_folder)
        frow.addWidget(self.folder, 1); frow.addWidget(b_folder)
        f2.addRow(tr("Cartella"), frow)
        self.overwrite = QCheckBox(tr("Sovrascrivi i file di uscita già esistenti (altrimenti si aggiunge un numero)"))
        self.overwrite.setChecked(s.value("ocr/overwrite", False) in (True, "true", 1, "1"))
        f2.addRow("", self.overwrite)
        self.example = QLabel(""); self.example.setStyleSheet("color: gray")
        f2.addRow("", self.example)
        lay.addWidget(g2)

        self.status = QLabel(""); self.status.setWordWrap(True)
        self.bar = QProgressBar(); self.bar.setVisible(False)
        lay.addWidget(self.status); lay.addWidget(self.bar)
        brow = QHBoxLayout()
        b_langs = QPushButton(tr("Lingue OCR…")); b_langs.clicked.connect(self._langs)
        brow.addWidget(b_langs); brow.addStretch(1)
        self.b_go = QPushButton(tr("Riconosci il testo")); self.b_go.setDefault(True)
        self.b_close = QPushButton(tr("Chiudi"))
        self.b_go.clicked.connect(self.run); self.b_close.clicked.connect(self._close_or_cancel)
        brow.addWidget(self.b_go); brow.addWidget(self.b_close)
        lay.addLayout(brow)

        self.items: list = []
        if current is not None:
            path, pdf, title = current
            self._append({"path": path, "pdf": pdf, "current": True, "title": title})
        for p in files or []:
            self.add_file(p)
        self._example()

    # ---------------------------------------------------------------- elenco
    @staticmethod
    def _page_info(doc) -> str:
        if doc.needs_pass:
            return tr("protetto")
        n = doc.page_count
        no_text = sum(1 for p in doc if not ocr.page_has_text(p))
        return tr("{n} ({k} senza testo)").format(n=n, k=no_text)

    def _append(self, it: dict) -> None:
        self.items.append(it)
        r = self.table.rowCount(); self.table.insertRow(r)
        name = it["title"] + ("  " + tr("(documento aperto)") if it["current"] else "")
        cell = QTableWidgetItem(name); cell.setToolTip(it["path"] or it["title"])
        self.table.setItem(r, 0, cell)
        try:
            if it["current"]:
                info = self._page_info(it["pdf"].doc)
            else:
                import pymupdf as fitz
                with fitz.open(it["path"]) as d:
                    info = self._page_info(d)
        except Exception:
            info = "?"
        self.table.setItem(r, 1, QTableWidgetItem(info))
        self.table.setItem(r, 2, QTableWidgetItem(tr("In attesa")))

    def add_file(self, path: str) -> None:
        ap = os.path.abspath(path)
        if any(i["path"] and os.path.abspath(i["path"]) == ap and not i["current"] for i in self.items):
            return
        self._append({"path": ap, "pdf": None, "current": False, "title": os.path.basename(ap)})
        self._example()

    def _add_dialog(self) -> None:
        start = str(settings().value("lastdir", ""))
        fs, _ = QFileDialog.getOpenFileNames(self, tr("Aggiungi PDF"), start, tr("PDF (*.pdf)"))
        for p in fs:
            self.add_file(p)

    def _remove(self) -> None:
        for r in sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(r); del self.items[r]
        self._example()

    def _pick_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("Cartella dei file di uscita"), self.folder.text() or str(settings().value("lastdir", "")))
        if d:
            self.folder.setText(d); self._example()

    def _example(self, *_a) -> None:
        sfx = self.suffix.text().strip()
        src = next((i["path"] for i in self.items if i["path"]), None) or "relazione.pdf"
        self.example.setText(tr("Esempio: {a} → {b}").format(a=os.path.basename(src),
                                                              b=os.path.splitext(os.path.basename(src))[0] + sfx + ".pdf"))

    def _langs(self) -> None:
        keep = self.langs.value()
        LanguagesDialog(self).exec()
        self.langs.fill(keep)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for u in e.mimeData().urls():
            p = u.toLocalFile()
            if p.lower().endswith(".pdf") and os.path.isfile(p):
                self.add_file(p)

    # ---------------------------------------------------------------- esecuzione
    def _set_state(self, r: int, text: str, tip: str = "") -> None:
        self.table.item(r, 2).setText(text)
        if tip:
            self.table.item(r, 2).setToolTip(tip)
        QApplication.processEvents()

    def _progress_for(self, title: str):
        def cb(i: int, n: int) -> bool:
            self.bar.setMaximum(max(1, n)); self.bar.setValue(i)
            self.status.setText(tr("{t}: pagina {i} di {n}").format(t=title, i=min(i + 1, n), n=n))
            QApplication.processEvents()
            return not self.cancelled
        return cb

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
        s.setValue("ocr/langs", self.langs.value()); s.setValue("ocr/only_missing", self.only_missing.isChecked())
        s.setValue("ocr/dpi", self.dpi.currentData()); s.setValue("ocr/suffix", self.suffix.text())
        s.setValue("ocr/folder", self.folder.text().strip()); s.setValue("ocr/overwrite", self.overwrite.isChecked())

    def run(self) -> None:
        if not self.items:
            QMessageBox.information(self, tr("OCR"), tr("Aggiungi almeno un PDF.")); return
        if not ocr.languages() and not ensure_languages(self):
            return
        if not ocr.languages():
            return
        self.langs.fill(self.langs.value())
        langs = self.langs.value()
        if not langs:
            QMessageBox.information(self, tr("OCR"), tr("Scegli almeno una lingua per l'OCR")); return
        sfx = self.suffix.text().strip()
        folder = self.folder.text().strip()
        if not sfx and not folder:
            QMessageBox.information(self, tr("OCR"), tr("Indica un suffisso o una cartella diversa: i file originali non vengono sovrascritti."))
            return
        self._store()
        opts = dict(only_missing=self.only_missing.isChecked(), dpi=self.dpi.currentData())
        self.running = True; self.cancelled = False
        for w in (self.b_go, self.b_add, self.b_del):
            w.setEnabled(False)
        self.b_close.setText(tr("Annulla")); self.bar.setVisible(True)
        self.results = []
        try:
            for r, it in enumerate(self.items):
                if self.cancelled:
                    break
                self._set_state(r, tr("Riconoscimento…"))
                cb = self._progress_for(it["title"])
                try:
                    # sempre un nuovo file «nome<suffisso>.pdf»; il documento aperto (con le modifiche non salvate)
                    # si riconosce dalla memoria e il risultato si apre in una scheda accanto
                    if it["current"]:
                        data_in = it["pdf"].current_bytes()
                        base = it["path"] or os.path.join(folder or str(settings().value("lastdir", "")) or os.path.expanduser("~"),
                                                          tr("documento") + ".pdf")
                    else:
                        with open(it["path"], "rb") as fh:
                            data_in = fh.read()
                        base = it["path"]
                    out = ocr.output_name(base, sfx, folder, self.overwrite.isChecked())
                    if it["path"] and os.path.abspath(out) == os.path.abspath(it["path"]):
                        raise ocr.OcrError(tr("Il file di uscita deve essere diverso dall'originale"))
                    data, rep = ocr.ocr_bytes(data_in, langs, progress=cb, **opts)
                    from .compress import write_atomic
                    os.makedirs(os.path.dirname(out), exist_ok=True)
                    write_atomic(out, data)
                    if it["current"] and self.on_newfile:
                        self.on_newfile(out, data)
                    self.results.append((r, out, rep))
                    self._set_state(r, tr("Fatto") if not rep.errors else tr("Fatto, con errori"), (out or "") + "\n" + rep.text())
                except Exception as e:  # noqa: BLE001
                    self.results.append((r, None, e))
                    self._set_state(r, tr("Annullato") if str(e) == tr("Operazione annullata") else tr("Errore"), str(e))
                    if str(e) == tr("Operazione annullata"):
                        break
            self._summary()
        finally:
            self.running = False
            for w in (self.b_go, self.b_add, self.b_del):
                w.setEnabled(True)
            self.b_close.setText(tr("Chiudi")); self.bar.setVisible(False)

    def _summary(self) -> None:
        ok = [x for x in self.results if not isinstance(x[2], Exception)]
        bad = [x for x in self.results if isinstance(x[2], Exception)]
        lines = [tr("{n} documenti elaborati, {e} con errori.").format(n=len(ok), e=len(bad))]
        for r, out, rep in ok:
            lines.append(f"• {self.items[r]['title']}" + (f" → {os.path.basename(out)}" if out else "") + ": " + rep.text())
        for r, _out, e in bad:
            lines.append(f"• {self.items[r]['title']}: {e}")
        self.status.setText("\n".join(lines))
