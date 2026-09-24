from __future__ import annotations

from pathlib import Path


class ProcessedStore:
    """IDs de correos ya vistos: memoria + archivo para no perderlos al reiniciar."""

    def __init__(self, ruta: str) -> None:
        self.ruta = Path(ruta)
        self._ids: set[str] = set()
        self._cargar()

    def _cargar(self) -> None:
        if not self.ruta.is_file():
            return
        self._ids = {
            linea.strip()
            for linea in self.ruta.read_text(encoding="utf-8").splitlines()
            if linea.strip()
        }

    def contiene(self, message_id: str) -> bool:
        return bool(message_id) and message_id in self._ids

    def registrar(self, message_id: str) -> None:
        if not message_id or message_id in self._ids:
            return
        self._ids.add(message_id)
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        with self.ruta.open("a", encoding="utf-8") as archivo:
            archivo.write(message_id + "\n")

    def __len__(self) -> int:
        return len(self._ids)
