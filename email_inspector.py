from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from config import SUBJECT_KEYWORD
from graph_client import listar_adjuntos, listar_mensajes_no_leidos


@dataclass
class Adjunto:
    nombre: str
    content_type: str
    tamano_bytes: int
    inline: bool = False


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


def _adjuntos_de(mensaje_id: str) -> list[Adjunto]:
    adjuntos: list[Adjunto] = []
    for item in listar_adjuntos(mensaje_id):
        adjuntos.append(
            Adjunto(
                nombre=item.get("name") or "sin_nombre",
                content_type=item.get("contentType") or "application/octet-stream",
                tamano_bytes=int(item.get("size") or 0),
                inline=bool(item.get("isInline")),
            )
        )
    return adjuntos


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
