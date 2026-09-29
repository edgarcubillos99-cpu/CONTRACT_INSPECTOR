from __future__ import annotations

from typing import Any

import requests

from config import (
    UBERSMITH_PASSWORD,
    UBERSMITH_QUEUE,
    UBERSMITH_URL,
    UBERSMITH_USER,
)


class UbersmithError(RuntimeError):
    pass


def _post(
    method: str,
    data: dict[str, str],
    files: dict[str, tuple[str, bytes, str]] | None = None,
) -> Any:
    respuesta = requests.post(
        UBERSMITH_URL,
        params={"method": method},
        auth=(UBERSMITH_USER, UBERSMITH_PASSWORD),
        data=data,
        files=files,
        timeout=60,
    )
    if not respuesta.ok:
        raise UbersmithError(
            f"Ubersmith HTTP {respuesta.status_code} ({method}): {respuesta.text[:400]}"
        )
    try:
        payload = respuesta.json()
    except ValueError as exc:
        raise UbersmithError(
            f"Ubersmith no devolvió JSON ({method}): {respuesta.text[:400]}"
        ) from exc

    if not payload.get("status"):
        codigo = payload.get("error_code")
        mensaje = payload.get("error_message") or payload
        raise UbersmithError(f"Ubersmith rechazó {method} ({codigo}): {mensaje}")
    return payload.get("data")


def publicar_contrato(ticket_id: str, nombre_archivo: str, pdf_bytes: bytes) -> Any:
    """Publica el PDF como comentario de staff. No envía subject."""
    return _post(
        "support.ticket_post_staff_response",
        {
            "ticket_id": ticket_id,
            "comment": "1",
            "body": "Se adjunta contrato",
        },
        files={
            "attach[0]": (nombre_archivo, pdf_bytes, "application/pdf"),
        },
    )


def actualizar_queue(ticket_id: str) -> Any:
    """Cambia solo el departamento (queue) del ticket."""
    if not UBERSMITH_QUEUE:
        raise UbersmithError("Falta UBERSMITH_QUEUE (ID del departamento en Ubersmith).")
    return _post(
        "support.ticket_update",
        {
            "ticket_id": ticket_id,
            "queue": UBERSMITH_QUEUE,
        },
    )
