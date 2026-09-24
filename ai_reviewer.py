from __future__ import annotations

import base64
import io
import json
from dataclasses import dataclass

import pdfplumber
import pypdfium2 as pdfium
from openai import OpenAI

from config import OPENAI_API_KEY, OPENAI_MODEL
from email_inspector import Adjunto, CorreoCandidato, tipo_hilo


@dataclass
class RevisionIA:
    es_contrato_firmado: bool
    ticket_id: str | None
    motivo: str
    archivo: str | None = None


class AIReviewError(RuntimeError):
    pass


def _texto_pdf(pdf_bytes: bytes, max_paginas: int = 2) -> str:
    partes: list[str] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for indice, pagina in enumerate(pdf.pages[:max_paginas], start=1):
            texto = (pagina.extract_text() or "").strip()
            if texto:
                partes.append(f"--- Página {indice} ---\n{texto}")
    return "\n\n".join(partes)


def _imagen_primera_pagina(pdf_bytes: bytes) -> str | None:
    try:
        documento = pdfium.PdfDocument(pdf_bytes)
        if len(documento) == 0:
            return None
        imagen = documento[0].render(scale=1.4).to_pil()
        imagen.thumbnail((1400, 1800))
        buffer = io.BytesIO()
        imagen.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("ascii")
    except Exception:
        return None


def revisar_correo(candidato: CorreoCandidato, pdfs: list[tuple[Adjunto, bytes]]) -> RevisionIA:
    if not OPENAI_API_KEY:
        raise AIReviewError("Falta OPENAI_API_KEY en .env.")

    nombres = [adjunto.nombre for adjunto, _ in pdfs]
    bloques_texto: list[str] = []
    imagenes: list[str] = []
    for adjunto, contenido in pdfs[:3]:
        texto = _texto_pdf(contenido)
        bloques_texto.append(f"Archivo: {adjunto.nombre}\n{texto or '(sin texto extraíble)'}")
        imagen = _imagen_primera_pagina(contenido)
        if imagen:
            imagenes.append(imagen)

    clase = tipo_hilo(candidato.asunto)
    prompt = f"""Eres un agente que revisa correos de ventas de Osnet / GoFiberX.

Decide si el mensaje y sus archivos son el recibido de un CONTRATO DE SERVICIO FIRMADO por el cliente
(no cotización, no borrador interno, no guía, no prueba, no solo firma pendiente).

El correo puede ser un mensaje nuevo, una RESPUESTA (Re:/Resp:) o un REENVÍO (Fwd:/Fw:/RV:/Reenvío).
Eso no lo invalida. Revisa el cuerpo citado del hilo y los adjuntos, incluidos PDFs que vengan
dentro de un correo reenviado. Si hay un contrato firmado con ticket, trátalo como válido.

Una respuesta tipo "gracias" o "recibido" SIN contrato firmado en los archivos no es un contrato.
No uses un ticket que solo aparezca en un hilo viejo si no hay PDF de contrato en este mensaje.

Si lo es, extrae el ticket_id. En estos contratos suele estar en la primera página junto a
"# Ticket", "TICKET" o "TICKET_ID". Es un número (normalmente 4 a 10 dígitos).
No inventes un ticket. Si no está claro, ticket_id debe ser null.

Tipo de hilo: {clase}
Correo:
De: {candidato.de}
Para: {candidato.para}
Fecha: {candidato.fecha}
Asunto: {candidato.asunto}
Cuerpo:
{candidato.cuerpo[:8000] or '(vacío)'}

Adjuntos: {', '.join(nombres) or 'ninguno'}

Texto extraído de los PDF:
{chr(10).join(bloques_texto)[:12000]}

Responde SOLO un JSON con estas claves:
- es_contrato_firmado: boolean
- ticket_id: string o null
- motivo: string breve
- archivo: nombre del PDF del contrato, o null
"""

    contenido: list[dict] = [{"type": "text", "text": prompt}]
    for imagen in imagenes:
        contenido.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{imagen}"},
            }
        )

    cliente = OpenAI(api_key=OPENAI_API_KEY)
    try:
        respuesta = cliente.chat.completions.create(
            model=OPENAI_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": "Clasificas correos de contratos y extraes ticket_id. Solo JSON válido.",
                },
                {"role": "user", "content": contenido},
            ],
        )
    except Exception as exc:
        raise AIReviewError(f"OpenAI falló: {exc}") from exc

    crudo = (respuesta.choices[0].message.content or "").strip()
    try:
        data = json.loads(crudo)
    except json.JSONDecodeError as exc:
        raise AIReviewError(f"OpenAI no devolvió JSON válido: {crudo[:400]}") from exc

    ticket = data.get("ticket_id")
    if ticket is not None:
        ticket = str(ticket).strip() or None
        if ticket and not ticket.isdigit():
            solo = "".join(c for c in ticket if c.isdigit())
            ticket = solo or None

    return RevisionIA(
        es_contrato_firmado=bool(data.get("es_contrato_firmado")),
        ticket_id=ticket,
        motivo=str(data.get("motivo") or "").strip() or "sin motivo",
        archivo=(str(data.get("archivo")).strip() if data.get("archivo") else None),
    )
