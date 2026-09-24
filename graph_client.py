from __future__ import annotations

import base64
from typing import Any
from urllib.parse import quote

import msal
import requests

from config import (
    EMAIL_ACCOUNT,
    GRAPH_BASE_URL,
    GRAPH_CLIENT_ID,
    GRAPH_CLIENT_SECRET,
    GRAPH_SCOPE,
    GRAPH_TENANT_ID,
    MAILBOX,
)

_app: msal.ConfidentialClientApplication | None = None


class GraphError(RuntimeError):
    def __init__(self, mensaje: str, status_code: int | None = None) -> None:
        super().__init__(mensaje)
        self.status_code = status_code


def _app_msal() -> msal.ConfidentialClientApplication:
    global _app
    if _app is None:
        _app = msal.ConfidentialClientApplication(
            GRAPH_CLIENT_ID,
            authority=f"https://login.microsoftonline.com/{GRAPH_TENANT_ID}",
            client_credential=GRAPH_CLIENT_SECRET,
        )
    return _app


def obtener_token() -> str:
    resultado = _app_msal().acquire_token_for_client(scopes=GRAPH_SCOPE)
    if "access_token" not in resultado:
        error = resultado.get("error_description") or resultado.get("error") or resultado
        raise GraphError(
            "No se pudo obtener token de Microsoft. "
            "Revisa tenant, client id y client secret. Detalle: "
            f"{error}"
        )
    return resultado["access_token"]


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {obtener_token()}",
        "Accept": "application/json",
    }


def _explicar_error(respuesta: requests.Response) -> str:
    try:
        detalle = respuesta.json()
        mensaje = detalle.get("error", {}).get("message") or detalle
    except ValueError:
        mensaje = respuesta.text or respuesta.reason

    if respuesta.status_code == 401:
        return (
            "Microsoft rechazó el token (401). Revisa client secret y que la app exista."
        )
    if respuesta.status_code == 403:
        return (
            "Sin permiso para el buzón (403). Se necesitan Mail.Read y Mail.ReadWrite "
            "de tipo Application, más Grant admin consent. Detalle: "
            f"{mensaje}"
        )
    if respuesta.status_code == 404:
        return (
            f"No se encontró el buzón o la carpeta ({EMAIL_ACCOUNT!r}, {MAILBOX!r}). "
            f"Detalle: {mensaje}"
        )
    return f"Error de Graph {respuesta.status_code}: {mensaje}"


def graph_get(ruta: str, params: dict[str, str] | None = None) -> dict[str, Any]:
    url = ruta if ruta.startswith("http") else f"{GRAPH_BASE_URL}{ruta}"
    respuesta = requests.get(url, headers=_headers(), params=params, timeout=30)
    if not respuesta.ok:
        raise GraphError(_explicar_error(respuesta), status_code=respuesta.status_code)
    return respuesta.json()


def graph_patch(ruta: str, payload: dict[str, Any]) -> None:
    url = ruta if ruta.startswith("http") else f"{GRAPH_BASE_URL}{ruta}"
    cabeceras = {**_headers(), "Content-Type": "application/json"}
    respuesta = requests.patch(url, headers=cabeceras, json=payload, timeout=30)
    if not respuesta.ok:
        raise GraphError(_explicar_error(respuesta), status_code=respuesta.status_code)


def graph_get_bytes(ruta: str) -> bytes:
    url = ruta if ruta.startswith("http") else f"{GRAPH_BASE_URL}{ruta}"
    respuesta = requests.get(url, headers=_headers(), timeout=60)
    if not respuesta.ok:
        raise GraphError(_explicar_error(respuesta), status_code=respuesta.status_code)
    return respuesta.content


def _buzon() -> str:
    return quote(EMAIL_ACCOUNT)


def listar_mensajes_no_leidos() -> list[dict[str, Any]]:
    mensajes: list[dict[str, Any]] = []
    ruta = f"/users/{_buzon()}/mailFolders/{quote(MAILBOX)}/messages"
    params = {
        "$filter": "isRead eq false",
        "$select": "id,subject,from,toRecipients,receivedDateTime,body,hasAttachments,isRead,conversationId",
        "$top": "50",
        "$orderby": "receivedDateTime desc",
    }
    data = graph_get(ruta, params=params)
    mensajes.extend(data.get("value") or [])
    while data.get("@odata.nextLink"):
        data = graph_get(data["@odata.nextLink"])
        mensajes.extend(data.get("value") or [])
    return mensajes


def listar_adjuntos(message_id: str) -> list[dict[str, Any]]:
    ruta = f"/users/{_buzon()}/messages/{quote(message_id)}/attachments"
    data = graph_get(ruta)
    return data.get("value") or []


def listar_adjuntos_de_item(message_id: str, attachment_id: str) -> list[dict[str, Any]]:
    rutas = (
        f"/users/{_buzon()}/messages/{quote(message_id)}"
        f"/attachments/{quote(attachment_id)}/item/attachments",
        f"/users/{_buzon()}/messages/{quote(message_id)}"
        f"/attachments/{quote(attachment_id)}/microsoft.graph.itemAttachment/item/attachments",
    )
    for ruta in rutas:
        try:
            data = graph_get(ruta)
            return data.get("value") or []
        except GraphError:
            continue
    return []


def descargar_adjunto(message_id: str, attachment_id: str) -> bytes:
    ruta = (
        f"/users/{_buzon()}/messages/{quote(message_id)}"
        f"/attachments/{quote(attachment_id)}"
    )
    data = graph_get(ruta)
    if data.get("contentBytes"):
        return base64.b64decode(data["contentBytes"])
    return graph_get_bytes(f"{ruta}/$value")


def descargar_adjunto_anidado(
    message_id: str, item_attachment_id: str, file_attachment_id: str
) -> bytes:
    bases = (
        f"/users/{_buzon()}/messages/{quote(message_id)}"
        f"/attachments/{quote(item_attachment_id)}/item/attachments/{quote(file_attachment_id)}",
        f"/users/{_buzon()}/messages/{quote(message_id)}"
        f"/attachments/{quote(item_attachment_id)}"
        f"/microsoft.graph.itemAttachment/item/attachments/{quote(file_attachment_id)}",
    )
    ultimo: GraphError | None = None
    for ruta in bases:
        try:
            data = graph_get(ruta)
            if data.get("contentBytes"):
                return base64.b64decode(data["contentBytes"])
            return graph_get_bytes(f"{ruta}/$value")
        except GraphError as exc:
            ultimo = exc
    raise ultimo or GraphError("No se pudo descargar el adjunto anidado.")


def marcar_como_leido(message_id: str) -> None:
    graph_patch(f"/users/{_buzon()}/messages/{quote(message_id)}", {"isRead": True})
