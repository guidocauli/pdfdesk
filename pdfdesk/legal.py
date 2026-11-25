# PDFDesk — Guido Cauli
# legal.py: esclusione di responsabilità mostrata nel programma (Informazioni, --version).
#


DISCLAIMER_SHORT = "Questo programma è fornito «così com'è», SENZA ALCUNA GARANZIA, nei limiti consentiti dalla legge (licenza AGPL-3.0-or-later, sezioni 15 e 16)."

DISCLAIMER_TEXT = (
    "PDFDesk è software libero distribuito «così com'è» (AS IS), SENZA GARANZIE DI ALCUN TIPO, esplicite o implicite, "
    "comprese le garanzie di commerciabilità e di idoneità a uno scopo particolare, nei limiti consentiti dalla legge applicabile.",
    "In nessun caso l'autore o chi distribuisce il programma risponde di danni diretti, indiretti, incidentali o consequenziali "
    "derivanti dall'uso o dall'impossibilità di usare il programma, compresi la perdita o l'alterazione di dati e documenti.",
    "Spetta all'utente verificare i risultati prima di farvi affidamento, in particolare: che le redazioni abbiano rimosso davvero "
    "le informazioni; la validità legale delle firme digitali; la conformità effettiva dei file PDF/A e PDF/X; l'accuratezza del testo "
    "prodotto da OCR e traduzione automatica. Conservare sempre una copia dei documenti originali.",
    "Il testo vincolante è quello delle sezioni 15 e 16 della licenza GNU AGPL versione 3.",
)


def disclaimer_html() -> str:
    from .i18n import tr
    return "".join(f"<p>{tr(p)}</p>" for p in DISCLAIMER_TEXT)


def disclaimer_short() -> str:
    from .i18n import tr
    return tr(DISCLAIMER_SHORT)
