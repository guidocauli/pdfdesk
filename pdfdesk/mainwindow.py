# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# mainwindow.py: finestra principale, strumenti, flussi di salvataggio e firma.
from __future__ import annotations

import os
from typing import Optional

import pymupdf as fitz
from PySide6.QtCore import QEventLoop, QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QFont, QIcon, QActionGroup, QColor, QImage, QKeySequence, QPixmap
from PySide6.QtWidgets import (QApplication, QDockWidget, QMenu, QProgressDialog, QTabBar, QSpinBox, QToolButton, QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel,
                               QLineEdit, QMainWindow, QMessageBox, QPushButton, QToolBar, QVBoxLayout, QWidget,
                               QComboBox)

from . import AUTHOR, CREDITS, VERSION_LINE, compress, fonts, pdfstd, signing, sigstore
from .core import PasswordRequired, PdfDocument, PdfError, T_FREETEXT, T_STAMP, to_page_rect
from .inmenu import InMenuBar, wayland_session
from .dialogs import (AboutDialog, ImageDialog, MergeDialog, ScanDialog, ExportDialog, ExtractImagesDialog, ImageOutDialog, MetadataDialog, FieldTextDialog, StandardDialog, PropertiesPanel, SaveDialog, SignatureLibraryDialog, SignDialog, TextDialog,
                      ThumbPanel, VerifyDialog, CertDialog, PreferencesDialog, settings)
from .icons import app_icon, icon
from .view import DocView, grid_from_settings, pix_to_qimage
from . import export as exporter
from . import imgutil
from . import extract as extractor
from .i18n import tr

TOOLS = [  # chiave, etichetta, scorciatoia, suggerimento
    ("select", tr("Seleziona"), "V", tr("Seleziona, sposta e ridimensiona annotazioni (doppio clic sul testo per modificarlo)")),
    ("editobj", tr("Modifica oggetti"), "J", tr("Seleziona con il mouse caselle di testo, immagini e grafica già presenti nel PDF: sposta, ridimensiona, elimina; doppio clic sul testo per riscriverlo")),
    ("hand", tr("Mano"), "H", tr("Trascina la pagina")),
    ("textsel", tr("Copia testo"), "T", tr("Trascina su un testo per copiarlo negli appunti")),
    None,
    ("pen", tr("Penna"), "P", tr("Disegno a mano libera")),
    ("highlighter", tr("Evidenziatore"), "E", tr("Evidenziatore a mano libera")),
    ("hl", tr("Evidenzia testo"), "", tr("Evidenzia il testo trascinando sull'area")),
    ("ul", tr("Sottolinea testo"), "", tr("Sottolinea il testo trascinando sull'area")),
    ("st", tr("Barra testo"), "", tr("Barra il testo trascinando sull'area")),
    None,
    ("rect", tr("Rettangolo/cornice"), "R", tr("Cornice o area colorata (trascina)")),
    ("ellipse", tr("Ellisse"), "O", tr("Ellisse o area ovale (trascina)")),
    ("line", tr("Linea"), "L", tr("Linea (trascina)")),
    ("arrow", tr("Freccia"), "A", tr("Freccia (trascina)")),
    ("text", tr("Casella di testo"), "X", tr("Casella di testo (trascina o clicca)")),
    ("form", tr("Compila modulo"), "K", tr("Clicca sui campi del modulo per compilarli")),
    ("edittext", tr("Modifica testo"), "M", tr("Clicca su un blocco di testo del PDF per riscriverlo")),
    None,
    ("image", tr("Immagine"), "I", tr("Inserisci un'immagine (clicca o trascina)")),
    ("sign", tr("Firma olografica"), "F", tr("Inserisci la firma come immagine (clicca o trascina)")),
    ("grab", tr("Estrai immagine/area"), "", tr("Clicca su un'immagine del PDF per salvarla, oppure trascina su un'area (testo, grafica e immagini) per salvarla come JPG, TIFF o PNG")),
    ("redact", tr("Redazione"), "D", tr("Clicca un oggetto o trascina un'area da oscurare in modo permanente")),
    ("eraser", tr("Gomma"), "G", tr("Clicca su un'annotazione per eliminarla")),
]
TOOL_STYLE = {"pen": "pen", "highlighter": "highlighter", "rect": "shape", "ellipse": "shape", "line": "shape",
              "arrow": "shape", "text": "text"}


class MainWindow(QMainWindow):
    def __init__(self, path: Optional[str] = None) -> None:
        super().__init__()
        self.setWindowIcon(app_icon())
        self.resize(1280, 860)
        self.setAcceptDrops(True)
        self.pdf: Optional[PdfDocument] = None
        self.docs: list[PdfDocument] = []              # documenti aperti, nello stesso ordine delle schede
        self._tab_lock = False
        self.tool = "select"
        self.current_signature: Optional[str] = None
        self.pending_sign = None
        self.pending_std = (None, None)
        self.found: list = []
        self.found_idx = -1
        self.styles = {
            "pen": {"pen": (0.05, 0.1, 0.55), "width": 2.0, "opacity": 1.0},
            "highlighter": {"pen": (1.0, 0.9, 0.0), "width": 14.0, "opacity": 0.45},
            "shape": {"pen": (0.8, 0.0, 0.0), "fill": None, "width": 2.0, "opacity": 1.0},
            "text": {"pen": (0.0, 0.0, 0.0), "fill": None, "width": 0.0, "opacity": 1.0, "fontsize": 12.0, "fontname": "helv"},
        }
        self._thumb_queue: list[int] = []
        fonts.start_system_scan()                      # scansione dei font di sistema in background
        self._thumb_timer = QTimer(self)
        self._thumb_timer.setInterval(15)
        self._thumb_timer.timeout.connect(self._thumb_step)

        self.view = DocView()
        self.banner = self._make_banner()
        central = QWidget()
        lay = QVBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.tabbar = QTabBar()
        self.tabbar.setTabsClosable(True)
        self.tabbar.setMovable(True)
        self.tabbar.setDocumentMode(True)
        self.tabbar.setExpanding(False)
        self.tabbar.setUsesScrollButtons(True)
        self.tabbar.setElideMode(Qt.ElideMiddle)
        self.tabbar.setVisible(False)
        self.tabbar.currentChanged.connect(self._on_tab_changed)
        self.tabbar.tabCloseRequested.connect(self._on_tab_close)
        self.tabbar.tabMoved.connect(self._on_tab_moved)
        lay.addWidget(self.tabbar)
        lay.addWidget(self.banner)
        lay.addWidget(self.view, 1)
        lay.addWidget(self._make_findbar())
        self.setCentralWidget(central)

        self.thumbs = ThumbPanel()
        d = QDockWidget(tr("Miniature"), self)
        d.setObjectName("dockPages")
        d.setWidget(self.thumbs)
        self.addDockWidget(Qt.LeftDockWidgetArea, d)
        self.dock_pages = d
        self.props = PropertiesPanel(compact=True)

        self._build_actions()
        self._build_menus()
        self._build_toolbars()

        self.lbl_page = QLabel("")
        self.lbl_zoom = QLabel("")
        self.statusBar().addPermanentWidget(self.lbl_page)
        self.statusBar().addPermanentWidget(self.lbl_zoom)

        v_ = self.view
        v_.rectDrawn.connect(self.on_rect)
        v_.textFlowDrawn.connect(self.on_text_flow)
        v_.strokeDrawn.connect(self.on_stroke)
        v_.lineDrawn.connect(self.on_line)
        v_.pointClicked.connect(self.on_click)
        v_.contextRequested.connect(self.on_context)
        v_.selectionChanged.connect(self.on_selection)
        v_.transformRequested.connect(self.on_transform)
        v_.multiMoveRequested.connect(self.on_multi_move)
        v_.annotDoubleClicked.connect(self.on_double)
        v_.fieldClicked.connect(self.on_field)
        v_.deleteRequested.connect(self.delete_selection)
        v_.contentSelected.connect(self.on_content_selected)
        v_.contentTransformRequested.connect(self.on_content_transform)
        v_.contentDoubleClicked.connect(self.on_content_double)
        v_.currentPageChanged.connect(self.on_page_changed)
        v_.zoomChanged.connect(lambda z: self.lbl_zoom.setText(f"{z * 100:.0f}%"))
        self.thumbs.pageSelected.connect(lambda i: self.view.go_to_page(i))
        self.thumbs.pageMoved.connect(self.on_thumb_moved)
        self.thumbs.action.connect(self.on_thumb_action)
        self.props.changed.connect(self.on_props_changed)

        self.set_tool("select")
        self._refresh_ui()
        s = settings()
        self.dock_pages.setVisible(str(s.value("view/thumbs", "true")).lower() == "true")
        self.apply_prefs(relayout=True)
        if s.value("geometry"):
            self.restoreGeometry(s.value("geometry"))
        if s.value("windowState2"):
            self.restoreState(s.value("windowState2"))
        self.apply_prefs()
        if path:
            paths = [path] if isinstance(path, str) else list(path)
            QTimer.singleShot(0, lambda: [self.open_path(p) for p in paths])

    # ================================================================== costruzione UI
    def _make_banner(self) -> QFrame:
        f = QFrame()
        f.setStyleSheet("QFrame { background: #fff3cd; border-bottom: 1px solid #e0c36a; } QLabel { color: #5a4500; }")
        h = QHBoxLayout(f)
        h.setContentsMargins(10, 4, 10, 4)
        self.banner_lbl = QLabel("")
        self.banner_lbl.setWordWrap(True)
        h.addWidget(self.banner_lbl, 1)
        b = QPushButton(tr("Verifica firme"))
        b.clicked.connect(self.verify_signatures)
        h.addWidget(b)
        f.hide()
        return f

    def _make_findbar(self) -> QWidget:
        self.findbar = QFrame()
        h = QHBoxLayout(self.findbar)
        h.setContentsMargins(6, 3, 6, 3)
        h.addWidget(QLabel(tr("Cerca:")))
        self.find_edit = QLineEdit()
        self.find_edit.returnPressed.connect(self.find_run)
        h.addWidget(self.find_edit, 1)
        for text, fn in (("◀", lambda: self.find_step(-1)), ("▶", lambda: self.find_step(1))):
            b = QPushButton(text)
            b.setFixedWidth(34)
            b.clicked.connect(fn)
            h.addWidget(b)
        self.find_lbl = QLabel("")
        h.addWidget(self.find_lbl)
        c = QPushButton("✕")
        c.setFixedWidth(30)
        c.clicked.connect(self.find_close)
        h.addWidget(c)
        self.findbar.hide()
        return self.findbar

    def _act(self, text: str, slot, shortcut: str = "", tip: str = "", icon_name: str = "") -> QAction:
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        clean = text.replace("&", "").rstrip("…").strip()
        a.setToolTip(clean + (f" ({shortcut})" if shortcut else "") + (f"\n{tip}" if tip else ""))
        if tip:
            a.setStatusTip(tip)
        if icon_name:
            a.setIcon(icon(icon_name))
        a.triggered.connect(lambda _=False: slot())
        return a

    def _build_actions(self) -> None:
        A = self._act
        self.a_open = A(tr("&Apri…"), self.open_dialog, tr("Ctrl+O"))
        self.a_save = A(tr("&Salva"), self.save, tr("Ctrl+S"))
        self.a_saveas = A(tr("Salva con nome / &Ottimizza…"), self.save_as, tr("Ctrl+Shift+S"),
                          tr("Salva scegliendo qualità e compressione"))
        self.a_close = A(tr("&Chiudi"), self.close_doc, tr("Ctrl+W"))
        self.a_quit = A(tr("&Esci"), self.close, tr("Ctrl+Q"))
        self.a_new = A(tr("&Nuovo PDF vuoto"), self.new_doc, tr("Ctrl+N"))
        self.a_meta = A(tr("&Metadati del documento…"), self.edit_metadata, tr("Ctrl+D"), tr("Visualizza, modifica e aggiungi i metadati (titolo, autore, campi personalizzati, XMP)"))
        self.a_extract_imgs = A(tr("Estrai tutte le &immagini…"), self.extract_images, "", tr("Elenca le immagini incorporate nel PDF e salvale in JPG, TIFF o PNG"))
        self.a_merge = A(tr("&Unisci PDF…"), self.merge_dialog, "", tr("Unisce più PDF (e immagini) in un unico PDF, nell'ordine che scegli"))
        self.a_scan = A(tr("Crea PDF da &scansione…"), self.scan_dialog, "", tr("Acquisisce pagine da uno scanner (WIA, SANE) o da immagini e crea un PDF"))
        self.a_print = A(tr("&Stampa…"), self.print_doc, tr("Ctrl+P"), tr("Stampa il documento (tutte le pagine o un intervallo)"))
        self.a_export = A(tr("&Esporta…"), lambda: self.export_doc(None), tr("Ctrl+Shift+E"),
                          tr("Esporta come immagini (PNG, JPG, TIFF), testo, Word (DOCX) o OpenDocument (ODT)"))
        self.a_closeall = A(tr("Chiudi &tutti"), self.close_all, "", tr("Chiude tutte le schede"))
        self.a_nexttab = A(tr("Scheda successiva"), lambda: self._step_tab(1), tr("Ctrl+Tab"))
        self.a_prevtab = A(tr("Scheda precedente"), lambda: self._step_tab(-1), tr("Ctrl+Shift+Tab"))
        self.export_actions = {}
        for key, (label, _ext) in exporter.FORMATS.items():
            a = QAction(label + "…", self)
            a.setToolTip(tr("Esporta: ") + label)
            a.triggered.connect(lambda _=False, k=key: self.export_doc(k))
            self.export_actions[key] = a
        self.a_undo = A(tr("&Annulla"), self.undo, tr("Ctrl+Z"))
        self.a_redo = A(tr("&Ripristina"), self.redo, tr("Ctrl+Y"))
        self.a_del = A(tr("&Elimina selezione"), self.delete_selection, "")
        self.a_apply_red = A(tr("Applica &redazioni (permanente)…"), self.apply_redactions, tr("Ctrl+Shift+R"))
        self.a_group = A(tr("&Raggruppa"), lambda: self.group_selection(), tr("Ctrl+G"), tr("Raggruppa gli oggetti selezionati: si selezionano e si spostano insieme"))
        self.a_ungroup = A(tr("&Separa il gruppo"), lambda: self.ungroup_selection(), tr("Ctrl+Shift+G"), tr("Separa gli oggetti del gruppo selezionato"))
        self.a_imgprops = A(tr("Proprietà &immagine…"), lambda: self.image_properties(), "", tr("Dimensioni numeriche, proporzioni, rotazione, sostituzione ed esportazione dell'immagine selezionata"))
        self.a_standard = A(tr("Conformità PDF/&A e PDF/X…"), self.standard_dialog, "",
                            tr("Verifica e converte a PDF/A (archiviazione) e PDF/X (stampa)"))
        self.a_flatten = A(tr("&Appiattisci campi del modulo…"), self.flatten_forms, "",
                           tr("Rende il contenuto dei campi parte della pagina (non più modificabile)"))
        self.a_formtool = A(tr("&Compila modulo"), lambda: self.set_tool("form"), "", tr("Clicca sui campi per compilarli"))
        self.a_showfields = A(tr("Evidenzia i campi del modulo"), self.toggle_fields, "")
        self.a_showfields.setCheckable(True); self.a_showfields.setChecked(True)
        self.a_gridshow = A(tr("Mostra la griglia"), lambda: self._toggle_grid("grid/show", self.a_gridshow), "", tr("Mostra la griglia (passo impostato in Preferenze)"))
        self.a_gridsnap = A(tr("Aggancia alla griglia"), lambda: self._toggle_grid("grid/snap", self.a_gridsnap), "", tr("Spostando o ridimensionando gli oggetti, gli spigoli si agganciano agli incroci della griglia"))
        for a_ in (self.a_gridshow, self.a_gridsnap):
            a_.setCheckable(True)
        self.a_find = A(tr("&Cerca…"), self.find_open, tr("Ctrl+F"))
        self.a_find_next = A(tr("Cerca successivo"), lambda: self.find_step(1), tr("F3"))
        self.a_find_prev = A(tr("Cerca precedente"), lambda: self.find_step(-1), tr("Shift+F3"))
        self.a_zin = A(tr("Ingrandisci"), lambda: self.view.set_zoom(self.view.zoom * 1.2), tr("Ctrl++"))
        self.a_zout = A(tr("Riduci"), lambda: self.view.set_zoom(self.view.zoom / 1.2), tr("Ctrl+-"))
        self.a_z100 = A(tr("Dimensione reale (100%)"), lambda: self.view.set_zoom(1.0), tr("Ctrl+1"))
        self.a_fitw = A(tr("Adatta alla larghezza"), self.view.fit_width, tr("Ctrl+2"))
        self.a_fitp = A(tr("Adatta alla pagina"), self.view.fit_page, tr("Ctrl+3"))
        self.a_rotl = A(tr("Ruota a sinistra"), lambda: self.rotate(-90), tr("Ctrl+Shift+L"))
        self.a_rotr = A(tr("Ruota a destra"), lambda: self.rotate(90), tr("Ctrl+Shift+R") if False else tr("Ctrl+Shift+Right"))
        self.a_deletep = A(tr("Elimina pagina corrente"), lambda: self.page_action("delete", [self.view.current_page()]))
        self.a_dup = A(tr("Duplica pagina"), lambda: self.page_action("dup", [self.view.current_page()]))
        self.a_blank = A(tr("Inserisci pagina vuota dopo"), lambda: self.page_action("blank", [self.view.current_page()]))
        self.a_insert = A(tr("Inserisci pagine da PDF…"), lambda: self.page_action("insert", [self.view.current_page()]))
        self.a_extract = A(tr("Estrai pagina corrente in nuovo PDF…"), lambda: self.page_action("extract", [self.view.current_page()]))
        self.a_sigimg = A(tr("Firma &olografica (immagine)…"), self.pick_signature, "", tr("Scegli o crea una firma-immagine e inseriscila"))
        self.a_sigdraw = A(tr("Gestisci firme olografiche…"), self.manage_signatures)
        self.a_sigdig = A(tr("Firma &digitale (PAdES)…"), self.sign_digital, tr("Ctrl+Shift+D"))
        self.a_verify = A(tr("&Verifica firme…"), self.verify_signatures)
        self.a_cert = A(tr("Crea certificato autofirmato…"), self.create_cert)
        self.a_about = A(tr("&Informazioni"), lambda: AboutDialog(self).exec())
        self.a_prefs = A(tr("&Preferenze…"), self.preferences, tr("Ctrl+,"), tr("Opzioni principali del programma"))
        self.a_prevp = A(tr("Pagina precedente"), lambda: self._goto(self.view.current_page() - 1), "", tr("Vai alla pagina precedente"))
        self.a_nextp = A(tr("Pagina successiva"), lambda: self._goto(self.view.current_page() + 1), "", tr("Vai alla pagina successiva"))
        for act, nm in ((self.a_open, "open"), (self.a_merge, "merge"), (self.a_scan, "scan"), (self.a_extract_imgs, "export"), (self.a_meta, "info"), (self.a_print, "print"), (self.a_export, "export"), (self.a_closeall, "close"),
                        (self.a_nexttab, "next"), (self.a_prevtab, "prev"), (self.a_save, "save"), (self.a_saveas, "saveas"), (self.a_close, "close"),
                        (self.a_new, "new"), (self.a_undo, "undo"), (self.a_redo, "redo"), (self.a_del, "trash"),
                        (self.a_apply_red, "applyred"), (self.a_imgprops, "image"), (self.a_group, "group"), (self.a_ungroup, "ungroup"), (self.a_standard, "std"), (self.a_flatten, "flatten"),
                        (self.a_formtool, "edittext"), (self.a_find, "find"), (self.a_zin, "zin"), (self.a_zout, "zout"),
                        (self.a_z100, "z100"), (self.a_fitw, "fitw"), (self.a_fitp, "fitp"), (self.a_rotl, "rotl"),
                        (self.a_rotr, "rotr"), (self.a_deletep, "trash"), (self.a_dup, "dup"), (self.a_blank, "blank"),
                        (self.a_insert, "insert"), (self.a_extract, "extract"), (self.a_sigimg, "sign"),
                        (self.a_sigdraw, "sigmanage"), (self.a_sigdig, "sigdig"), (self.a_verify, "verify"),
                        (self.a_cert, "cert"), (self.a_about, "info"), (self.a_prefs, "prefs"), (self.a_prevp, "prev"),
                        (self.a_nextp, "next")):
            act.setIcon(icon(nm))
        self.a_sigimg.setToolTip(tr("Firma olografica (immagine)\nScegli o crea una firma-immagine e inseriscila"))
        self.a_sigdig.setToolTip(tr("Firma digitale PAdES (Ctrl+Shift+D)\nFile .p12 o smart card"))
        self.a_apply_red.setToolTip(tr("Applica redazioni (Ctrl+Shift+R)\nOscura in modo permanente le aree segnate"))
        self.a_deletep.setText(tr("Elimina pagina corrente"))
        self.tool_actions: dict[str, QAction] = {}

    def _build_menus(self) -> None:
        mb = InMenuBar(self)
        self.setMenuBar(mb)
        self.menus = mb.mgr
        mb.setNativeMenuBar(False)          # i menu si aprono dalla barra del menu della finestra, non dalla barra di sistema
        self.menu_zoom = QMenu(tr("&Ingrandimento"), self)
        self.menu_zoom.setIcon(icon("zoom"))
        for pct in (25, 50, 75, 100, 125, 150, 200, 300, 400, 800):
            self.menu_zoom.addAction(f"{pct}%", lambda _=False, p=pct: self.view.set_zoom(p / 100))
        self.menu_zoom.addSeparator()
        for a in (self.a_fitw, self.a_fitp):
            self.menu_zoom.addAction(a)
        self.menu_zoom.addSeparator()
        for a in (self.a_zin, self.a_zout):
            self.menu_zoom.addAction(a)
        self.menu_zoom.addAction(tr("Altro…"), self.zoom_custom)
        m = mb.addMenu(tr("&File"))
        self.menu_recent = m.addMenu(tr("Apri recenti"))
        m.insertAction(self.menu_recent.menuAction(), self.a_open)
        m.addAction(self.a_new)
        m.addAction(self.a_scan)
        m.addAction(self.a_merge)
        m.addSeparator()
        for a in (self.a_save, self.a_saveas, self.a_standard):
            m.addAction(a)
        m.addSeparator()
        m.addAction(self.a_meta)
        m.addSeparator()
        m.addAction(self.a_print)
        self.menu_export = m.addMenu(tr("Esporta"))
        self.menu_export.setIcon(icon("export"))
        for a in self.export_actions.values():
            self.menu_export.addAction(a)
        m.addSeparator()
        m.addAction(self.a_close)
        m.addAction(self.a_closeall)
        m.addAction(self.a_quit)
        m = mb.addMenu(tr("&Modifica"))
        for a in (self.a_undo, self.a_redo):
            m.addAction(a)
        m.addSeparator()
        for a in (self.a_del, self.a_group, self.a_ungroup, self.a_imgprops, self.a_apply_red):
            m.addAction(a)
        m.addSeparator()
        for a in (self.a_find, self.a_find_next, self.a_find_prev):
            m.addAction(a)
        m.addSeparator()
        m.addAction(self.a_prefs)
        m = mb.addMenu(tr("&Visualizza"))
        m.addMenu(self.menu_zoom)
        m.addAction(self.a_z100)
        m.addSeparator()
        m.addAction(self.a_nexttab)
        m.addAction(self.a_prevtab)
        m.addSeparator()
        m.addAction(self.dock_pages.toggleViewAction())
        self.menu_bars = m.addMenu(tr("Barre degli strumenti"))
        m = mb.addMenu(tr("&Pagine"))
        for a in (self.a_rotl, self.a_rotr, self.a_dup, self.a_blank, self.a_insert, self.a_extract, self.a_deletep):
            m.addAction(a)
        m = mb.addMenu(tr("M&oduli"))
        m.addAction(self.a_formtool)
        m.addAction(self.a_showfields)
        m.addAction(self.a_gridshow)
        m.addAction(self.a_gridsnap)
        m.addSeparator()
        m.addAction(self.a_flatten)
        m = mb.addMenu(tr("&Firma"))
        for a in (self.a_sigimg, self.a_sigdraw):
            m.addAction(a)
        m.addSeparator()
        for a in (self.a_sigdig, self.a_verify, self.a_cert):
            m.addAction(a)
        m = mb.addMenu(tr("&Aiuto"))
        m.addAction(self.a_about)
        self._rebuild_recent()

    def _bar(self, title: str, name: str) -> QToolBar:
        tb = QToolBar(title, self)
        tb.setObjectName(name)
        tb.setToolTip(tr("Barra «{}» — trascina la maniglia a sinistra per spostarla").format(title))
        tb.setAllowedAreas(Qt.AllToolBarAreas)
        tb.orientationChanged.connect(lambda o, t=tb: self._bar_orientation(t, o))
        return tb

    def _bar_orientation(self, tb: QToolBar, o) -> None:
        """Barra agganciata ai lati: i widget (proprietà, pagina) si dispongono in colonna."""
        vertical = o == Qt.Vertical
        if tb.objectName() == "toolProps":
            self.props.set_vertical(vertical)
        elif tb.objectName() == "toolMain" and hasattr(self, "zoom_btn"):
            self.zoom_btn.setText(tr("Zoom ▾") if vertical else tr("Ingrandimento ▾"))
        tb.adjustSize()

    def _build_toolbars(self) -> None:
        # --- Principale
        main = self._bar(tr("Principale"), "toolMain")
        for a in (self.a_new, self.a_open, self.a_save, self.a_saveas, self.a_standard, self.a_print, self.a_export):
            main.addAction(a)
        main.addSeparator()
        for a in (self.a_undo, self.a_redo, self.a_find):
            main.addAction(a)
        main.addSeparator()
        main.addAction(self.a_zout)
        self.zoom_btn = QToolButton()
        self.zoom_btn.setIcon(icon("zoom"))
        self.zoom_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.zoom_btn.setText(tr("Ingrandimento ▾"))
        self.zoom_btn.setPopupMode(QToolButton.InstantPopup)
        self.zoom_btn.clicked.connect(lambda: self.menus.enabled and self.menus.open(
            self.menu_zoom, self.zoom_btn, self.zoom_btn.rect(), key=self.zoom_btn))
        self.zoom_btn.setToolTip(tr("Ingrandimento\nScegli una percentuale o adatta alla larghezza/pagina"))
        main.addWidget(self.zoom_btn)
        main.addAction(self.a_zin)
        main.addSeparator()
        for a in (self.a_sigimg, self.a_sigdig, self.a_verify, self.a_apply_red):
            main.addAction(a)
        main.addSeparator()
        main.addAction(self.a_prefs)
        # --- Pagine
        pages = self._bar(tr("Pagine"), "toolPages")
        pages.addAction(self.a_prevp)
        self.spin_page = QSpinBox()
        self.spin_page.setRange(0, 0)
        self.spin_page.setKeyboardTracking(False)
        self.spin_page.setToolTip(tr("Numero della pagina corrente: scrivi un numero per andarci"))
        self.spin_page.valueChanged.connect(lambda v: self._goto(v - 1) if self.pdf and v >= 1 else None)
        pages.addWidget(self.spin_page)
        self.lbl_total = QLabel(" / 0 ")
        self.lbl_total.setToolTip(tr("Pagine totali"))
        pages.addWidget(self.lbl_total)
        pages.addAction(self.a_nextp)
        pages.addSeparator()
        for a in (self.a_rotl, self.a_rotr, self.a_dup, self.a_blank, self.a_insert, self.a_extract, self.a_deletep):
            pages.addAction(a)
        pages.addSeparator()
        ta = self.dock_pages.toggleViewAction()
        ta.setIcon(icon("thumbs")); ta.setText(tr("Miniature")); ta.setToolTip(tr("Mostra/nascondi il pannello delle miniature"))
        pages.addAction(ta)
        # --- Strumenti (orizzontale)
        tools = self._bar(tr("Strumenti"), "toolTools")
        grp = QActionGroup(self)
        grp.setExclusive(True)
        for t in TOOLS:
            if t is None:
                tools.addSeparator()
                continue
            key, label, sc, tip = t
            a = QAction(icon(key), label, self)
            a.setCheckable(True)
            a.setToolTip(f"{label}" + (f" ({sc})" if sc else "") + f"\n{tip}")
            a.setStatusTip(tip)
            if sc:
                a.setShortcut(QKeySequence(sc))
            a.triggered.connect(lambda _=False, k=key: self.set_tool(k))
            grp.addAction(a)
            tools.addAction(a)
            self.tool_actions[key] = a
        # --- Proprietà
        propb = self._bar(tr("Proprietà"), "toolProps")
        propb.addWidget(self.props)
        self.bars = [main, pages, tools, propb]
        self._build_insert_menus()
        for tb in self.bars:
            self.addToolBar(Qt.TopToolBarArea, tb)
            self.menu_bars.addAction(tb.toggleViewAction())

    def _build_insert_menus(self) -> None:
        """Menu «Inserisci» e «Strumenti»: le stesse azioni (stesso stato) della barra Strumenti."""
        T = self.tool_actions
        ins = QMenu(tr("&Inserisci"), self)
        ins.setToolTipsVisible(True)
        for key in ("text", "image", "sign"):
            ins.addAction(T[key])
        ins.addAction(self.a_sigdig)
        ins.addSeparator()
        for key in ("rect", "ellipse", "line", "arrow"):
            ins.addAction(T[key])
        ins.addSeparator()
        for key in ("pen", "highlighter", "hl", "ul", "st"):
            ins.addAction(T[key])
        ins.addSeparator()
        ins.addAction(T["redact"])
        ins.addSeparator()
        for a in (self.a_blank, self.a_insert):
            ins.addAction(a)
        st = QMenu(tr("&Strumenti"), self)
        st.setToolTipsVisible(True)
        for key in ("select", "editobj", "edittext", "hand", "textsel", "form", "eraser"):
            st.addAction(T[key])
        st.addSeparator()
        st.addAction(T["grab"])
        st.addAction(self.a_extract_imgs)
        before = next((a for a in self.menuBar().actions() if a.text().replace("&", "") == tr("Pagine")), None)
        for mn in (ins, st):
            if before is not None:
                self.menuBar().insertMenu(before, mn)
            else:
                self.menuBar().addMenu(mn)
        self.menu_insert, self.menu_tools = ins, st

    def _apply_font(self, pct: int) -> None:
        """Dimensione del carattere dell'interfaccia (menu compresi) in percentuale di quella di sistema."""
        app = QApplication.instance()
        base = app.property("pdfdesk_base_font")
        if base is None:
            base = QFont(app.font()); app.setProperty("pdfdesk_base_font", base)
        f = QFont(base)
        size = base.pointSizeF() if base.pointSizeF() > 0 else 10.0
        f.setPointSizeF(max(6.0, size * max(70, min(200, pct)) / 100.0))
        app.setFont(f)
        self.menuBar().setFont(f)
        for mn in self.menuBar().findChildren(QMenu):
            mn.setFont(f)
        self.setFont(f)

    def apply_prefs(self, relayout: bool = False) -> None:
        s = settings()
        from . import theme
        theme.apply(QApplication.instance(), int(s.value("ui/theme", 0)))
        self._apply_font(int(s.value("ui/fontpct", 100)))
        mode = int(s.value("ui/inmenus", 0))                   # 0 automatico, 1 integrati, 2 standard di Qt
        self.menus.enabled = wayland_session() if mode == 0 else mode == 1
        self.zoom_btn.setMenu(None if self.menus.enabled else self.menu_zoom)
        px = (18, 22, 32)[max(0, min(2, int(s.value("ui/iconsize", 1))))]
        style = (Qt.ToolButtonIconOnly, Qt.ToolButtonTextBesideIcon, Qt.ToolButtonTextUnderIcon)[max(0, min(2, int(s.value("ui/btnstyle", 0))))]
        locked = str(s.value("ui/locked", "false")).lower() == "true"
        for tb in self.bars:
            tb.setIconSize(QSize(px, px))
            tb.setToolButtonStyle(style)
            tb.setMovable(not locked)
        self.zoom_btn.setIconSize(QSize(px, px))
        self.zoom_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        # la barra Proprietà e i controlli contengono widget: restano sempre a icone/testo propri
        self.a_showfields.setChecked(str(s.value("view/fields", "true")).lower() == "true")
        self.view.set_show_fields(self.a_showfields.isChecked())
        self.view.text_flow = str(s.value("view/textsel", "flow")) != "area"
        snap, show, gx, gy = grid_from_settings(s)
        self.a_gridsnap.setChecked(snap); self.a_gridshow.setChecked(show)
        self.view.set_grid(snap, show, gx, gy)
        if relayout:
            top = [tb for tb in self.bars if self.toolBarArea(tb) in (Qt.TopToolBarArea, Qt.NoToolBarArea)]
            for tb in top:
                if self.toolBarBreak(tb):
                    self.removeToolBarBreak(tb)
                self.removeToolBar(tb)
            mode = int(s.value("ui/rows", 0))
            if mode == 0:       # automatica: una riga solo se tutte le barre ci stanno
                need = sum(tb.sizeHint().width() for tb in top) + 40
                mode = 1 if need <= self.width() else 2
            for i, tb in enumerate(top):
                if i == 2 and mode == 2:
                    self.addToolBarBreak(Qt.TopToolBarArea)
                self.addToolBar(Qt.TopToolBarArea, tb)
                tb.show()
        self._rebuild_recent()

    def _toggle_grid(self, key: str, act) -> None:
        settings().setValue(key, act.isChecked())
        self.apply_prefs()

    def preferences(self) -> None:
        old_rows = int(settings().value("ui/rows", 0))
        old_lang = str(settings().value("ui/lang", "it"))
        dlg = PreferencesDialog(self)
        if dlg.exec():
            dlg.store()
            if str(settings().value("ui/lang", "it")) != old_lang:
                QMessageBox.information(self, tr("Lingua"), tr("La nuova lingua sarà applicata al prossimo avvio di PDFDesk."))
            self.apply_prefs(relayout=int(settings().value("ui/rows", 0)) != old_rows)
            self.msg(tr("Preferenze salvate."))

    def zoom_custom(self) -> None:
        v, ok = QInputDialog.getInt(self, tr("Ingrandimento"), tr("Percentuale:"), int(round(self.view.zoom * 100)), 10, 1600)
        if ok:
            self.view.set_zoom(v / 100)

    def _goto(self, pno: int) -> None:
        if self.pdf and 0 <= pno < self.pdf.page_count and pno != self.view.current_page():
            self.view.go_to_page(pno)

    # ================================================================== stato
    def _refresh_ui(self) -> None:
        has = self.pdf is not None
        for a in (self.a_save, self.a_saveas, self.a_close, self.a_find, self.a_zin, self.a_zout, self.a_z100, self.a_fitw,
                  self.a_fitp, self.a_rotl, self.a_rotr, self.a_deletep, self.a_dup, self.a_blank, self.a_insert,
                  self.a_extract, self.a_sigimg, self.a_sigdraw, self.a_sigdig, self.a_verify, self.a_apply_red, self.a_del, self.a_imgprops, self.a_group, self.a_ungroup,
                  self.a_prevp, self.a_nextp):
            a.setEnabled(has)
        self.spin_page.setEnabled(has); self.zoom_btn.setEnabled(has)
        # nessuno strumento (disegno, inserimento, modifica, moduli, firma…) è attivo senza un PDF aperto
        for a in list(self.tool_actions.values()) + [self.a_standard, self.a_flatten, self.a_formtool, self.a_showfields,
                                                      self.a_find_next, self.a_find_prev, self.a_print, self.a_export, self.a_meta, self.a_extract_imgs,
                                                      self.a_closeall, *self.export_actions.values()]:
            a.setEnabled(has)
        self.a_nexttab.setEnabled(len(self.docs) > 1); self.a_prevtab.setEnabled(len(self.docs) > 1)
        self.props.setEnabled(has)
        for mn in (self.menu_insert, self.menu_tools, self.menu_export):
            mn.menuAction().setEnabled(has)
        for mn in self.menuBar().actions():
            if mn.text().replace("&", "") in (tr("Pagine"), tr("Moduli")):
                mn.setEnabled(has)
        self._sync_tabs()
        self.a_undo.setEnabled(bool(has and self.pdf.can_undo))
        self.a_redo.setEnabled(bool(has and self.pdf.can_redo))
        self.a_undo.setToolTip(tr("Annulla"))
        name = os.path.basename(self.pdf.path) if has and self.pdf.path else (tr("Senza titolo") if has else "")
        mod = "*" if has and self.pdf.modified else ""
        self.setWindowTitle(tr("{}{} — PDFDesk").format(mod, name) if has else tr("PDFDesk"))
        if has and self.pdf.is_signed:
            self.banner_lbl.setText(tr("🔒 Questo PDF contiene {} firma/e digitale/i. Le modifiche vengono aggiunte come revisione successiva (le firme restano riconoscibili nella loro revisione); la compressione non è disponibile.").format(self.pdf.signed_count))
            self.banner.show()
        else:
            self.banner.hide()
        if has:
            self.lbl_page.setText(tr("Pagina {} / {}   ").format(self.view.current_page() + 1, self.pdf.page_count))
            self.spin_page.blockSignals(True)
            self.spin_page.setRange(1, self.pdf.page_count)
            self.spin_page.setValue(self.view.current_page() + 1)
            self.spin_page.blockSignals(False)
            self.lbl_total.setText(f" / {self.pdf.page_count} ")
        else:
            self.lbl_page.setText("")
            self.spin_page.blockSignals(True); self.spin_page.setRange(0, 0); self.spin_page.blockSignals(False)
            self.lbl_total.setText(" / 0 ")

    def _rebuild_recent(self) -> None:
        self.menu_recent.clear()
        for p in (settings().value("recent", []) or [])[:int(settings().value("recent_max", 10))]:
            if os.path.exists(p):
                self.menu_recent.addAction(os.path.basename(p), lambda _=False, pp=p: self.open_path(pp)).setToolTip(p)

    def _add_recent(self, path: str) -> None:
        s = settings()
        r = [p for p in (s.value("recent", []) or []) if p != path]
        s.setValue("recent", ([path] + r)[:int(s.value("recent_max", 10))])
        self._rebuild_recent()

    def msg(self, text: str, ms: int = 6000) -> None:
        self.statusBar().showMessage(text, ms)

    def changed(self, pages: Optional[list[int]] = None) -> None:
        """Dopo una modifica alle annotazioni: ridisegna le pagine toccate e le miniature."""
        if self.pdf and self.pdf.standard and not self.pdf.standard_warned:
            self.pdf.standard_warned = True
            self.msg(tr("⚠ Il documento è {}: le modifiche possono renderlo non conforme. Al salvataggio potrai ripristinare la conformità.").format(self.pdf.standard), 15000)
        if pages is None:
            self.view.refresh_all()
            self._queue_thumbs(None)
        else:
            for p in pages:
                self.view.refresh_page(p)
            self._queue_thumbs(pages)
        self._refresh_ui()

    def structural(self, keep_page: Optional[int] = None) -> None:
        """Dopo operazioni sulle pagine: ricostruisce vista e miniature."""
        cur = self.view.current_page() if keep_page is None else keep_page
        self.view.clear_selection()
        self.view.reload()
        self.thumbs.set_count(self.pdf.page_count)
        self._queue_thumbs(None)
        cur = min(cur, self.pdf.page_count - 1)
        QTimer.singleShot(0, lambda: self.view.go_to_page(cur))
        self._refresh_ui()

    # ================================================================== miniature
    def _queue_thumbs(self, pages: Optional[list[int]]) -> None:
        if not self.pdf:
            return
        n = self.pdf.page_count
        todo = list(range(n)) if pages is None else [p for p in pages if p < n]
        self._thumb_queue = todo + [p for p in self._thumb_queue if p not in todo]
        self._thumb_timer.start()

    def _thumb_step(self) -> None:
        if not self.pdf or not self._thumb_queue:
            self._thumb_timer.stop()
            return
        p = self._thumb_queue.pop(0)
        try:
            w, h = self.pdf.page_size(p)
            sc = min(300 / w, 420 / h)               # a risoluzione abbondante: il pannello la ridimensiona alla larghezza della colonna
            pm = QPixmap.fromImage(pix_to_qimage(self.pdf.render(p, sc)))
            from PySide6.QtGui import QPainter, QPen
            pt = QPainter(pm)
            pt.setPen(QPen(QColor(120, 120, 120), 1))
            pt.drawRect(0, 0, pm.width() - 1, pm.height() - 1)
            pt.end()
            canvas = pm
            self.thumbs.set_thumb(p, canvas)
        except Exception:
            pass

    # ================================================================== apertura / chiusura
    def dragEnterEvent(self, e) -> None:
        if e.mimeData().hasUrls() and any(u.toLocalFile().lower().endswith(".pdf") for u in e.mimeData().urls()):
            e.acceptProposedAction()

    def dropEvent(self, e) -> None:
        for u in e.mimeData().urls():
            if u.toLocalFile().lower().endswith(".pdf"):
                self.open_path(u.toLocalFile())

    def merge_dialog(self, files: Optional[list] = None, out: Optional[str] = None, items: Optional[list] = None,
                     bookmarks: bool = True, open_after: bool = True) -> Optional[str]:
        """Unione in batch. Con `items` e `out` lavora senza finestra (uso da script e test)."""
        from . import merge as mg
        if items is None:
            start = settings().value("lastdir", "")
            dlg = MergeDialog(self, files, os.path.join(start, "unito.pdf") if start else "")
            if dlg.exec() != MergeDialog.Accepted:
                return None
            items, out, bookmarks, open_after = dlg.items(), dlg.out_path, dlg.bookmarks.isChecked(), dlg.open_after.isChecked()
        pd, cb = self._progress(tr("Unione in corso…"), len(items))
        try:
            n = mg.merge_pdfs(items, out, bookmarks, cb)
        except Exception as e:
            pd.close()
            if str(e) != "Operazione annullata":
                QMessageBox.critical(self, tr("Unisci PDF"), tr("Unione non riuscita:\n{}").format(e))
            return None
        pd.close()
        settings().setValue("lastdir", os.path.dirname(out))
        self.msg(tr("Creato {} ({} pagine)").format(out, n), 10000)
        if open_after:
            self.open_path(out, force_new=True)
        return out

    def scan_dialog(self) -> Optional[str]:
        dlg = ScanDialog(self, os.path.join(settings().value("lastdir", os.path.expanduser("~")), "scansione.pdf"))
        if dlg.exec() != ScanDialog.Accepted:
            return None
        settings().setValue("lastdir", os.path.dirname(dlg.out_path))
        self.msg(tr("Creato {}").format(dlg.out_path), 10000)
        if dlg.open_after.isChecked():
            self.open_path(dlg.out_path, force_new=True)
        return dlg.out_path

    def open_dialog(self) -> None:
        start = settings().value("lastdir", "")
        paths, _ = QFileDialog.getOpenFileNames(self, tr("Apri PDF"), start, tr("PDF (*.pdf);;Tutti i file (*)"))
        for p in paths:
            self.open_path(p)

    # ---------------------------------------------------------------- schede
    def _doc_label(self, d: PdfDocument) -> str:
        return ("*" if d.modified else "") + (os.path.basename(d.path) if d.path else tr("Senza titolo"))

    def _sync_tabs(self) -> None:
        """Aggiorna titoli e suggerimenti delle schede (asterisco = modifiche non salvate)."""
        self._tab_lock = True
        try:
            for i, d in enumerate(self.docs):
                if i < self.tabbar.count():
                    self.tabbar.setTabText(i, self._doc_label(d).replace("&", "&&"))
                    self.tabbar.setTabToolTip(i, d.path or tr("Documento non ancora salvato"))
            self.tabbar.setVisible(bool(self.docs))
        finally:
            self._tab_lock = False

    def _save_tab_state(self) -> None:
        d = self.pdf
        if d is not None and d in self.docs:
            d._tab = {"zoom": self.view.zoom, "v": self.view.verticalScrollBar().value(),
                      "h": self.view.horizontalScrollBar().value()}

    def _on_tab_changed(self, i: int) -> None:
        if self._tab_lock or not (0 <= i < len(self.docs)) or self.docs[i] is self.pdf:
            return
        self._save_tab_state()
        self._activate(self.docs[i])

    def _on_tab_moved(self, frm: int, to: int) -> None:
        self.docs.insert(to, self.docs.pop(frm))

    def _step_tab(self, d: int) -> None:
        n = self.tabbar.count()
        if n > 1:
            self.tabbar.setCurrentIndex((self.tabbar.currentIndex() + d) % n)

    def _on_tab_close(self, i: int) -> None:
        if 0 <= i < len(self.docs):
            self._close_index(i)

    def _add_tab(self, doc: PdfDocument) -> None:
        self._save_tab_state()
        self.docs.append(doc)
        self._tab_lock = True
        try:
            i = self.tabbar.addTab(self._doc_label(doc).replace("&", "&&"))
            self.tabbar.setCurrentIndex(i)
        finally:
            self._tab_lock = False
        self._activate(doc, fresh=True)

    def _activate(self, doc: PdfDocument, fresh: bool = False) -> None:
        """Mostra `doc` (scheda attiva): vista, miniature, stato; una scheda già vista riprende zoom e posizione."""
        self.pdf = doc
        self.found = []
        self.found_idx = -1
        self._thumb_queue = []
        self.view.set_document(doc)
        self.thumbs.set_count(doc.page_count)
        self._queue_thumbs(None)
        self._refresh_ui()
        self.props.enable_for(self.tool)
        self.view.set_show_fields(self.a_showfields.isChecked())
        st = getattr(doc, "_tab", None)
        if st and not fresh:
            self.view.set_zoom(st["zoom"])
            QTimer.singleShot(0, lambda: (self.view.verticalScrollBar().setValue(st["v"]),
                                          self.view.horizontalScrollBar().setValue(st["h"])))
        else:
            zi = int(settings().value("view/initzoom", 0))
            if zi < 3:
                QTimer.singleShot(0, (self.view.fit_width, self.view.fit_page, lambda: self.view.set_zoom(1.0))[zi])
        if fresh:
            if doc.has_form():
                n = doc.count_fields()
                self.set_tool("form")
                self.msg(tr("Modulo con {} campi: clicca su un campo per compilarlo.").format(n), 10000)
            elif doc.is_signed:
                self.msg(tr("Documento firmato digitalmente ({} firme)").format(doc.signed_count))

    def _close_index(self, i: int, ask: bool = True) -> bool:
        """Chiude la scheda `i`; con `ask` chiede di salvare le modifiche."""
        doc = self.docs[i]
        if ask and doc.modified:
            if doc is not self.pdf:
                self.tabbar.setCurrentIndex(i)          # le azioni di salvataggio lavorano sul documento attivo
            if not self.confirm_discard():
                return False
        return self._remove_doc(doc)

    def _remove_doc(self, doc: PdfDocument) -> bool:
        i = self.docs.index(doc)
        was_active = doc is self.pdf
        self._tab_lock = True
        try:
            self.docs.pop(i)
            self.tabbar.removeTab(i)
        finally:
            self._tab_lock = False
        try:
            doc.close()
        except Exception:
            pass
        if was_active:
            if self.docs:
                self._activate(self.docs[min(i, len(self.docs) - 1)])
                self._tab_lock = True
                self.tabbar.setCurrentIndex(self.docs.index(self.pdf))
                self._tab_lock = False
            else:
                self.pdf = None
                self.found = []
                self.view.set_document(None)
                self.thumbs.set_count(0)
                self._refresh_ui()
        else:
            self._refresh_ui()
        return True

    def open_path(self, path: str, force_new: bool = False) -> bool:
        ap = os.path.abspath(path)
        if not force_new:
            for i, d in enumerate(self.docs):
                if d.path and os.path.abspath(d.path) == ap:      # già aperto: passa a quella scheda
                    self.tabbar.setCurrentIndex(i)
                    return True
        pw = None
        while True:
            try:
                doc = PdfDocument.open(path, pw)
                break
            except PasswordRequired:
                pw, ok = QInputDialog.getText(self, tr("PDF protetto"), tr("Password per {}:").format(os.path.basename(path)), QLineEdit.Password)
                if not ok:
                    return False
            except Exception as e:
                QMessageBox.critical(self, tr("Errore"), tr("Impossibile aprire il file:\n{}").format(e))
                return False
        self._add_tab(doc)
        settings().setValue("lastdir", os.path.dirname(path))
        self._add_recent(ap)
        return True

    def new_doc(self) -> None:
        self._add_tab(PdfDocument.new())

    def close_doc(self) -> None:
        if self.pdf is not None:
            self._close_index(self.docs.index(self.pdf))

    def close_all(self) -> bool:
        while self.docs:
            if not self._close_index(len(self.docs) - 1):
                return False
        return True

    def confirm_discard(self) -> bool:
        """Se il documento attivo ha modifiche non salvate chiede se salvarle."""
        if self.pdf and self.pdf.modified:
            r = QMessageBox.question(self, tr("Modifiche non salvate"),
                                     tr("«{}» ha modifiche non salvate. Salvarle?").format(self._doc_label(self.pdf).lstrip('*')),
                                     QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
            if r == QMessageBox.Cancel:
                return False
            if r == QMessageBox.Save:
                return self.save()
        return True

    def closeEvent(self, e) -> None:
        for i in range(len(self.docs) - 1, -1, -1):          # controlla tutte le schede con modifiche
            d = self.docs[i]
            if d.modified:
                self.tabbar.setCurrentIndex(i)
                if not self.confirm_discard():
                    e.ignore()
                    return
        s = settings()
        s.setValue("geometry", self.saveGeometry())
        s.setValue("windowState2", self.saveState())
        for d in self.docs:
            d.close()
        e.accept()

    # ================================================================== stampa ed esportazione
    def _progress(self, text: str, n: int) -> tuple:
        dlg = QProgressDialog(text, tr("Annulla"), 0, n, self)
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(400)
        dlg.setAutoClose(False); dlg.setAutoReset(False)

        def cb(i: int, total: int) -> bool:
            dlg.setMaximum(max(1, total)); dlg.setValue(i)
            QApplication.processEvents()
            return not dlg.wasCanceled()
        return dlg, cb

    def print_doc(self) -> None:
        if not self.pdf:
            return
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter
        from . import printing
        printer = QPrinter(QPrinter.HighResolution)
        printer.setDocName(self._doc_label(self.pdf).lstrip("*"))
        n = self.pdf.page_count
        printer.setFromTo(1, n)
        dlg = QPrintDialog(printer, self)
        dlg.setOption(QPrintDialog.PrintPageRange, True)
        dlg.setOption(QPrintDialog.PrintCurrentPage, True)
        dlg.setMinMax(1, n)
        dlg.setWindowTitle(tr("Stampa"))
        if dlg.exec() != QPrintDialog.Accepted:
            return
        if printer.printRange() == QPrinter.PageRange:
            pages = list(range(printer.fromPage() - 1, printer.toPage()))
        elif printer.printRange() == QPrinter.CurrentPage:
            pages = [self.view.current_page()]
        else:
            pages = list(range(n))
        self.print_pages_to(printer, pages)

    def print_pages_to(self, printer, pages: list[int]) -> bool:
        from . import printing
        pd, cb = self._progress(tr("Stampa in corso…"), len(pages))
        try:
            ok = printing.print_pages(self.pdf.doc, printer, pages, cb)
        except Exception as e:
            pd.close()
            QMessageBox.critical(self, tr("Stampa"), tr("Stampa non riuscita:\n{}").format(e))
            return False
        pd.close()
        self.msg(tr("Stampa inviata.") if ok else tr("Stampa annullata."))
        return ok

    def export_doc(self, fmt: Optional[str] = None) -> bool:
        if not self.pdf:
            return False
        s = settings()
        dlg = ExportDialog(self, self.pdf.page_count, self.view.current_page(), fmt or str(s.value("export/fmt", "png")))
        if fmt:
            dlg.fmt.setEnabled(False)
        if dlg.exec() != ExportDialog.Accepted:
            return False
        o = dlg.options()
        s.setValue("export/fmt", o["fmt"])
        return self.export_to(o)

    def export_to(self, o: dict, target: Optional[str] = None) -> bool:
        fmt, pages = o["fmt"], o["pages"]
        base = os.path.splitext(os.path.basename(self.pdf.path))[0] if self.pdf.path else "documento"
        start = settings().value("lastdir", os.path.expanduser("~"))
        image = fmt in ("png", "jpg", "tiff")
        one_file = not image or (fmt == "tiff" and o.get("tiff_multipage", True))
        if target is None:
            if one_file:
                label, ext = exporter.FORMATS[fmt]
                target, _ = QFileDialog.getSaveFileName(self, tr("Esporta come ") + label, os.path.join(start, base + ext),
                                                        f"{label} (*{ext})")
                if not target:
                    return False
                if not target.lower().endswith(ext) and not (fmt == "tiff" and target.lower().endswith(".tif")):
                    target += ext
            else:
                target = QFileDialog.getExistingDirectory(self, tr("Cartella in cui salvare le immagini"), start)
                if not target:
                    return False
        pd, cb = self._progress(tr("Esportazione in corso…"), len(pages))
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            out = exporter.export(self.pdf.doc, fmt, pages, target, progress=cb, **{k: v for k, v in o.items() if k not in ("fmt", "pages")})
        except exporter.Cancelled:
            self.msg(tr("Esportazione annullata."))
            return False
        except Exception as e:
            QMessageBox.critical(self, tr("Esporta"), tr("Esportazione non riuscita:\n{}").format(e))
            return False
        finally:
            QApplication.restoreOverrideCursor()
            pd.close()
        self.msg(tr("Esportato: {}").format(out[0] if len(out) == 1 else f'{len(out)} file in {target}'), 10000)
        return True

    # ================================================================== salvataggio
    def ask_keep_signatures(self) -> Optional[bool]:
        """Documento firmato con modifiche permanenti: True = salvataggio incrementale (firme conservate),
        False = riscrittura senza firme, None = annulla. Senza modifiche permanenti non chiede nulla (True)."""
        if not (self.pdf.is_signed and self.pdf.has_permanent_changes):
            return True
        box = QMessageBox(QMessageBox.Question, tr("Firme digitali"), "", parent=self)
        box.setText(tr("<b>Il documento firmato contiene modifiche permanenti.</b>"))
        box.setInformativeText(
            tr("<b>Mantieni le firme</b>: il file è salvato in modo incrementale; la firma resta valida per la revisione "
            "originale, ma i lettori PDF segnalano «modificato dopo la firma». Il contenuto eliminato, redatto o "
            "sostituito <b>resta recuperabile nel file</b>: non adatto alle redazioni.\n\n"
            "<b>Scarta le firme</b>: il file contiene soltanto il contenuto nuovo."))
        b_keep = box.addButton(tr("Mantieni le firme"), QMessageBox.AcceptRole)
        b_drop = box.addButton(tr("Scarta le firme"), QMessageBox.DestructiveRole)
        box.addButton(tr("Annulla"), QMessageBox.RejectRole)
        box.setDefaultButton(b_drop)
        box.setEscapeButton(box.buttons()[-1])
        box.exec()
        c = box.clickedButton()
        return True if c is b_keep else False if c is b_drop else None

    def confirm_permanent_overwrite(self) -> str:
        """Avviso prima di sovrascrivere il file originale con modifiche irreversibili.
        Restituisce «overwrite», «saveas» o «cancel»."""
        box = QMessageBox(QMessageBox.Warning, tr("Modifiche permanenti"), "", parent=self)
        box.setText(tr("<b>Stai per sovrascrivere il file originale con modifiche definitive.</b>"))
        box.setInformativeText(
            tr("Questo documento contiene redazioni o contenuti eliminati (testo, immagini, grafica): una volta salvato "
            "sopra l'originale, quei contenuti <b>non saranno più recuperabili</b>")
            + tr(".\n\n"
            "Si consiglia di usare <b>Salva con nome</b> per conservare l'originale."))
        b_as = box.addButton(tr("Salva con nome…"), QMessageBox.AcceptRole)
        b_ow = box.addButton(tr("Sovrascrivi l'originale"), QMessageBox.DestructiveRole)
        box.addButton(tr("Annulla"), QMessageBox.RejectRole)
        box.setDefaultButton(b_as)
        box.setEscapeButton(box.buttons()[-1])
        box.exec()
        c = box.clickedButton()
        return "saveas" if c is b_as else "overwrite" if c is b_ow else "cancel"

    def save(self) -> bool:
        if not self.pdf:
            return False
        if not self.pdf.path:
            return self.save_as()
        if self.pdf.has_permanent_changes and os.path.exists(self.pdf.path):
            c = self.confirm_permanent_overwrite()
            if c == "cancel":
                return False
            if c == "saveas":
                return self.save_as()
        if self.pdf.standard and self.pdf.modified and not self.pdf.is_signed:
            r = QMessageBox.question(self, tr("Standard ") + self.pdf.standard,
                                     tr("Il documento era {}: le modifiche possono averlo reso non conforme.\n\nVuoi ripristinare la conformità salvando? (le annotazioni vengono appiattite nella pagina)").format(self.pdf.standard),
                                     QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel, QMessageBox.Yes)
            if r == QMessageBox.Cancel:
                return False
            if r == QMessageBox.Yes:
                key = StandardDialog._key_for(self.pdf.standard)
                if key and self._write_standard(self.pdf.path, key, None):
                    return True
                if key is None:
                    QMessageBox.information(self, tr("Standard"), tr("Questo livello non è tra quelli convertibili: il file sarà salvato senza ripristino."))
                else:
                    return False
        keep = self.ask_keep_signatures()
        if keep is None:
            return False
        self.pdf.keep_signatures = keep
        try:
            compress.write_atomic(self.pdf.path, self.pdf.current_bytes())
        except Exception as e:
            QMessageBox.critical(self, tr("Salvataggio"), tr("Salvataggio non riuscito:\n{}").format(e))
            return False
        self.pdf.mark_saved(self.pdf.path)
        self.msg(tr("Salvato ") + self.pdf.path)
        self._refresh_ui()
        return True

    def save_as(self) -> bool:
        if not self.pdf:
            return False
        default = self.pdf.path or os.path.join(settings().value("lastdir", os.path.expanduser("~")), "documento.pdf")
        dlg = SaveDialog(self, default, self.pdf.is_signed, standard=self.pdf.standard, raw=lambda: self.pdf.doc.tobytes(garbage=0))
        if dlg.exec() != SaveDialog.Accepted:
            return False
        opts = dlg.options()
        out = dlg.path.text().strip()
        if (self.pdf.has_permanent_changes and self.pdf.path and os.path.abspath(out) == os.path.abspath(self.pdf.path)
                and os.path.exists(out)):
            c = self.confirm_permanent_overwrite()
            if c == "cancel":
                return False
            if c == "saveas":
                return self.save_as()
        keep_sig = True
        if self.pdf.is_signed and dlg.preserves_signatures():
            keep_sig = self.ask_keep_signatures()
            if keep_sig is None:
                return False
            self.pdf.keep_signatures = keep_sig
        try:
            if self.pdf.is_signed and dlg.preserves_signatures() and keep_sig:
                data = self.pdf.current_bytes()            # incrementale: firme intatte
                before = len(data)
            else:
                raw = self.pdf.doc.tobytes(garbage=0)
                if self.pdf.is_signed:                     # le firme si scartano solo a salvataggio riuscito (mark_saved)
                    cur = fitz.open("pdf", raw)
                    for page in cur:
                        for w in list(page.widgets() or []):
                            if w.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE:
                                page.delete_widget(w)
                    raw = cur.tobytes(garbage=0); cur.close()
                    self.pdf._pending_drop = True
                before = len(raw)
                opts.runner = self.run_bg
                data = compress.optimize_bytes(raw, opts)
            if os.path.abspath(out) == (self.pdf.path or ""):
                pass
            compress.write_atomic(out, data)
        except Exception as e:
            QMessageBox.critical(self, tr("Salvataggio"), tr("Salvataggio non riuscito:\n{}").format(e))
            return False
        self.pdf.mark_saved(out)
        self._after_standard_save(data)
        self._add_recent(os.path.abspath(out))
        self.msg(tr("Salvato {}: {} → {}").format(os.path.basename(out), compress.human_size(before), compress.human_size(len(data))), 10000)
        self._refresh_ui()
        return True

    def run_bg(self, fn, text: str = tr("Conversione in corso…")):
        """Esegue `fn` (solo codice che non tocca i documenti aperti: es. un sottoprocesso) in un thread, tenendo viva l'interfaccia."""
        import threading
        from PySide6.QtWidgets import QProgressDialog
        res: dict = {}

        def work():
            try:
                res["v"] = fn()
            except BaseException as e:   # noqa: BLE001
                res["e"] = e
        t = threading.Thread(target=work, daemon=True)
        t.start()
        dlg = QProgressDialog(text, None, 0, 0, self)
        dlg.setWindowTitle(tr("PDFDesk"))
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(300)
        dlg.setCancelButton(None)
        loop = QEventLoop()
        tm = QTimer()
        tm.timeout.connect(lambda: None if t.is_alive() else loop.quit())
        tm.start(40)
        if t.is_alive():
            loop.exec()
        tm.stop()
        dlg.close()
        if "e" in res:
            raise res["e"]
        return res["v"]

    def _after_standard_save(self, data: bytes) -> None:
        """Dopo un salvataggio: aggiorna lo standard dichiarato (il documento aperto resta quello modificabile)."""
        try:
            self.pdf.standard = pdfstd.detect(data)
            self.pdf.standard_warned = False
        except Exception:
            pass

    def _write_standard(self, out: str, key: str, icc) -> bool:
        try:
            raw = self.pdf.doc.tobytes(garbage=0)
            data = compress.optimize_bytes(raw, compress.SaveOptions("original", standard=key, icc=icc, runner=self.run_bg))
            rep = pdfstd.check(data, key)
            compress.write_atomic(out, data)
        except Exception as e:
            QMessageBox.critical(self, tr("Conversione"), tr("Conversione non riuscita:\n{}").format(e))
            return False
        self.pdf.mark_saved(out)
        self._after_standard_save(data)
        self._add_recent(os.path.abspath(out))
        self._refresh_ui()
        if rep.ok:
            self.msg(tr("Salvato come {} ({}), verifica superata.").format(pdfstd.STANDARDS[key].label, compress.human_size(len(data))), 10000)
        else:
            QMessageBox.warning(self, tr("Conformità"), tr("Il file è stato salvato ma la verifica segnala problemi:\n\n") + rep.text())
        return True

    def standard_dialog(self) -> None:
        if not self.pdf:
            return
        d = StandardDialog(self, lambda: self.pdf.current_bytes() if self.pdf.is_signed else self.pdf.doc.tobytes(garbage=0),
                           self.pdf.standard, self.pdf.is_signed)
        if d.exec() != StandardDialog.Accepted or not d.convert_requested:
            return
        key, icc = d.choice()
        base = self.pdf.path or os.path.join(settings().value("lastdir", os.path.expanduser("~")), "documento.pdf")
        default = os.path.splitext(base)[0] + "-" + key + ".pdf"
        out, _ = QFileDialog.getSaveFileName(self, tr("Salva convertito"), default, tr("PDF (*.pdf)"))
        if out:
            self._write_standard(out if out.lower().endswith(".pdf") else out + ".pdf", key, icc)

    # ================================================================== strumenti
    def set_tool(self, tool: str) -> None:
        self.tool = tool
        if tool in self.tool_actions:
            self.tool_actions[tool].setChecked(True)
        self.view.set_tool(tool)
        key = TOOL_STYLE.get(tool)
        if key:
            st = self.styles[key]
            self.view.style = {"pen": st["pen"], "width": st["width"], "opacity": st.get("opacity", 1.0)}
            self.props.load(st)
        if self.pdf is not None:
            self.props.enable_for(tool)
        hints = {"sign": tr("Clicca o trascina sulla pagina per inserire la firma."), "image": tr("Clicca o trascina per inserire un'immagine."),
                 "edittext": tr("Clicca su un blocco di testo del PDF per modificarlo."),
                 "editobj": tr("Clicca un testo, un'immagine o una grafica del PDF: trascinalo per spostarlo, usa le maniglie per ridimensionarlo, Canc per eliminarlo."), "redact": tr("Clicca un testo, un'immagine o una grafica per segnarli, oppure trascina per segnare un'area; poi Modifica → Applica redazioni."),
                 "textsel": tr("Trascina dal primo all'ultimo carattere per copiare il testo (anche su più righe); con Alt selezioni ad area."), "sigbox": tr("Trascina per disegnare il riquadro della firma digitale.")}
        self.msg(hints.get(tool, ""), 8000) if tool in hints else None
        if tool == "sign" and not self.current_signature:
            QTimer.singleShot(0, self.pick_signature)

    def style_for(self, tool: str) -> dict:
        return self.styles[TOOL_STYLE.get(tool, "shape")]

    def _fz(self, r: QRectF) -> fitz.Rect:
        return fitz.Rect(r.left(), r.top(), r.right(), r.bottom())

    def guard(self, fn, *a, **kw):
        """Esegue un'operazione sul documento mostrando gli errori in modo gentile."""
        try:
            return fn(*a, **kw)
        except PdfError as e:
            self.msg(str(e))
        except Exception as e:
            QMessageBox.warning(self, tr("Operazione non riuscita"), str(e))
        return None

    def on_stroke(self, tool: str, pno: int, pts: list) -> None:
        st = self.style_for(tool)
        x = self.guard(self.pdf.add_ink, pno, [pts], st["pen"], st["width"], st.get("opacity", 1.0), tool == "highlighter")
        if x is not None:
            self.changed([pno])

    def on_line(self, tool: str, pno: int, a: QPointF, b: QPointF) -> None:
        st = self.style_for(tool)
        x = self.guard(self.pdf.add_line, pno, (a.x(), a.y()), (b.x(), b.y()), st["pen"], st["width"], tool == "arrow", st.get("opacity", 1.0))
        if x is not None:
            self.changed([pno])

    def on_text_flow(self, tool: str, pno: int, a: QPointF, b: QPointF) -> None:
        """Selezione del testo a righe (dal punto iniziale al finale, anche su più righe)."""
        pa, pb = (a.x(), a.y()), (b.x(), b.y())
        if tool == "textsel":
            txt = self.pdf.text_between(pno, pa, pb)
            if txt:
                QApplication.clipboard().setText(txt)
                self.msg(tr("Copiati {} caratteri negli appunti").format(len(txt)))
            else:
                self.msg(tr("Nessun testo nella selezione"))
            return
        x = self.guard(self.pdf.add_markup_flow, pno, tool, pa, pb)
        if x is not None:
            self.changed([pno])

    def on_rect(self, tool: str, pno: int, r: QRectF) -> None:
        st = self.style_for(tool)
        fr = self._fz(r)
        if tool in ("rect", "ellipse"):
            x = self.guard(self.pdf.add_shape, pno, tool, fr, st["pen"], st.get("fill"), st["width"], st.get("opacity", 1.0))
        elif tool == "text":
            x = self.add_text_box(pno, fr)
        elif tool == "redact":
            x = self.guard(self.pdf.add_redact, pno, fr)
            if x is not None:
                self.msg(tr("Area di redazione segnata. Usa Modifica → Applica redazioni per oscurarla in modo permanente."), 9000)
        elif tool in ("hl", "ul", "st"):
            x = self.guard(self.pdf.add_markup, pno, tool, fr)
        elif tool == "textsel":
            txt = self.pdf.text_in_rect(pno, fr)
            if txt:
                QApplication.clipboard().setText(txt)
                self.msg(tr("Copiati {} caratteri negli appunti").format(len(txt)))
            else:
                self.msg(tr("Nessun testo nell'area"))
            return
        elif tool in ("image", "sign"):
            x = self.insert_image_at(tool, pno, r)
        elif tool == "sigbox":
            self.finish_visible_signature(pno, fr)
            return
        elif tool == "grab":
            self.grab_area(pno, fr)
            return
        else:
            return
        if x is not None:
            self.changed([pno])

    # ------------------------------------------------------------------ menu contestuale (tasto destro)
    # ------------------------------------------------------------------ selezione multipla e gruppi
    def _items_now(self) -> tuple:
        """(pagina, voci) della selezione corrente, singola o multipla."""
        v = self.view
        if v.sel_page < 0 or not self.pdf:
            return -1, []
        return v.sel_page, v._current_items(v.sel_page)

    def _reselect(self, pno: int, items: list) -> None:
        fresh = []
        for it in items:
            if it["kind"] == "annot":
                inf = self.pdf.annot_info(pno, it["xref"])
                if inf is not None:
                    fresh.append({"kind": "annot", "xref": it["xref"], "rect": fitz.Rect(inf.rect)})
            else:
                r = fitz.Rect(it["rect"])
                o = self.pdf.content_at(pno, (r.x0 + r.width / 2, r.y0 + r.height / 2))
                if o is not None:
                    fresh.append({"kind": "content", "obj": o, "rect": fitz.Rect(o["rect"])})
        self.view._apply_items(pno, fresh)

    def on_multi_move(self, pno: int, dx: float, dy: float) -> None:
        items = list(self.view.multi)
        done = []
        with self.pdf.batch(tr("sposta oggetti")):
            for it in items:
                r = fitz.Rect(it["rect"]) + (dx, dy, dx, dy)
                if it["kind"] == "annot":
                    inf = self.pdf.annot_info(pno, it["xref"])
                    if inf is None or not inf.movable:
                        done.append(it)
                        continue
                    nx = self.guard(self.pdf.set_rect, pno, it["xref"], r)
                    done.append({"kind": "annot", "xref": nx if nx is not None else it["xref"], "rect": r})
                else:
                    self.guard(self.pdf.move_content, pno, it["obj"], r)
                    done.append({"kind": "content", "obj": it["obj"], "rect": r})
        self.changed([pno])
        self._reselect(pno, done)

    def group_selection(self) -> None:
        pno, items = self._items_now()
        ok = [i for i in items if i["kind"] == "annot" or i["obj"]["kind"] == "image"]
        if len(ok) < 2:
            self.msg(tr("Seleziona almeno due oggetti (Ctrl+clic o trascina un rettangolo con lo strumento Modifica oggetti). "
                     "Testo e grafica del PDF non si possono raggruppare."), 9000)
            return
        skipped = len(items) - len(ok)
        xs = []
        try:
            with self.pdf.batch(tr("raggruppa")):
                for i in ok:
                    xs.append(i["xref"] if i["kind"] == "annot" else self.pdf.content_image_to_stamp(pno, i["obj"]))
                self.pdf.group_annots(pno, xs)
        except Exception as e:
            self.msg(str(e))
            return
        self.changed([pno])
        self.view.clear_selection()
        self.view.select(pno, xs[0])
        self.msg(tr("Gruppo creato con {} oggetti.").format(len(xs)) + (tr(" {} elementi (testo o grafica del PDF) sono rimasti fuori.").format(skipped) if skipped else ""), 8000)

    def ungroup_selection(self) -> None:
        pno, items = self._items_now()
        xs = [i["xref"] for i in items if i["kind"] == "annot"]
        n = self.pdf.ungroup_annots(pno, xs) if (xs and self.pdf) else 0
        if not n:
            self.msg(tr("La selezione non contiene gruppi."), 6000)
            return
        self.changed([pno])
        fresh = [{"kind": "annot", "xref": x, "rect": fitz.Rect(self.pdf.annot_info(pno, x).rect)} for x in xs if self.pdf.annot_info(pno, x)]
        self.view._apply_items(pno, fresh)
        self.msg(tr("Gruppo separato."), 5000)

    def _toggle_redact(self, pno: int, rect) -> None:
        """Segna l'oggetto per la redazione oppure, se è già segnato, toglie il segno (come il clic con lo strumento Redazione)."""
        r = fitz.Rect(rect)
        xr = self.pdf.redact_at(pno, (r.x0 + r.width / 2, r.y0 + r.height / 2))
        if xr is not None:
            if self.guard(self.pdf.delete_annot, pno, xr):
                self.msg(tr("Segno di redazione rimosso."), 5000)
                self.changed([pno])
            return
        self._mark_redact(pno, r)

    def _is_marked(self, pno: int, rect) -> bool:
        r = fitz.Rect(rect)
        return self.pdf.redact_at(pno, (r.x0 + r.width / 2, r.y0 + r.height / 2)) is not None

    def selected_rects_toggle_redact(self, pno: int, items: list) -> None:
        marked = [i for i in items if self._is_marked(pno, i["rect"])]
        with self.pdf.batch(tr("redazione")):
            if len(marked) == len(items):
                for i in items:
                    r = fitz.Rect(i["rect"]); xr = self.pdf.redact_at(pno, (r.x0 + r.width / 2, r.y0 + r.height / 2))
                    if xr is not None:
                        self.pdf.delete_annot(pno, xr)
            else:
                for i in items:
                    if i not in marked:
                        self.pdf.add_redact(pno, fitz.Rect(i["rect"]))
        self.changed([pno])

    def build_context_menu(self, pno: int, p: QPointF) -> QMenu:
        """Menu con le funzioni degli strumenti applicabili all'oggetto selezionato (annotazione, testo/immagine/grafica del PDF,
        campo di modulo) oppure, fuori da ogni oggetto, alla pagina."""
        v, pdf = self.view, self.pdf
        m = QMenu(self)
        m.setToolTipsVisible(True)
        add = lambda text, fn, ic=None: m.addAction(icon(ic) if ic else QIcon(), text, fn)
        clip = {"fmt": "png", "dpi": 150, "quality": 90, "annots": True, "copy": True}
        rect = None
        field = pdf.field_at(pno, (p.x(), p.y()))
        if v.multi and v.sel_page == pno:
            items = list(v.multi)
            u = fitz.Rect(items[0]["rect"])
            for it in items[1:]:
                u |= fitz.Rect(it["rect"])
            rect = u
            add(tr("Raggruppa"), self.group_selection, "group")
            if any(i["kind"] == "annot" and len(pdf.annot_group(pno, i["xref"])) > 1 for i in items):
                add(tr("Separa il gruppo"), self.ungroup_selection, "ungroup")
            m.addSeparator()
            allm = all(self._is_marked(pno, i["rect"]) for i in items)
            add(tr("Annulla redazione") if allm else tr("Segna per la redazione"),
                lambda: self.selected_rects_toggle_redact(pno, items), "redact")
            m.addSeparator()
            add(tr("Elimina"), self.delete_selection, "trash")
        elif field is not None:
            add(tr("Modifica campo…"), lambda: self.on_field(pno, field.xref), "form")
            rect = fitz.Rect(field.rect) if hasattr(field, "rect") and field.rect else None
        elif v.sel_info is not None and v.sel_page == pno:
            info = v.sel_info
            rect = fitz.Rect(info.rect)
            if len(pdf.annot_group(pno, info.xref)) > 1:
                add(tr("Separa il gruppo"), self.ungroup_selection, "ungroup")
            if info.type == T_FREETEXT:
                add(tr("Modifica testo…"), lambda: self.on_double(pno, info.xref), "edittext")
            if info.type == T_STAMP:
                tg = {"kind": "annot", "xref": info.xref}
                add(tr("Proprietà immagine…"), lambda: self.image_properties(pno, tg), "image")
                add(tr("Sostituisci immagine…"), lambda: self.image_properties(pno, tg, replace_first=True), "image")
                add(tr("Ruota di 90° in senso orario"), lambda: self._rotate_image(pno, tg, 90), "rotr")
                add(tr("Ruota di 90° in senso antiorario"), lambda: self._rotate_image(pno, tg, -90), "rotl")
                add(tr("Esporta immagine (PNG/JPG/TIFF)…"), lambda: self.export_image(pno, tg), "grab")
                m.addSeparator()
            if info.type == fitz.PDF_ANNOT_REDACT:
                add(tr("Annulla redazione"), self.delete_selection, "redact")
            else:
                add(tr("Annulla redazione") if self._is_marked(pno, rect) else tr("Segna per la redazione"),
                    lambda: self._toggle_redact(pno, rect), "redact")
                m.addSeparator()
                add(tr("Elimina"), self.delete_selection, "trash")
        elif v.sel_content is not None and v.sel_page == pno:
            obj = v.sel_content
            rect = fitz.Rect(obj["rect"])
            if obj["kind"] == "text":
                add(tr("Modifica testo…"), lambda: self.edit_text_block(pno, obj), "edittext")
                add(tr("Copia testo"), lambda: QApplication.clipboard().setText(obj.get("text", "")))
                mk = m.addMenu(tr("Marca il testo"))
                for k, t in (("hl", tr("Evidenzia")), ("ul", tr("Sottolinea")), ("st", tr("Barra"))):
                    mk.addAction(t, lambda k=k: self._mark_text(pno, k, rect))
            elif obj["kind"] == "image":
                tg = {"kind": "content", "obj": obj}
                add(tr("Proprietà immagine…"), lambda: self.image_properties(pno, tg), "image")
                add(tr("Sostituisci immagine…"), lambda: self.image_properties(pno, tg, replace_first=True), "image")
                add(tr("Ruota di 90° in senso orario"), lambda: self._rotate_image(pno, tg, 90), "rotr")
                add(tr("Ruota di 90° in senso antiorario"), lambda: self._rotate_image(pno, tg, -90), "rotl")
                add(tr("Esporta immagine (PNG/JPG/TIFF)…"), lambda: self.export_image(pno, tg), "grab")
            add(tr("Annulla redazione") if self._is_marked(pno, rect) else tr("Segna per la redazione"),
                lambda: self._toggle_redact(pno, rect), "redact")
            m.addSeparator()
            add(tr("Elimina"), self.delete_selection, "trash")
        if rect is not None:
            m.addSeparator()
            add(tr("Salva l'area come immagine…"), lambda: self.grab_area(pno, rect), "grab")
            add(tr("Copia l'area negli appunti"), lambda: self.grab_area(pno, rect, opts=dict(clip)), "export")
        if rect is None and field is None:
            add(tr("Aggiungi casella di testo qui"), lambda: self._ctx_text(pno, p), "text")
            add(tr("Inserisci immagine qui"), lambda: self._ctx_image(pno, p), "image")
            m.addSeparator()
            for a in (self.a_rotl, self.a_rotr, self.a_dup, self.a_deletep):
                m.addAction(a)
        return m

    def selected_image(self):
        """(pagina, bersaglio) se l'oggetto selezionato è un'immagine (timbro inserito o immagine del PDF)."""
        v = self.view
        if self.pdf is None or v.sel_page < 0:
            return None
        if v.sel_content is not None and v.sel_content.get("kind") == "image":
            return v.sel_page, {"kind": "content", "obj": v.sel_content}
        if v.sel_info is not None and v.sel_info.type == T_STAMP:
            return v.sel_page, {"kind": "annot", "xref": v.sel_info.xref}
        return None

    def image_properties(self, pno: Optional[int] = None, target: Optional[dict] = None, replace_first: bool = False) -> None:
        """Finestra con dimensioni numeriche (con unità), proporzioni, rotazione, sostituzione ed esportazione."""
        if target is None:
            sel = self.selected_image()
            if sel is None:
                self.msg(tr("Seleziona prima un'immagine (strumento Seleziona o Modifica oggetti)."), 6000)
                return
            pno, target = sel
        try:
            r = self.pdf.image_rect_of(pno, target)
            pix = self.pdf.image_pixmap_of(pno, target)
        except Exception as e:
            QMessageBox.warning(self, tr("Immagine"), str(e))
            return

        def export():
            self.export_image(pno, target)
        dlg = ImageDialog(self, r.width, r.height, (pix.width, pix.height), on_export=export)
        if replace_first:
            QTimer.singleShot(0, dlg._replace)
        if dlg.exec() != ImageDialog.Accepted:
            return
        w, h, angle, repl = dlg.values()
        if abs(w - r.width) < 0.005 and abs(h - r.height) < 0.005 and abs(angle) < 1e-6 and repl is None:
            return
        new = fitz.Rect(r.x0, r.y0, r.x0 + w, r.y0 + h)
        t2 = self.guard(self.pdf.modify_image, pno, target, new, angle, repl)
        if t2 is None:
            return
        self.view.clear_selection()
        self.changed([pno])
        if t2["kind"] == "content" and t2.get("obj"):
            self.view.select_content(pno, t2["obj"])
        elif t2["kind"] == "annot":
            self.view.select(pno, t2["xref"])

    def export_image(self, pno: int, target: dict) -> Optional[str]:
        dlg = ImageOutDialog(self, tr("Esporta l'immagine"), with_dpi=False)
        if dlg.exec() != ImageOutDialog.Accepted:
            return None
        fmt, q = dlg.fmt.currentData(), dlg.quality.value()
        path = self._save_target(tr("Esporta l'immagine"), fmt, f"{self._stem()}_pag{pno + 1}_immagine")
        if not path:
            return None
        try:
            self.pdf.export_image_of(pno, target, path, fmt, q)
        except Exception as e:
            QMessageBox.critical(self, tr("Esporta immagine"), tr("Salvataggio non riuscito:\n{}").format(e))
            return None
        settings().setValue("lastdir", os.path.dirname(path))
        self.msg(tr("Immagine salvata: {}").format(path), 8000)
        return path

    def _mark_redact(self, pno: int, rect) -> None:
        if self.guard(self.pdf.add_redact, pno, fitz.Rect(rect)) is not None:
            self.msg(tr("Segnato per la redazione. Modifica → Applica redazioni per oscurarlo in modo permanente."), 8000)
            self.changed([pno])

    def _rotate_image(self, pno: int, target: dict, angle: float) -> None:
        r = self.pdf.image_rect_of(pno, target)
        t2 = self.guard(self.pdf.modify_image, pno, target, r, angle, None)
        if t2 is None:
            return
        self.view.clear_selection()
        self.changed([pno])
        if t2["kind"] == "content" and t2.get("obj"):
            self.view.select_content(pno, t2["obj"])
        elif t2["kind"] == "annot":
            self.view.select(pno, t2["xref"])

    def _mark_text(self, pno: int, kind: str, rect) -> None:
        if self.guard(self.pdf.add_markup, pno, kind, fitz.Rect(rect)) is not None:
            self.changed([pno])

    def _ctx_text(self, pno: int, p: QPointF) -> None:
        if self.add_text_box(pno, fitz.Rect(p.x(), p.y(), p.x() + 200, p.y() + 40)) is not None:
            self.changed([pno])

    def _ctx_image(self, pno: int, p: QPointF) -> None:
        if self.insert_image_at("image", pno, QRectF(p.x(), p.y(), 0, 0)) is not None:
            self.changed([pno])

    def on_context(self, pno: int, p: QPointF, gpos) -> None:
        if not self.pdf:
            return
        self.build_context_menu(pno, p).exec(gpos)

    def redact_object_at(self, pno: int, p: QPointF) -> bool:
        """Strumento Redazione, clic: segna come da oscurare l'intero oggetto sotto il punto (testo, immagine o grafica);
        un clic su un'area già segnata la toglie. Tutto resta annullabile finché la redazione non è applicata."""
        xr = self.pdf.redact_at(pno, (p.x(), p.y()))
        if xr is not None:
            self.guard(self.pdf.delete_annot, pno, xr)
            self.msg(tr("Segno di redazione rimosso."), 5000)
            return True
        obj = self.pdf.content_at(pno, (p.x(), p.y()))
        if not obj:
            self.msg(tr("Nessun oggetto in questo punto: trascina per segnare un'area."), 6000)
            return False
        x = self.guard(self.pdf.add_redact, pno, fitz.Rect(obj["rect"]))
        if x is None:
            return False
        names = {"text": "testo", "image": "immagine", "vector": "grafica"}
        self.msg(tr("{} segnato per la redazione. Clic di nuovo per toglierlo; Modifica → Applica redazioni per oscurarlo in modo permanente.").format(names.get(obj['kind'], 'Oggetto').capitalize()), 9000)
        return True

    def on_click(self, tool: str, pno: int, p: QPointF) -> None:
        if tool == "redact":
            if self.redact_object_at(pno, p):
                self.changed([pno])
        elif tool == "grab":
            self.grab_image_at(pno, p)
        elif tool == "edittext":
            self.edit_text_at(pno, p)
        elif tool == "eraser":
            x = self.pdf.annot_at(pno, (p.x(), p.y()))
            if x is not None and self.pdf.delete_annot(pno, x):
                self.changed([pno])
        elif tool == "text":
            x = self.add_text_box(pno, fitz.Rect(p.x(), p.y(), p.x() + 200, p.y() + 40))
            if x is not None:
                self.changed([pno])
        elif tool in ("image", "sign"):
            x = self.insert_image_at(tool, pno, QRectF(p.x(), p.y(), 0, 0))
            if x is not None:
                self.changed([pno])
        elif tool == "sigbox":
            self.finish_visible_signature(pno, fitz.Rect(p.x(), p.y(), p.x() + 180, p.y() + 70))

    def add_text_box(self, pno: int, rect: fitz.Rect):
        st = self.styles["text"]
        d = TextDialog(self, tr("Casella di testo"), "", st.get("fontsize", 12), st.get("fontname", "helv"), st["pen"], st.get("fill"))
        if d.exec() != TextDialog.Accepted or not d.values()["text"].strip():
            return None
        v = d.values()
        st.update({"pen": v["color"], "fill": v["fill"], "fontsize": v["fontsize"], "fontname": v["fontname"]})
        return self.guard(self.pdf.add_text, pno, rect, v["text"], v["fontsize"], v["fontname"], v["color"], v["fill"], st.get("width", 0))

    def edit_text_at(self, pno: int, p: QPointF) -> None:
        blk = self.pdf.text_block_at(pno, (p.x(), p.y()))
        if not blk:
            self.msg(tr("Nessun testo modificabile in questo punto (potrebbe essere un'immagine)."))
            return
        self.edit_text_block(pno, blk)

    def edit_text_block(self, pno: int, blk: dict) -> None:
        d = TextDialog(self, tr("Modifica testo del PDF"), blk["text"], blk["fontsize"], blk["fontname"], blk["color"], show_style=False)
        if d.exec() != TextDialog.Accepted:
            return
        v = d.values()
        if self.guard(self.pdf.replace_text_block, pno, blk["rect"], v["text"], v["fontsize"], v["fontname"], v["color"]) is None:
            pass
        self.changed([pno])
        self.msg(tr("Testo sostituito. Il vecchio testo è stato rimosso dal documento."))

    def insert_image_at(self, tool: str, pno: int, r: QRectF):
        if tool == "sign":
            if not self.current_signature or not os.path.exists(self.current_signature):
                self.pick_signature()
                if not self.current_signature:
                    return None
            img = QImage(self.current_signature)
            maxw = 170.0
        else:
            path, _ = QFileDialog.getOpenFileName(self, tr("Scegli immagine"), settings().value("lastimgdir", ""),
                                                  tr("Immagini (*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff *.webp)"))
            if not path:
                return None
            settings().setValue("lastimgdir", os.path.dirname(path))
            img = QImage(path)
            if img.isNull():              # formati che Qt non legge (TIFF particolari, 16 bit, CMYK…): via Pillow, con trasparenza
                try:
                    img = QImage.fromData(imgutil.to_png_bytes(path))
                except Exception:
                    pass
            maxw = 240.0
        if img.isNull():
            QMessageBox.warning(self, tr("Immagine"), tr("Impossibile leggere l'immagine."))
            return None
        img = sigstore.limit_size(img.convertToFormat(QImage.Format_ARGB32))
        ratio = img.width() / img.height()
        pw, ph = self.pdf.page_size(pno)
        if r.width() < 3 or r.height() < 3:
            w = min(maxw, pw * 0.6)
            h = w / ratio
            rect = fitz.Rect(r.x(), r.y(), r.x() + w, r.y() + h)
            if rect.x1 > pw:
                rect.x0, rect.x1 = pw - w, pw
            if rect.y1 > ph:
                rect.y0, rect.y1 = ph - h, ph
        else:
            w, h = r.width(), r.height()
            if w / h > ratio:
                nw = h * ratio
                x0 = r.x() + (w - nw) / 2
                rect = fitz.Rect(x0, r.y(), x0 + nw, r.y() + h)
            else:
                nh = w / ratio
                y0 = r.y() + (h - nh) / 2
                rect = fitz.Rect(r.x(), y0, r.x() + w, y0 + nh)
        rot = self.pdf.page(pno).rotation
        if rot:   # l'annotazione vive nello spazio pagina non ruotato: si contro-ruota l'immagine perché appaia dritta
            from PySide6.QtGui import QTransform
            img = img.transformed(QTransform().rotate(-rot), Qt.SmoothTransformation)
        return self.guard(self.pdf.add_image, pno, rect, sigstore.png_bytes(img))

    # ================================================================== selezione e proprietà
    def on_selection(self, pno: int, xref: int) -> None:
        if pno < 0 or not self.pdf:
            key = TOOL_STYLE.get(self.tool)
            if key:
                self.props.load(self.styles[key])
            self.props.enable_for(self.tool)
            return
        info = self.pdf.annot_info(pno, xref)
        if not info:
            return
        style = {"pen": info.stroke or (0, 0, 0), "fill": info.fill, "width": info.width, "opacity": info.opacity,
                 "fontsize": info.fontsize, "fontname": info.fontname}
        if info.type == T_FREETEXT:
            style["pen"] = info.text_color
        self.props.load(style)
        self.props.enable_for("select")
        self.msg(tr("Selezionato: {}").format(info.kind))

    def on_props_changed(self, kw: dict) -> None:
        sel_p, sel_x = self.view.sel_page, self.view.sel_xref
        if sel_p >= 0 and self.pdf:
            m = {}
            if "stroke" in kw:
                m["stroke"] = kw["stroke"]
            if "fill" in kw:
                m["fill"] = kw["fill"]
            for k in ("width", "opacity", "fontsize", "fontname"):
                if k in kw:
                    m[k] = kw[k]
            info = self.pdf.annot_info(sel_p, sel_x)
            if info and info.type == T_FREETEXT and "stroke" in m:
                m["text_color"] = m.pop("stroke")
            nx = self.guard(self.pdf.set_props, sel_p, sel_x, **m)
            if nx is not None:
                self.changed([sel_p])
                self.view.select(sel_p, nx)
            return
        key = TOOL_STYLE.get(self.tool)
        if key:
            st = self.styles[key]
            for k, v in kw.items():
                st["pen" if k == "stroke" else k] = v
            self.view.style = {"pen": st["pen"], "width": st["width"], "opacity": st.get("opacity", 1.0)}

    def on_transform(self, pno: int, xref: int, r: QRectF, resize: bool) -> None:
        nx = self.guard(self.pdf.set_rect, pno, xref, self._fz(r))
        self.changed([pno])
        if nx is not None:
            self.view.select(pno, nx)

    # ------------------------------------------------------------------ moduli
    def on_field(self, pno: int, xref: int) -> None:
        f = next((x for x in self.pdf.list_fields(pno) if x.xref == xref), None)
        if f is None:
            return
        if f.readonly:
            self.msg(tr("Campo di sola lettura."))
            return
        if f.kind in ("checkbox", "radio"):
            nv = (not f.value) if f.kind == "checkbox" else True
            if self.guard(self.pdf.set_field, pno, xref, nv) is not None or True:
                self.changed([pno])
            self._after_form_change(pno)
            return
        if f.kind == "signature":
            self.sign_field(pno, f)
            return
        if f.kind in ("combo", "list"):
            items = list(f.choices)
            cur = items.index(f.value) if f.value in items else 0
            v, ok = QInputDialog.getItem(self, tr("Campo «{}»").format(f.name), tr("Scegli un valore:"), items, cur, False)
            if not ok:
                return
        elif f.kind == "text":
            d = FieldTextDialog(self, f.name, str(f.value), f.multiline, f.maxlen, f.password)
            if d.exec() != FieldTextDialog.Accepted:
                return
            v = d.value()
        else:
            self.msg(tr("Questo tipo di campo non è compilabile."))
            return
        self.guard(self.pdf.set_field, pno, xref, v)
        self.changed([pno])
        self._after_form_change(pno)

    def _after_form_change(self, pno: int) -> None:
        self.view.refresh_page(pno)

    def toggle_fields(self) -> None:
        self.view.set_show_fields(self.a_showfields.isChecked())
        settings().setValue("view/fields", self.a_showfields.isChecked())

    def flatten_forms(self) -> None:
        if not self.pdf or not self.pdf.has_form():
            QMessageBox.information(self, tr("Moduli"), tr("Il documento non contiene campi compilabili."))
            return
        if self.pdf.is_signed:
            QMessageBox.warning(self, tr("Moduli"), tr("Il documento è firmato: appiattire i campi invaliderebbe le firme."))
            return
        if QMessageBox.question(self, tr("Appiattisci moduli"),
                                tr("I campi diventeranno testo fisso e non potranno più essere compilati.\n"
                                "Anche i campi di firma vuoti verranno rimossi. Continuare?")) != QMessageBox.Yes:
            return
        n = self.guard(self.pdf.flatten_forms)
        if n:
            self.changed(None)
            self.msg(tr("{} campi appiattiti.").format(n))

    def sign_field(self, pno: int, f) -> None:
        if f.signed:
            self.msg(tr("Questo campo è già firmato: usa Firma → Verifica firme."))
            return
        QMessageBox.information(self, tr("Campo firma"), tr("Si aprirà la finestra di firma digitale: la firma sarà inserita in questo campo."))
        self.sign_digital(field=(pno, f))

    def on_double(self, pno: int, xref: int) -> None:
        info = self.pdf.annot_info(pno, xref)
        if not info or info.type != T_FREETEXT:
            return
        d = TextDialog(self, tr("Modifica casella di testo"), info.text, info.fontsize, info.fontname, info.text_color, info.fill)
        if d.exec() != TextDialog.Accepted:
            return
        v = d.values()
        nx = self.guard(self.pdf.set_props, pno, xref, text=v["text"], fontsize=v["fontsize"], fontname=v["fontname"],
                        text_color=v["color"], fill=v["fill"])
        self.changed([pno])
        if nx is not None:
            self.view.select(pno, nx)

    # ------------------------------------------------------------------ oggetti del contenuto (testo, immagini, grafica)
    _KIND = {"text": tr("blocco di testo"), "image": "immagine", "vector": tr("grafica vettoriale")}

    def on_content_selected(self, pno: int, obj: dict) -> None:
        self.msg(tr("Selezionato: {} — trascina per spostare, maniglie per ridimensionare, Canc per eliminare").format(self._KIND.get(obj['kind'], 'oggetto')) + (tr(", doppio clic per riscrivere il testo.") if obj["kind"] == "text" else "."), 9000)

    def on_content_transform(self, pno: int, obj: dict, r: QRectF) -> None:
        try:
            self.pdf.move_content(pno, obj, self._fz(r))
        except PdfError as e:
            self.msg(str(e))
            self.view.reload()
            return
        except Exception as e:
            QMessageBox.warning(self, tr("Operazione non riuscita"), str(e))
            self.view.reload()
            return
        self.changed([pno])
        c = self._fz(r)
        new = self.pdf.content_at(pno, ((c.x0 + c.x1) / 2, (c.y0 + c.y1) / 2))
        if new is not None and self.tool == "editobj":
            self.view.select_content(pno, new)

    def on_content_double(self, pno: int, obj: dict) -> None:
        self.edit_text_block(pno, obj)

    def delete_selection(self) -> None:
        if self.view.multi and self.pdf:
            p, items = self.view.sel_page, list(self.view.multi)
            self.view.clear_selection()
            with self.pdf.batch(tr("elimina oggetti")):
                for i in items:
                    if i["kind"] == "annot":
                        self.pdf.delete_annot(p, i["xref"])
                for i in items:
                    if i["kind"] == "content":
                        self.guard(self.pdf.delete_content, p, i["obj"])
            self.changed([p])
            return
        if self.view.sel_content is not None and self.pdf:
            p, obj = self.view.sel_page, self.view.sel_content
            self.view.clear_selection()
            if self.guard(self.pdf.delete_content, p, obj) is None:
                self.changed([p])
            return
        if self.view.sel_page >= 0 and self.pdf:
            p = self.view.sel_page
            if self.pdf.delete_annot(p, self.view.sel_xref):
                self.view.clear_selection()
                self.changed([p])

    def _confirm_redactions(self, n: int) -> tuple:
        """Chiede conferma; restituisce (procedere, rimuovere_anche_i_metadati)."""
        from PySide6.QtWidgets import QCheckBox
        box = QMessageBox(QMessageBox.Warning, tr("Applica redazioni"), "", QMessageBox.Yes | QMessageBox.Cancel, self)
        box.setText(tr("Verranno rimossi in modo PERMANENTE testo, immagini e grafica sotto {} area/e, insieme a note e campi compilati sovrapposti.").format(n))
        box.setInformativeText(tr("L'operazione si può annullare finché non salvi e chiudi, ma il file salvato non è recuperabile: "
                               "per conservare l'originale usa «Salva con nome».\nProcedere?"))
        box.setDefaultButton(QMessageBox.Cancel)
        cb = QCheckBox(tr("Rimuovi anche i metadati del documento (titolo, autore, campi personalizzati, XMP)"))
        cb.setChecked(bool(settings().value("redact/strip_meta", False, type=bool)))
        box.setCheckBox(cb)
        ok = box.exec() == QMessageBox.Yes
        if ok:
            settings().setValue("redact/strip_meta", cb.isChecked())
        return ok, cb.isChecked()

    def apply_redactions(self) -> None:
        if not self.pdf:
            return
        n = self.pdf.pending_redactions()
        if n == 0:
            QMessageBox.information(self, tr("Redazione"), tr("Non ci sono aree di redazione da applicare.\nUsa lo strumento «Redazione» per segnarle."))
            return
        ok, strip = self._confirm_redactions(n)
        if ok:
            self.guard(self.pdf.apply_redactions, strip)
            self.view.clear_selection()
            self.changed(None)
            self.msg(tr("Applicate {} redazioni").format(n) + (tr(" e rimossi i metadati") if strip else ""))

    # ---------------------------------------------------------------- estrazione di immagini e aree
    def _save_target(self, title: str, fmt: str, stem: str) -> Optional[str]:
        ext = extractor.FORMATS[fmt][1]
        start = os.path.join(settings().value("lastdir", os.path.expanduser("~")), stem + ext)
        p, _ = QFileDialog.getSaveFileName(self, title, start, f"{extractor.FORMATS[fmt][0]} (*{ext})")
        if p and not p.lower().endswith((ext, ".tif") if fmt == "tiff" else ext):
            p += ext
        return p or None

    def _stem(self) -> str:
        return os.path.splitext(os.path.basename(self.pdf.path))[0] if self.pdf.path else "documento"

    def grab_area(self, pno: int, rect, target: Optional[str] = None, opts: Optional[dict] = None) -> Optional[str]:
        """Salva (o copia negli appunti) l'area `rect` (coordinate di visualizzazione) della pagina."""
        if opts is None:
            dlg = ImageOutDialog(self, tr("Salva l'area selezionata"), with_dpi=True, with_annots=True, copy_button=True)
            if dlg.exec() != ImageOutDialog.Accepted:
                return None
            opts = {"fmt": dlg.fmt.currentData(), "dpi": dlg.dpi.value(), "quality": dlg.quality.value(),
                    "annots": dlg.annots.isChecked(), "copy": dlg.copy_requested}
        try:
            pix = extractor.render_area(self.pdf.doc, pno, rect, opts["dpi"], opts.get("annots", True))
        except Exception as e:
            QMessageBox.warning(self, tr("Estrai area"), str(e))
            return None
        if opts.get("copy"):
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()
            QApplication.clipboard().setImage(img)
            self.msg(tr("Area copiata negli appunti ({}×{} px)").format(pix.width, pix.height))
            return "clipboard"
        target = target or self._save_target(tr("Salva l'area selezionata"), opts["fmt"], f"{self._stem()}_pag{pno + 1}_area")
        if not target:
            return None
        try:
            extractor.write_pixmap(pix, target, opts["fmt"], opts["quality"], opts["dpi"])
        except Exception as e:
            QMessageBox.critical(self, tr("Estrai area"), tr("Salvataggio non riuscito:\n{}").format(e))
            return None
        settings().setValue("lastdir", os.path.dirname(target))
        self.msg(tr("Area salvata: {} ({}×{} px)").format(target, pix.width, pix.height), 10000)
        return target

    def grab_image_at(self, pno: int, p, target: Optional[str] = None, opts: Optional[dict] = None) -> Optional[str]:
        """Clic con lo strumento «Estrai»: salva l'immagine incorporata sotto il punto."""
        obj = self.pdf.content_at(pno, (p.x(), p.y()))
        if not obj or obj.get("kind") != "image":
            self.msg(tr("Qui non c'è un'immagine incorporata: trascina per salvare un'area."), 6000)
            return None
        if opts is None:
            dlg = ImageOutDialog(self, tr("Salva l'immagine"), with_dpi=False)
            if dlg.exec() != ImageOutDialog.Accepted:
                return None
            opts = {"fmt": dlg.fmt.currentData(), "quality": dlg.quality.value()}
        target = target or self._save_target(tr("Salva l'immagine"), opts["fmt"], f"{self._stem()}_pag{pno + 1}_immagine")
        if not target:
            return None
        try:
            pix = extractor.image_pixmap(self.pdf.doc, obj["xref"])
            r = fitz.Rect(obj["page_rect"])
            dpi = int(pix.width / (r.width / 72)) if r.width > 0 else None
            extractor.write_pixmap(pix, target, opts["fmt"], opts["quality"], dpi)
        except Exception as e:
            QMessageBox.critical(self, tr("Estrai immagine"), tr("Salvataggio non riuscito:\n{}").format(e))
            return None
        settings().setValue("lastdir", os.path.dirname(target))
        self.msg(tr("Immagine salvata: {} ({}×{} px)").format(target, pix.width, pix.height), 10000)
        return target

    def extract_images(self, folder: Optional[str] = None, items: Optional[list] = None, fmt: Optional[str] = None,
                       quality: int = 90) -> list:
        """Finestra con tutte le immagini incorporate: salva quelle scelte in una cartella."""
        if not self.pdf:
            return []
        if items is None:
            allitems = extractor.list_images(self.pdf.doc)
            if not allitems:
                QMessageBox.information(self, tr("Estrai immagini"), tr("Questo PDF non contiene immagini incorporate.\nCon lo strumento «Estrai immagine/area» puoi salvare un'area della pagina."))
                return []
            dlg = ExtractImagesDialog(self, self.pdf.doc, allitems, self.view.current_page())
            if dlg.exec() != ExtractImagesDialog.Accepted:
                return []
            items, fmt, quality = dlg.selected(), dlg.fmt.currentData(), dlg.quality.value()
        if folder is None:
            folder = QFileDialog.getExistingDirectory(self, tr("Cartella in cui salvare le immagini"), settings().value("lastdir", os.path.expanduser("~")))
            if not folder:
                return []
        pd, cb = self._progress(tr("Estrazione in corso…"), len(items))
        try:
            out = extractor.extract_images(self.pdf.doc, items, fmt, folder, quality, cb)
        except Exception as e:
            QMessageBox.critical(self, tr("Estrai immagini"), tr("Estrazione non riuscita:\n{}").format(e))
            return []
        finally:
            pd.close()
        settings().setValue("lastdir", folder)
        self.msg(tr("Estratte {} immagini in {}").format(len(out), folder), 10000)
        return out

    def edit_metadata(self) -> None:
        if not self.pdf:
            return
        meta = self.pdf.get_metadata()
        dlg = MetadataDialog(self, meta, self.pdf.document_info(), self.pdf.standard)
        if dlg.exec() != MetadataDialog.Accepted:
            return
        v = dlg.values
        xmp = self.pdf.make_xmp(v["standard"]) if v["regen_xmp"] else None
        if (v["standard"] == meta["standard"] and v["custom"] == meta["custom"] and xmp is None and not v["remove_xmp"]):
            return
        try:
            self.pdf.set_metadata(v["standard"], v["custom"], xmp, v["remove_xmp"])
        except Exception as e:
            QMessageBox.warning(self, tr("Metadati"), tr("Operazione non riuscita:\n{}").format(e))
            return
        self.msg(tr("Metadati aggiornati"))
        self._refresh_ui()

    # ================================================================== annulla / ripeti / pagine
    def undo(self) -> None:
        if self.pdf and self.pdf.undo():
            self._after_undo()

    def redo(self) -> None:
        if self.pdf and self.pdf.redo():
            self._after_undo()

    def _after_undo(self) -> None:
        """Ridisegna solo le pagine che l'annulla/ripeti ha davvero cambiato (niente lampo sull'intero foglio);
        il layout si ricostruisce solo se cambiano numero, dimensione o rotazione delle pagine."""
        self.view.clear_selection()
        pages = self.pdf.last_changed
        if pages is None or len(self.view.page_rects) != self.pdf.page_count:
            self.structural()
        else:
            self.changed(pages)

    def rotate(self, delta: int) -> None:
        if self.pdf:
            pages = self.thumbs.selected_pages() or [self.view.current_page()]
            self.pdf.rotate_pages(pages, delta)
            self.structural()

    def on_page_changed(self, pno: int) -> None:
        self.thumbs.mark_current(pno)
        self._refresh_ui()

    def on_thumb_moved(self, src: int, dest: int) -> None:
        if self.pdf:
            self.guard(self.pdf.move_page, src, dest)
            self.structural()

    def on_thumb_action(self, key: str, pages: list) -> None:
        self.page_action(key, [p for p in pages if p >= 0])

    def page_action(self, key: str, pages: list[int]) -> None:
        if not self.pdf or not pages:
            return
        try:
            if key == "rot_l":
                self.pdf.rotate_pages(pages, -90)
            elif key == "rot_r":
                self.pdf.rotate_pages(pages, 90)
            elif key == "dup":
                for p in sorted(pages, reverse=True):
                    self.pdf.duplicate_page(p)
            elif key == "blank":
                self.pdf.insert_blank(max(pages))
            elif key == "delete":
                if QMessageBox.question(self, tr("Elimina pagine"), tr("Eliminare {} pagina/e?").format(len(pages))) != QMessageBox.Yes:
                    return
                self.pdf.delete_pages(pages)
            elif key == "insert":
                p, _ = QFileDialog.getOpenFileName(self, tr("Inserisci pagine da PDF"), settings().value("lastdir", ""), tr("PDF (*.pdf)"))
                if not p:
                    return
                pw = None
                while True:
                    try:
                        n = self.pdf.insert_pdf(p, max(pages), pw)
                        break
                    except PasswordRequired:
                        pw, ok = QInputDialog.getText(self, tr("PDF protetto"), tr("Password:"), QLineEdit.Password)
                        if not ok:
                            return
                self.msg(tr("Inserite {} pagine").format(n))
            elif key == "extract":
                p, _ = QFileDialog.getSaveFileName(self, tr("Estrai pagine in…"), "estratto.pdf", tr("PDF (*.pdf)"))
                if not p:
                    return
                self.pdf.extract_pages(pages, p if p.lower().endswith(".pdf") else p + ".pdf")
                self.msg(tr("Estratte {} pagine in {}").format(len(pages), os.path.basename(p)))
                return
        except PdfError as e:
            self.msg(str(e))
            return
        except Exception as e:
            QMessageBox.warning(self, tr("Operazione non riuscita"), str(e))
            return
        self.structural(keep_page=pages[0])

    # ================================================================== ricerca
    def find_open(self) -> None:
        self.findbar.show()
        self.find_edit.setFocus()
        self.find_edit.selectAll()

    def find_close(self) -> None:
        self.findbar.hide()
        self.view.set_found([])
        self.found = []

    def find_run(self) -> None:
        if not self.pdf:
            return
        self.found = self.pdf.search(self.find_edit.text())
        self.found_idx = 0 if self.found else -1
        self._show_found()

    def find_step(self, d: int) -> None:
        if not self.found:
            self.find_open() if not self.findbar.isVisible() else self.find_run()
            return
        self.found_idx = (self.found_idx + d) % len(self.found)
        self._show_found()

    def _show_found(self) -> None:
        items = [(p, QRectF(r.x0, r.y0, r.width, r.height)) for p, r in self.found]
        self.view.set_found(items, self.found_idx)
        self.find_lbl.setText(f"{self.found_idx + 1}/{len(self.found)}" if self.found else tr("nessun risultato"))

    # ================================================================== firme
    def pick_signature(self) -> None:
        d = SignatureLibraryDialog(self, select_mode=True)
        if d.exec() == SignatureLibraryDialog.Accepted and d.chosen:
            self.current_signature = d.chosen
            self.set_tool("sign")
            self.msg(tr("Clicca o trascina sulla pagina per inserire la firma."))
        elif self.tool == "sign" and not self.current_signature:
            self.set_tool("select")

    def manage_signatures(self) -> None:
        SignatureLibraryDialog(self, select_mode=False).exec()

    def create_cert(self) -> None:
        d = CertDialog(self)
        if d.exec() == CertDialog.Accepted:
            QMessageBox.information(self, tr("Certificato"), tr("Certificato creato:\n{}").format(d.path.text()))

    def sign_digital(self, field=None) -> None:
        """Firma digitale. `field` = (pagina, FieldInfo) per firmare in un campo firma già presente nel modulo."""
        if not self.pdf:
            return
        base = self.pdf.path or os.path.join(settings().value("lastdir", os.path.expanduser("~")), "documento.pdf")
        default = os.path.splitext(base)[0] + "-firmato.pdf"
        d = SignDialog(self, default, self.pdf.page_count, self.pdf.is_signed, in_field=field is not None, standard=self.pdf.standard)
        if d.exec() != SignDialog.Accepted:
            return
        common = dict(reason=d.reason.text(), location=d.loc.text(), image_path=d.img_path if d.use_img.isChecked() else None,
                      show_text=d.show_text.isChecked(), timestamp_url=d.tsa.text().strip() or None)
        if d.src.currentData() == "card":
            common.update(d.card_params())
            params = signing.SignParams("", field_name=self._free_field_name(), **common)
        else:
            params = signing.SignParams(d.cert.text(), d.pw.text(), field_name=self._free_field_name(), **common)
        self.pending_std = (d.std.key(), d.std.icc_path()) if d.std.isEnabled() else (None, None)
        if field is not None:
            params.field_name, params.existing_field = field[1].name, True
            self.pending_sign = (params, d.out.text().strip(), d.preset.currentData(), field[0])
            self._do_sign()
            return
        self.pending_sign = (params, d.out.text().strip(), d.preset.currentData(), d.page.value() - 1 if d.visible.isChecked() else None)
        if d.visible.isChecked():
            self.view.go_to_page(self.pending_sign[3])
            self.set_tool("sigbox")
            self.msg(tr("Trascina sulla pagina il riquadro dove apparirà la firma (Esc per annullare)."), 15000)
        else:
            self._do_sign()

    def _free_field_name(self) -> str:
        n = (self.pdf.signed_count if self.pdf else 0) + 1
        used = {f.name for p in range(self.pdf.page_count) for f in self.pdf.list_fields(p)} if self.pdf else set()
        while f"Firma{n}" in used:
            n += 1
        return f"Firma{n}"

    def finish_visible_signature(self, pno: int, rect: fitz.Rect) -> None:
        if not self.pending_sign:
            self.set_tool("select")
            return
        params, out, preset, _ = self.pending_sign
        page = self.pdf.page(pno)
        pr = to_page_rect(page, rect)
        pdf_rect = (pr * ~page.transformation_matrix).normalize()
        params.page, params.box = pno, (pdf_rect.x0, pdf_rect.y0, pdf_rect.x1, pdf_rect.y1)
        self.set_tool("select")
        self._do_sign()

    def _do_sign(self) -> None:
        params, out, preset, _ = self.pending_sign
        self.pending_sign = None
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            if self.pdf.is_signed:
                data = self.pdf.current_bytes()
            else:
                data = self.pdf.doc.tobytes(garbage=1, deflate=True)
                if preset != "original" or self.pending_std[0]:
                    data = compress.optimize_bytes(data, compress.SaveOptions(preset, standard=self.pending_std[0], icc=self.pending_std[1], runner=self.run_bg))
            signed = signing.sign_pdf_bytes(data, params)
            compress.write_atomic(out, signed)
            st = signing.verify_pdf_bytes(signed)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, tr("Firma digitale"), str(e))
            return
        QApplication.restoreOverrideCursor()
        ok = bool(st) and st[-1].intact and st[-1].valid
        self.pdf.modified = False
        src = self.pdf
        if self.open_path(out, force_new=True):
            self._remove_doc(src)                       # il documento firmato prende il posto dell'originale
            self.msg(tr("Documento firmato: {} ({})").format(os.path.basename(out), compress.human_size(len(signed))), 10000)
            if not ok:
                QMessageBox.warning(self, tr("Firma digitale"), tr("Il file è stato creato ma la verifica della firma non è riuscita."))

    def verify_signatures(self) -> None:
        if not self.pdf:
            return
        try:
            data = self.pdf.current_bytes() if self.pdf.is_signed else self.pdf.doc.tobytes()
            st = signing.verify_pdf_bytes(data)
        except Exception as e:
            QMessageBox.warning(self, tr("Verifica firme"), str(e))
            return
        VerifyDialog(self, st).exec()
