from __future__ import annotations

import email
import re
from dataclasses import dataclass, field
from email import policy
from typing import Any, Iterable

from config import SUBJECT_KEYWORD
from graph_client import (
    descargar_adjunto,
    descargar_adjunto_anidado,
    listar_adjuntos,
    listar_adjuntos_de_item,
    listar_mensajes_no_leidos,
)


@dataclass
class Adjunto:
    id: str
    nombre: str
    content_type: str
    tamano_bytes: int
    inline: bool = False
    item_parent_id: str | None = None
    contenido: bytes | None = None

    def es_pdf(self) -> bool:
        tipo = (self.content_type or "").lower()
        nombre = (self.nombre or "").lower()
        return (not self.inline) and (
            "pdf" in tipo or nombre.endswith(".pdf")
        )


@dataclass
class CorreoCandidato:
    uid: str
    de: str
    para: str
    asunto: str
    fecha: str
    cuerpo: str
    adjuntos: list[Adjunto] = field(default_factory=list)


def _html_a_texto(html: str) -> str:
    texto = html
    for etiqueta in ("script", "style"):
        inicio = texto.lower().find(f"<{etiqueta}")
        while inicio != -1:
            cierre = texto.lower().find(f"</{etiqueta}>", inicio)
            if cierre == -1:
                break
            texto = texto[:inicio] + texto[cierre + len(etiqueta) + 3 :]
            inicio = texto.lower().find(f"<{etiqueta}")
    limpio: list[str] = []
    dentro_etiqueta = False
    for caracter in texto:
        if caracter == "<":
            dentro_etiqueta = True
            continue
        if caracter == ">":
            dentro_etiqueta = False
            limpio.append(" ")
            continue
        if not dentro_etiqueta:
            limpio.append(caracter)
    return " ".join("".join(limpio).split())


def _direccion(bloque: dict[str, Any] | None) -> str:
    if not bloque:
        return ""
    correo = bloque.get("emailAddress") or {}
    nombre = (correo.get("name") or "").strip()
    address = (correo.get("address") or "").strip()
    if nombre and address:
        return f"{nombre} <{address}>"
    return nombre or address


def _destinatarios(mensaje: dict[str, Any]) -> str:
    partes = [_direccion(item) for item in mensaje.get("toRecipients") or []]
    return ", ".join(p for p in partes if p)


def _cuerpo(mensaje: dict[str, Any]) -> str:
    cuerpo = mensaje.get("body") or {}
    contenido = (cuerpo.get("content") or "").strip()
    if not contenido:
        return ""
    if (cuerpo.get("contentType") or "").lower() == "html":
        return _html_a_texto(contenido)
    return contenido


def _asunto_coincide(asunto: str) -> bool:
    return SUBJECT_KEYWORD in (asunto or "").lower()


def tipo_hilo(asunto: str) -> str:
    normal = (asunto or "").strip().lower()
    if re.match(r"^(re|resp)\s*:", normal):
        return "respuesta"
    if re.match(r"^(fwd|fw|rv|reenv[ií]o)\s*:", normal):
        return "reenvio"
    return "nuevo"


def _es_item(item: dict[str, Any]) -> bool:
    tipo = (item.get("@odata.type") or "").lower()
    return "itemattachment" in tipo


def _es_eml(item: dict[str, Any]) -> bool:
    nombre = (item.get("name") or "").lower()
    tipo = (item.get("contentType") or "").lower()
    return nombre.endswith(".eml") or tipo in {"message/rfc822", "message/rfc822-headers"}


def _pdfs_desde_eml(raw: bytes) -> list[tuple[Adjunto, bytes]]:
    try:
        mensaje = email.message_from_bytes(raw, policy=policy.default)
    except Exception:
        return []
    hallados: list[tuple[Adjunto, bytes]] = []
    for parte in mensaje.walk():
        nombre = parte.get_filename() or ""
        tipo = parte.get_content_type() or ""
        payload = parte.get_payload(decode=True)
        if not payload:
            continue
        if "pdf" in tipo.lower() or nombre.lower().endswith(".pdf"):
            adjunto = Adjunto(
                id="",
                nombre=nombre or "contrato.pdf",
                content_type="application/pdf",
                tamano_bytes=len(payload),
                contenido=payload,
            )
            hallados.append((adjunto, payload))
        elif nombre.lower().endswith(".eml") or tipo == "message/rfc822":
            hallados.extend(_pdfs_desde_eml(payload))
    return hallados


def _adjuntos_de(mensaje_id: str) -> list[Adjunto]:
    adjuntos: list[Adjunto] = []
    for item in listar_adjuntos(mensaje_id):
        adjuntos.append(
            Adjunto(
                id=item.get("id") or "",
                nombre=item.get("name") or "sin_nombre",
                content_type=item.get("contentType") or "application/octet-stream",
                tamano_bytes=int(item.get("size") or 0),
                inline=bool(item.get("isInline")),
            )
        )
    return adjuntos


def descargar_pdfs(candidato: CorreoCandidato) -> list[tuple[Adjunto, bytes]]:
    descargados: list[tuple[Adjunto, bytes]] = []
    vistos: set[tuple[str, int]] = set()

    def _agregar(adjunto: Adjunto, contenido: bytes) -> None:
        clave = (adjunto.nombre.lower(), len(contenido))
        if not contenido or clave in vistos:
            return
        vistos.add(clave)
        descargados.append((adjunto, contenido))

    items = listar_adjuntos(candidato.uid)
    for item in items:
        if item.get("isInline"):
            continue
        adjunto_id = item.get("id") or ""
        if _es_item(item) and adjunto_id:
            for anidado in listar_adjuntos_de_item(candidato.uid, adjunto_id):
                if anidado.get("isInline"):
                    continue
                hijo = Adjunto(
                    id=anidado.get("id") or "",
                    nombre=anidado.get("name") or "sin_nombre",
                    content_type=anidado.get("contentType") or "application/octet-stream",
                    tamano_bytes=int(anidado.get("size") or 0),
                    item_parent_id=adjunto_id,
                )
                if hijo.es_pdf() and hijo.id:
                    _agregar(
                        hijo,
                        descargar_adjunto_anidado(candidato.uid, adjunto_id, hijo.id),
                    )
            try:
                crudo = descargar_adjunto(candidato.uid, adjunto_id)
            except Exception:
                crudo = b""
            for extra, contenido in _pdfs_desde_eml(crudo):
                _agregar(extra, contenido)
            continue
        if _es_eml(item) and adjunto_id:
            for extra, contenido in _pdfs_desde_eml(
                descargar_adjunto(candidato.uid, adjunto_id)
            ):
                _agregar(extra, contenido)
            continue
        adjunto = Adjunto(
            id=adjunto_id,
            nombre=item.get("name") or "sin_nombre",
            content_type=item.get("contentType") or "application/octet-stream",
            tamano_bytes=int(item.get("size") or 0),
            inline=bool(item.get("isInline")),
        )
        if adjunto.es_pdf() and adjunto.id:
            _agregar(adjunto, descargar_adjunto(candidato.uid, adjunto.id))
    return descargados


def inspeccionar_correos() -> list[CorreoCandidato]:
    """Revisa no leídos vía Graph y devuelve los que tienen 'contrato' en el asunto."""
    candidatos: list[CorreoCandidato] = []
    for mensaje in listar_mensajes_no_leidos():
        asunto = mensaje.get("subject") or ""
        if not _asunto_coincide(asunto):
            continue
        mensaje_id = mensaje.get("id") or ""
        candidatos.append(
            CorreoCandidato(
                uid=mensaje_id,
                de=_direccion(mensaje.get("from")),
                para=_destinatarios(mensaje),
                asunto=asunto,
                fecha=mensaje.get("receivedDateTime") or "",
                cuerpo=_cuerpo(mensaje),
                adjuntos=_adjuntos_de(mensaje_id) if mensaje.get("hasAttachments") else [],
            )
        )
    return candidatos


def resumir(candidatos: Iterable[CorreoCandidato]) -> None:
    candidatos = list(candidatos)
    if not candidatos:
        print("No hay correos no leídos con 'contrato' en el asunto.")
        return

    print(f"Candidatos encontrados: {len(candidatos)}\n")
    for item in candidatos:
        print("=" * 60)
        print(f"ID:      {item.uid}")
        print(f"De:      {item.de}")
        print(f"Para:    {item.para}")
        print(f"Fecha:   {item.fecha}")
        print(f"Asunto:  {item.asunto}")
        print(f"Tipo:    {tipo_hilo(item.asunto)}")
        print(f"Cuerpo:  {item.cuerpo[:500] or '(vacío)'}{'...' if len(item.cuerpo) > 500 else ''}")
        visibles = [a for a in item.adjuntos if not a.inline]
        if visibles:
            print("Adjuntos:")
            for adjunto in visibles:
                print(
                    f"  - {adjunto.nombre} ({adjunto.content_type}, {adjunto.tamano_bytes} bytes)"
                )
        else:
            print("Adjuntos: ninguno")
        print()
