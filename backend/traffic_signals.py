"""Semáforos complementares do mapa padrão, por nó e bairro."""

import json
from pathlib import Path


SIMULATED_SIGNALS_FILE = "blumenau-semaforos-simulados.json"


def load_simulated_signals(data_dir: Path) -> dict[str, str]:
    path = data_dir / SIMULATED_SIGNALS_FILE
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
