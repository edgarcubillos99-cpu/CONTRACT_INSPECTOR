from __future__ import annotations

import io
import re

import pdfplumber

_TICKET_EN_TEXTO = re.compile(
    r"(?:#\s*)?ticket(?:[_\s-]*id)?\s*:?\s*(\d{4,10})",
    re.IGNORECASE,
)


def extraer_ticket_texto(texto: str) -> str | None:
    if not texto:
        return None
    hallado = _TICKET_EN_TEXTO.search(texto)
    if hallado:
        return hallado.group(1)
    return None


def extraer_ticket_pdf(pdf_bytes: bytes) -> str | None:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        if not pdf.pages:
            return None
        pagina = pdf.pages[0]
        for palabra in pagina.extract_words() or []:
            directo = extraer_ticket_texto((palabra.get("text") or "").strip())
            if directo:
                return directo
        texto_pagina = pagina.extract_text() or ""
    return extraer_ticket_texto(texto_pagina)


def extraer_ticket(cuerpo_correo: str, pdfs: list[bytes]) -> str | None:
    for pdf in pdfs:
        ticket = extraer_ticket_pdf(pdf)
        if ticket:
            return ticket
    return extraer_ticket_texto(cuerpo_correo)
