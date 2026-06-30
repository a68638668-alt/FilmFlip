from pathlib import Path

IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".tif",
    ".tiff",
    ".bmp",
    ".webp",
}


def find_images(folder):
    images = sorted(
        [
            f
            for f in Path(folder).iterdir()
            if (
                f.is_file()
                and f.suffix.lower() in IMAGE_EXTENSIONS
                and not f.name.startswith(".")
            )
        ]
    )

    return images


def _safe_component(text):
    text = (text or "").strip()

    for char in ['/', '\\', ':', '*', '?', '"', '<', '>', '|']:
        text = text.replace(char, "")

    return text.strip()


def _make_template(
    template=None,
    camera="",
    film="",
    lab="",
    place="",
):
    if template:
        return template

    parts = [
        _safe_component(camera),
        _safe_component(film),
        _safe_component(lab),
        _safe_component(place),
    ]
    parts = [part for part in parts if part]
    parts.append("{n}")

    return "_".join(parts)


def build_preview(
    images,
    template="{n}",
    reverse=True,
    camera="",
    film="",
    lab="",
    place="",
):
    preview = []

    total = len(images)
    digits = 3
    template = _make_template(
        template=template,
        camera=camera,
        film=film,
        lab=lab,
        place=place,
    )

    for index, image in enumerate(images):
        if reverse:
            new_number = total - index
        else:
            new_number = index + 1

        number = f"{new_number:0{digits}d}"
        base_name = template.replace("{n}", number)
        new_name = f"{base_name}{image.suffix.lower()}"

        preview.append(
            (
                image,
                image.name,
                new_name,
            )
        )

    return preview


LAST_UNDO = []


def rename_images(preview):
    """
    충돌 없이 파일명을 변경한다.
    1차 : 임시 파일명으로 변경
    2차 : 최종 파일명으로 변경
    """

    global LAST_UNDO
    LAST_UNDO = build_undo_list(preview)

    temp_files = []

    # 1차 Rename
    for image, _, new_name in preview:

        temp_path = image.with_name(
            image.name + ".filmflip_tmp"
        )

        image.rename(temp_path)

        temp_files.append(
            (
                temp_path,
                image.name,
                new_name,
            )
        )

    # 2차 Rename
    for temp_path, _, new_name in temp_files:

        final_path = temp_path.with_name(new_name)

        temp_path.rename(final_path)


def build_undo_list(preview):
    """
    Undo를 위한 정보 생성
    """

    undo = []

    for image, old_name, new_name in preview:

        undo.append(
            (
                new_name,
                old_name,
            )
        )

    return undo


def undo_rename(folder, undo_list):
    """
    마지막 Rename 되돌리기
    """

    folder = Path(folder)

    temp_files = []

    for current_name, old_name in undo_list:

        current_path = folder / current_name

        if not current_path.exists():
            continue

        temp_path = folder / (current_name + ".filmflip_tmp")

        current_path.rename(temp_path)

        temp_files.append(
            (
                temp_path,
                old_name,
            )
        )

    for temp_path, old_name in temp_files:

        final_path = folder / old_name

        temp_path.rename(final_path)
