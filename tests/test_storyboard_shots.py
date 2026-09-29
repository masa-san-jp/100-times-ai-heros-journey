"""ショットリスト生成のテスト。"""

import json
import shutil
from pathlib import Path

import pytest

import src.storyboard as storyboard
from src.storyboard import (
    _build_prompt,
    _parse_plot,
    _plan_stage_for_unit,
    _read_run_input,
    _shot_sizes_for_unit,
    _stage_plan,
    StoryboardError,
    build_shot_list,
)


ROLES = ("protagonist", "messenger", "supporter", "adversary")


def _write_run(tmp_path, chapters=True):
    run = tmp_path / "run_001"
    run.mkdir()
    metadata = {
        "chapter_count": 2 if chapters else 0,
        "character_names": {role: f"{role}名" for role in ROLES},
    }
    (run / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False), encoding="utf-8"
    )
    body = [
        "# テスト作品",
        "",
        "## 登場人物",
        "",
        "## プロット",
        "",
        "1. **日常世界**",
        "日常の説明。",
        "2. **冒険への呼びかけ**",
        "呼びかけの説明。",
    ]
    if chapters:
        body.extend(
            [
                "",
                "# 第1章: はじまり",
                "第1章の本文。",
                "",
                "# 第2章: 変化",
                "第2章の本文。",
                "",
                "## メタ情報",
                "- 総章数: 2章",
            ]
        )
    (run / "story.md").write_text("\n".join(body), encoding="utf-8")
    visual = ["# ビジュアルプロンプト", ""]
    for role in ROLES:
        visual.extend(
            [
                f"## {role}",
                "",
                f"Appearance of {role}. Atmosphere: role mood. Lighting: role light.",
                "",
            ]
        )
    (run / "visual_prompts.md").write_text("\n".join(visual), encoding="utf-8")
    return run


class FakeClient:
    def __init__(self, responses=None):
        self.calls = []
        self.responses = list(responses or [])

    def chat_json(self, prompt, **_kwargs):
        self.calls.append(prompt)
        if self.responses:
            response = self.responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return response
        return {
            "shots": [
                {
                    "title_ja": "場面",
                    "caption_ja": "説明。",
                    "characters": ["protagonist", "unknown", "messenger", "supporter"],
                    "setting": "街、朝、晴れ",
                    "action": "歩く",
                    "camera": "wide shot, low angle",
                    "mood": "golden hour",
                }
            ]
        }


def test_auto_uses_chapters_and_reuses_cache(tmp_path):
    run = _write_run(tmp_path)
    client = FakeClient()

    first = build_shot_list(run, client)
    second = build_shot_list(run, client)

    assert first.unit == "chapter"
    assert len(first.shots) == 2
    assert len(client.calls) == 2
    assert second.shots == first.shots
    assert (run / "storyboard" / "shots.md").exists()


def test_stage_unit_and_refresh(tmp_path):
    run = _write_run(tmp_path, chapters=False)
    client = FakeClient()

    result = build_shot_list(run, client, unit="stage")
    build_shot_list(run, client, unit="stage", refresh=True)

    assert len(result.shots) == 2
    assert result.shots[0]["stage"] == 1
    assert len(client.calls) == 4


def test_auto_uses_plot_stages_without_chapters(tmp_path):
    run = _write_run(tmp_path, chapters=False)
    result = build_shot_list(run, FakeClient())

    assert result.unit == "stage"
    assert len(result.shots) == 2


def test_prompt_is_deterministic_and_roles_are_limited(tmp_path):
    run = _write_run(tmp_path)
    result = build_shot_list(run, FakeClient())
    shot = result.shots[0]

    assert shot["characters"] == ["protagonist", "messenger"]
    assert "The protagonist: Appearance of protagonist." in shot["prompt_en"]
    assert "The messenger: Appearance of messenger." in shot["prompt_en"]
    assert "unknown" not in shot["prompt_en"]
    assert "unknown" not in shot["characters"]
    assert "Character 1:" not in shot["prompt_en"]
    assert "Atmosphere:" not in shot["prompt_en"]
    assert "Lighting:" not in shot["prompt_en"]
    assert "full frame without letterbox bars" in shot["prompt_en"]


def test_rebuild_prompts_does_not_call_llm_or_change_cached_unit(tmp_path):
    run = _write_run(tmp_path)
    build_shot_list(run, FakeClient())
    shots_path = run / "storyboard" / "shots.json"
    cached = json.loads(shots_path.read_text(encoding="utf-8"))
    for shot in cached["shots"]:
        shot.pop("shot_size", None)
        shot.pop("plan_stage", None)
    shots_path.write_text(json.dumps(cached, ensure_ascii=False), encoding="utf-8")

    rebuilt = build_shot_list(
        run,
        None,
        unit="stage",
        style="custom cinematic style",
        rebuild_prompts=True,
    )

    assert rebuilt.unit == "chapter"
    assert rebuilt.shots[0]["prompt_en"].endswith("custom cinematic style")
    assert rebuilt.shots[0]["shot_size"] == "full"
    assert rebuilt.shots[0]["plan_stage"] == 1


def test_chapter_count_mismatch_warns_and_uses_body_chapters(tmp_path, capsys):
    run = _write_run(tmp_path)
    metadata_path = run / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["chapter_count"] = 99
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    result = build_shot_list(run, FakeClient())

    assert len(result.shots) == 2
    assert "一致しません" in capsys.readouterr().err


def test_failed_cached_unit_is_retried_only(tmp_path):
    run = _write_run(tmp_path)
    valid = FakeClient().chat_json("")
    first_client = FakeClient([ValueError("invalid"), ValueError("invalid"), valid])
    first = build_shot_list(run, first_client)
    old_success_id = first.shots[1]["id"]
    assert first.shots[0]["status"] == "failed"

    retry_client = FakeClient([valid])
    retried = build_shot_list(run, retry_client, unit="stage")

    assert len(retry_client.calls) == 1
    assert retried.unit == "chapter"
    assert all(shot.get("status") != "failed" for shot in retried.shots)
    assert retried.shots[1]["id"] == old_success_id


def test_example_run_structure_can_be_read_without_writing_examples(tmp_path):
    source = Path("examples/batch_full-gpt-oss-20b/run_001")
    run = tmp_path / "run_001"
    shutil.copytree(source, run)

    parsed = _read_run_input(run)

    assert len(parsed.chapters) == 10
    assert len(parsed.plot) == 12
    assert len(parsed.visual_prompts) == 4
    assert all(parsed.visual_prompts[role] for role in ROLES)


def test_example_runs_parse_all_twelve_stage_details(tmp_path):
    expected_names = [
        "日常世界",
        "冒険への呼びかけ",
        "拒否",
        "師との出会い",
        "第一関門の突破",
        "試練、仲間、敵",
        "最も危険な場所への接近",
        "最大の試練",
        "報酬",
        "帰路",
        "復活",
        "宝を持ち帰る",
    ]
    for batch_name in (
        "batch_full-gpt-oss-20b",
        "batch_full-qwen3.8-27b",
        "batch_full-gemma4-e4b",
    ):
        source = Path("examples") / batch_name / "run_001"
        run = tmp_path / batch_name / "run_001"
        shutil.copytree(source, run)

        parsed = _read_run_input(run)

        assert len(parsed.plot) == 12
        assert [stage.name for stage in parsed.plot] == expected_names


def test_numbered_plot_outline_is_used_when_details_are_missing():
    body = """# テスト作品

## プロット

【プロットアウトライン】
**【ヒーローズ・ジャーニー12段階プロット】**

1. **日常世界**
日常の説明。
2. **冒険への呼びかけ**
呼びかけの説明。
"""

    parsed = _parse_plot(body)

    assert [stage.name for stage in parsed] == ["日常世界", "冒険への呼びかけ"]


def test_empty_plot_uses_manifest_stage_count_for_chapters_and_rejects_stages(
    tmp_path, capsys
):
    run = _write_run(tmp_path, chapters=True)
    body = """# テスト作品

## プロット

自由記述のプロット本文。

# 第1章: はじまり
第1章の本文。

# 第2章: 変化
第2章の本文。

## メタ情報
"""
    (run / "story.md").write_text(body, encoding="utf-8")
    (tmp_path / "batch_manifest.json").write_text(
        json.dumps({"settings": {"journey_stage_count": 11}}), encoding="utf-8"
    )

    client = FakeClient()
    result = build_shot_list(run, client, unit="chapter")

    assert result.unit == "chapter"
    assert "自由記述のプロット本文。" in client.calls[0]
    assert "プロット全体:\n[]" not in client.calls[0]
    assert "11段階" in capsys.readouterr().err

    (tmp_path / "stage").mkdir()
    stage_run = _write_run(tmp_path / "stage", chapters=True)
    (stage_run / "story.md").write_text(body, encoding="utf-8")
    (stage_run.parent / "batch_manifest.json").write_text(
        json.dumps({"journey_stage_count": 12}), encoding="utf-8"
    )
    with pytest.raises(StoryboardError, match="--unit stage"):
        build_shot_list(stage_run, FakeClient(), unit="stage")


def test_invalid_json_retries_and_failed_is_recorded(tmp_path):
    run = _write_run(tmp_path)
    retry_client = FakeClient([ValueError("invalid"), FakeClient().chat_json("")])
    result = build_shot_list(run, retry_client)
    assert len(retry_client.calls) == 3
    assert all(shot.get("status") != "failed" for shot in result.shots)

    failed_client = FakeClient([ValueError("invalid")] * 4)
    failed = build_shot_list(run, failed_client, refresh=True)
    assert len(failed_client.calls) == 4
    assert all(shot["status"] == "failed" for shot in failed.shots)


def test_shot_plan_has_11_and_12_stage_mappings():
    assert _stage_plan(12) == [
        "extreme_long", "long", "close_up", "full", "long", "medium",
        "extreme_long", "close_up", "full", "long", "close_up", "extreme_long",
    ]
    assert _stage_plan(11) == [
        "extreme_long", "long", "close_up", "full", "long", "medium",
        "close_up", "full", "long", "close_up", "extreme_long",
    ]


def test_chapter_plan_stage_mapping_for_10_12_and_3_chapters():
    assert [_plan_stage_for_unit("chapter", i, 10, 12) for i in range(1, 11)] == [
        1, 2, 4, 5, 6, 7, 8, 10, 11, 12
    ]
    assert [_plan_stage_for_unit("chapter", i, 12, 12) for i in range(1, 13)] == list(range(1, 13))
    assert [_plan_stage_for_unit("chapter", i, 3, 12) for i in range(1, 4)] == [2, 6, 10]


def test_shot_size_distribution_is_wide_for_12_stages_and_10_chapters():
    stage_sizes = _stage_plan(12)
    chapter_stages = [_plan_stage_for_unit("chapter", i, 10, 12) for i in range(1, 11)]
    chapter_sizes = [stage_sizes[stage - 1] for stage in chapter_stages]
    long_sizes = {"extreme_long", "long", "full"}
    close_sizes = {"close_up"}

    assert sum(size in long_sizes for size in stage_sizes) / len(stage_sizes) >= 0.5
    assert sum(size in close_sizes for size in stage_sizes) / len(stage_sizes) <= 0.3
    assert sum(size in long_sizes for size in chapter_sizes) / len(chapter_sizes) >= 0.5
    assert sum(size in close_sizes for size in chapter_sizes) / len(chapter_sizes) <= 0.3


def test_shots_per_unit_alternate_with_adjacent_sizes():
    _plan_stage, sizes = _shot_sizes_for_unit("stage", 6, 12, 12, 4)
    assert sizes == ["medium", "close_up", "full", "close_up"]


def test_prompt_starts_with_size_phrase_and_shortens_distant_appearance():
    visual = {
        "protagonist": (
            "Age: 22, lean muscular build, determined eyes. "
            "Dark brown short hair, slightly tousled. "
            "Wears a tailored charcoal suit with a silver pin. "
            "Atmosphere: calm. Lighting: soft."
        )
    }
    long_prompt = _build_prompt(
        {
            "shot_size": "long",
            "setting": "open valley",
            "action": "the protagonist waits",
            "characters": ["protagonist"],
            "camera": "low angle",
            "mood": "dawn",
        },
        visual,
        "film grain",
    )
    close_prompt = _build_prompt(
        {"shot_size": "close_up", "characters": ["protagonist"]},
        visual,
        "film grain",
    )

    assert long_prompt.startswith(
        "Long shot, the whole environment is visible, figures are small and occupy about one third of the frame height, deep focus"
    )
    assert "Dark brown short hair, slightly tousled." in long_prompt
    assert "Wears a tailored charcoal suit with a silver pin." in long_prompt
    assert "Age: 22, lean muscular build, determined eyes." not in long_prompt
    assert close_prompt.startswith("Close-up on the face, shallow depth of field")
    assert "Age: 22, lean muscular build, determined eyes." in close_prompt

    fallback_prompt = _build_prompt(
        {
            "shot_size": "full",
            "characters": ["protagonist"],
        },
        {"protagonist": "Age: 22. Calm expression. Atmosphere: quiet."},
        "film grain",
    )
    assert "Age: 22. Calm expression." in fallback_prompt


def test_prompt_uses_size_settings_for_order_and_appearance_sentences():
    visual = {
        "protagonist": (
            "Age: 22, lean build, determined eyes. "
            "Dark brown short hair, slightly tousled. "
            "Wears a tailored charcoal suit with a silver pin. "
            "Carries a worn leather satchel."
        )
    }
    shot = {
        "shot_size": "extreme_long",
        "setting": "a vast valley and distant city",
        "action": "the valley stretches toward the horizon",
        "camera": "high angle, 24mm lens",
        "mood": "storm light",
        "characters": ["protagonist"],
    }

    prompt = _build_prompt(shot, visual, "film grain")

    assert prompt.startswith(
        "Extreme long shot, vast establishing view of the environment, human figures are tiny and occupy less than one tenth of the frame height, deep focus"
    )
    assert prompt.index("a vast valley") < prompt.index("Mood and lighting: storm light")
    assert prompt.index("Mood and lighting: storm light") < prompt.index("Camera: high angle")
    assert prompt.index("Camera: high angle") < prompt.index("the valley stretches")
    assert "The protagonist, a tiny distant figure: Wears a tailored charcoal suit" in prompt
    assert "Dark brown short hair" not in prompt
    assert "Age: 22" not in prompt

    medium = _build_prompt({**shot, "shot_size": "medium"}, visual, "film grain")
    assert "Age: 22, lean build, determined eyes." in medium
    assert "Dark brown short hair, slightly tousled." in medium
    assert "Wears a tailored charcoal suit with a silver pin." in medium
    assert "Carries a worn leather satchel." in medium


def test_old_shot_plan_prompt_keeps_legacy_behaviour(monkeypatch):
    monkeypatch.setattr(storyboard, "SHOT_SETTINGS", {})
    monkeypatch.setattr(storyboard, "SHOT_PROMPT_PHRASES", {"long": "Legacy long shot"})

    prompt = _build_prompt(
        {
            "shot_size": "long",
            "setting": "open valley",
            "action": "the protagonist waits",
            "camera": "low angle",
            "mood": "dawn",
            "characters": ["protagonist"],
        },
        {"protagonist": "Dark hair. Wears a dark coat. Age 22."},
        "film grain",
    )

    assert prompt.startswith(
        "Legacy long shot, open valley, the protagonist waits, Camera: low angle, Mood and lighting: dawn"
    )
    assert "The protagonist: Dark hair. Wears a dark coat." in prompt
    assert "tiny distant figure" not in prompt
