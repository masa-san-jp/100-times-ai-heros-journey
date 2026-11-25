"""複数バッチ比較のテスト（LLMは使わない）。"""

import json

import pytest

from src.batch_analyzer import BatchAnalysisError
from src.batch_comparison import REPORT_JSON, REPORT_MD, compare_batches

NARRATIVE = {"loss": "安心できる場所", "desire": "尊敬されたい"}


def _write_batch(tmp_path, name, manifest, works, narrative=NARRATIVE):
    batch = tmp_path / name
    batch.mkdir()
    (batch / "batch_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )
    if narrative is not None:
        (batch / "narrative.json").write_text(
            json.dumps(narrative, ensure_ascii=False), encoding="utf-8"
        )
    for number, (title, plot_type, chapters, want) in enumerate(works, start=1):
        run = batch / f"run_{number:03d}"
        run.mkdir()
        (run / "metadata.json").write_text(
            json.dumps(
                {
                    "title": title,
                    "plot_type": {"name": plot_type},
                    "chapter_count": chapters,
                    "character_names": {"protagonist": f"主人公{number}"},
                    "selected_elements": {
                        "want": want, "ability": "共感", "role": "孤独", "narrative": "対話",
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (run / f"story_{number}.md").write_text(f"# {title}\n\n本文。", encoding="utf-8")
    return batch


def _two_batches(tmp_path, narrative_b=NARRATIVE):
    journey = _write_batch(
        tmp_path,
        "batch_journey",
        # structure を持たない旧バッチは journey_stage_count から構造を読む
        {"model": "m1", "journey_stage_count": 12},
        [("旅の作品", "旅", 10, "居場所"), ("旅の作品2", "旅", 10, "名声")],
    )
    kishotenketsu = _write_batch(
        tmp_path,
        "batch_kishotenketsu",
        {"model": "m1", "structure": "kishotenketsu-4", "journey_stage_count": 4},
        [("起承転結の作品", "再生", 4, "居場所")],
        narrative=narrative_b,
    )
    return journey, kishotenketsu


def test_compare_batches_writes_side_by_side_report(tmp_path):
    journey, kishotenketsu = _two_batches(tmp_path)
    out = tmp_path / "comparison"

    report = compare_batches([journey, kishotenketsu], output_dir=out)

    assert report["same_narrative"] is True
    first, second = report["batches"]
    assert (first["structure"], first["stage_count"], first["work_count"]) == ("journey-12", 12, 2)
    assert (second["structure"], second["stage_count"], second["work_count"]) == (
        "kishotenketsu-4", 4, 1,
    )
    assert second["stage_names"] == ["起", "承", "転", "結"]
    assert first["average_chapter_count"] == 10
    assert report["element_frequencies"]["want"][0] == {"value": "居場所", "counts": [1, 1]}

    markdown = (out / REPORT_MD).read_text(encoding="utf-8")
    assert "| 構造 | journey-12（ヒーローズ・ジャーニー） | kishotenketsu-4（起承転結） |" in markdown
    assert "| 段数 | 12 | 4 |" in markdown
    assert "起 → 承 → 転 → 結" in markdown
    assert "](../batch_kishotenketsu/run_001/story_1.md)" in markdown
    assert json.loads((out / REPORT_JSON).read_text(encoding="utf-8"))["batches"][1]["name"] == (
        "batch_kishotenketsu"
    )


def test_compare_batches_rejects_different_narratives_unless_allowed(tmp_path):
    journey, other = _two_batches(tmp_path, narrative_b={"loss": "別の喪失"})

    with pytest.raises(BatchAnalysisError, match="allow-different-narratives"):
        compare_batches([journey, other], output_dir=tmp_path / "out")
    assert not (tmp_path / "out").exists()

    report = compare_batches(
        [journey, other], output_dir=tmp_path / "out", allow_different_narratives=True
    )
    assert report["same_narrative"] is False
    assert "一致しない" in (tmp_path / "out" / REPORT_MD).read_text(encoding="utf-8")


def test_compare_batches_needs_two_distinct_batches_with_runs(tmp_path):
    journey, _ = _two_batches(tmp_path)
    empty = tmp_path / "batch_empty"
    empty.mkdir()

    with pytest.raises(BatchAnalysisError, match="2つ以上"):
        compare_batches([journey])
    with pytest.raises(BatchAnalysisError, match="重複"):
        compare_batches([journey, journey])
    with pytest.raises(BatchAnalysisError, match="完了済みrunが0件"):
        compare_batches([journey, empty], output_dir=tmp_path / "out")


def test_single_batch_analysis_is_unchanged_by_comparison(tmp_path):
    from src.batch_analyzer import analyze_batch

    journey, kishotenketsu = _two_batches(tmp_path)
    before = analyze_batch(journey, no_llm=True)
    compare_batches([journey, kishotenketsu], output_dir=tmp_path / "out")
    after = analyze_batch(journey, no_llm=True)

    assert after == before
    assert not (journey / REPORT_MD).exists()
