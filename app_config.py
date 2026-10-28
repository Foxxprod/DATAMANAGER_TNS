# Persistance de la configuration utilisateur (config.json) : theme clair/
# sombre et titre du logiciel. Lue une fois au demarrage (main.py) dans un
# dict partage par reference avec layout.build_header, qui le modifie et
# le sauvegarde depuis la boite de dialogue Parametres.
#
# config.json n'est PAS commite (voir .gitignore) : c'est un reglage
# d'instance/machine. Fichier absent ou incomplet -> complete avec
# DEFAULT_CONFIG.

import json

from paths import user_data_path

CONFIG_PATH = user_data_path("config.json")

DEFAULT_CONFIG = {
    "dark_mode": False,
    "software_title": "TENNIS - DATA MANAGER",
}


def load_config() -> dict:
    config = dict(DEFAULT_CONFIG)

    try:
        with open(CONFIG_PATH, encoding="utf-8") as file:
            stored = json.load(file)
        if isinstance(stored, dict):
            config.update({key: stored[key] for key in DEFAULT_CONFIG if key in stored})
    except (OSError, json.JSONDecodeError):
        pass

    return config


def save_config(config: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as file:
        json.dump(config, file, indent=4, ensure_ascii=False)
