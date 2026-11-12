# Compilare PDFDesk

**PDFDesk — Guido Cauli <guido.cauli@gmail.com>**

## Ambiente di compilazione

Tutti gli eseguibili si compilano con **Python 3.11** e con le versioni esatte dei moduli in `requirements.lock`, in modo identico su Windows, Linux e macOS. Python 3.11 è necessario perché Wine, usato per compilare Windows da Linux, non supporta Python 3.12 e successivi.

`build.sh`, `build.bat` e `build_windows_wine.sh` installano il lock (con `--no-deps`: il lock è completo, così non entrano pacchetti in più, come i moduli di analisi del layout di PyMuPDF che il programma non usa) e lanciano `check_build_env.py`, che blocca la compilazione se Python o un modulo non corrispondono. La versione di patch di Python (3.11.x) può variare.

NumPy è fissato alla 1.26.4: serve a PyMuPDF per riconoscere le tabelle, e le versioni 2.x non si caricano sotto Wine.

Il sorgente deve restare compatibile con Python 3.11: per esempio, niente f-string con apici dello stesso tipo o barre rovesciate dentro le espressioni.

### Requisiti

| Sistema | Requisiti |
|---|---|
| Tutti | Python 3.11, **Ghostscript** (viene incluso nel pacchetto) |
| Debian / Ubuntu | `apt install ghostscript fonts-urw-base35 libegl1 libgl1 libxkbcommon0 libdbus-1-3 libfontconfig1 libxcb-cursor0` |
| Fedora / RedHat | `dnf install ghostscript mesa-libEGL mesa-libGL libxkbcommon dbus-libs fontconfig xcb-util-cursor` |
| Arch | `pacman -S ghostscript libglvnd libxkbcommon dbus fontconfig xcb-util-cursor` |
| macOS | Xcode Command Line Tools, `brew install python@3.11 ghostscript` |
| Windows | Python 3.11 da python.org, Ghostscript da ghostscript.com |

## Comandi

PyInstaller non compila per altri sistemi: ogni eseguibile si costruisce con le librerie della propria piattaforma.

| Obiettivo | Da dove | Comando |
|---|---|---|
| Linux | Linux | `./build.sh` |
| Windows | Windows (anche una VM) | `build.bat` |
| Windows | Linux, con Wine | `./build_windows_wine.sh [--with-tests]` |
| macOS | un Mac | `PYTHON=python3.11 ./build.sh` |
| macOS | Linux, con un Mac raggiungibile via SSH | `MAC_HOST=utente@mac.lan ./build_macos_remote.sh` |
| macOS Apple Silicon | GitHub Actions | *Actions → build → Run workflow*, oppure push di un tag `v*` |
| tutto il possibile | Linux | `MAC_HOST=… ./build_all.sh` |

Con `--skip-tests` `build.sh` salta la suite di test.

**Windows con Wine.** Produce un vero `pdfdesk.exe` con Python 3.11. Sotto Wine si può eseguire l'autotest della parte non grafica; la finestra richiede Windows, perché Qt usa librerie (`icuuc.dll`) che Wine non fornisce.

**GitHub Actions.** Il workflow `.github/workflows/build.yml` compila e collauda solo macOS Apple Silicon e produce l'artefatto `pdfdesk-macos-arm64` (zip con `sblocca.sh`). Windows e Linux si compilano in locale. macOS Intel non si compila: `cryptography` 50 non ha pacchetti per macOS x86_64.

**macOS in VM.** Le licenze Apple consentono macOS virtualizzato solo su hardware Apple.

## Pacchetti

| Comando | Risultato |
|---|---|
| `./build.sh` (Linux) | `dist/pdfdesk-<versione>-linux-x86_64.tar.gz`, che si estrae in `pdfdesk-<versione>/` |
| `./build.sh` (macOS) | `dist/pdfdesk-<versione>-macos-<arch>.zip` con `sblocca.sh` |
| `./build_installer.sh` | `dist/pdfdesk-<versione>-windows-x86_64-setup.exe`, firmato |
| `./make_sources.sh` | `dist/pdfdesk-<versione>-sorgenti.tar.gz` (senza chiavi di firma) |

La versione si legge da `pdfdesk/__init__.py`.

### Installatore Windows

`./build_installer.sh` richiede `makensis` (pacchetto `nsis`) e parte da `dist-wine/pdfdesk.exe` o `dist/pdfdesk.exe`. Lo script NSIS è `packaging/windows/pdfdesk.nsi`. Componenti: programma, collegamenti, associazione ai PDF, certificato dell'editore, OCR (Tesseract scaricato da internet, versione e SHA-256 fissati in `pdfdesk/scan.py`).

Le icone si rigenerano con `python packaging/make_icons.py` (cartella `packaging/assets/`).

### Firma degli eseguibili Windows

```bash
./sign_windows.sh ENTRATA.exe USCITA.exe
```

Usa la chiave privata `packaging/signing/pdfdesk-sign.key`, che non è nel repository, e richiede `osslsigncode`. `build_installer.sh` firma da solo eseguibile e installatore. Il certificato pubblico è `packaging/windows/pdfdesk-sign.cer`.

## Test

```bash
export QT_QPA_PLATFORM=offscreen
pip install -r requirements-test.txt
python -I -W ignore tests/test_core.py         # annotazioni, redazione, compressione, firme, riga di comando
python -I -W ignore tests/test_gui.py          # interfaccia con mouse simulato
python -I -W ignore tests/test_features.py     # font TTF/OTF, moduli, smart card (con SoftHSM, se installato)
python -I -W ignore tests/test_standards.py    # PDF/A e PDF/X (richiede Ghostscript; veraPDF facoltativo)
python -I -W ignore tests/test_newfeatures.py  # funzioni recenti, pacchetti, OCR
python -I -W ignore tests/test_mergescan.py    # unione e scansione
```

Tutta la suite: `python -W ignore -m unittest discover -s tests -p "test_*.py"`.

L'eseguibile compilato si collauda con `pdfdesk --selftest`.

## Traduzioni

I testi dell'interfaccia passano da `tr()` (`pdfdesk/i18n.py`). Il catalogo inglese è `pdfdesk/i18n_en.py`; per una nuova lingua basta un catalogo analogo.
