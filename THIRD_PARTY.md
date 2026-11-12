# PDFDesk — Guido Cauli <guido.cauli@gmail.com>

# Componenti di terze parti inclusi negli eseguibili

| Componente | Licenza | Uso |
|---|---|---|
| Qt / PySide6 | LGPL-3.0 | interfaccia grafica |
| PyMuPDF / MuPDF | AGPL-3.0 | lettura, rendering, annotazioni |
| pyHanko | MIT | firme digitali PAdES |
| python-pkcs11 | MIT | smart card (PKCS#11) |
| pikepdf / QPDF | MPL-2.0 / Apache-2.0 | metadati e correzioni PDF/A e PDF/X |
| **Ghostscript** | **AGPL-3.0** | conversione a PDF/A e PDF/X (https://ghostscript.com) |
| Font URW++ base 35 | AGPL-3.0 con eccezione per i font | sostituti metricamente compatibili dei font base-14, incorporati nei file PDF/A e PDF/X |
| fontTools, Pillow, cryptography | MIT-like | font, immagini, certificati |
| CTranslate2 | MIT | traduzione locale (motore dei modelli) |
| SentencePiece | Apache-2.0 | traduzione locale (suddivisione del testo per i modelli) |
| langdetect | Apache-2.0 | rilevamento della lingua |
| Modelli Argos Translate / OPUS-MT | MIT / CC-BY 4.0 | scaricati al primo uso, non inclusi nel programma (https://github.com/argosopentech/argos-translate) |

PDFDesk è distribuito con licenza AGPL-3.0 (vedi `LICENSE`): il codice sorgente completo è disponibile insieme agli eseguibili.
Ghostscript è usato come programma separato (processo figlio); il suo sorgente è disponibile su https://ghostscript.com.
Non è incluso alcun profilo colore proprietario: per PDF/X si può indicare il profilo del proprio stampatore.
