"""Connessioni HTTPS: archivio dei certificati del sistema, poi certifi; la verifica non si disattiva mai."""
import os
import ssl
import sys
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdfdesk import net  # noqa: E402


class NetTests(unittest.TestCase):
    def test_archivi(self):
        names = [n for n, _ in net.contexts()]
        self.assertEqual(names[:2], ["sistema", "certifi"])
        for _, c in net.contexts():
            self.assertEqual(c.verify_mode, ssl.CERT_REQUIRED)
            self.assertTrue(c.check_hostname)

    def test_ripiega_su_certifi(self):
        calls = []

        def fake(req, timeout, context):
            calls.append(context)
            if len(calls) == 1:
                raise urllib.error.URLError(ssl.SSLCertVerificationError(1, "CERTIFICATE_VERIFY_FAILED"))
            return "ok"
        with mock.patch("urllib.request.urlopen", fake):
            self.assertEqual(net.urlopen("https://example.org"), "ok")
        self.assertEqual(len(calls), 2)

    def test_errori_non_di_certificato_passano(self):
        def fake(req, timeout, context):
            raise urllib.error.URLError("rete irraggiungibile")
        with mock.patch("urllib.request.urlopen", fake):
            with self.assertRaises(urllib.error.URLError) as cm:
                net.urlopen("https://example.org")
        self.assertIn("irraggiungibile", str(cm.exception))

    def test_tutti_falliscono_messaggio_chiaro(self):
        def fake(req, timeout, context):
            raise urllib.error.URLError(ssl.SSLCertVerificationError(1, "CERTIFICATE_VERIFY_FAILED"))
        with mock.patch("urllib.request.urlopen", fake):
            with self.assertRaises(urllib.error.URLError) as cm:
                net.urlopen("https://example.org")
        self.assertIn("proxy", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
