from config import EMAIL_ACCOUNT, SUBJECT_KEYWORD, validate
from email_inspector import inspeccionar_correos, resumir
from graph_client import GraphError


def main() -> None:
    validate()
    print(f"Leyendo {EMAIL_ACCOUNT} con Microsoft Graph")
    print(f"Filtro: correos no leídos cuyo asunto contenga {SUBJECT_KEYWORD!r}")
    try:
        candidatos = inspeccionar_correos()
    except GraphError as exc:
        raise SystemExit(str(exc)) from exc
    resumir(candidatos)
    print(
        "Siguiente paso: un clasificador de IA recibirá estos candidatos "
        "para decidir si el correo es un contrato firmado por el cliente."
    )


if __name__ == "__main__":
    main()
