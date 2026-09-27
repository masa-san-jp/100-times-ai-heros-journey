"""ショットリスト生成のテスト。"""

import json
import shutil
from pathlib import Path

from src.storyboard import _read_run_input, build_shot_list


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

    rebuilt = build_shot_list(
        run,
        None,
        unit="stage",
        style="custom cinematic style",
        rebuild_prompts=True,
    )

    assert rebuilt.unit == "chapter"
    assert rebuilt.shots[0]["prompt_en"].endswith("custom cinematic style")


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
