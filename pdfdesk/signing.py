# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# signing.py: firma digitale PAdES (pyHanko), verifica firme, creazione certificati autofirmati.
from __future__ import annotations

import datetime
import io
import contextlib
import glob
import logging
import os
import sys
from dataclasses import dataclass, field as dc_field
from typing import Optional

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from pyhanko.pdf_utils import images
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign import fields, signers, timestamps
from pyhanko.sign.validation import validate_pdf_signature
from pyhanko.stamp import TextStampStyle
from pyhanko_certvalidator import ValidationContext


for _n in ("pyhanko", "pyhanko_certvalidator"):
    logging.getLogger(_n).setLevel(logging.CRITICAL)   # i certificati autofirmati non sono un errore da stampare


class SigningError(Exception):
    pass


@dataclass
class SignParams:
    p12_path: str
    p12_password: str = ""
    reason: str = ""
    location: str = ""
    field_name: str = "Firma1"
    # firma visibile: pagina (0-based) e riquadro in coordinate PDF (x0, y0, x1, y1), origine in basso a sinistra
    page: Optional[int] = None
    box: Optional[tuple[float, float, float, float]] = None
    image_path: Optional[str] = None       # immagine (firma olografica) come sfondo del riquadro
    show_text: bool = True
    timestamp_url: Optional[str] = None    # server TSA RFC 3161 (richiede rete)
    existing_field: bool = False           # firma in un campo firma già presente nel modulo
    # smart card / token: modulo PKCS#11 (se impostato sostituisce il file .p12)
    pkcs11_lib: Optional[str] = None
    pkcs11_token_label: Optional[str] = None   # etichetta della scheda (da list_tokens)
    pkcs11_token_serial: Optional[str] = None
    pkcs11_pin: Optional[str] = None       # None/"" con pkcs11_pinpad=True: il PIN si digita sul lettore
    pkcs11_pinpad: bool = False
    pkcs11_cert_id: Optional[str] = None   # CKA_ID del certificato in esadecimale
    pkcs11_cert_label: Optional[str] = None


def create_self_signed_p12(path: str, password: str, common_name: str, organization: str = "",
                           email: str = "", days: int = 1825) -> None:
    """Crea un certificato autofirmato (RSA 3072) in un file PKCS#12. Utile per test e uso interno."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    attrs = [x509.NameAttribute(NameOID.COMMON_NAME, common_name)]
    if organization:
        attrs.append(x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization))
    if email:
        attrs.append(x509.NameAttribute(NameOID.EMAIL_ADDRESS, email))
    name = x509.Name(attrs)
    now = datetime.datetime.now(datetime.timezone.utc)
    builder = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
               .public_key(key.public_key()).serial_number(x509.random_serial_number())
               .not_valid_before(now - datetime.timedelta(minutes=5))
               .not_valid_after(now + datetime.timedelta(days=days))
               .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
               .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=True, key_encipherment=False,
                                            data_encipherment=False, key_agreement=False, key_cert_sign=False,
                                            crl_sign=False, encipher_only=False, decipher_only=False), critical=True))
    cert = builder.sign(key, hashes.SHA256())
    enc = (serialization.BestAvailableEncryption(password.encode()) if password
           else serialization.NoEncryption())
    data = pkcs12.serialize_key_and_certificates(common_name.encode(), key, cert, None, enc)
    with open(path, "wb") as f:
        f.write(data)


def load_signer(p12_path: str, password: str = "") -> signers.SimpleSigner:
    try:
        s = signers.SimpleSigner.load_pkcs12(p12_path, passphrase=password.encode() if password else None)
    except Exception as e:
        raise SigningError(f"impossibile aprire il certificato (password errata o file non valido): {e}") from e
    if s is None:
        raise SigningError("il file non contiene chiave privata e certificato")
    return s


# ---------------------------------------------------------------------- smart card / token (PKCS#11)
_LIB_CANDIDATES = {
    "win32": [r"C:\Windows\System32\opensc-pkcs11.dll", r"C:\Program Files\OpenSC Project\OpenSC\pkcs11\opensc-pkcs11.dll",
              r"C:\Windows\System32\bit4ipki.dll", r"C:\Windows\System32\bit4xpki.dll", r"C:\Windows\System32\incryptoki2.dll",
              r"C:\Windows\System32\cmP11.dll", r"C:\Windows\System32\eTPKCS11.dll", r"C:\Windows\System32\aetpkss1.dll",
              r"C:\Windows\System32\CNS_PKCS11.dll", r"C:\Windows\System32\SSC_PKCS11.dll", r"C:\Windows\System32\IPM_PKCS11.dll"],
    "darwin": ["/Library/OpenSC/lib/opensc-pkcs11.so", "/usr/local/lib/opensc-pkcs11.so", "/opt/homebrew/lib/pkcs11/opensc-pkcs11.so",
               "/Library/bit4id/pkcs11/libbit4ipki.dylib", "/usr/local/lib/libbit4xpki.dylib", "/Library/Frameworks/eToken.framework/Versions/Current/libeTPkcs11.dylib",
               "/usr/local/lib/libcmP11.dylib", "/Library/Application Support/Aruba Key/lib/libcmP11.dylib"],
    "linux": ["/usr/lib/x86_64-linux-gnu/opensc-pkcs11.so", "/usr/lib/opensc-pkcs11.so", "/usr/lib64/opensc-pkcs11.so",
              "/usr/lib/aarch64-linux-gnu/opensc-pkcs11.so", "/usr/lib/x86_64-linux-gnu/pkcs11/opensc-pkcs11.so",
              "/usr/lib/libbit4ipki.so", "/usr/lib/libbit4xpki.so", "/usr/lib/libcmP11.so", "/usr/lib/libeTPkcs11.so",
              "/usr/lib/x86_64-linux-gnu/libbit4ipki.so", "/usr/lib/softhsm/libsofthsm2.so", "/usr/lib/x86_64-linux-gnu/softhsm/libsofthsm2.so"],
}


def pkcs11_candidates() -> list[str]:
    """Moduli PKCS#11 comuni effettivamente presenti sul computer (OpenSC e driver dei produttori)."""
    key = "win32" if sys.platform.startswith("win") else ("darwin" if sys.platform == "darwin" else "linux")
    found = [p for p in _LIB_CANDIDATES[key] if os.path.isfile(p)]
    env = os.environ.get("PDFDESK_PKCS11")
    if env and os.path.isfile(env):
        found.insert(0, env)
    return list(dict.fromkeys(found))


@dataclass
class CardCert:
    label: str
    cert_id: str          # esadecimale
    subject: str
    can_sign: bool = True


@dataclass
class TokenInfo:
    slot: int
    label: str
    serial: str
    certs: list = dc_field(default_factory=list)


def _pkcs11():
    try:
        import pkcs11
        from pkcs11 import Attribute, ObjectClass
    except Exception as e:  # pragma: no cover
        raise SigningError(f"supporto smart card non disponibile in questa installazione: {e}") from e
    return pkcs11, Attribute, ObjectClass


def _txt(v) -> str:
    return (v.decode("utf-8", "replace") if isinstance(v, (bytes, bytearray)) else (v or "")).strip()


def list_tokens(lib_path: str) -> list[TokenInfo]:
    """Elenca schede/token inseriti con i relativi certificati (la lettura dei certificati non richiede il PIN)."""
    if not lib_path or not os.path.isfile(lib_path):
        raise SigningError("modulo PKCS#11 non trovato")
    pkcs11, Attribute, ObjectClass = _pkcs11()
    from asn1crypto import x509 as ax509
    try:
        lib = pkcs11.lib(lib_path)
        slots = lib.get_slots(token_present=True)
    except Exception as e:
        raise SigningError(f"impossibile caricare il modulo PKCS#11: {e}") from e
    out: list[TokenInfo] = []
    for sl in slots:
        tok = sl.get_token()
        info = TokenInfo(sl.slot_id, _txt(tok.label), _txt(tok.serial))
        try:
            with tok.open() as sess:
                for obj in sess.get_objects({Attribute.CLASS: ObjectClass.CERTIFICATE}):
                    try:
                        der = obj[Attribute.VALUE]
                        subj = ax509.Certificate.load(der).subject.human_friendly
                        cid = obj[Attribute.ID] or b""
                        label = obj[Attribute.LABEL] or ""
                        info.certs.append(CardCert(label, cid.hex(), subj))
                    except Exception:
                        continue
        except Exception:
            pass
        out.append(info)
    return out


@contextlib.contextmanager
def _signer_for(params: "SignParams"):
    """Fornisce il firmatario (da .p12 oppure da smart card) e chiude la sessione al termine."""
    if params.pkcs11_lib:
        from pyhanko.sign import pkcs11 as hp11
        pkcs11, _, _ = _pkcs11()
        if not os.path.isfile(params.pkcs11_lib):
            raise SigningError("modulo PKCS#11 non trovato")
        if not params.pkcs11_pinpad and not params.pkcs11_pin:
            raise SigningError("PIN della smart card mancante")
        pin = hp11.PROTECTED_AUTH if params.pkcs11_pinpad else params.pkcs11_pin
        try:
            crit = None
            if params.pkcs11_token_label or params.pkcs11_token_serial:
                from pyhanko.config.pkcs11 import TokenCriteria
                crit = TokenCriteria(label=params.pkcs11_token_label or None,
                                     serial=params.pkcs11_token_serial.encode() if params.pkcs11_token_serial else None)
            sess = hp11.open_pkcs11_session(params.pkcs11_lib, token_criteria=crit, user_pin=pin)
        except Exception as e:
            name = type(e).__name__
            if name == "PinIncorrect":
                msg = "PIN errato (attenzione: troppi tentativi bloccano la scheda)"
            elif name in ("PinLocked", "PinExpired"):
                msg = "PIN bloccato o scaduto: sbloccalo con il PUK"
            elif name == "TokenNotPresent":
                msg = "scheda non inserita"
            elif "more than 1 slot" in str(e):
                msg = "più schede/lettori presenti: selezionane una con «Rileva»"
            elif "No token matching" in str(e):
                msg = "scheda non trovata: inseriscila e premi «Rileva»"
            else:
                msg = str(e) or name
            raise SigningError(f"accesso alla smart card non riuscito: {msg}") from e
        try:
            kw = {}
            if params.pkcs11_cert_id:
                kw["cert_id"] = bytes.fromhex(params.pkcs11_cert_id)
                kw["key_id"] = bytes.fromhex(params.pkcs11_cert_id)
            elif params.pkcs11_cert_label:
                kw["cert_label"] = params.pkcs11_cert_label
                kw["key_label"] = params.pkcs11_cert_label
            signer = hp11.PKCS11Signer(sess, **kw)
            yield signer
        finally:
            try:
                sess.close()
            except Exception:
                pass
    else:
        yield load_signer(params.p12_path, params.p12_password)


def sign_pdf_bytes(data: bytes, params: SignParams) -> bytes:
    """Aggiunge una firma digitale PAdES come aggiornamento incrementale (il contenuto resta invariato)."""
    meta = signers.PdfSignatureMetadata(field_name=params.field_name, reason=params.reason or None,
                                        location=params.location or None, md_algorithm="sha256",
                                        subfilter=fields.SigSeedSubFilter.PADES)
    new_field = None
    stamp = None
    if params.existing_field or (params.page is not None and params.box is not None):
        if not params.existing_field:
            new_field = fields.SigFieldSpec(params.field_name, on_page=params.page, box=tuple(params.box))
        text = ("Firmato digitalmente da:\n%(signer)s\nData: %(ts)s" if params.show_text else "")
        bg = images.PdfImage(params.image_path) if params.image_path else None
        stamp = TextStampStyle(stamp_text=text, background=bg,
                               background_opacity=1.0, border_width=1 if params.show_text else 0)
    timestamper = timestamps.HTTPTimeStamper(params.timestamp_url) if params.timestamp_url else None
    try:
        with _signer_for(params) as signer:
            pdf_signer = signers.PdfSigner(meta, signer=signer, stamp_style=stamp, new_field_spec=new_field,
                                           timestamper=timestamper)
            writer = IncrementalPdfFileWriter(io.BytesIO(data), strict=False)
            out = io.BytesIO()
            pdf_signer.sign_pdf(writer, output=out)
    except SigningError:
        raise
    except Exception as e:
        raise SigningError(f"firma non riuscita: {e}") from e
    return out.getvalue()


@dataclass
class CertInfo:
    subject: list = dc_field(default_factory=list)   # [(etichetta, valore)]
    issuer: list = dc_field(default_factory=list)
    serial: str = ""
    not_before: str = ""
    not_after: str = ""
    key_algo: str = ""
    sig_algo: str = ""
    key_usage: str = ""
    ext_key_usage: str = ""
    sha1: str = ""
    sha256: str = ""
    self_signed: bool = False
    is_ca: bool = False


@dataclass
class SigStatus:
    field: str
    signer: str
    intact: bool
    valid: bool
    trusted: bool
    coverage: str
    modified_after: bool
    signed_at: str
    summary: str
    cert: Optional[CertInfo] = None
    chain: list = dc_field(default_factory=list)      # [CertInfo] certificati incorporati / percorso
    digest_algo: str = ""
    sig_mechanism: str = ""
    reason: str = ""
    location: str = ""
    contact: str = ""
    name: str = ""
    sign_time_dict: str = ""        # /M dichiarato nel dizionario di firma
    timestamp: str = ""             # marca temporale (se presente)
    timestamp_valid: Optional[bool] = None
    byte_range: list = dc_field(default_factory=list)
    revision: int = 0
    total_revisions: int = 0
    docmdp: str = ""
    modification_level: str = ""
    subfilter: str = ""
    filter: str = ""
    problems: list = dc_field(default_factory=list)


_DN_LABELS = {
    "common_name": "Nome comune (CN)", "organization_name": "Organizzazione (O)",
    "organizational_unit_name": "Unità organizzativa (OU)", "country_name": "Paese (C)",
    "state_or_province_name": "Provincia/Stato (ST)", "locality_name": "Località (L)",
    "email_address": "Email", "serial_number": "Numero di serie", "surname": "Cognome",
    "given_name": "Nome", "title": "Titolo", "organization_identifier": "Identificativo organizzazione",
    "domain_component": "Componente di dominio (DC)", "user_id": "UID",
}


def _fmt_dt(d) -> str:
    try:
        return d.strftime("%Y-%m-%d %H:%M:%S %z").strip()
    except Exception:
        return str(d or "")


def _dn_rows(name) -> list:
    rows = []
    try:
        for rdn in name.chosen:
            for atv in rdn:
                key = atv["type"].native
                try:
                    val = atv["value"].native
                except Exception:
                    val = str(atv["value"])
                rows.append((_DN_LABELS.get(key, str(key)), str(val)))
    except Exception:
        rows = [("", name.human_friendly)]
    return rows


def _flags(v) -> str:
    try:
        if v is None:
            return ""
        return ", ".join(sorted(str(x) for x in v.native)) if hasattr(v, "native") and v.native is not None else ""
    except Exception:
        return ""


def _hexfp(b: bytes) -> str:
    h = b.hex().upper()
    return ":".join(h[i:i + 2] for i in range(0, len(h), 2))


def cert_info(c) -> CertInfo:
    ci = CertInfo()
    try:
        ci.subject = _dn_rows(c.subject)
        ci.issuer = _dn_rows(c.issuer)
        ci.serial = f"{c.serial_number:X}"
        ci.not_before = _fmt_dt(c.not_valid_before)
        ci.not_after = _fmt_dt(c.not_valid_after)
        pk = c.public_key
        ci.key_algo = f"{pk.algorithm.upper()} {pk.bit_size} bit"
        ci.sig_algo = f"{c.hash_algo}/{c.signature_algo}"
        ci.key_usage = _flags(c.key_usage_value)
        ci.ext_key_usage = _flags(c.extended_key_usage_value)
        ci.sha1 = _hexfp(c.sha1)
        ci.sha256 = _hexfp(c.sha256)
        ci.self_signed = bool(c.self_signed) if isinstance(c.self_signed, bool) else c.self_signed != "no"
        ci.is_ca = bool(c.ca)
    except Exception:
        pass
    return ci


def _dn_short(ci: CertInfo) -> str:
    return ", ".join(f"{k.split(' (')[0]}: {v}" for k, v in ci.subject) or "?"


def verify_pdf_bytes(data: bytes) -> list[SigStatus]:
    reader = PdfFileReader(io.BytesIO(data), strict=False)
    out: list[SigStatus] = []
    vc = ValidationContext(allow_fetching=False)
    sigs = list(reader.embedded_regular_signatures)
    try:
        total = reader.xrefs.total_revisions
    except Exception:
        total = 0
    for emb in sigs:
        try:
            st = validate_pdf_signature(emb, signer_validation_context=vc)
            cov = st.coverage.name if st.coverage else "?"
            modified = cov != "ENTIRE_FILE"
            cert = cert_info(st.signing_cert) if st.signing_cert else None
            who = st.signing_cert.subject.human_friendly if st.signing_cert else "?"
            when = _fmt_dt(st.signer_reported_dt) if st.signer_reported_dt else ""
            s = SigStatus(emb.field_name, who, bool(st.intact), bool(st.valid), bool(st.trusted),
                          cov, modified, when, st.summary(), cert=cert)
            s.digest_algo = str(st.md_algorithm or "")
            s.sig_mechanism = str(getattr(st.pkcs7_signature_mechanism, "signature_algo", st.pkcs7_signature_mechanism) or "")
            so = emb.sig_object
            def g(k):
                try:
                    v = so.get(k)
                    return str(v) if v is not None else ""
                except Exception:
                    return ""
            s.reason, s.location, s.contact, s.name = g("/Reason"), g("/Location"), g("/ContactInfo"), g("/Name")
            s.sign_time_dict = g("/M")
            s.subfilter, s.filter = g("/SubFilter"), g("/Filter")
            s.byte_range = list(emb.byte_range or [])
            s.revision = int(emb.signed_revision or 0)
            s.total_revisions = int(total)
            s.modification_level = str(getattr(st.modification_level, "name", st.modification_level) or "")
            s.docmdp = ("sì (certificazione): " + str(emb.docmdp_level)) if emb.docmdp_level is not None else "no (firma di approvazione)"
            ts = getattr(st, "timestamp_validity", None)
            if ts is not None:
                s.timestamp = _fmt_dt(getattr(ts, "timestamp", None))
                s.timestamp_valid = bool(getattr(ts, "valid", False) and getattr(ts, "intact", False))
            chain = []
            try:
                for c in [st.signing_cert] + list(emb.other_embedded_certs or []):
                    if c is not None:
                        chain.append(cert_info(c))
            except Exception:
                pass
            s.chain = chain
            try:
                s.problems = [str(x) for x in (st.trust_problem_indic or [])] if st.trust_problem_indic else []
                if not st.trusted and getattr(st, "bottom_line", True) is False:
                    pass
            except Exception:
                pass
            out.append(s)
        except Exception as e:
            out.append(SigStatus(emb.field_name, "?", False, False, False, "?", False, "", f"errore: {e}"))
    return out


def describe_status(s: SigStatus) -> str:
    """Testo completo e copiabile con tutti i dati di una firma."""
    L = []
    def row(k, v):
        if v not in ("", None, []):
            L.append(f"{k}: {v}")
    L.append(f"=== Firma «{s.field}» ===")
    row("Esito", s.summary)
    row("Contenuto integro", "sì" if s.intact else "NO")
    row("Firma crittograficamente valida", "sì" if s.valid else "NO")
    row("Certificato attendibile", "sì" if s.trusted else "no (non verificabile in un archivio fiduciario)")
    row("Copertura", "tutto il file" if s.coverage == "ENTIRE_FILE" else s.coverage)
    row("Modificato dopo la firma", "SÌ" if s.modified_after else "no")
    row("Livello di modifica", s.modification_level)
    row("Certificazione (DocMDP)", s.docmdp)
    L.append("")
    L.append("-- Firma --")
    row("Data/ora dichiarata dal firmatario", s.signed_at)
    row("Data/ora nel dizionario (/M)", s.sign_time_dict)
    row("Marca temporale", (s.timestamp + (" (valida)" if s.timestamp_valid else " (NON valida)")) if s.timestamp else "")
    row("Motivo", s.reason); row("Luogo", s.location); row("Contatto", s.contact); row("Nome nel dizionario", s.name)
    row("Algoritmo di digest", s.digest_algo); row("Meccanismo di firma", s.sig_mechanism)
    row("Filtro", s.filter); row("SubFilter", s.subfilter)
    row("Byte range", s.byte_range)
    if s.total_revisions:
        row("Revisione firmata", f"{s.revision + 1} di {s.total_revisions}")
    if s.problems:
        row("Problemi di fiducia", "; ".join(s.problems))
    for i, c in enumerate(s.chain):
        L.append("")
        L.append("-- Certificato del firmatario --" if i == 0 else f"-- Certificato incorporato #{i} --")
        L.append("Soggetto:")
        for k, v in c.subject:
            L.append(f"    {k}: {v}")
        L.append("Emittente:")
        for k, v in c.issuer:
            L.append(f"    {k}: {v}")
        row("Numero di serie (hex)", c.serial)
        row("Valido dal", c.not_before); row("Valido fino al", c.not_after)
        row("Chiave pubblica", c.key_algo); row("Algoritmo di firma", c.sig_algo)
        row("Uso della chiave", c.key_usage); row("Uso esteso", c.ext_key_usage)
        row("Autofirmato", "sì" if c.self_signed else "no"); row("CA", "sì" if c.is_ca else "no")
        row("Impronta SHA-1", c.sha1); row("Impronta SHA-256", c.sha256)
    return "\n".join(L)
