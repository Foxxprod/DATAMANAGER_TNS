# Logos des tournois : n'importe quelle image courante (PNG, JPEG, WEBP,
# GIF, BMP...), redimensionnee pour tenir dans LOGO_MAX_SIZE en gardant ses
# proportions, convertie en PNG (transparence conservee). Stockes dans le
# dossier utilisateur logos/ (voir media.py), tournament_<id>.png, servis
# sous /logos.

import io

from PIL import Image, UnidentifiedImageError

from media import MediaError, MediaStore

LOGO_MAX_SIZE = (512, 512)
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
ACCEPTED_TYPES = ".png,.jpg,.jpeg,.webp,.gif,.bmp,image/*"


def _resize_logo(data: bytes) -> bytes:
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError) as error:
        raise MediaError("Le fichier n'est pas une image reconnue (PNG, JPEG, WEBP...)") from error
    image = image.convert("RGBA")
    #thumbnail : reduit seulement (un petit logo n'est pas agrandi), proportions conservees
    image.thumbnail(LOGO_MAX_SIZE, Image.LANCZOS)
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


LOGOS = MediaStore("logos", "/logos", "tournament", MAX_UPLOAD_BYTES, _resize_logo)
