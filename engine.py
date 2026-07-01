import os
import re
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

# Windows/macOS 파일명에서 문제가 될 수 있는 문자
_INVALID_FILENAME_CHARS = str.maketrans({
    "/": "",
    "\\": "",
    ":": "",
    "*": "",
    "?": "",
    '"': "",
    "<": "",
    ">": "",
    "|": "",
})

_WHITESPACE_PATTERN = re.compile(r"\s+")


def find_images(folder):
    """
    폴더 안의 이미지 파일을 찾는다.

    v1.1 perf:
    - Path.iterdir() 대신 os.scandir() 사용
      → 폴더 열 때 파일 타입 확인 비용을 줄임
    - macOS 점파일/리소스 포크(._파일) 무시 유지
    - 반환값은 기존과 동일하게 Path 리스트 유지
    """

    folder_path = Path(folder)
    images = []

    try:
        with os.scandir(folder_path) as entries:
            for entry in entries:
                name = entry.name

                if name.startswith("."):
                    continue

                suffix = os.path.splitext(name)[1].lower()
                if suffix not in IMAGE_EXTENSIONS:
                    continue

                try:
                    if not entry.is_file():
                        continue
                except OSError:
                    continue

                images.append(folder_path / name)

    except (FileNotFoundError, NotADirectoryError, PermissionError):
        return []

    images.sort(key=lambda path: path.name.lower())
    return images


def _safe_component(text):
    text = (text or "").strip()
    return text.translate(_INVALID_FILENAME_CHARS).strip()


def _normalize_date(text):
    """
    날짜 입력값은 사용자가 적은 형태를 최대한 유지한다.
    예: 2026-07-01, 2026.07.01, 20260701 모두 그대로 사용
    단, 파일명에서 문제가 되는 문자(/ 등)는 _safe_component에서 제거된다.
    """

    return _safe_component(text)


def _normalize_memo(text):
    """메모는 파일명에서 공백 없이 붙여 쓴다."""

    text = _safe_component(text)
    return _WHITESPACE_PATTERN.sub("", text)


def _make_template(
    template=None,
    date="",
    camera="",
    film="",
    lab="",
    place="",
    scanner="",
    memo="",
):
    if template:
        return template

    parts = [
        _normalize_date(date),
        _safe_component(camera),
        _safe_component(film),
        _safe_component(lab),
        _safe_component(place),
        _safe_component(scanner),
        _normalize_memo(memo),
    ]
    parts = [part for part in parts if part]
    parts.append("{n}")

    return "_".join(parts)


def build_preview(
    images,
    template="{n}",
    reverse=True,
    date="",
    camera="",
    film="",
    lab="",
    place="",
    scanner="",
    memo="",
):
    """
    변경될 파일명 미리보기 생성.

    v1.2:
    - date / scanner / memo 파일명 구성 지원
    - date는 사용자가 입력한 형태를 최대한 유지
    - memo는 공백 제거

    v1.1 perf:
    - 반복문 안에서 자주 쓰는 값은 지역 변수로 고정
    - append 함수 참조를 지역화해서 작은 비용 절감
    - 입력 images가 list/tuple이 아니어도 한 번만 리스트화
    """

    if not isinstance(images, (list, tuple)):
        images = list(images)

    total = len(images)
    digits = 3
    resolved_template = _make_template(
        template=template,
        date=date,
        camera=camera,
        film=film,
        lab=lab,
        place=place,
        scanner=scanner,
        memo=memo,
    )

    preview = []
    append = preview.append
    replace_number = resolved_template.replace

    for index, image in enumerate(images):
        new_number = total - index if reverse else index + 1
        number = f"{new_number:0{digits}d}"
        base_name = replace_number("{n}", number)
        new_name = f"{base_name}{image.suffix.lower()}"

        append((image, image.name, new_name))

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
    append_temp = temp_files.append

    # 1차 Rename
    for image, _, new_name in preview:
        temp_path = image.with_name(image.name + ".filmflip_tmp")
        image.rename(temp_path)
        append_temp((temp_path, image.name, new_name))

    # 2차 Rename
    for temp_path, _, new_name in temp_files:
        final_path = temp_path.with_name(new_name)
        temp_path.rename(final_path)


def build_undo_list(preview):
    """
    Undo를 위한 정보 생성
    """

    return [(new_name, old_name) for _, old_name, new_name in preview]


def undo_rename(folder, undo_list):
    """
    마지막 Rename 되돌리기
    """

    folder = Path(folder)
    temp_files = []
    append_temp = temp_files.append

    for current_name, old_name in undo_list:
        current_path = folder / current_name

        if not current_path.exists():
            continue

        temp_path = folder / (current_name + ".filmflip_tmp")
        current_path.rename(temp_path)
        append_temp((temp_path, old_name))

    for temp_path, old_name in temp_files:
        final_path = folder / old_name
        temp_path.rename(final_path)
