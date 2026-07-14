from fractions import Fraction
from pathlib import Path

import piexif
from piexif import helper


SUPPORTED_EXIF_SUFFIXES = {".jpg", ".jpeg"}
_MISSING = object()


def _decode(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").rstrip("\x00")
    return str(value or "")


def _rational_text(value):
    if not isinstance(value, tuple) or len(value) != 2 or not value[1]:
        return ""
    numerator, denominator = value
    fraction = Fraction(int(numerator), int(denominator))
    if fraction.denominator == 1:
        return str(fraction.numerator)
    if abs(float(fraction)) < 1:
        return f"{fraction.numerator}/{fraction.denominator}"
    return f"{float(fraction):.2f}".rstrip("0").rstrip(".")


def _as_rational(text):
    value = str(text or "").strip().lower().replace("mm", "").replace("f/", "")
    if not value:
        return None
    fraction = Fraction(value).limit_denominator(10000)
    return (fraction.numerator, fraction.denominator)


def _datetime_text(text):
    value = str(text or "").strip().replace("T", " ")
    if not value:
        return ""
    if len(value) == 10:
        value += " 00:00:00"
    if len(value) >= 10:
        value = value[:4] + ":" + value[5:7] + ":" + value[8:]
    return value


def read_exif(path):
    path = Path(path)
    if path.suffix.lower() not in SUPPORTED_EXIF_SUFFIXES:
        return {}

    try:
        data = piexif.load(str(path))
    except Exception:
        return {}

    zero = data.get("0th", {})
    exif = data.get("Exif", {})
    user_comment = exif.get(piexif.ExifIFD.UserComment, b"")
    if user_comment:
        try:
            user_comment = helper.UserComment.load(user_comment)
        except Exception:
            user_comment = _decode(user_comment)

    return {
        "datetime_original": _decode(exif.get(piexif.ExifIFD.DateTimeOriginal, b"")),
        "make": _decode(zero.get(piexif.ImageIFD.Make, b"")),
        "model": _decode(zero.get(piexif.ImageIFD.Model, b"")),
        "lens_model": _decode(exif.get(piexif.ExifIFD.LensModel, b"")),
        "iso": str(exif.get(piexif.ExifIFD.ISOSpeedRatings, "") or ""),
        "aperture": _rational_text(exif.get(piexif.ExifIFD.FNumber)),
        "shutter_speed": _rational_text(exif.get(piexif.ExifIFD.ExposureTime)),
        "focal_length": _rational_text(exif.get(piexif.ExifIFD.FocalLength)),
        "artist": _decode(zero.get(piexif.ImageIFD.Artist, b"")),
        "copyright": _decode(zero.get(piexif.ImageIFD.Copyright, b"")),
        "description": _decode(zero.get(piexif.ImageIFD.ImageDescription, b"")),
        "user_comment": str(user_comment or ""),
    }


def _set_bytes(container, tag, value, keep_blank):
    value = str(value or "").strip()
    if value:
        encoded = value.encode("utf-8")
        if container.get(tag) == encoded:
            return False
        container[tag] = encoded
        return True
    elif not keep_blank:
        return container.pop(tag, _MISSING) is not _MISSING
    return False


def _set_rational(container, tag, value, keep_blank):
    value = str(value or "").strip()
    if value:
        rational = _as_rational(value)
        if container.get(tag) == rational:
            return False
        container[tag] = rational
        return True
    elif not keep_blank:
        return container.pop(tag, _MISSING) is not _MISSING
    return False


def _set_value(container, tag, value, keep_blank):
    if value is not None:
        if container.get(tag) == value:
            return False
        container[tag] = value
        return True
    if not keep_blank:
        return container.pop(tag, _MISSING) is not _MISSING
    return False


def write_exif(images, values, progress_callback=None):
    images = list(images)
    total = len(images)
    keep_blank = bool(values.get("keep_blank", True))
    changed = 0
    skipped = 0
    errors = []

    def report_progress(done, path):
        if progress_callback is None:
            return
        try:
            progress_callback(done, total, path.name)
        except Exception:
            # Progress reporting must never make EXIF writes fail.
            pass

    for index, image in enumerate(images, start=1):
        path = Path(image)
        if path.suffix.lower() not in SUPPORTED_EXIF_SUFFIXES:
            skipped += 1
            report_progress(index, path)
            continue

        try:
            try:
                data = piexif.load(str(path))
            except Exception:
                data = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}

            zero = data.setdefault("0th", {})
            exif = data.setdefault("Exif", {})
            modified = False

            datetime_value = _datetime_text(values.get("datetime_original"))
            modified |= _set_bytes(exif, piexif.ExifIFD.DateTimeOriginal, datetime_value, keep_blank)
            modified |= _set_bytes(zero, piexif.ImageIFD.DateTime, datetime_value, keep_blank)
            modified |= _set_bytes(zero, piexif.ImageIFD.Make, values.get("make"), keep_blank)
            modified |= _set_bytes(zero, piexif.ImageIFD.Model, values.get("model"), keep_blank)
            modified |= _set_bytes(exif, piexif.ExifIFD.LensModel, values.get("lens_model"), keep_blank)
            modified |= _set_bytes(zero, piexif.ImageIFD.Artist, values.get("artist"), keep_blank)
            modified |= _set_bytes(zero, piexif.ImageIFD.Copyright, values.get("copyright"), keep_blank)
            modified |= _set_bytes(zero, piexif.ImageIFD.ImageDescription, values.get("description"), keep_blank)

            iso = str(values.get("iso") or "").strip()
            iso_value = int(float(iso)) if iso else None
            modified |= _set_value(
                exif,
                piexif.ExifIFD.ISOSpeedRatings,
                iso_value,
                keep_blank,
            )

            modified |= _set_rational(exif, piexif.ExifIFD.FNumber, values.get("aperture"), keep_blank)
            modified |= _set_rational(exif, piexif.ExifIFD.ExposureTime, values.get("shutter_speed"), keep_blank)
            modified |= _set_rational(exif, piexif.ExifIFD.FocalLength, values.get("focal_length"), keep_blank)

            comment = str(values.get("user_comment") or "").strip()
            comment_value = helper.UserComment.dump(comment, encoding="unicode") if comment else None
            modified |= _set_value(
                exif,
                piexif.ExifIFD.UserComment,
                comment_value,
                keep_blank,
            )

            legacy_backup = path.with_name(path.name + ".exif.bak")
            if legacy_backup.exists():
                legacy_backup.unlink()

            # 값이 이미 같으면 큰 JPEG 파일 전체를 다시 쓰지 않는다.
            if modified:
                piexif.insert(piexif.dump(data), str(path))
            changed += 1
        except Exception as error:
            errors.append(f"{path.name}: {error}")
        finally:
            report_progress(index, path)

    return {"changed": changed, "skipped": skipped, "errors": errors}
