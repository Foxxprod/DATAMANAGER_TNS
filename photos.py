# Photos des joueurs : PNG d'exactement 3000x3000, stockes tels quels (pas
# de retouche) dans le dossier utilisateur photos/ (voir media.py),
# player_<id>.png, servis sous /photos.

from media import MediaError, MediaStore

PHOTO_SIZE = (3000, 3000)
#un PNG 3000x3000 fait quelques Mo a quelques dizaines de Mo selon son contenu
MAX_UPLOAD_BYTES = 80 * 1024 * 1024

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


#(largeur, hauteur) d'un PNG lues dans son entete (bloc IHDR), None si les
#donnees ne sont pas un PNG
def png_size(header: bytes) -> tuple[int, int] | None:
    if len(header) < 24 or not header.startswith(PNG_SIGNATURE) or header[12:16] != b"IHDR":
        return None
    return int.from_bytes(header[16:20], "big"), int.from_bytes(header[20:24], "big")


def _check_photo(data: bytes) -> bytes:
    size = png_size(data[:24])
    if size is None:
        raise MediaError("Le fichier n'est pas une image PNG")
    if size != PHOTO_SIZE:
        raise MediaError(
            f"La photo doit faire {PHOTO_SIZE[0]} x {PHOTO_SIZE[1]} px (fichier recu : {size[0]} x {size[1]} px)"
        )
    return data


PHOTOS = MediaStore("photos", "/photos", "player", MAX_UPLOAD_BYTES, _check_photo)
