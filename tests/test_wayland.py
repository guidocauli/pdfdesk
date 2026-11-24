"""Wayland nativo, compositor a tasselli (niri, Hyprland, sway…) e dimensioni delle finestre."""
import os
import sys
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
TMP = tempfile.mkdtemp(prefix="pdfdesk-wl-")
os.environ["PDFDESK_DATA"] = os.path.join(TMP, "data")

from PySide6.QtCore import QSettings, QSize  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from pdfdesk import wayland  # noqa: E402

QSettings.setDefaultFormat(QSettings.IniFormat); QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, TMP)
app = QApplication.instance() or QApplication([])

CLEAN = {k: "" for k in ("NIRI_SOCKET", "HYPRLAND_INSTANCE_SIGNATURE", "SWAYSOCK", "I3SOCK", "XDG_CURRENT_DESKTOP",
                         "XDG_SESSION_DESKTOP", "XDG_SESSION_TYPE", "WAYLAND_DISPLAY")}


def env(**kw):
    e = dict(CLEAN); e.update(kw)
    return mock.patch.dict(os.environ, e)


@unittest.skipUnless(sys.platform.startswith("linux"), "solo Linux")
class DetectTests(unittest.TestCase):
    def test_compositor(self):
        with env():
            self.assertEqual(wayland.tiling_compositor(), "")
        with env(NIRI_SOCKET="/run/user/1000/niri.sock"):
            self.assertEqual(wayland.tiling_compositor(), "niri")
        with env(HYPRLAND_INSTANCE_SIGNATURE="abc"):
            self.assertEqual(wayland.tiling_compositor(), "Hyprland")
        with env(SWAYSOCK="/run/sway.sock"):
            self.assertEqual(wayland.tiling_compositor(), "sway")
        with env(XDG_CURRENT_DESKTOP="niri"):
            self.assertEqual(wayland.tiling_compositor(), "niri")
        with env(XDG_CURRENT_DESKTOP="GNOME"):
            self.assertEqual(wayland.tiling_compositor(), "")
        with env(XDG_CURRENT_DESKTOP="KDE"):
            self.assertEqual(wayland.tiling_compositor(), "")

    def test_piattaforma(self):
        saved = os.environ.pop("QT_QPA_PLATFORM", None)
        try:
            with env(XDG_SESSION_TYPE="wayland", WAYLAND_DISPLAY="wayland-1"), \
                    mock.patch.object(wayland, "platform_pref", return_value="auto"):
                self.assertEqual(wayland.configure_platform(), "wayland;xcb")      # nativo, con ripiego su X11
                os.environ.pop("QT_QPA_PLATFORM")
            with env(XDG_SESSION_TYPE="wayland", WAYLAND_DISPLAY="wayland-1", DISPLAY=":0"), \
                    mock.patch.object(wayland, "platform_pref", return_value="x11"):
                self.assertEqual(wayland.configure_platform(), "xcb")
                os.environ.pop("QT_QPA_PLATFORM")
            with env(DISPLAY=":0"), mock.patch.object(wayland, "platform_pref", return_value="auto"):
                self.assertEqual(wayland.configure_platform(), "")                # sessione X11: invariato
            with env(XDG_SESSION_TYPE="wayland", QT_QPA_PLATFORM="xcb"):
                self.assertEqual(wayland.configure_platform(), "")                # scelta dell'utente: vince
        finally:
            if saved is not None:
                os.environ["QT_QPA_PLATFORM"] = saved


class SizeTests(unittest.TestCase):
    def test_fit(self):
        self.assertEqual(wayland.fit_size(QSize(3000, 2000), QSize(1366, 768), 0.9), QSize(1229, 691))
        self.assertEqual(wayland.fit_size(QSize(800, 600), QSize(1920, 1080)), QSize(800, 600))

    def test_dialogo_entro_lo_schermo(self):
        f = wayland.DialogFitter(app)
        app.installEventFilter(f)
        try:
            d = QDialog(); d.setMinimumSize(5000, 4000); d.resize(6000, 5000)
            d.show(); app.processEvents()
            avail = wayland.available_size(d)
            self.assertLessEqual(d.width(), avail.width()); self.assertLessEqual(d.height(), avail.height())
            self.assertLessEqual(d.minimumWidth(), avail.width())
            d.close()
        finally:
            app.removeEventFilter(f)

    def test_finestra_principale(self):
        from make_samples import block_modal_dialogs; block_modal_dialogs()
        from pdfdesk.mainwindow import MainWindow
        w = MainWindow(); w.show(); app.processEvents()
        # stretta: deve stare in una colonna di un compositor a tasselli (un terzo di 1366 px = 455)
        self.assertLessEqual(w.minimumSizeHint().width(), 450)
        avail = wayland.available_size(w)
        self.assertLessEqual(w.width(), avail.width()); self.assertLessEqual(w.height(), avail.height())
        # a tasselli la geometria salvata non si impone
        w.resize(500, 400)
        with mock.patch.object(wayland, "tiling_compositor", return_value="niri"):
            wayland.restore_main_geometry(w, b"\x01\xd9\xd0\xcb\x00\x03\x00\x00")
        self.assertEqual(w.size(), QSize(500, 400))
        # proprietà nella barra: gruppi separati, abilitati insieme al pannello
        self.assertGreaterEqual(len(w.props.groups), 5)
        w.props.setEnabled(False)
        self.assertTrue(all(not g.isEnabled() for g in w.props.groups))
        w.props.setEnabled(True)
        w.close(); w.deleteLater(); app.processEvents()


if __name__ == "__main__":
    unittest.main()
