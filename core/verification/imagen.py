from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}
MAX_SIDE = 2000


class ImageValidationError(ValueError):
    """La imagen no cumple las restricciones del modulo."""


@dataclass(frozen=True)
class ImagenSaneada:
    datos: bytes
    mime: str
    sha256_original: str


def sanear_imagen(imagen: bytes, mime: str, max_image_mb: float = 5) -> ImagenSaneada:
    original_hash = sha256(imagen).hexdigest()
    if mime.lower() not in ALLOWED_MIME:
        raise ImageValidationError("formato_no_permitido")
    if len(imagen) > max_image_mb * 1024 * 1024:
        raise ImageValidationError("imagen_demasiado_grande")

    try:
        with Image.open(BytesIO(imagen)) as source:
            source.load()
            if source.format not in {"JPEG", "PNG", "WEBP"}:
                raise ImageValidationError("formato_no_permitido")
            image = ImageOps.exif_transpose(source)
            if max(image.size) > MAX_SIDE:
                scale = MAX_SIDE / max(image.size)
                image = image.resize(
                    (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
                    Image.Resampling.LANCZOS,
                )
            if mime.lower() == "image/jpeg" and image.mode not in {"RGB", "L"}:
                image = image.convert("RGB")
            output = BytesIO()
            image.save(output, format={"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}[mime.lower()])
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ImageValidationError("imagen_invalida") from exc

    return ImagenSaneada(output.getvalue(), mime.lower(), original_hash)