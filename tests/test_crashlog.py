# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# Registro degli errori: eccezioni, crash nativi (in un processo separato), sessione non chiusa, avviso nell'interfaccia.
import os, subprocess, sys, tempfile, unittest
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def run_py(code, data):
    env = dict(os.environ, PDFDESK_DATA=data, QT_QPA_PLATFORM="offscreen", PYTHONPATH=ROOT)
    return subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=120)


class CrashLogTests(unittest.TestCase):
    def setUp(self):
        self.data = tempfile.mkdtemp(prefix="pdfdesk-log-")
        self.log = os.path.join(self.data, "pdfdesk-errori.log")

    def read(self):
        with open(self.log, encoding="utf-8") as f:
            return f.read()

    def test_unhandled_exception_logged(self):
        r = run_py("from pdfdesk import crashlog; crashlog.install()\nraise ValueError('prova di errore')", self.data)
        self.assertNotEqual(r.returncode, 0)
        t = self.read()
        self.assertIn("ValueError: prova di errore", t); self.assertIn("PDFDesk ", t); self.assertIn("Traceback", t)

    def test_native_crash_logged(self):
        r = run_py("from pdfdesk import crashlog; crashlog.install()\nimport ctypes; ctypes.string_at(0)", self.data)
        self.assertNotEqual(r.returncode, 0)
        t = self.read()
        self.assertIn("Fatal Python error", t); self.assertIn("string_at", t)    # dove si trovava il programma

    def test_thread_exception_logged(self):
        run_py("from pdfdesk import crashlog; crashlog.install()\nimport threading\n"
               "t = threading.Thread(target=lambda: 1/0, name='lavoro'); t.start(); t.join()", self.data)
        t = self.read()
        self.assertIn("thread lavoro", t); self.assertIn("ZeroDivisionError", t)

    def test_previous_session_detected(self):
        code = ("from pdfdesk import crashlog; crashlog.install(gui=True); print(crashlog.previous_crash())\n"
                "import sys\nif len(sys.argv) > 0 and {clean}: crashlog.clean_exit()")
        self.assertEqual(run_py(code.format(clean=False), self.data).stdout.strip(), "False")   # prima volta
        self.assertEqual(run_py(code.format(clean=True), self.data).stdout.strip(), "True")    # la precedente non si era chiusa
        self.assertEqual(run_py(code.format(clean=True), self.data).stdout.strip(), "False")   # chiusura normale
        self.assertIn("non si è chiusa normalmente", self.read())

    def test_log_rotation(self):
        with open(self.log, "w") as f:
            f.write("x" * 1_100_000)
        run_py("from pdfdesk import crashlog; crashlog.install(); crashlog.write('nuova voce')", self.data)
        self.assertTrue(os.path.exists(self.log + ".1")); self.assertLess(os.path.getsize(self.log), 10_000)

    def test_gui_error_in_slot_notified_and_logged(self):
        code = (
            "import sys, os\n"
            "from PySide6.QtCore import QSettings, QTimer\n"
            "from PySide6.QtWidgets import QApplication, QMessageBox\n"
            "QSettings.setDefaultFormat(QSettings.IniFormat); QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, os.environ['PDFDESK_DATA'])\n"
            "app = QApplication([])\n"
            "from pdfdesk import crashlog; crashlog.install(gui=True)\n"
            "from pdfdesk.mainwindow import MainWindow\n"
            "w = MainWindow(); crashlog.set_gui_notify(w.notify_error); w.show()\n"
            "def boom(): raise RuntimeError('errore in un pulsante')\n"
            "QTimer.singleShot(50, boom)\n"
            "def check():\n"
            "    boxes = [b for b in app.topLevelWidgets() if isinstance(b, QMessageBox) and b.isVisible()]\n"
            "    print('AVVISO', len(boxes), boxes[0].informativeText() if boxes else '')\n"
            "    for b in boxes: b.close()\n"
            "    w.close(); app.quit()\n"
            "QTimer.singleShot(600, check)\n"
            "app.exec(); crashlog.clean_exit()\n")
        r = run_py(code, self.data)
        self.assertIn("AVVISO 1 RuntimeError: errore in un pulsante", r.stdout, r.stdout + r.stderr[-800:])
        self.assertIn("RuntimeError: errore in un pulsante", self.read())
        self.assertFalse(os.path.exists(os.path.join(self.data, "session.lock")))


class CliMissingFileTests(unittest.TestCase):
    def test_missing_input_is_a_clear_error(self):
        import io, contextlib
        from pdfdesk import cli
        for args in (["--compress", "/non/esiste.pdf", "/tmp/x.pdf"], ["--check", "/non/esiste.pdf"],
                     ["--verify", "/non/esiste.pdf"], ["--translate", "/non/esiste.pdf", "--to", "en"]):
            err = io.StringIO()
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(args), 2, args)
            self.assertIn("file non trovato", err.getvalue())


if __name__ == "__main__":
    unittest.main()
