"""Archivos de medios en disco: tipo real, guardado y variantes WebP (RF-13, RF-14).

Cada medio vive en MEDIA_ROOT/<site_id>/<media_id>/: el original (`original.<ext>`) y,
si es imagen, `miniatura.webp`, `mediana.webp` y `grande.webp`.
"""

import shutil
from pathlib import Path

from flask import current_app
from PIL import Image, ImageOps

from app.media.models import VARIANTS

# Se rechaza en vez de advertir: una imagen gigante comprimida podría agotar la memoria.
Image.MAX_IMAGE_PIXELS = 50_000_000
IMAGE_FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp", "GIF": "image/gif"}
EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
    "application/pdf": "pdf",
}


class InvalidFile(ValueError):
    pass


def detect(stream):
    """Tipo real según el contenido, no la extensión. Devuelve (mime, ancho, alto)."""
    stream.seek(0)
    if stream.read(5) == b"%PDF-":
        stream.seek(0)
        return "application/pdf", None, None
    stream.seek(0)
    try:
        with Image.open(stream) as img:
            fmt, (width, height) = img.format, img.size
            img.verify()
    except (OSError, SyntaxError, ValueError, Image.DecompressionBombError) as e:
        raise InvalidFile("no es una imagen JPEG, PNG, WebP o GIF ni un PDF válido") from e
    finally:
        stream.seek(0)
    if fmt not in IMAGE_FORMATS:
        raise InvalidFile("no es una imagen JPEG, PNG, WebP o GIF ni un PDF válido")
    if fmt == "JPEG":  # la orientación EXIF puede invertir ancho y alto
        with Image.open(stream) as img:
            width, height = ImageOps.exif_transpose(img).size
        stream.seek(0)
    return IMAGE_FORMATS[fmt], width, height


def folder(media):
    return Path(current_app.config["MEDIA_ROOT"]) / str(media.site_id) / str(media.id)


def original_path(media):
    return folder(media) / f"original.{EXTENSIONS[media.mime]}"


def variant_path(media, name):
    return folder(media) / f"{name}.webp"


def store(media, stream):
    path = original_path(media)
    path.parent.mkdir(parents=True, exist_ok=True)
    stream.seek(0)
    with path.open("wb") as f:
        shutil.copyfileobj(stream, f)


def remove(media):
    shutil.rmtree(folder(media), ignore_errors=True)


def make_variants(media):
    """Genera las WebP sin agrandar: solo los anchos menores o iguales al original."""
    result = {}
    with Image.open(original_path(media)) as img:
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGBA" if img.mode in {"RGBA", "LA", "P"} else "RGB")
        for name, width in VARIANTS.items():
            if width > img.width and result:
                continue  # la miniatura siempre se genera, aunque la imagen sea más angosta
            copy = img.copy()
            copy.thumbnail((width, img.height))  # nunca agranda
            copy.save(variant_path(media, name), "WEBP", quality=82, method=6)
            result[name] = {"width": copy.width, "height": copy.height}
    return result
