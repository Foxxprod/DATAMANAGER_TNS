# Stockage des images envoyees depuis l'interface (photos des joueurs, logos
# des tournois) : fichiers sur disque dans un dossier utilisateur (voir
# paths.py), la base ne gardant que le nom du fichier. Servis en fichiers
# statiques (voir main.py) : apercu dans l'interface, et plus tard la future
# API.
#
# Une image choisie dans une fenetre de saisie est d'abord ecrite dans
# <dossier>/_pending/ (apercu possible avant enregistrement, element pas
# encore cree), puis deplacee en <dossier>/<prefixe>_<id>.png a
# l'enregistrement - ou supprimee si la fenetre est fermee sans enregistrer.

import os
import uuid
from typing import Callable

from paths import user_data_path


#image refusee : le message est affiche tel quel a l'operateur
class MediaError(Exception):
    pass


class MediaStore:
    #`process` : verifie/transforme les octets recus et renvoie le PNG a
    #stocker, ou leve MediaError (format, dimensions...)
    def __init__(
        self, folder: str, url: str, prefix: str, max_upload_bytes: int, process: Callable[[bytes], bytes]
    ) -> None:
        self.dir = user_data_path(folder)
        self.pending_dir = self.dir / "_pending"
        self.url = url
        self.prefix = prefix
        self.max_upload_bytes = max_upload_bytes
        self.process = process

    def ensure_dirs(self) -> None:
        self.pending_dir.mkdir(parents=True, exist_ok=True)

    #supprime les fichiers en attente laisses par une session precedente
    #(fenetre fermee brutalement, serveur arrete...)
    def cleanup_pending(self) -> None:
        for file in self.pending_dir.glob("*.png"):
            file.unlink(missing_ok=True)

    #verifie/transforme l'image puis l'ecrit en attente, renvoie son nom
    def save_pending(self, data: bytes) -> str:
        png = self.process(data)
        self.ensure_dirs()
        name = f"{uuid.uuid4().hex}.png"
        (self.pending_dir / name).write_bytes(png)
        return name

    def delete_pending(self, name: str) -> None:
        (self.pending_dir / name).unlink(missing_ok=True)

    #deplace le fichier en attente vers le fichier definitif de l'element
    #(remplace l'eventuel precedent), renvoie le nom a enregistrer en base
    def commit_pending(self, name: str, owner_id: int) -> str:
        final_name = f"{self.prefix}_{owner_id}.png"
        os.replace(self.pending_dir / name, self.dir / final_name)
        return final_name

    def delete(self, name: str) -> None:
        if name:
            (self.dir / name).unlink(missing_ok=True)

    def pending_url(self, name: str) -> str:
        return f"{self.url}/_pending/{name}"

    #`version` (ex: date de mise a jour de l'element) force le navigateur a
    #recharger l'image quand elle a ete remplacee sous le meme nom
    def file_url(self, name: str, version: str = "") -> str:
        return f"{self.url}/{name}" + (f"?v={version}" if version else "")
