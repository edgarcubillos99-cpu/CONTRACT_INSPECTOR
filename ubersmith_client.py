from __future__ import annotations

from typing import Any

import requests

from config import UBERSMITH_PASSWORD, UBERSMITH_URL, UBERSMITH_USER


class UbersmithError(RuntimeError):
    pass


def publicar_contrato(ticket_id: str, nombre_archivo: str, pdf_bytes: bytes) -> Any:
    """Publica el PDF como comentario de staff. No envía subject."""
    respuesta = requests.post(
        UBERSMITH_URL,
        params={"method": "support.ticket_post_staff_response"},
        auth=(UBERSMITH_USER, UBERSMITH_PASSWORD),
        data={
            "ticket_id": ticket_id,
            "comment": "1",
            "body": "Se adjunta contrato",
        },
        files={
            "attach[0]": (nombre_archivo, pdf_bytes, "application/pdf"),
        },
        timeout=60,
    )
    if not respuesta.ok:
        raise UbersmithError(
            f"Ubersmith HTTP {respuesta.status_code}: {respuesta.text[:400]}"
        )
    try:
        payload = respuesta.json()
    except ValueError as exc:
        raise UbersmithError(f"Ubersmith no devolvió JSON: {respuesta.text[:400]}") from exc

    if not payload.get("status"):
        codigo = payload.get("error_code")
        mensaje = payload.get("error_message") or payload
        raise UbersmithError(f"Ubersmith rechazó el post ({codigo}): {mensaje}")
    return payload.get("data")
