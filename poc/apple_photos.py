"""Read photo metadata from local Apple Photos library via osxphotos."""

import os
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

try:
    import osxphotos
except ImportError:
    print("Error: osxphotos not installed. Run: pip install -r requirements.txt")
    sys.exit(1)


@dataclass
class ApplePhoto:
    uuid: str
    filename: str
    original_filename: str
    date: Optional[datetime]
    file_size: Optional[int]
    camera_make: Optional[str]
    camera_model: Optional[str]
    in_trash: bool


def load_apple_photos(library_path: Optional[str] = None) -> list[ApplePhoto]:
    """Load all non-trashed photos from Apple Photos library."""
    kwargs = {"dbfile": library_path} if library_path else {}
    db = osxphotos.PhotosDB(**kwargs)

    photos = []
    for p in db.photos():
        exif = p.exif_info

        camera_make = None
        camera_model = None
        if exif:
            camera_make = getattr(exif, "camera_make", None)
            camera_model = getattr(exif, "camera_model", None)

        photos.append(ApplePhoto(
            uuid=p.uuid,
            filename=p.filename,
            original_filename=p.original_filename or p.filename,
            date=p.date,
            file_size=p.file_size,
            camera_make=camera_make,
            camera_model=camera_model,
            in_trash=p.intrash,
        ))

    return photos


def get_active_photos(library_path: Optional[str] = None) -> list[ApplePhoto]:
    """Return only photos not in the trash."""
    return [p for p in load_apple_photos(library_path) if not p.in_trash]


def get_deleted_photos(library_path: Optional[str] = None) -> list[ApplePhoto]:
    """Return photos in the Apple Photos trash (deleted but not purged)."""
    return [p for p in load_apple_photos(library_path) if p.in_trash]


def build_lookup_key(filename: str, date: Optional[datetime]) -> str:
    """Build a match key from filename + date truncated to the minute."""
    base = os.path.splitext(filename.lower())[0]
    if date:
        return f"{base}_{date.strftime('%Y%m%d_%H%M')}"
    return base
