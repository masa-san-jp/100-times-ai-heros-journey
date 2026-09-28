"""ストーリーボードのMarkdownと一覧シートを出力する。"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Iterable, List, Mapping, Optional, Tuple


IMAGE_WIDTH = 720
IMAGE_HEIGHT = 400
DEFAULT_COLUMNS = 2
MAX_SHEET_WIDTH = 2400
LABEL_HEIGHT = 104
TITLE_HEIGHT = 72

_MACOS_FONTS = (
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/ヒラギノ丸ゴ ProN W4.otf",
)
_LINUX_FONTS = (
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.otf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.otf",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
)


def _load_pillow() -> Optional[Tuple[Any, Any, Any]]:
    """Pillowを遅延importし、画像機能だけを任意依存にする。"""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print(
            "警告: Pillowをimportできないため、storyboard_sheet.pngをスキップします。"
            " requirements-image.txtをインストールしてください。",
            file=sys.stderr,
        )
        return None
    return Image, ImageDraw, ImageFont


def _font_candidates() -> Iterable[str]:
    configured = os.getenv("LABEL_FONT_PATH", "").strip()
    if configured:
        yield configured
    yield from _MACOS_FONTS
    yield from _LINUX_FONTS


def _load_font(
    image_font: Any, size: int, candidates: Iterable[str]
) -> Tuple[Any, bool]:
    for candidate in candidates:
        try:
            return image_font.truetype(candidate, size=size), False
        except (OSError, ValueError):
            continue
    print(
        "警告: 日本語フォントが見つからないため、既定フォントでシートを生成します。",
        file=sys.stderr,
    )
    return image_font.load_default(), True


def _display_text(text: str, fallback: bool) -> str:
    if not fallback:
        return text
    return text.encode("ascii", "replace").decode("ascii")


def _text_bbox(draw: Any, text: str, font: Any, fallback: bool) -> Tuple[int, int, int, int]:
    return draw.textbbox((0, 0), _display_text(text, fallback), font=font)


def _wrap_text(
    draw: Any,
    text: str,
    font: Any,
    fallback: bool,
    available_width: int,
    max_lines: int,
) -> List[str]:
    text = str(text).strip()
    if not text:
        return []
    lines: List[str] = []
    current = ""
    for character in text:
        candidate = current + character
        left, _top, right, _bottom = _text_bbox(draw, candidate, font, fallback)
        if current and right - left > available_width:
            lines.append(current)
            current = character
        else:
            current = candidate
    if current:
        lines.append(current)
    if len(lines) <= max_lines:
        return lines

    lines = lines[:max_lines]
    last = lines[-1]
    while last and _text_bbox(draw, last + "…", font, fallback)[2] > available_width:
        last = last[:-1]
    lines[-1] = (last + "…") if last else "…"
    return lines


def _shot_value(shot_list: Any, key: str, default: Any = "") -> Any:
    if isinstance(shot_list, Mapping):
        return shot_list.get(key, default)
    return getattr(shot_list, key, default)


def _shots(shot_list: Any) -> List[Mapping[str, Any]]:
    return [shot for shot in _shot_value(shot_list, "shots", []) if isinstance(shot, Mapping)]


def _shot_id(index: int, shot: Mapping[str, Any]) -> str:
    return str(shot.get("id") or f"{index + 1:02d}")


def _title(run_dir: Path, shot_list: Any) -> str:
    title = str(_shot_value(shot_list, "title", "")).strip()
    if title:
        return title
    for path in sorted(run_dir.glob("*.md")):
        try:
            body = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        first_line = body.lstrip("\ufeff").splitlines()[0] if body.splitlines() else ""
        match = re.match(r"^\s*#\s+(.+?)\s*$", first_line)
        if match:
            return match.group(1).strip()
    return "無題"


def _image_is_generated(run_dir: Path, shot: Mapping[str, Any], index: int) -> bool:
    if shot.get("status") == "failed":
        return False
    shot_id = _shot_id(index, shot)
    image_path = run_dir / "storyboard" / f"shot_{shot_id}.png"
    if not image_path.exists():
        return False
    manifest_path = run_dir / "storyboard" / "render_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return True
    if not isinstance(manifest, Mapping):
        return True
    for entry in manifest.get("shots", []):
        if isinstance(entry, Mapping) and str(entry.get("id")) == shot_id:
            return entry.get("status") in ("success", "skipped")
    return True


def write_storyboard_markdown(run_dir: str | Path, shot_list: Any) -> Path:
    """画像の有無にかかわらず、Markdown形式の絵コンテを保存する。"""
    run_path = Path(run_dir)
    storyboard_dir = run_path / "storyboard"
    storyboard_dir.mkdir(parents=True, exist_ok=True)
    title = _title(run_path, shot_list)
    unit = str(_shot_value(shot_list, "unit", "chapter"))
    lines = [f"# ストーリーボード: {title}", ""]
    for index, shot in enumerate(_shots(shot_list)):
        shot_id = _shot_id(index, shot)
        shot_title = str(shot.get("title_ja", "")).strip() or "（無題のショット）"
        image_name = f"shot_{shot_id}.png"
        lines.extend([f"## {shot_id}. {shot_title}", ""])
        if _image_is_generated(run_path, shot, index):
            lines.extend([f"![{image_name}]({image_name})", ""])
        else:
            lines.extend(["未生成", ""])
        chapter_number = shot.get("chapter", shot.get("stage", ""))
        chapter_label = "章" if unit == "chapter" else "段階"
        characters = shot.get("characters", [])
        if isinstance(characters, (list, tuple)):
            character_text = ", ".join(str(item) for item in characters) or "なし"
        else:
            character_text = str(characters or "なし")
        lines.extend(
            [
                f"- 章番号: {chapter_number} ({chapter_label})",
                f"- キャプション: {shot.get('caption_ja', '')}",
                f"- 登場人物: {character_text}",
                f"- カメラ: {shot.get('shot_size', '')} / {shot.get('camera', '')}",
                "",
            ]
        )
    path = storyboard_dir / "storyboard.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def create_storyboard_sheet(
    run_dir: str | Path, shot_list: Any, columns: int = DEFAULT_COLUMNS
) -> Optional[Path]:
    """ショット画像をラベル付きのシートにまとめる。Pillowがなければ省略する。"""
    if not isinstance(columns, int) or isinstance(columns, bool) or columns < 1:
        raise ValueError("sheet columns must be a positive integer")
    pillow = _load_pillow()
    if pillow is None:
        return None
    image_module, image_draw, image_font = pillow
    run_path = Path(run_dir)
    shots = _shots(shot_list)
    rows = max(1, (len(shots) + columns - 1) // columns)
    scale = min(1.0, MAX_SHEET_WIDTH / (columns * IMAGE_WIDTH))
    cell_width = max(1, round(IMAGE_WIDTH * scale))
    cell_height = max(1, round(IMAGE_HEIGHT * scale))
    label_height = max(48, round(LABEL_HEIGHT * scale))
    title_height = max(48, round(TITLE_HEIGHT * scale))
    sheet = image_module.new(
        "RGB", (cell_width * columns, title_height + rows * (cell_height + label_height)), "white"
    )
    draw = image_draw.Draw(sheet)
    candidates = tuple(_font_candidates())
    title_font, title_fallback = _load_font(
        image_font, max(14, round(30 * scale)), candidates
    )
    title = _title(run_path, shot_list)
    draw.text(
        (round(20 * scale), round(14 * scale)),
        _display_text(title, title_fallback),
        fill="black",
        font=title_font,
    )

    label_font, label_fallback = _load_font(
        image_font, max(10, round(20 * scale)), candidates
    )
    line_height = max(12, round(25 * scale))
    for index, shot in enumerate(shots):
        row, column = divmod(index, columns)
        x = column * cell_width
        y = title_height + row * (cell_height + label_height)
        generated = _image_is_generated(run_path, shot, index)
        source = run_path / "storyboard" / f"shot_{_shot_id(index, shot)}.png"
        if generated:
            try:
                with image_module.open(source) as opened:
                    image = opened.convert("RGB")
                    image.thumbnail((cell_width, cell_height), image_module.Resampling.LANCZOS)
                    frame = image_module.new("RGB", (cell_width, cell_height), "white")
                    frame.paste(
                        image,
                        ((cell_width - image.width) // 2, (cell_height - image.height) // 2),
                    )
                    image.close()
            except (OSError, ValueError):
                generated = False
        if not generated:
            frame = image_module.new("RGB", (cell_width, cell_height), "#d0d0d0")
            missing_font, missing_fallback = _load_font(
                image_font, max(12, round(24 * scale)), candidates
            )
            missing_text = _display_text("未生成", missing_fallback)
            box = draw.textbbox((0, 0), missing_text, font=missing_font)
            image_draw.Draw(frame).text(
                ((cell_width - (box[2] - box[0])) // 2, (cell_height - (box[3] - box[1])) // 2 - box[1]),
                missing_text,
                fill="#666666",
                font=missing_font,
            )
        sheet.paste(frame, (x, y))
        frame.close()

        label_draw = image_draw.Draw(sheet)
        label_draw.rectangle(
            (x, y + cell_height, x + cell_width, y + cell_height + label_height),
            fill="#f4f4f4",
        )
        shot_id = _shot_id(index, shot)
        heading = f"shot_{shot_id}  {shot.get('title_ja', '')}".strip()
        caption = str(shot.get("caption_ja", "")).strip()
        available_width = max(1, cell_width - max(12, round(16 * scale)))
        label_lines = _wrap_text(
            label_draw,
            heading,
            label_font,
            label_fallback,
            available_width,
            1,
        )
        label_lines.extend(
            _wrap_text(
                label_draw,
                caption,
                label_font,
                label_fallback,
                available_width,
                max(1, (label_height // line_height) - len(label_lines)),
            )
        )
        label_lines = label_lines[: max(1, label_height // line_height)]
        text_y = y + cell_height + max(4, round(8 * scale))
        for line in label_lines:
            label_draw.text(
                (x + max(8, round(8 * scale)), text_y),
                _display_text(line, label_fallback),
                fill="black",
                font=label_font,
            )
            text_y += line_height

    storyboard_dir = run_path / "storyboard"
    storyboard_dir.mkdir(parents=True, exist_ok=True)
    path = storyboard_dir / "storyboard_sheet.png"
    try:
        sheet.save(path, format="PNG")
    finally:
        sheet.close()
    return path


def write_storyboard_outputs(
    run_dir: str | Path, shot_list: Any, columns: int = DEFAULT_COLUMNS
) -> Tuple[Path, Optional[Path]]:
    """Markdownを必ず出力し、Pillowが使える場合だけシートも出力する。"""
    markdown_path = write_storyboard_markdown(run_dir, shot_list)
    sheet_path = create_storyboard_sheet(run_dir, shot_list, columns)
    return markdown_path, sheet_path


__all__ = [
    "DEFAULT_COLUMNS",
    "IMAGE_HEIGHT",
    "IMAGE_WIDTH",
    "MAX_SHEET_WIDTH",
    "create_storyboard_sheet",
    "write_storyboard_markdown",
    "write_storyboard_outputs",
]
