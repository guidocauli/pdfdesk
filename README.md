# PDFDesk — Guido Cauli <guido.cauli@gmail.com>

Editor PDF grafico e semplice da usare per **Windows, Linux e macOS**, distribuito come **singolo eseguibile** (nessuna installazione di Python o di librerie).

## Cosa fa

| Funzione | Come |
|---|---|
| Aprire e visualizzare PDF | scorrimento continuo, zoom (Ctrl+rotella, adatta larghezza/pagina), miniature, ricerca testo (Ctrl+F), PDF protetti da password, trascina e rilascia |
| Annotare e disegnare | **Penna**, **Evidenziatore**, evidenzia/sottolinea/barra il **testo**, linee, frecce, rettangoli e ellissi (cornici o aree colorate), colore/spessore/opacità |
| Caselle di testo | crea (trascina), modifica con doppio clic, cambia carattere/dimensione/colore/sfondo; sposta e ridimensiona con le maniglie |
| Font **TTF/OTF** | nel selettore del carattere: *Aggiungi font…* importa file `.ttf`/`.otf` nella libreria personale; sono disponibili anche i font installati nel sistema. Funzionano nelle caselle di testo e in «Modifica testo» |
| **Moduli** compilabili | strumento «Compila modulo» (K): clic su un campo per scrivere (anche multiriga), spuntare caselle e opzioni, scegliere dai menu; i campi sono evidenziati; *Moduli → Appiattisci* rende fisso il contenuto |
| Modificare il testo esistente | strumento «Modifica testo»: riscrive un blocco di testo del PDF (il vecchio testo viene rimosso dal file) |
| Redazione | segna aree da oscurare, poi **Applica redazioni**: testo, immagini e grafica sotto l'area sono rimossi in modo permanente |
| Inserire immagini | da file (PNG con trasparenza supportato), spostabili e ridimensionabili |
| Gestire le pagine | riordina trascinando le miniature, ruota, duplica, elimina, inserisci pagine vuote o da un altro PDF, estrai in un nuovo PDF |
| Firma **olografica** | disegna la firma con mouse/penna o importala da una foto (sfondo reso trasparente); resta in una libreria e si inserisce con un clic |
| Firma **digitale** | PAdES con certificato `.p12/.pfx` **oppure con smart card / token USB** (PKCS#11, PIN o pinpad del lettore); riquadro visibile opzionale con la firma-immagine; firma anche nei **campi firma** dei moduli; marca temporale RFC 3161 opzionale |
| Verifica firme | integrità, copertura, attendibilità di ogni firma |
| **PDF/A** e **PDF/X** | conversione a PDF/A-1b, 2b, 3b (archiviazione) e PDF/X-1a, X-3, X-4 (stampa) e verifica di conformità; il file aperto che dichiara uno standard viene riconosciuto e, dopo le modifiche, si può **ripristinare la conformità** al salvataggio |
| **Schede** | più PDF aperti insieme, uno per scheda (Ctrl+O anche con selezione multipla, trascina più file, `pdfdesk a.pdf b.pdf`); Ctrl+W chiude, Ctrl+Tab cambia; ogni scheda ricorda zoom, posizione e cronologia di annulla; un asterisco segna le modifiche non salvate |
| **Stampa** | File → Stampa (Ctrl+P): stampanti di sistema o «Stampa su file PDF», tutte le pagine, intervallo o pagina corrente |
| **Esporta** | File → Esporta (Ctrl+Maiusc+E): **immagini PNG / JPG / TIFF** (risoluzione, qualità, TIFF multipagina), **testo semplice**, **DOCX** e **ODT** con la struttura ricostruita: titoli, paragrafi (grassetto, corsivo, dimensione, colore, allineamento), tabelle, immagini e interruzioni di pagina |
| Salvare a diverse qualità | *Originale*, *Alta* (300 dpi), *Media* (150), *Bassa* (96), *Minima* (72); opzioni: scala di grigi, rimuovi metadati, riduci i font |

Il **testo resta sempre testo** (selezionabile e ricercabile): la compressione agisce solo su immagini e struttura del file.

## Firme digitali e compressione: cosa è possibile

Una firma digitale protegge l'esatto contenuto del file: **qualsiasi riscrittura del file, compressione compresa, invalida le firme già presenti**. Per questo:

- **Comprimere e firmare**: usa *Firma → Firma digitale*, che comprime *prima* e firma *dopo* (il file finale è firmato e valido).
- **PDF già firmato**: si può annotare e salvare, ma le modifiche vengono aggiunte come *revisione successiva* e le firme restano valide; in questi documenti Annulla e compressione sono disattivati. Se scegli comunque di comprimere, il programma chiede conferma ed elimina i campi firma (non restano firme «rotte»).
- Si possono aggiungere **più firme** in sequenza senza invalidare le precedenti.

I certificati autofirmati (si creano da *Firma → Crea certificato autofirmato*) garantiscono l'integrità ma i lettori PDF li segnalano «non attendibili». Per firme con valore legale servono certificati di un prestatore qualificato.

## Metadati, compressione, estrazione, firme

- **Redazione per oggetto**: con lo strumento Redazione un clic segna l'intero testo, immagine o grafica sotto il cursore (un secondo clic sul segno lo toglie); in alternativa si trascina un'area. I segni sono annotazioni selezionabili e ogni passo si annulla con Annulla finché non applichi le redazioni.
- **Menu contestuale** (tasto destro): seleziona l'oggetto sotto il cursore e offre le funzioni pertinenti: per testo del PDF modifica, copia, evidenzia/sottolinea/barra; per le immagini salva; per ogni oggetto o annotazione segna per la redazione, elimina, salva l'area come immagine o copiala negli appunti; per i campi modifica; su pagina vuota aggiungi testo o immagine, ruota, duplica, elimina pagina.
- **Trasparenza**: le immagini con canale alfa o maschera morbida (PNG, JPX, SMask, anche CMYK) si spostano, estraggono e mostrano conservando l'alfa.
- Tutte le finestre di dialogo sono modali sull'intera applicazione.

- **Metadati** (File ▸ Metadati, Ctrl+D): visualizza e modifica i campi standard (titolo, autore, oggetto, parole chiave, date), aggiunge o elimina campi personalizzati, mostra l'XMP e permette di rigenerarlo o rimuoverlo. L'operazione si può annullare.
- **Redazione**: nella conferma c'è l'opzione «Rimuovi anche i metadati» (Info, campi personalizzati, XMP).
- **Salva con nome**: schede *Qualità* (preset o «Personalizzata»: soglia e risoluzione di arrivo, qualità JPEG, tipi di immagine, ricompressione con/senza perdita), *Avanzate* (garbage collection, flussi di contenuto, flussi di oggetti, miniature, allegati, JavaScript, Fast web view) e *Analisi e stima* (dove sta lo spazio e dimensione prevista). Con PDF/A e PDF/X i controlli di compressione sono disattivati perché i parametri sono obbligatori.
- **Estrazione**: *Strumenti ▸ Estrai immagini…* salva tutte (o le scelte) le immagini incorporate; lo strumento «Estrai immagine/area» salva l'immagine cliccata o un'area trascinata (testo, grafica e immagini insieme) in PNG, JPG o TIFF, oppure la copia negli appunti.
- **Firme digitali** (Verifica firme): elenco delle firme e, per quella selezionata, tutti i dati: esito, integrità, copertura e modifiche successive, DocMDP, data dichiarata e marca temporale, motivo/luogo/contatto, algoritmi, byte range, revisione, e per ogni certificato soggetto, emittente, seriale, validità, chiave, usi, impronte SHA-1/SHA-256. Il testo si può copiare.

## Unire PDF e scansione

- **Unisci PDF** (File ▸ Unisci PDF…, disponibile anche senza documenti aperti): aggiungi PDF e immagini, riordinali trascinando o con Su/Giù (anche «Ordina per nome» e «Inverti ordine»), limita le pagine di ogni file (es. `1-3,5`), gestisce i PDF protetti da password; opzione per un segnalibro per ogni file sorgente. Da riga di comando: `pdfdesk --merge uscita.pdf a.pdf b.pdf scansione.png`.
- **Crea PDF da scansione** (File ▸ Crea PDF da scansione…): usa **WIA** su Windows (PowerShell, incluso in Windows) e **SANE** su Linux e macOS (comando `scanimage`: pacchetto `sane-utils` su Debian/Ubuntu, `sane` su Arch/RedHat, `sane-backends` con Homebrew su macOS). Si scelgono scanner, origine (piano o alimentatore automatico, che acquisisce tutte le pagine), modo (colore, grigi, bianco e nero), risoluzione e formato carta. Le pagine acquisite si riordinano, si ruotano e si eliminano; si possono aggiungere immagini già salvate. Il PDF ha la dimensione fisica corretta, compressione PNG o JPEG a scelta e, se è installato **Tesseract**, l'OCR per rendere il testo ricercabile. Senza driver resta l'importazione da file immagine.
- Limite: non c'è un driver nativo macOS (ImageCaptureCore): serve SANE, oppure si importano le immagini acquisite con l'app Acquisizione Immagine.

## Font, moduli e smart card: dettagli

**Font TTF/OTF.** Le caselle con font personale sono annotazioni il cui aspetto è disegnato dal programma, quindi si vedono identiche in qualsiasi lettore. Il font **non** viene incorporato per intero nel file (licenze e dimensioni): se apri il PDF su un altro computer senza quel font, l'aspetto già salvato resta corretto, ma per *modificare* quella casella serve avere il font (altrimenti il programma lo segnala e puoi sceglierne un altro). Le caselle accettano qualsiasi carattere presente nel font (accenti, €, greco, cirillico, …).

**Moduli.** Supporta i moduli AcroForm (la grande maggioranza): testo, multiriga, caselle, opzioni, menu a tendina e liste, campi di firma. Non supporta i moduli **XFA** (alcuni moduli dinamici di Adobe): in quel caso il PDF mostra la pagina di ripiego. Compilare un modulo già firmato aggiunge una revisione senza invalidare le firme precedenti; appiattire invece è bloccato nei file firmati. Nota: *Appiattisci* trasforma in testo fisso anche i campi firma ancora vuoti.

**Smart card.** In *Firma → Firma digitale* scegli «Smart card / token USB», indica il modulo **PKCS#11** del produttore (il programma cerca da solo OpenSC e i driver più comuni: Bit4id, Aruba Key, InfoCamere/Incard, SafeNet…), premi *Rileva* e scegli il certificato di firma. Il PIN non viene mai salvato; con i lettori con tastierino (pinpad) spunta l'opzione dedicata e digitalo sul lettore. Attenzione: più PIN errati consecutivi bloccano la scheda. Puoi usare la stessa finestra per firmare in un campo firma del modulo.

- Il programma firma **con la chiave della tua scheda** (CNS, Firma Digitale su token, ecc.): la validità legale (firma qualificata/FEQ) dipende dal certificato emesso dal tuo prestatore, non dal programma.
- La **Carta d'Identità Elettronica (CIE)** usa un proprio modulo e un PIN dedicato: funziona solo se espone un modulo PKCS#11 con certificato di firma sul tuo sistema. Non ho potuto provare schede reali: il funzionamento è stato verificato con un token virtuale SoftHSM.
- La **firma remota** (OTP/app dei prestatori) non è supportata.

## PDF/A e PDF/X

**Come si usa.** *File → Conformità PDF/A e PDF/X…* verifica il documento e lo converte in un nuovo file; la stessa scelta è nella finestra *Salva con nome / Ottimizza* (dopo la compressione, come ultimo passo) e in *Firma → Firma digitale* (si converte e poi si firma: la firma resta valida e lo standard dichiarato rimane). Da terminale: `pdfdesk --compress in.pdf out.pdf --standard pdfa-2b` e `pdfdesk --check file.pdf [--standard pdfx-4]`.

| Standard | Quando | Cosa fa la conversione |
|---|---|---|
| PDF/A-1b, 2b, 3b | archiviazione a lungo termine | font incorporati (anche i base-14), profilo sRGB, XMP, niente JavaScript/cifratura; in A-1b le trasparenze sono portate su sfondo bianco; A-3b ammette allegati |
| PDF/X-1a, X-3, X-4 | file per la stampa | colori in CMYK con profilo di stampa (a scelta, altrimenti CMYK generico), TrimBox/BleedBox, ID e Trapped, font incorporati; X-1a e X-3 senza trasparenze, X-4 le conserva |

Cosa succede al documento (è importante saperlo):
- **Annotazioni e campi dei moduli sono appiattiti** nella pagina (diventano parte del contenuto, non più modificabili); i campi firma vuoti sono eliminati. Il **testo resta testo** (selezionabile, ricercabile, anche cirillico, greco, ecc.).
- **Trasparenze** non ammesse dallo standard: evidenziazioni e opacità sono sostituite da colori pieni equivalenti su sfondo bianco; le immagini con trasparenza sono composte su bianco.
- **Collegamenti ipertestuali**: mantenuti in PDF/A (pagine non ruotate); eliminati in PDF/X (le annotazioni stampabili sono vietate). Le pagine ruotate vengono riscritte già ruotate.
- **Firme digitali**: la conversione le invaliderebbe, perciò è rifiutata per i documenti già firmati. Ordine giusto: modifica → comprimi → converti → firma.
- **Livello «b»**: PDF/A-xb garantisce l'aspetto visivo identico nel tempo; i livelli «a» (accessibilità, struttura etichettata) e «u» non sono prodotti.
- **PDF/X richiede il profilo del tuo stampatore**: senza, viene usato il CMYK generico di Ghostscript, valido per lo standard ma non adatto alla stampa professionale. Scegli il profilo ICC (es. FOGRA39, SWOP) nella finestra.

**Verifica.** Per PDF/A il programma esegue un controllo interno e, se è installato **veraPDF** (variabile `PDFDESK_VERAPDF` o comando `verapdf`), lo usa come validatore indipendente; tutti i file prodotti dai test risultano conformi secondo veraPDF 1.30. Per PDF/X non esiste un validatore libero incluso: la verifica è solo interna (versione dichiarata, OutputIntent, riquadri, font, colori, trasparenze, annotazioni) e **non sostituisce il preflight dello stampatore**.

La conversione usa **Ghostscript** (incluso nei pacchetti ufficiali; da sorgente va installato o indicato con `PDFDESK_GS`) e può richiedere alcuni secondi per documenti con molte immagini: l'interfaccia resta reattiva e mostra un indicatore. Vedi `THIRD_PARTY.md` per le licenze.

## Interfaccia e Preferenze
- Quattro barre — **Principale**, **Pagine**, **Strumenti**, **Proprietà** — con icone e tooltip su ogni controllo. Si spostano trascinando la maniglia e si agganciano in alto, in basso **o ai lati** della finestra (in verticale i controlli si dispongono in colonna); per impostazione predefinita stanno su una riga se la finestra è abbastanza larga, altrimenti su due.
- Finché non è aperto un PDF, strumenti, inserimenti, firme, pagine, moduli, stampa ed esportazione sono disattivati (restano Apri, Nuovo, Preferenze, Informazioni).
- **Ingrandimento**: menu a discesa nella barra Principale (e in Visualizza) con percentuali, «adatta alla larghezza/pagina» e «Altro…».
- La barra **Pagine** ha navigazione (precedente/successiva/numero), rotazione, duplica, inserisci, estrai, elimina e il pannello Miniature.
- **Modifica → Preferenze** (Ctrl+,): dimensione icone, testo sui pulsanti, righe delle barre, blocco barre, ingrandimento iniziale, miniature all'avvio, evidenziazione campi, file recenti.
- **Inserisci**: menu con tutte le funzioni di inserimento della barra Strumenti (casella di testo, immagine, firme, forme, penne, evidenziazioni, redazione, pagine). **Strumenti**: selezione, modifica oggetti/testo, mano, copia testo, moduli, gomma.
- **Annulla/Ripeti** ridisegna solo le pagine che cambiano (nessun lampo sull'intero foglio).
- **Modifica oggetti** (tasto J): con il mouse si selezionano blocchi di testo, immagini e grafica vettoriale già presenti nel PDF; si spostano trascinando, si ridimensionano con le maniglie (le immagini mantengono le proporzioni; Maiusc per liberarle), si eliminano con Canc, il testo si riscrive con un doppio clic. Limiti: il testo riscritto usa un font standard simile all'originale; le immagini non si spostano sulle pagine ruotate; la grafica complessa va selezionata pezzo per pezzo. Le annotazioni (anche di altri programmi) si modificano con **Seleziona**.
- **Griglia**: Preferenze → Griglia (e Visualizza) permette di mostrare una griglia con passo arbitrario (mm, cm, pollici o punti) e di agganciare ai suoi vertici lo spostamento e il ridimensionamento degli oggetti.
- **Miniature**: lo zoom delle miniature segue automaticamente la larghezza della colonna.
- **Annulla** vale per tutte le operazioni sugli oggetti, anche nei PDF firmati (le firme restano valide finché non si compie un'operazione permanente; in tal caso vengono scartate solo al salvataggio).
- **Tema**: Preferenze → Tema (Come il sistema / Chiaro / Scuro). «Come il sistema» segue Windows, macOS e, su Linux, il portale/GNOME/KDE.
- **Menu a tendina**: su Wayland i menu popup di Qt possono comparire staccati dalla barra; per questo, di default, su Wayland le tendine sono disegnate dentro la finestra (Preferenze → Menu a tendina: Automatico / Integrati / Standard di Qt). Con i menu integrati si naviga con il mouse e Esc chiude.
- Il menu usa la barra dei menu della finestra (non quella nativa di sistema): le voci si aprono sotto il proprio titolo.

## Uso rapido

1. **Apri** un PDF (Ctrl+O o trascinalo nella finestra).
2. Scegli uno strumento nella barra a sinistra (scorciatoie: V seleziona, P penna, E evidenziatore, R rettangolo, O ellisse, L linea, A freccia, X testo, M modifica testo, I immagine, F firma, D redazione, G gomma, K compila modulo).
3. Con **Seleziona**: clic su un'annotazione per spostarla/ridimensionarla (Maiusc libera le proporzioni delle immagini), Canc per eliminarla, frecce per spostarla di 1 punto (Maiusc: 10).
4. **Salva** (Ctrl+S) o **Salva con nome / Ottimizza** (Ctrl+Maiusc+S) per scegliere qualità e compressione.

Da terminale: `pdfdesk --version`, `pdfdesk --compress in.pdf out.pdf --preset medium`, `pdfdesk --verify file.pdf`, `pdfdesk --selftest`.

## Limiti noti (versione 0.5)

- **Redazione e modifiche permanenti**: l'applicazione elimina davvero dal file testo, immagini e grafica sotto le aree, oltre a note/commenti e campi compilati sovrapposti e all'anteprima incorporata della pagina (verificato con scansione di tutti gli oggetti e i flussi del file salvato, anche sui PDF firmati, che vengono riscritti per intero: le firme sono rimosse perché un salvataggio incrementale conserverebbe la revisione originale). Prima di sovrascrivere il file originale con modifiche irreversibili compare un avviso che consiglia «Salva con nome». I metadati (titolo, autore…), i segnalibri e gli allegati non vengono modificati: per i metadati usa «Salva con nome» → rimuovi metadati.

- **Esporta in DOCX/ODT**: la struttura è ricostruita dal contenuto del PDF (ordine di lettura, dimensione del testo per riconoscere i titoli, linee per le tabelle): l'impaginazione esatta, le colonne multiple, le tabelle senza bordi e i PDF scansionati (senza testo) non sono riprodotti fedelmente; per le scansioni usa l'esportazione in immagini.
- **Stampa**: le pagine sono stampate come immagini (fino a 300 dpi), con annotazioni e campi del modulo visibili.

- **Firma remota** (OTP, app del prestatore) non supportata; le smart card sono supportate via PKCS#11 ma provate solo con un token virtuale, non con schede fisiche.
- **Modifica testo**: riscrive il blocco con carattere standard (Helvetica/Times/Courier, scelto in base all'originale) e non fa il reflow del resto della pagina; in «Modifica testo» per i caratteri fuori dal latino scegli un font TTF/OTF che li contenga.
- Il colore del testo di una casella è anche il colore del suo bordo (limite del formato PDF per le annotazioni di testo).
- Moduli **XFA** non supportati (solo AcroForm). I font TTF/OTF delle caselle non sono incorporati per intero (vedi sopra).
- Le immagini inserite sono annotazioni (spostabili/eliminabili); le immagini già presenti nel PDF non sono modificabili singolarmente (si possono oscurare con la redazione).
- PDF/A e PDF/X: vedi la sezione dedicata (annotazioni appiattite, livello «b», PDF/X validato solo internamente).
- Annulla/ripeti conserva copie dello stato (limite ~400 MB): con PDF molto grandi la cronologia si accorcia.
- Gli eseguibili non sono firmati dal produttore: Windows SmartScreen e macOS Gatekeeper mostreranno un avviso al primo avvio (macOS: clic destro → Apri).

## Compilare

```bash
./build.sh            # Linux / macOS: test + eseguibile + selftest + pacchetto in dist/
build.bat             # Windows
```

Per compilare Windows, Linux e macOS (Intel e Apple Silicon) in un colpo solo c'è il workflow GitHub Actions `.github/workflows/build.yml` (avvio manuale o tag `v*`). Per compilare serve **Ghostscript** installato (viene incluso nel pacchetto): `apt install ghostscript fonts-urw-base35`, `brew install ghostscript`, oppure l'installer da ghostscript.com (Windows). Su Linux servono le librerie di sistema di Qt: Debian/Ubuntu `libegl1 libgl1 libxkbcommon0 libdbus-1-3 libfontconfig1 libxcb-cursor0`; Fedora/RedHat `mesa-libEGL mesa-libGL libxkbcommon dbus-libs fontconfig xcb-util-cursor`; Arch `libglvnd libxkbcommon dbus fontconfig xcb-util-cursor`.

I pacchetti hanno il numero di versione nel nome: `pdfdesk-<versione>-linux-<arch>.tar.gz`, `pdfdesk-<versione>-windows-x86_64.zip`, `pdfdesk-<versione>-macos-<arch>.zip`, `pdfdesk-<versione>-sorgenti.tar.gz` (`./make_sources.sh`). La versione si legge da `pdfdesk/__init__.py`.

Esecuzione da sorgente: `pip install -r requirements.txt && python run_pdfdesk.py [file.pdf]`.

### Compilare Windows e macOS da questo computer
PyInstaller non fa cross-compilazione: ogni eseguibile va costruito con le librerie della propria piattaforma. Gli script qui sotto automatizzano i tre percorsi possibili (nessuno di essi è stato provato dall'autore sul proprio ambiente: vedi le note).

| Obiettivo | Da dove | Comando |
|---|---|---|
| Linux | Linux | `./build.sh` |
| Windows | Windows (anche una VM) | `build.bat` |
| Windows | Linux con Docker (Wine + Python per Windows) | `./build_windows_wine.sh [--with-tests]` |
| macOS | un Mac | `./build.sh` (serve `brew install ghostscript`) |
| macOS | Linux, con un Mac raggiungibile via SSH | `MAC_HOST=utente@mac.lan ./build_macos_remote.sh` |
| tutto il possibile | Linux | `MAC_HOST=… ./build_all.sh` |

- La compilazione sotto Wine produce un vero `pdfdesk.exe` (Python 3.11: Wine 9 non supporta `CopyFile2` di Python 3.12). Sotto Wine si può provare la parte non grafica (conversione PDF/A con Ghostscript incluso); la finestra no, perché Qt richiede `icuuc.dll` di Windows. Prova sempre l'eseguibile su Windows reale prima di distribuirlo.
- macOS richiede macOS: le licenze Apple consentono le VM macOS solo su hardware Apple, quindi non è prevista una compilazione su un hypervisor generico.

## Test

```bash
QT_QPA_PLATFORM=offscreen python -I -W ignore tests/test_core.py   # annotazioni, redazione, compressione, firme, CLI
QT_QPA_PLATFORM=offscreen python -I -W ignore tests/test_gui.py    # interfaccia con mouse simulato
QT_QPA_PLATFORM=offscreen python -I -W ignore tests/test_features.py  # font TTF/OTF, moduli, smart card (con SoftHSM, se installato)
QT_QPA_PLATFORM=offscreen python -I -W ignore tests/test_standards.py  # PDF/A e PDF/X (richiede Ghostscript; veraPDF opzionale)
```

## Licenza

AGPL-3.0-or-later (vedi `LICENSE`), perché usa PyMuPDF (AGPL). Altri componenti: Qt/PySide6 (LGPL), pyHanko (MIT), cryptography (Apache/BSD).

— PDFDesk, Guido Cauli <guido.cauli@gmail.com>
