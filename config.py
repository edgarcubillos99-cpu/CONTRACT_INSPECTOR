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

UBERSMITH_URL = os.getenv(
    "UBERSMITH_URL", "https://billing.gofiberx.com/api/2.0/"
).strip()
UBERSMITH_USER = os.getenv("UBERSMITH_USER", "").strip()
UBERSMITH_PASSWORD = (
    os.getenv("UBERSMITH_PASSWORD", "").strip()
    or os.getenv("UBERSMITH_TOKEN", "").strip()
)
PORT = int(os.getenv("PORT", "8080") or "8080")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60") or "60")
MARK_AS_READ = os.getenv("MARK_AS_READ", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "si",
    "sí",
}
REPLY_INCOMPLETE = os.getenv("REPLY_INCOMPLETE", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "si",
    "sí",
}
PROCESSED_FILE = os.getenv("PROCESSED_FILE", "data/processed_ids.txt").strip() or (
    "data/processed_ids.txt"
)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"


def validate() -> None:
    faltantes = [
        nombre
        for nombre, valor in {
            "GRAPH_TENANT_ID": GRAPH_TENANT_ID,
            "GRAPH_CLIENT_ID": GRAPH_CLIENT_ID,
            "GRAPH_CLIENT_SECRET": GRAPH_CLIENT_SECRET,
            "EMAIL_ACCOUNT": EMAIL_ACCOUNT,
            "UBERSMITH_USER": UBERSMITH_USER,
            "UBERSMITH_PASSWORD": UBERSMITH_PASSWORD,
            "OPENAI_API_KEY": OPENAI_API_KEY,
        }.items()
        if not valor
    ]
    if faltantes:
        raise SystemExit(
            "Faltan variables en .env: "
            + ", ".join(faltantes)
            + ". Completa Azure, Ubersmith y OPENAI_API_KEY."
        )
