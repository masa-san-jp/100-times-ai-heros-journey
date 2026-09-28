"""ストーリーボードシートとMarkdownのテスト。"""

from pathlib import Path

import pytest

from src import storyboard_sheet


def _shot_list():
    return {
        "title": "作品タイトル",
        "unit": "chapter",
        "shots": [
            {
                "id": "01",
                "chapter": 1,
                "title_ja": "長い場面のタイトル",
                "caption_ja": "これはラベル帯で折り返される説明文です。",
                "characters": ["protagonist"],
                "camera": "wide shot",
            },
            {
                "id": "02",
                "chapter": 2,
                "title_ja": "未生成の場面",
                "caption_ja": "まだ画像がありません。",
                "characters": [],
                "camera": "close-up",
            },
            {
                "id": "03",
                "chapter": 3,
                "title_ja": "3番目",
                "caption_ja": "3番目の説明",
                "characters": [],
                "camera": "medium shot",
            },
        ],
    }


def _write_image(path: Path, color=(20, 40, 60)):
    pytest.importorskip("PIL")
    from PIL import Image

    image = Image.new("RGB", (720, 400), color)
    image.save(path)
    image.close()


def test_sheet_dimensions_and_missing_shot(tmp_path):
    pytest.importorskip("PIL")
    run = tmp_path / "run_001"
    storyboard = run / "storyboard"
    storyboard.mkdir(parents=True)
    _write_image(storyboard / "shot_01.png")
    _write_image(storyboard / "shot_03.png", (70, 80, 90))

    sheet_path = storyboard_sheet.create_storyboard_sheet(run, _shot_list(), columns=2)

    assert sheet_path is not None
    pytest.importorskip("PIL")
    from PIL import Image

    with Image.open(sheet_path) as sheet:
        assert sheet.size == (2 * storyboard_sheet.IMAGE_WIDTH, storyboard_sheet.TITLE_HEIGHT + 2 * (storyboard_sheet.IMAGE_HEIGHT + storyboard_sheet.LABEL_HEIGHT))
        assert sheet.getpixel((storyboard_sheet.IMAGE_WIDTH + 10, storyboard_sheet.TITLE_HEIGHT + 10)) == (208, 208, 208)


def test_source_images_are_not_modified(tmp_path):
    pytest.importorskip("PIL")
    run = tmp_path / "run_001"
    storyboard = run / "storyboard"
    storyboard.mkdir(parents=True)
    image_path = storyboard / "shot_01.png"
    _write_image(image_path)
    before = image_path.read_bytes()

    storyboard_sheet.create_storyboard_sheet(run, _shot_list(), columns=2)

    assert image_path.read_bytes() == before


def test_markdown_is_written_when_pillow_is_unavailable(tmp_path, monkeypatch):
    run = tmp_path / "run_001"
    (run / "storyboard").mkdir(parents=True)
    monkeypatch.setattr(storyboard_sheet, "_load_pillow", lambda: None)

    markdown_path, sheet_path = storyboard_sheet.write_storyboard_outputs(run, _shot_list())

    assert markdown_path.exists()
    assert sheet_path is None
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "未生成" in markdown
    assert "shot_01.png" not in markdown
    assert "章番号: 1 (章)" in markdown
