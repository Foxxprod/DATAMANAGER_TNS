# Chemins de fichiers, compatibles a la fois avec une execution en mode
# developpement (python main.py depuis le repo) ET en mode installe
# (executable compile via PyInstaller) - meme principe que Biath Control
# Center.
#
#   - resource_path() : ressources EN LECTURE SEULE embarquees dans
#     l'executable (logo, icone). En mode installe, PyInstaller les
#     extrait dans sys._MEIPASS - jamais a utiliser pour ecrire.
#
#   - user_data_path() : fichiers UTILISATEUR modifiables par le logiciel
#     (config.json, base SQLite). En mode installe,
#     %APPDATA%\DataManagerTNS ; en developpement, la racine du projet.

import os
import sys
from pathlib import Path

#True uniquement dans un executable compile par PyInstaller
FROZEN = getattr(sys, "frozen", False)


def resource_path(*parts: str) -> Path:
    if FROZEN:
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        base = Path(__file__).parent

    return base.joinpath(*parts)


def user_data_path(*parts: str) -> Path:
    if FROZEN:
        base = Path(os.environ.get("APPDATA", Path.home())) / "DataManagerTNS"
        base.mkdir(parents=True, exist_ok=True)
    else:
        base = Path(__file__).parent

    return base.joinpath(*parts)
