import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

GRAPH_TENANT_ID = os.getenv("GRAPH_TENANT_ID", "").strip()
GRAPH_CLIENT_ID = os.getenv("GRAPH_CLIENT_ID", "").strip()
GRAPH_CLIENT_SECRET = os.getenv("GRAPH_CLIENT_SECRET", "").strip()
EMAIL_ACCOUNT = os.getenv("EMAIL_ACCOUNT", "").strip()
MAILBOX = os.getenv("MAILBOX", "inbox").strip().lower() or "inbox"
SUBJECT_KEYWORD = os.getenv("SUBJECT_KEYWORD", "contrato").strip().lower() or "contrato"
GRAPH_SCOPE = ["https://graph.microsoft.com/.default"]
GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"


def validate() -> None:
    faltantes = [
        nombre
        for nombre, valor in {
            "GRAPH_TENANT_ID": GRAPH_TENANT_ID,
            "GRAPH_CLIENT_ID": GRAPH_CLIENT_ID,
            "GRAPH_CLIENT_SECRET": GRAPH_CLIENT_SECRET,
            "EMAIL_ACCOUNT": EMAIL_ACCOUNT,
        }.items()
        if not valor
    ]
    if faltantes:
        raise SystemExit(
            "Faltan variables en .env: "
            + ", ".join(faltantes)
            + ". Copia .env.example a .env y completa los datos de Azure."
        )
