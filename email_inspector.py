from __future__ import annotations

import imaplib
import email
from dataclasses import dataclass, field
from email.header import decode_header, make_header
from email.message import Message
from typing import Iterable

from config import (
    EMAIL_ACCOUNT,
    EMAIL_PASSWORD,
    IMAP_PORT,
    IMAP_SERVER,
    MAILBOX,
    PEEK_ONLY,
    SUBJECT_KEYWORD,
)


@dataclass
class Adjunto:
    nombre: str
    content_type: str
    tamano_bytes: int


@dataclass
class CorreoCandidato:
    uid: str
    de: str
    para: str
    asunto: str
    fecha: str
    cuerpo: str
    adjuntos: list[Adjunto] = field(default_factory=list)


def _decodificar(valor: str | None) -> str:
    if not valor:
        return ""
    try:
        return str(make_header(decode_header(valor))).strip()
    except Exception:
        return valor.strip()


def _extraer_cuerpo(mensaje: Message) -> str:
    textos: list[str] = []
    if mensaje.is_multipart():
        for parte in mensaje.walk():
            if parte.get_content_maintype() == "multipart":
                continue
            if parte.get_filename():
                continue
            contenido = _decodificar_payload(parte)
            if contenido:
                textos.append(contenido)
    else:
        contenido = _decodificar_payload(mensaje)
        if contenido:
            textos.append(contenido)
    return "\n\n".join(textos).strip()


def _decodificar_payload(parte: Message) -> str:
    payload = parte.get_payload(decode=True)
    if payload is None:
        return ""
    charset = parte.get_content_charset() or "utf-8"
    try:
        texto = payload.decode(charset, errors="replace")
    except LookupError:
        texto = payload.decode("utf-8", errors="replace")
    if parte.get_content_type() == "text/html":
        return _html_a_texto(texto)
    return texto.strip()


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


def _listar_adjuntos(mensaje: Message) -> list[Adjunto]:
    adjuntos: list[Adjunto] = []
    for parte in mensaje.walk():
        nombre = parte.get_filename()
        disposicion = (parte.get("Content-Disposition") or "").lower()
        if not nombre and "attachment" not in disposicion:
            continue
        nombre = _decodificar(nombre) or "sin_nombre"
        payload = parte.get_payload(decode=True) or b""
        adjuntos.append(
            Adjunto(
                nombre=nombre,
                content_type=parte.get_content_type(),
                tamano_bytes=len(payload),
            )
        )
    return adjuntos


def _asunto_coincide(asunto: str) -> bool:
    return SUBJECT_KEYWORD in asunto.lower()


def _conectar() -> imaplib.IMAP4_SSL:
    correo = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
    correo.login(EMAIL_ACCOUNT, EMAIL_PASSWORD)
    estado, _ = correo.select(MAILBOX, readonly=PEEK_ONLY)
    if estado != "OK":
        raise RuntimeError(f"No se pudo abrir la bandeja {MAILBOX!r}.")
    return correo


def _uids_no_leidos(correo: imaplib.IMAP4_SSL) -> list[bytes]:
    estado, data = correo.uid("search", None, "UNSEEN")
    if estado != "OK" or not data or not data[0]:
        return []
    return data[0].split()


def _obtener_mensaje(correo: imaplib.IMAP4_SSL, uid: bytes) -> Message:
    # BODY.PEEK no marca el correo como leído.
    estado, data = correo.uid("fetch", uid, "(BODY.PEEK[])")
    if estado != "OK" or not data:
        raise RuntimeError(f"No se pudo leer el correo UID {uid!r}.")
    for parte in data:
        if isinstance(parte, tuple):
            return email.message_from_bytes(parte[1])
    raise RuntimeError(f"Respuesta IMAP inesperada para UID {uid!r}.")


def inspeccionar_correos() -> list[CorreoCandidato]:
    """Revisa no leídos y devuelve los que tienen 'contrato' en el asunto."""
    correo = _conectar()
    candidatos: list[CorreoCandidato] = []
    try:
        for uid in _uids_no_leidos(correo):
            mensaje = _obtener_mensaje(correo, uid)
            asunto = _decodificar(mensaje.get("Subject"))
            if not _asunto_coincide(asunto):
                continue
            candidatos.append(
                CorreoCandidato(
                    uid=uid.decode("utf-8", errors="replace"),
                    de=_decodificar(mensaje.get("From")),
                    para=_decodificar(mensaje.get("To")),
                    asunto=asunto,
                    fecha=_decodificar(mensaje.get("Date")),
                    cuerpo=_extraer_cuerpo(mensaje),
                    adjuntos=_listar_adjuntos(mensaje),
                )
            )
    finally:
        try:
            correo.close()
        except Exception:
            pass
        correo.logout()
    return candidatos


def resumir(candidatos: Iterable[CorreoCandidato]) -> None:
    candidatos = list(candidatos)
    if not candidatos:
        print("No hay correos no leídos con 'contrato' en el asunto.")
        return

    print(f"Candidatos encontrados: {len(candidatos)}\n")
    for item in candidatos:
        print("=" * 60)
        print(f"UID:     {item.uid}")
        print(f"De:      {item.de}")
        print(f"Para:    {item.para}")
        print(f"Fecha:   {item.fecha}")
        print(f"Asunto:  {item.asunto}")
        print(f"Cuerpo:  {item.cuerpo[:500] or '(vacío)'}{'...' if len(item.cuerpo) > 500 else ''}")
        if item.adjuntos:
            print("Adjuntos:")
            for adjunto in item.adjuntos:
                print(
                    f"  - {adjunto.nombre} ({adjunto.content_type}, {adjunto.tamano_bytes} bytes)"
                )
        else:
            print("Adjuntos: ninguno")
        print()
