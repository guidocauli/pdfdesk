; PDFDesk — Guido Cauli <guido.cauli@gmail.com>
; Installer per Windows (NSIS). Installa, AGGIORNA una versione precedente (stessa cartella, stessi collegamenti) e si disinstalla.
; Compilazione: makensis -DVERSION=0.7.13 -DEXE=..\..\dist-wine\pdfdesk.exe -DOUTFILE=pdfdesk-0.7.13-windows-x86_64-setup.exe pdfdesk.nsi
; Opzioni da riga di comando:  /S (silenzioso)   /D=C:\percorso (cartella, ultimo parametro)   /CERT (con /S: installa anche il certificato)
; L'eseguibile e questo installer sono firmati con il certificato autofirmato pdfdesk-sign.cer (vedi sign_windows.sh): la sezione
; «Certificato» lo aggiunge alle autorità attendibili e agli editori attendibili del computer, così Windows riconosce la firma.
; Sezione «OCR»: scarica Tesseract da internet (versione e SHA-256 fissati in pdfdesk/scan.py) eseguendo «pdfdesk.exe --install-ocr»;
; in modalità silenziosa solo con /OCR. Opzioni:  /S  /D=C:\percorso  /CERT  /OCR

Unicode true
!ifndef VERSION
  !define VERSION "0.0.0"
!endif
!ifndef EXE
  !define EXE "..\..\dist\pdfdesk.exe"
!endif
!ifndef OUTFILE
  !define OUTFILE "pdfdesk-${VERSION}-windows-x86_64-setup.exe"
!endif
!define APP "PDFDesk"
!define PUBLISHER "Guido Cauli"
!define URL "https://github.com/guidocauli/pdfdesk"
!define UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP}"
!define APP_KEY "Software\${APP}"

Name "${APP} ${VERSION}"
OutFile "${OUTFILE}"
InstallDir "$PROGRAMFILES64\${APP}"
InstallDirRegKey HKLM "${APP_KEY}" "InstallDir"
RequestExecutionLevel admin
SetCompressor /SOLID lzma
BrandingText "${APP} ${VERSION} — Guido Cauli <guido.cauli@gmail.com>"
VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "${APP}"
VIAddVersionKey "CompanyName" "${PUBLISHER}"
VIAddVersionKey "FileDescription" "Installazione di ${APP}"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "LegalCopyright" "Guido Cauli <guido.cauli@gmail.com>"

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "WordFunc.nsh"
!include "x64.nsh"
!include "Sections.nsh"
!include "FileFunc.nsh"
!insertmacro GetSize
!insertmacro GetParameters
!insertmacro GetOptions

!define MUI_ICON "..\assets\pdfdesk.ico"
!define MUI_UNICON "..\assets\pdfdesk.ico"
!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\pdfdesk.exe"
!define MUI_FINISHPAGE_RUN_NOTCHECKED
!define MUI_FINISHPAGE_LINK "${URL}"
!define MUI_FINISHPAGE_LINK_LOCATION "${URL}"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "..\..\LICENSE"
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "Italian"
!insertmacro MUI_LANGUAGE "English"

LangString MSG_UPDATE ${LANG_ITALIAN} "È installato PDFDesk $0. Vuoi aggiornarlo alla versione ${VERSION}?$\n$\nLe tue impostazioni e le firme salvate vengono conservate."
LangString MSG_UPDATE ${LANG_ENGLISH} "PDFDesk $0 is installed. Do you want to update it to version ${VERSION}?$\n$\nYour settings and saved signatures are kept."
LangString MSG_SAME ${LANG_ITALIAN} "PDFDesk ${VERSION} è già installato. Vuoi reinstallarlo?"
LangString MSG_SAME ${LANG_ENGLISH} "PDFDesk ${VERSION} is already installed. Do you want to reinstall it?"
LangString MSG_OLDER ${LANG_ITALIAN} "È già installata una versione più recente di PDFDesk ($0). Vuoi installare comunque la ${VERSION}?"
LangString MSG_OLDER ${LANG_ENGLISH} "A newer version of PDFDesk ($0) is already installed. Do you want to install ${VERSION} anyway?"
LangString MSG_RUNNING ${LANG_ITALIAN} "PDFDesk è in esecuzione. Chiudilo e premi Riprova, oppure Annulla per interrompere."
LangString MSG_RUNNING ${LANG_ENGLISH} "PDFDesk is running. Close it and press Retry, or Cancel to stop."
LangString MSG_64 ${LANG_ITALIAN} "PDFDesk richiede Windows a 64 bit."
LangString MSG_64 ${LANG_ENGLISH} "PDFDesk requires 64-bit Windows."
LangString SEC_MAIN ${LANG_ITALIAN} "PDFDesk (obbligatorio)"
LangString SEC_MAIN ${LANG_ENGLISH} "PDFDesk (required)"
LangString SEC_DESK ${LANG_ITALIAN} "Icona sul desktop"
LangString SEC_DESK ${LANG_ENGLISH} "Desktop shortcut"
LangString SEC_ASSOC ${LANG_ITALIAN} "Mostra PDFDesk in «Apri con» per i file PDF"
LangString SEC_ASSOC ${LANG_ENGLISH} "Show PDFDesk in «Open with» for PDF files"
LangString SEC_CERT ${LANG_ITALIAN} "Certificato dell'editore (consigliato: Windows riconosce la firma di PDFDesk)"
LangString SEC_CERT ${LANG_ENGLISH} "Publisher certificate (recommended: Windows recognises PDFDesk's signature)"
LangString DESC_CERT ${LANG_ITALIAN} "Aggiunge il certificato di Guido Cauli alle autorità e agli editori attendibili di questo computer, così Windows non tratta PDFDesk come software di un editore sconosciuto. Fidati solo se hai scaricato questo programma da una fonte che ritieni sicura."
LangString DESC_CERT ${LANG_ENGLISH} "Adds Guido Cauli's certificate to this computer's trusted root authorities and trusted publishers, so Windows no longer treats PDFDesk as coming from an unknown publisher. Trust it only if you downloaded this program from a source you consider safe."
LangString SEC_OCR ${LANG_ITALIAN} "OCR: scarica Tesseract da internet (circa 50 MB, per rendere ricercabili le scansioni)"
LangString SEC_OCR ${LANG_ENGLISH} "OCR: download Tesseract from the internet (about 50 MB, makes scans searchable)"
LangString DESC_OCR ${LANG_ITALIAN} "Scarica Tesseract (motore OCR) dal sito dell'Università di Mannheim e lo installa nella cartella di PDFDesk, con la lingua italiana. Richiede internet; se il download non riesce, PDFDesk si installa lo stesso e l'OCR si può scaricare più tardi dalla finestra «Crea PDF da scansione»."
LangString DESC_OCR ${LANG_ENGLISH} "Downloads Tesseract (OCR engine) from the University of Mannheim and installs it in PDFDesk's folder, with Italian language data. Requires internet; if the download fails PDFDesk is still installed and OCR can be downloaded later from the «Create PDF from scan» window."
LangString MSG_OCR_FAIL ${LANG_ITALIAN} "Download dell'OCR non riuscito (nessuna connessione o file non valido). PDFDesk è stato installato: l'OCR si può scaricare più tardi dalla finestra «Crea PDF da scansione»."
LangString MSG_OCR_FAIL ${LANG_ENGLISH} "OCR download failed (no connection or invalid file). PDFDesk was installed: OCR can be downloaded later from the «Create PDF from scan» window."
LangString UNINST_KEEP ${LANG_ITALIAN} "PDFDesk è stato rimosso. Le impostazioni personali e le firme salvate sono state conservate."
LangString UNINST_KEEP ${LANG_ENGLISH} "PDFDesk has been removed. Your personal settings and saved signatures were kept."

Var PrevVersion
Var IsUpdate


Section "$(SEC_MAIN)" SecMain
  SectionIn RO
  SetRegView 64
  SetOutPath "$INSTDIR"
  ; il vecchio eseguibile non si può sovrascrivere se il programma è aperto
  retry:
  ClearErrors
  IfFileExists "$INSTDIR\pdfdesk.exe" 0 free
  Delete "$INSTDIR\pdfdesk.exe"
  IfFileExists "$INSTDIR\pdfdesk.exe" 0 free
    IfSilent abortrun
    MessageBox MB_RETRYCANCEL|MB_ICONEXCLAMATION "$(MSG_RUNNING)" IDRETRY retry
  abortrun:
    Abort
  free:
  File "/oname=pdfdesk.exe" "${EXE}"
  File "..\..\LICENSE"
  File "..\..\README.md"
  File "..\..\THIRD_PARTY.md"
  File "..\assets\pdfdesk.ico"
  File "pdfdesk-sign.cer"
  CreateShortcut "$SMPROGRAMS\${APP}.lnk" "$INSTDIR\pdfdesk.exe" "" "$INSTDIR\pdfdesk.ico" 0
  ; registrazione in «App e funzionalità»
  WriteRegStr HKLM "${APP_KEY}" "InstallDir" "$INSTDIR"
  WriteRegStr HKLM "${APP_KEY}" "Version" "${VERSION}"
  WriteUninstaller "$INSTDIR\uninstall.exe"
  WriteRegStr HKLM "${UNINST_KEY}" "DisplayName" "${APP}"
  WriteRegStr HKLM "${UNINST_KEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKLM "${UNINST_KEY}" "Publisher" "${PUBLISHER}"
  WriteRegStr HKLM "${UNINST_KEY}" "URLInfoAbout" "${URL}"
  WriteRegStr HKLM "${UNINST_KEY}" "URLUpdateInfo" "${URL}/releases"
  WriteRegStr HKLM "${UNINST_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKLM "${UNINST_KEY}" "DisplayIcon" "$INSTDIR\pdfdesk.ico"
  WriteRegStr HKLM "${UNINST_KEY}" "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegStr HKLM "${UNINST_KEY}" "QuietUninstallString" '"$INSTDIR\uninstall.exe" /S'
  WriteRegDWORD HKLM "${UNINST_KEY}" "NoModify" 1
  WriteRegDWORD HKLM "${UNINST_KEY}" "NoRepair" 1
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  IntFmt $0 "0x%08X" $0
  WriteRegDWORD HKLM "${UNINST_KEY}" "EstimatedSize" "$0"
SectionEnd

Section "$(SEC_DESK)" SecDesktop
  CreateShortcut "$DESKTOP\${APP}.lnk" "$INSTDIR\pdfdesk.exe" "" "$INSTDIR\pdfdesk.ico" 0
SectionEnd

Section "$(SEC_ASSOC)" SecAssoc
  SetRegView 64
  WriteRegStr HKLM "Software\Classes\PDFDesk.Document" "" "Documento PDF (PDFDesk)"
  WriteRegStr HKLM "Software\Classes\PDFDesk.Document\DefaultIcon" "" "$INSTDIR\pdfdesk.ico"
  WriteRegStr HKLM "Software\Classes\PDFDesk.Document\shell\open\command" "" '"$INSTDIR\pdfdesk.exe" "%1"'
  WriteRegStr HKLM "Software\Classes\.pdf\OpenWithProgids" "PDFDesk.Document" ""
  WriteRegStr HKLM "Software\Classes\Applications\pdfdesk.exe\shell\open\command" "" '"$INSTDIR\pdfdesk.exe" "%1"'
  WriteRegStr HKLM "Software\Classes\Applications\pdfdesk.exe" "FriendlyAppName" "${APP}"
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, p 0, p 0)'
SectionEnd

Section "$(SEC_CERT)" SecCert
  SetRegView 64
  nsExec::ExecToLog '"$SYSDIR\certutil.exe" -addstore -f Root "$INSTDIR\pdfdesk-sign.cer"'
  Pop $0
  nsExec::ExecToLog '"$SYSDIR\certutil.exe" -addstore -f TrustedPublisher "$INSTDIR\pdfdesk-sign.cer"'
  Pop $1
  ${If} $0 == 0
  ${AndIf} $1 == 0
    WriteRegDWORD HKLM "${APP_KEY}" "CertInstalled" 1
  ${EndIf}
SectionEnd

Section "$(SEC_OCR)" SecOcr
  SetRegView 64
  DetailPrint "Tesseract (OCR)…"
  ExecWait '"$INSTDIR\pdfdesk.exe" --install-ocr "$INSTDIR\tesseract"' $0
  ${If} $0 != 0
    IfSilent +2 0
      MessageBox MB_ICONEXCLAMATION|MB_OK "$(MSG_OCR_FAIL)"
  ${Else}
    WriteRegDWORD HKLM "${APP_KEY}" "OcrInstalled" 1
  ${EndIf}
SectionEnd

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecCert} "$(DESC_CERT)"
  !insertmacro MUI_DESCRIPTION_TEXT ${SecOcr} "$(DESC_OCR)"
!insertmacro MUI_FUNCTION_DESCRIPTION_END

Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP|MB_OK "$(MSG_64)"
    Abort
  ${EndIf}
  SetRegView 64
  ; in modalità silenziosa il certificato si installa solo se richiesto esplicitamente con /CERT
  IfSilent 0 certdone
    ${GetParameters} $R0
    ClearErrors
    ${GetOptions} $R0 "/CERT" $R1
    IfErrors 0 certdone
      SectionSetFlags ${SecCert} 0
  certdone:
  IfSilent 0 ocrdone                                          ; come il certificato: in silenzio l'OCR si scarica solo con /OCR
    ${GetParameters} $R0
    ClearErrors
    ${GetOptions} $R0 "/OCR" $R1
    IfErrors 0 ocrdone
      SectionSetFlags ${SecOcr} 0
  ocrdone:
  StrCpy $IsUpdate "0"
  ReadRegStr $PrevVersion HKLM "${APP_KEY}" "Version"
  ${If} $PrevVersion != ""
    StrCpy $IsUpdate "1"
    StrCpy $0 $PrevVersion
    ${VersionCompare} "$PrevVersion" "${VERSION}" $1       ; 0 uguali, 1 installata più recente, 2 installata più vecchia
    ${If} $1 == 2
      MessageBox MB_ICONQUESTION|MB_YESNO|MB_DEFBUTTON1 "$(MSG_UPDATE)" /SD IDYES IDYES go
      Abort
    ${ElseIf} $1 == 0
      MessageBox MB_ICONQUESTION|MB_YESNO|MB_DEFBUTTON1 "$(MSG_SAME)" /SD IDYES IDYES go
      Abort
    ${Else}
      MessageBox MB_ICONEXCLAMATION|MB_YESNO|MB_DEFBUTTON2 "$(MSG_OLDER)" /SD IDYES IDYES go
      Abort
    ${EndIf}
    go:
    ; aggiornamento: i collegamenti che l'utente non aveva non vengono ricreati
    IfFileExists "$DESKTOP\${APP}.lnk" +2 0
      SectionSetFlags ${SecDesktop} 0
    ReadRegDWORD $3 HKLM "${APP_KEY}" "CertInstalled"           ; aggiornamento: il certificato è preselezionato solo se c'era già
    ${If} $3 != 1
      SectionSetFlags ${SecCert} 0
    ${EndIf}
    ReadRegDWORD $3 HKLM "${APP_KEY}" "OcrInstalled"             ; aggiornamento: l'OCR si riscarica solo se era stato installato
    ${If} $3 != 1
      SectionSetFlags ${SecOcr} 0
    ${EndIf}
    ReadRegStr $2 HKLM "Software\Classes\PDFDesk.Document" ""
    ${If} $2 == ""
      SectionSetFlags ${SecAssoc} 0
    ${EndIf}
  ${EndIf}
FunctionEnd

Section "Uninstall"
  SetRegView 64
  Delete "$INSTDIR\pdfdesk.exe"
  Delete "$INSTDIR\LICENSE"
  Delete "$INSTDIR\README.md"
  Delete "$INSTDIR\THIRD_PARTY.md"
  Delete "$INSTDIR\pdfdesk.ico"
  ReadRegDWORD $0 HKLM "${APP_KEY}" "CertInstalled"
  ${If} $0 == 1
    nsExec::ExecToLog '"$SYSDIR\certutil.exe" -delstore Root "PDFDesk - Guido Cauli"'
    nsExec::ExecToLog '"$SYSDIR\certutil.exe" -delstore TrustedPublisher "PDFDesk - Guido Cauli"'
  ${EndIf}
  Delete "$INSTDIR\pdfdesk-sign.cer"
  IfFileExists "$INSTDIR\tesseract\*.*" 0 noocr                  ; OCR scaricato: usa il suo disinstallatore (toglie anche la voce in «App e funzionalità»)
    IfFileExists "$INSTDIR\tesseract\uninstall.exe" 0 +2
      ExecWait '"$INSTDIR\tesseract\uninstall.exe" /S _?=$INSTDIR\tesseract'
    RMDir /r "$INSTDIR\tesseract"
  noocr:
  Delete "$INSTDIR\uninstall.exe"
  RMDir "$INSTDIR"
  Delete "$SMPROGRAMS\${APP}.lnk"
  Delete "$DESKTOP\${APP}.lnk"
  DeleteRegKey HKLM "Software\Classes\PDFDesk.Document"
  DeleteRegValue HKLM "Software\Classes\.pdf\OpenWithProgids" "PDFDesk.Document"
  DeleteRegKey HKLM "Software\Classes\Applications\pdfdesk.exe"
  DeleteRegKey HKLM "${UNINST_KEY}"
  DeleteRegKey HKLM "${APP_KEY}"
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, p 0, p 0)'
  IfSilent +2 0
    MessageBox MB_ICONINFORMATION|MB_OK "$(UNINST_KEEP)"
SectionEnd
