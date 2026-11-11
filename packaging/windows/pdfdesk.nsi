; PDFDesk — Guido Cauli <guido.cauli@gmail.com>
; Installer per Windows (NSIS). Installa, AGGIORNA una versione precedente (stessa cartella, stessi collegamenti) e si disinstalla.
; Compilazione: makensis -DVERSION=0.7.5 -DEXE=..\..\dist-wine\pdfdesk.exe -DOUTFILE=pdfdesk-0.7.5-windows-x86_64-setup.exe pdfdesk.nsi
; Opzioni da riga di comando:  /S (silenzioso)   /D=C:\percorso (cartella, ultimo parametro)

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

Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP|MB_OK "$(MSG_64)"
    Abort
  ${EndIf}
  SetRegView 64
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
