# PDFDesk

**PDFDesk — Guido Cauli <guido.cauli@gmail.com>**

Editor PDF grafico per **Windows, Linux e macOS**. Si distribuisce come singolo eseguibile: non serve installare Python né altre librerie.

- [Download e installazione](#download-e-installazione)
- [Funzioni](#funzioni)
- [Firme digitali](#firme-digitali)
- [PDF/A e PDF/X](#pdfa-e-pdfx)
- [Scansione e OCR](#scansione-e-ocr)
- [Interfaccia e preferenze](#interfaccia-e-preferenze)
- [Riga di comando](#riga-di-comando)
- [Funzioni non supportate e limiti](#funzioni-non-supportate-e-limiti)
- [Compilare dai sorgenti](#compilare-dai-sorgenti)
- [Licenza](#licenza)

---

## Download e installazione

I pacchetti si trovano nella pagina [Releases](https://github.com/guidocauli/pdfdesk/releases).

| Sistema | File |
|---|---|
| Windows 10/11 (64 bit) | `pdfdesk-<versione>-windows-x86_64-setup.exe` (installatore) oppure `…-windows-x86_64.zip` (portatile) |
| Linux x86_64 | `pdfdesk-<versione>-linux-x86_64.tar.gz` |
| macOS Apple Silicon (M1 e successivi) | `pdfdesk-<versione>-macos-arm64.zip` |
| Sorgenti | `pdfdesk-<versione>-sorgenti.tar.gz` |

### Windows

1. Esegui `…-setup.exe` (servono i diritti di amministratore).
2. Nei componenti puoi scegliere:
   - **Collegamento sul desktop** e **«Apri con» per i PDF**;
   - **Certificato dell'editore**: rende riconosciuta la firma del programma ed evita l'avviso «editore sconosciuto» di SmartScreen;
   - **OCR**: scarica Tesseract da internet per rendere ricercabili le scansioni (vedi [Scansione e OCR](#scansione-e-ocr)).
3. Il programma viene installato in `C:\Program Files\PDFDesk`.

Per **aggiornare** basta eseguire l'installatore della nuova versione: aggiorna la cartella esistente e mantiene impostazioni e firme salvate. Per **disinstallare** usa *Impostazioni → App*.

Versione portatile: estrai lo zip ed esegui `pdfdesk.exe`. Per installare il certificato, clic destro su `installa-certificato.cmd` → *Esegui come amministratore*.

Installazione silenziosa: `setup.exe /S [/CERT] [/OCR] [/D=C:\percorso]`.

> Gli eseguibili sono firmati con il certificato **autofirmato** «PDFDesk - Guido Cauli» (`pdfdesk-sign.cer`, impronta SHA-256 `9A:26:92:17:2A:EF:24:83:C1:00:CD:31:A2:90:F8:94:75:97:39:C3:C4:11:4B:C0:28:26:85:60:01:C9:F6:2D`). Installalo solo se hai scaricato il programma da questa pagina.

### Linux

```bash
mkdir pdfdesk && tar xzf pdfdesk-<versione>-linux-x86_64.tar.gz -C pdfdesk
cd pdfdesk
./install.sh                 # per l'utente corrente (~/.local)
sudo ./install.sh --system   # per tutti gli utenti (/opt/pdfdesk)
```

Lo script aggiunge la voce nel menu delle applicazioni, l'associazione ai PDF e le icone. Per aggiornare si lancia `install.sh` del pacchetto nuovo. Per rimuovere: `~/.local/share/pdfdesk/uninstall.sh` (oppure `sudo /opt/pdfdesk/uninstall.sh --system`).

Librerie di sistema richieste da Qt (di solito già presenti in un desktop):

| Distribuzione | Pacchetti |
|---|---|
| Debian / Ubuntu | `libegl1 libgl1 libxkbcommon0 libdbus-1-3 libfontconfig1 libxcb-cursor0` |
| Fedora / RedHat | `mesa-libEGL mesa-libGL libxkbcommon dbus-libs fontconfig xcb-util-cursor` |
| Arch | `libglvnd libxkbcommon dbus fontconfig xcb-util-cursor` |

### macOS

1. Apri lo zip e trascina `PDFDesk.app` in *Applicazioni*.
2. Al primo avvio macOS può segnalare l'app come «danneggiata», perché non è firmata da Apple. Nel Terminale esegui lo script incluso nello zip:
   ```bash
   sh sblocca.sh /Applications/PDFDesk.app
   ```
   Lo script toglie l'attributo di quarantena (`xattr -cr`). Va ripetuto a ogni nuova versione.

Per aggiornare si sostituisce l'app.

### Aggiornamenti

*Aiuto → Verifica aggiornamenti…* confronta la versione in uso con l'ultima release su GitHub. Il controllo avviene solo su richiesta e non invia dati.

---

## Funzioni

### Visualizzazione
- Più PDF aperti insieme, uno per scheda; ogni scheda ricorda zoom, posizione e cronologia di annulla.
- Scorrimento continuo, zoom (Ctrl+rotella, adatta alla larghezza o alla pagina), miniature, ricerca nel testo (Ctrl+F).
- PDF protetti da password, apertura con trascina e rilascia.

### Annotazioni e disegno
- Penna, evidenziatore, linee, frecce, rettangoli ed ellissi, con colore, spessore e opacità.
- Evidenziare, sottolineare e barrare il testo, selezionando per righe (come in un lettore PDF) oppure ad area tenendo premuto **Alt**.
- **Caselle di testo** con carattere, dimensione, colore, sfondo e stile (grassetto, corsivo, sottolineato, barrato).
- **Commenti**: note standard del PDF, leggibili in qualsiasi lettore.
- **Font TTF/OTF**: si usano i font del sistema o si aggiungono i propri file `.ttf`/`.otf`; supportano accenti, €, greco, cirillico e ogni carattere presente nel font.

### Testo, immagini e oggetti del PDF
- **Modifica testo**: riscrive un blocco di testo esistente (il testo originale viene rimosso dal file).
- **Modifica oggetti**: sposta, ridimensiona ed elimina testo, immagini e grafica già presenti nel PDF.
- **Immagini**: inserimento da file (anche PNG trasparenti), dimensioni numeriche, rotazione libera o a 90°, sostituzione ed esportazione. Un clic su un'immagine selezionata attiva la rotazione con il mouse (Maiusc = scatti di 15°).
- **Selezione multipla** (rettangolo o Ctrl+clic) e **gruppi** (Ctrl+G / Ctrl+Maiusc+G).
- **Griglia** con passo a scelta (mm, cm, pollici, punti) e aggancio degli oggetti.
- **Redazione**: oscura in modo permanente testo, immagini e grafica di un'area o di un singolo oggetto; può rimuovere anche i metadati.
- Annulla e ripeti per tutte le operazioni.

### Pagine
- Riordino trascinando le miniature, rotazione, duplicazione, eliminazione.
- Inserimento di pagine vuote o da un altro PDF, estrazione in un nuovo PDF.
- **Unisci PDF**: unisce PDF e immagini in un unico file, con scelta delle pagine di ogni sorgente e un segnalibro per ogni file.

### Moduli
- Compilazione dei moduli **AcroForm**: testo, multiriga, caselle, opzioni, menu e liste, campi firma.
- **Appiattisci**: rende fisso il contenuto dei campi.

### Firme
- **Firma olografica**: disegnata con mouse o penna, oppure importata da una foto con lo sfondo reso trasparente; resta in una libreria personale.
- **Firma digitale** PAdES con certificato `.p12`/`.pfx` o **smart card / token USB** (PKCS#11). Dettagli in [Firme digitali](#firme-digitali).

### Esportazione, stampa e salvataggio
- **Esporta** in PNG, JPG, TIFF (anche multipagina), testo semplice, **DOCX** e **ODT**, con titoli, paragrafi, tabelle e immagini ricostruiti.
- **Stampa** su qualsiasi stampante di sistema o su file PDF.
- **Salva con nome / Ottimizza**: qualità predefinite (*Originale*, *Alta* 300 dpi, *Media* 150, *Bassa* 96, *Minima* 72) o personalizzate, scala di grigi, rimozione dei metadati, riduzione dei font, con stima della dimensione finale. Il testo resta sempre testo selezionabile: la compressione agisce solo su immagini e struttura del file.
- **Metadati** (Ctrl+D): campi standard e personalizzati, XMP.
- **Estrai immagini**: tutte le immagini incorporate, oppure un'area della pagina in PNG, JPG o TIFF o negli appunti.

---

## Firme digitali

**Formati.** Firma PAdES con marca temporale RFC 3161 facoltativa e riquadro visibile facoltativo con la firma-immagine. Si può firmare anche dentro i campi firma dei moduli.

**Smart card e token.** In *Firma → Firma digitale* scegli «Smart card / token USB». Il programma cerca da solo i moduli PKCS#11 più comuni (OpenSC, Bit4id, Aruba Key, InfoCamere/Incard, SafeNet…); premi *Rileva* e scegli il certificato. Sono supportati i lettori con tastierino (pinpad). Il PIN non viene mai salvato.

> Più PIN errati consecutivi bloccano la scheda.

**Validità legale.** Il valore legale della firma (firma qualificata) dipende dal certificato emesso dal prestatore, non dal programma. I certificati autofirmati, che si creano da *Firma → Crea certificato autofirmato*, garantiscono l'integrità del documento, ma i lettori PDF li segnalano come «non attendibili».

**Firme e modifiche.**

| Situazione | Comportamento |
|---|---|
| Comprimere e firmare | *Firma → Firma digitale* comprime prima e firma dopo: il file finale è valido |
| Annotare un PDF già firmato | le modifiche si aggiungono come revisione successiva e le firme restano valide |
| Più firme | si aggiungono in sequenza senza invalidare le precedenti |
| Modifiche permanenti su un PDF firmato (testo, oggetti, redazioni) | al salvataggio si sceglie «Mantieni le firme» (salvataggio incrementale) o «Scarta le firme» |
| Comprimere un PDF già firmato | le firme verrebbero invalidate: il programma chiede conferma e rimuove i campi firma |

**Verifica firme.** Per ogni firma mostra esito, integrità, copertura, modifiche successive, data e marca temporale, algoritmi e tutti i dati dei certificati.

---

## PDF/A e PDF/X

*File → Conformità PDF/A e PDF/X…* verifica un documento e lo converte in un nuovo file. La stessa scelta è presente in *Salva con nome* e in *Firma digitale*, dove il documento viene prima convertito e poi firmato.

| Standard | Uso | Conversione |
|---|---|---|
| PDF/A-1b, 2b, 3b | archiviazione a lungo termine | font incorporati, profilo sRGB, metadati XMP, niente JavaScript né cifratura; A-3b ammette allegati |
| PDF/X-1a, X-3, X-4 | stampa | colori CMYK con il profilo di stampa scelto, riquadri di rifilo e abbondanza; X-4 conserva le trasparenze |

Effetti della conversione sul documento:
- annotazioni e campi dei moduli diventano parte della pagina e non sono più modificabili; il testo resta selezionabile e ricercabile;
- le trasparenze non ammesse dallo standard diventano colori pieni equivalenti;
- i collegamenti restano nei PDF/A e vengono rimossi nei PDF/X;
- i documenti già firmati non si convertono, perché la conversione invaliderebbe la firma. L'ordine corretto è modifica → comprimi → converti → firma.

Per PDF/X va scelto il **profilo ICC dello stampatore** (per esempio FOGRA39 o SWOP); senza, si usa un profilo CMYK generico.

Un file che dichiara uno standard viene riconosciuto all'apertura. Se lo modifichi, al salvataggio puoi ripristinarne la conformità.

**Verifica.** PDF/A si verifica con il controllo interno e, se installato, con **veraPDF** (comando `verapdf` o variabile `PDFDESK_VERAPDF`). PDF/X si verifica con il solo controllo interno, che non sostituisce il preflight dello stampatore.

---

## Scansione e OCR

*File → Crea PDF da scansione…* acquisisce dallo scanner:

| Sistema | Driver |
|---|---|
| Windows | WIA (già incluso in Windows) |
| Linux | SANE: `sane-utils` (Debian/Ubuntu), `sane` (Fedora, Arch) |
| macOS | SANE: `brew install sane-backends` |

Si scelgono scanner, piano o alimentatore automatico, colore/grigi/bianco e nero, risoluzione e formato. Le pagine si riordinano, ruotano ed eliminano prima di creare il PDF. Senza scanner si possono comunque importare immagini già salvate.

**OCR (testo ricercabile)** con [Tesseract](https://github.com/tesseract-ocr/tesseract):

| Sistema | Installazione |
|---|---|
| Windows | componente «OCR» dell'installatore, oppure pulsante **Scarica OCR…** nella finestra di scansione |
| Debian / Ubuntu | `sudo apt install tesseract-ocr tesseract-ocr-ita` |
| Fedora / RedHat | `sudo dnf install tesseract tesseract-langpack-ita` |
| Arch | `sudo pacman -S tesseract tesseract-data-ita` |
| macOS | `brew install tesseract tesseract-lang` |

Tesseract viene trovato automaticamente: nel PATH, in `C:\Program Files\Tesseract-OCR`, nella cartella di PDFDesk e nel profilo utente. Non serve modificare il PATH. Un percorso diverso si indica in *Preferenze → Scansione e OCR*.

---

## Interfaccia e preferenze

- Quattro barre (**Principale**, **Pagine**, **Strumenti**, **Proprietà**) da agganciare in alto, in basso o ai lati della finestra.
- **Esc** torna allo strumento Seleziona. Un doppio clic su un oggetto passa allo strumento adatto a modificarlo.
- Menu contestuale (tasto destro) con le azioni disponibili per l'oggetto sotto il cursore.

*Modifica → Preferenze* (Ctrl+,) è organizzata per sezioni:

| Sezione | Contenuto |
|---|---|
| Generale | lingua (italiano, inglese), numero di file recenti |
| Aspetto | tema (sistema, chiaro, scuro), menu a tendina, dimensione del testo (70–200 %), scala per schermi HiDPI/Retina (100–300 %) |
| Barre degli strumenti | icone, testo sui pulsanti, disposizione, blocco |
| Visualizzazione | ingrandimento iniziale, miniature, evidenziazione dei campi, griglia, selezione del testo |
| Prestazioni | disegno della vista (Software o OpenGL), numero di processori |
| Scansione e OCR | percorso di Tesseract |

**Prestazioni.** L'esportazione in immagini o testo e la ricerca nei documenti lunghi usano più processori, fino a *n − 1*. La vista OpenGL è sperimentale; se la scheda grafica non la supporta, il programma torna al disegno software.

**Scorciatoie degli strumenti:** V seleziona · J modifica oggetti · M modifica testo · X casella di testo · C commento · P penna · E evidenziatore · R rettangolo · O ellisse · L linea · A freccia · I immagine · F firma · D redazione · G gomma · K compila modulo.

---

## Riga di comando

```bash
pdfdesk a.pdf b.pdf                                         # apre i file in schede
pdfdesk --compress in.pdf out.pdf --preset medium           # comprime
pdfdesk --compress in.pdf out.pdf --standard pdfa-2b        # converte in PDF/A-2b
pdfdesk --check file.pdf [--standard pdfx-4]                # verifica la conformità
pdfdesk --verify file.pdf                                   # verifica le firme digitali
pdfdesk --merge uscita.pdf a.pdf b.pdf scansione.png        # unisce PDF e immagini
pdfdesk --selftest                                          # autotest del programma
pdfdesk --version
```

---

## Funzioni non supportate e limiti

**Non ancora supportate**
- Moduli **XFA** (alcuni moduli dinamici di Adobe): si vede la pagina di ripiego. Sono supportati i moduli AcroForm.
- **Firma remota** (OTP o app del prestatore).
- **Carta d'Identità Elettronica (CIE)** per la firma, salvo che il sistema metta a disposizione un modulo PKCS#11 con il certificato di firma.
- PDF/A di livello **«a»** (accessibile) e **«u»**: si producono i livelli «b».
- Driver di scansione nativo per macOS (ImageCaptureCore): si usa SANE oppure si importano le immagini.
- **macOS Intel**: si distribuisce solo la versione Apple Silicon.
- Direct3D e Metal per la vista (disponibili Software e OpenGL).

**Limiti**
- **Modifica testo** usa un carattere standard simile all'originale (Helvetica, Times o Courier) e non ridistribuisce il resto della pagina. Per i caratteri non latini serve un font TTF/OTF che li contenga.
- **Font TTF/OTF** nelle caselle di testo: l'aspetto salvato è identico in qualsiasi lettore, ma per *modificare* la casella su un altro computer serve lo stesso font. Grassetto e corsivo non sono disponibili con questi font.
- Il colore del testo di una casella è anche il colore del suo bordo (limite del formato PDF).
- **Esportazione DOCX/ODT**: impaginazione esatta, colonne multiple e tabelle senza bordi non sono riprodotte fedelmente. Per i PDF scansionati conviene esportare in immagini.
- La **stampa** invia le pagine come immagini (fino a 300 dpi).
- La **redazione** non modifica segnalibri e allegati. I metadati si rimuovono con l'opzione dedicata.
- **Annulla** conserva fino a circa 400 MB di stati: con PDF molto grandi la cronologia è più corta.
- In **Modifica oggetti** le immagini non si spostano sulle pagine ruotate e la grafica complessa si seleziona pezzo per pezzo.
- **Appiattisci** trasforma in contenuto fisso anche i campi firma vuoti. Nei file firmati è disattivato.
- Le build Windows usano un certificato autofirmato e quelle macOS non sono notarizzate da Apple (vedi [Download e installazione](#download-e-installazione)).

---

## Compilare dai sorgenti

Esecuzione diretta dai sorgenti (Python 3.11):

```bash
pip install -r requirements.lock
python run_pdfdesk.py [file.pdf]
```

Per creare gli eseguibili:

```bash
./build.sh      # Linux e macOS: test, eseguibile, autotest e pacchetto in dist/
build.bat       # Windows
```

Tutte le piattaforme si compilano con **Python 3.11** e con le versioni esatte dei moduli in `requirements.lock`; `check_build_env.py` blocca la compilazione se qualcosa non corrisponde. Serve **Ghostscript**, che viene incluso nel pacchetto.

Compilazione per Windows da Linux (Wine), installatore, firma degli eseguibili, macOS via SSH o GitHub Actions e test sono descritti in [COMPILARE.md](COMPILARE.md).

---

## Licenza

**AGPL-3.0-or-later** (vedi [LICENSE](LICENSE)), perché il programma usa PyMuPDF (AGPL). Componenti principali: Qt/PySide6 (LGPL), pyHanko (MIT), cryptography (Apache/BSD), Ghostscript (AGPL). Elenco completo in [THIRD_PARTY.md](THIRD_PARTY.md).

PDFDesk — Guido Cauli <guido.cauli@gmail.com>
