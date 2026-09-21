import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")


def _bool_env(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "si", "sí"}


IMAP_SERVER = os.getenv("IMAP_SERVER", "").strip()
IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))
EMAIL_ACCOUNT = os.getenv("EMAIL_ACCOUNT", "").strip()
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "").strip()
MAILBOX = os.getenv("MAILBOX", "INBOX").strip() or "INBOX"
SUBJECT_KEYWORD = os.getenv("SUBJECT_KEYWORD", "contrato").strip().lower() or "contrato"
PEEK_ONLY = _bool_env("PEEK_ONLY", "true")


def validate() -> None:
    faltantes = [
        nombre
        for nombre, valor in {
            "IMAP_SERVER": IMAP_SERVER,
            "EMAIL_ACCOUNT": EMAIL_ACCOUNT,
            "EMAIL_PASSWORD": EMAIL_PASSWORD,
        }.items()
        if not valor
    ]
    if faltantes:
        raise SystemExit(
            "Faltan variables en .env: "
            + ", ".join(faltantes)
            + ". Copia .env.example a .env y completa los datos."
        )
