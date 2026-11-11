@echo off
rem PDFDesk - Guido Cauli <guido.cauli@gmail.com>
rem Aggiunge il certificato di Guido Cauli (pdfdesk-sign.cer) alle autorita' e agli editori attendibili di questo computer,
rem cosi' Windows riconosce la firma di pdfdesk.exe. Richiede i diritti di amministratore (tasto destro - Esegui come amministratore).
rem Per annullare: certutil -delstore Root "PDFDesk - Guido Cauli"  e  certutil -delstore TrustedPublisher "PDFDesk - Guido Cauli"
net session >nul 2>&1
if errorlevel 1 (
  echo Serve un prompt da amministratore: clic destro su questo file - Esegui come amministratore.
  pause
  exit /b 1
)
certutil -addstore -f Root "%~dp0pdfdesk-sign.cer" || goto :err
certutil -addstore -f TrustedPublisher "%~dp0pdfdesk-sign.cer" || goto :err
echo.
echo Certificato installato. Ora Windows riconosce l'editore "PDFDesk - Guido Cauli".
pause
exit /b 0
:err
echo Installazione del certificato non riuscita.
pause
exit /b 1
