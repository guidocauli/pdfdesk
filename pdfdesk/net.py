# PDFDesk — Guido Cauli
# net.py: connessioni HTTPS verificate con i certificati del sistema operativo.
#
# Il Python incluso nei pacchetti non vede sempre i certificati del sistema:
#   - Windows aggiunge le autorità radice al proprio archivio solo quando servono la prima volta, quindi Python
#     (che legge l'archivio senza chiedere a Windows di completarlo) può non trovarle;
#   - nei pacchetti per macOS e Linux l'OpenSSL incluso cerca i certificati in percorsi che sul computer non esistono;
#   - nelle reti con ispezione del traffico (proxy aziendali o di ente) l'autorità del proxy è solo nell'archivio
#     del sistema.
# Per questo la verifica passa per primo da truststore (usa l'archivio e la verifica del sistema operativo); se non
# basta si riprova con le autorità di certifi. La verifica non viene mai disattivata.
from __future__ import annotations

import ssl
import urllib.error
import urllib.request
from typing import Optional

_contexts: Optional[list] = None


def _build_contexts() -> list:
    ctxs = []
    try:
        import truststore
        ctxs.append(("sistema", truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)))
    except Exception:
        pass
    try:
        import certifi
        ctxs.append(("certifi", ssl.create_default_context(cafile=certifi.where())))
    except Exception:
        pass
    ctxs.append(("python", ssl.create_default_context()))
    return ctxs


def contexts() -> list:
    global _contexts
    if _contexts is None:
        _contexts = _build_contexts()
    return _contexts


def _cert_error(e: BaseException) -> bool:
    r = getattr(e, "reason", e)
    return isinstance(r, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in str(e)


def urlopen(req, timeout: float = 60):
    """Come urllib.request.urlopen, con la verifica dei certificati descritta sopra. Gli errori HTTP (404, 403…)
    passano subito al chiamante; solo un certificato non riconosciuto fa provare l'archivio successivo."""
    if isinstance(req, str):
        req = urllib.request.Request(req, headers={"User-Agent": "PDFDesk"})
    last: Optional[BaseException] = None
    for _name, ctx in contexts():
        try:
            return urllib.request.urlopen(req, timeout=timeout, context=ctx)  # noqa: S310 (solo https verificato)
        except urllib.error.HTTPError:
            raise
        except Exception as e:  # noqa: BLE001
            if not _cert_error(e):
                raise
            last = e
    raise urllib.error.URLError(
        "il certificato del server non è riconosciuto né dal sistema né dall'elenco incluso nel programma. "
        "Se la rete usa un proxy con ispezione del traffico, la sua autorità di certificazione va installata nel "
        f"sistema. Dettagli: {getattr(last, 'reason', last)}")


def describe() -> str:
    """Archivi di certificati disponibili (per l'autodiagnosi)."""
    return ", ".join(n for n, _ in contexts())
