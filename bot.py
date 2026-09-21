from config import SUBJECT_KEYWORD, validate
from email_inspector import inspeccionar_correos, resumir


def main() -> None:
    validate()
    print(f"Inspeccionando correos no leídos con asunto que contenga: {SUBJECT_KEYWORD!r}")
    candidatos = inspeccionar_correos()
    resumir(candidatos)
    print(
        "Siguiente paso: un clasificador de IA recibirá estos candidatos "
        "para decidir si el correo es un contrato firmado por el cliente."
    )


if __name__ == "__main__":
    main()
