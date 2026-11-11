@echo off
rem PDFDesk — Guido Cauli <guido.cauli@gmail.com>
rem Compila l'eseguibile per Windows, lo collauda e lo impacchetta in dist\
echo PDFDesk — Guido Cauli ^<guido.cauli@gmail.com^> — build
for /f %%v in ('python -c "import sys;sys.path.insert(0,'.');import pdfdesk;print(pdfdesk.__version__)"') do set VER=%%v
python -m pip install -r requirements.txt || exit /b 1
set QT_QPA_PLATFORM=offscreen
python -I -W ignore tests\test_core.py || exit /b 1
python -I -W ignore tests\test_gui.py || exit /b 1
python -I -W ignore tests\test_features.py || exit /b 1
python -I -W ignore tests\test_standards.py || exit /b 1
set QT_QPA_PLATFORM=
pushd packaging
python -m PyInstaller --noconfirm --clean --distpath ..\dist --workpath ..\build pdfdesk.spec || exit /b 1
popd
dist\pdfdesk.exe --selftest
type "%TEMP%\pdfdesk-selftest.log"
powershell -Command "Compress-Archive -Force -Path dist\pdfdesk.exe,LICENSE,README.md,THIRD_PARTY.md -DestinationPath dist\pdfdesk-%VER%-windows-x86_64.zip"
echo Pacchetto creato in dist\
