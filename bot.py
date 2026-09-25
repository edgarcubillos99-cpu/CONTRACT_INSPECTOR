from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ai_reviewer import AIReviewError, RevisionIA, revisar_correo
from config import (
    EMAIL_ACCOUNT,
    MARK_AS_READ,
    OPENAI_MODEL,
    POLL_INTERVAL,
    PORT,
    PROCESSED_FILE,
    REPLY_INCOMPLETE,
    SUBJECT_KEYWORD,
    validate,
)
from email_inspector import (
    CorreoCandidato,
    descargar_pdfs,
    inspeccionar_correos,
    resumir,
    tipo_hilo,
)
from graph_client import GraphError, marcar_como_leido, responder_mensaje
from processed_store import ProcessedStore
from ubersmith_client import UbersmithError, publicar_contrato

_lock = threading.Lock()
_vistos = ProcessedStore(PROCESSED_FILE)
_estado: dict[str, str | None] = {
    "last_run": None,
    "last_error": None,
}


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cerrar(candidato: CorreoCandidato) -> None:
    _vistos.registrar(candidato.uid)
    if not MARK_AS_READ:
        print("  Registrado para no repetirlo (sin marcar leído).")
        return
    try:
        marcar_como_leido(candidato.uid)
        print("  Correo marcado como leído.")
    except GraphError as exc:
        print(f"  No se pudo marcar leído ({exc}). Quedó registrado en memoria.")


def _aviso_campos(revision: RevisionIA) -> str:
    faltantes = revision.campos_faltantes or ["(no se detallaron)"]
    lista = "\n".join(f"- {campo}" for campo in faltantes)
    ticket = revision.ticket_id or "no se encontró"
    archivo = revision.archivo or "el PDF adjunto"
    return (
        "Hola,\n\n"
        "El inspector automático de contratos revisó el adjunto y no puede "
        "cargarlo porque faltan campos por completar:\n\n"
        f"{lista}\n\n"
        f"Archivo: {archivo}\n"
        f"Ticket detectado: {ticket}\n\n"
        "Complete el contrato y reenvíelo a este correo con la palabra "
        '"contrato" en el asunto.\n\n'
        "Saludos,\n"
        "Inspector de contratos Osnet"
    )


def _avisar_incompleto(candidato: CorreoCandidato, revision: RevisionIA) -> None:
    destino = candidato.email_remitente or candidato.de
    if not REPLY_INCOMPLETE:
        print("  REPLY_INCOMPLETE=false: no se envió aviso.")
        return
    responder_mensaje(candidato.uid, _aviso_campos(revision))
    print(f"  Aviso de campos incompletos enviado a {destino}.")


def _procesar(candidato: CorreoCandidato) -> None:
    print(f"Procesando: {candidato.asunto!r} ({tipo_hilo(candidato.asunto)})")
    pdfs = descargar_pdfs(candidato)
    if not pdfs:
        print("  Sin PDF adjunto en este mensaje (ni en un reenvío anidado).")
        _cerrar(candidato)
        return

    revision = revisar_correo(candidato, pdfs)
    print(f"  IA: {revision.motivo}")
    if not revision.es_contrato_firmado:
        print("  La IA no lo clasificó como contrato firmado.")
        _cerrar(candidato)
        return
    if not revision.campos_completos:
        print(f"  Campos incompletos: {', '.join(revision.campos_faltantes) or 'sin detalle'}")
        _avisar_incompleto(candidato, revision)
        _cerrar(candidato)
        return
    if not revision.ticket_id:
        print("  La IA no encontró ticket_id.")
        _avisar_incompleto(candidato, revision)
        _cerrar(candidato)
        return

    adjunto, contenido = pdfs[0]
    if revision.archivo:
        for item, data in pdfs:
            if item.nombre == revision.archivo:
                adjunto, contenido = item, data
                break

    print(f"  Ticket encontrado: {revision.ticket_id}")
    print(f"  Enviando {adjunto.nombre} a Ubersmith...")
    post_id = publicar_contrato(revision.ticket_id, adjunto.nombre, contenido)
    print(f"  Comentario creado en ticket {revision.ticket_id} (post {post_id}).")
    _cerrar(candidato)


def run_ciclo() -> None:
    print(f"Leyendo {EMAIL_ACCOUNT} con Microsoft Graph")
    print(f"Filtro: correos no leídos cuyo asunto contenga {SUBJECT_KEYWORD!r}")
    with _lock:
        candidatos = [
            item for item in inspeccionar_correos() if not _vistos.contiene(item.uid)
        ]
        if candidatos:
            resumir(candidatos)
            for candidato in candidatos:
                _procesar(candidato)
        else:
            print("No hay correos nuevos por procesar.")
        _estado["last_run"] = _ahora()
        _estado["last_error"] = None


def _bucle_inspeccion() -> None:
    while True:
        try:
            run_ciclo()
        except (GraphError, UbersmithError, AIReviewError, Exception) as exc:
            _estado["last_run"] = _ahora()
            _estado["last_error"] = str(exc)
            print(f"Error en el ciclo (se reintenta): {exc}")
        time.sleep(max(POLL_INTERVAL, 5))


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, formato: str, *args: object) -> None:
        print(f"[http] {self.address_string()} {formato % args}")

    def _json(self, codigo: int, payload: dict) -> None:
        cuerpo = json.dumps(payload).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self) -> None:
        if self.path in {"/", "/health"}:
            self._json(
                200,
                {
                    "status": "listening",
                    "mailbox": EMAIL_ACCOUNT,
                    "poll_interval": POLL_INTERVAL,
                    "last_run": _estado["last_run"],
                    "last_error": _estado["last_error"],
                    "processed": len(_vistos),
                    "mark_as_read": MARK_AS_READ,
                    "reply_incomplete": REPLY_INCOMPLETE,
                    "openai_model": OPENAI_MODEL,
                },
            )
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path == "/inspect":
            try:
                run_ciclo()
                self._json(200, {"status": "ok", "last_run": _estado["last_run"]})
            except Exception as exc:
                self._json(500, {"status": "error", "detail": str(exc)})
            return
        self._json(404, {"error": "not found"})


def main() -> None:
    validate()
    trabajador = threading.Thread(target=_bucle_inspeccion, name="inspector", daemon=True)
    trabajador.start()
    servidor = ThreadingHTTPServer(("0.0.0.0", PORT), _Handler)
    print(f"Servicio escuchando en 0.0.0.0:{PORT}")
    print(f"Revisión de correo cada {POLL_INTERVAL}s")
    print(f"IDs ya vistos: {len(_vistos)} (archivo {PROCESSED_FILE})")
    print(f"Revisión de contratos con {OPENAI_MODEL}")
    if not MARK_AS_READ:
        print("MARK_AS_READ=false: no se marcarán correos como leídos.")
    if REPLY_INCOMPLETE:
        print("Si faltan campos, se responderá al remitente (Mail.Send).")
    servidor.serve_forever()


if __name__ == "__main__":
    main()
