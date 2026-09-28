"""render_storyboard.py の偽クライアントテスト。"""

import json
from pathlib import Path
from types import SimpleNamespace

import render_storyboard
from src.comfyui_client import ComfyUIConnectionError


def _write_run(parent: Path, number: int) -> Path:
    run = parent / f"run_{number:03d}"
    run.mkdir()
    (run / "metadata.json").write_text("{}", encoding="utf-8")
    (run / "story.md").write_text("# 作品\n本文", encoding="utf-8")
    return run


def _write_shots(run: Path, count: int = 2) -> None:
    storyboard = run / "storyboard"
    storyboard.mkdir()
    shots = [
        {
            "id": f"{index:02d}",
            "title_ja": f"場面{index}",
            "prompt_en": f"frame {index}",
        }
        for index in range(1, count + 1)
    ]
    (storyboard / "shots.json").write_text(
        json.dumps({"title": "作品", "unit": "stage", "shots_per_unit": 1, "style": "style", "shots": shots}),
        encoding="utf-8",
    )


def test_selects_run_and_batch_ranges(tmp_path):
    batch = tmp_path / "batch"
    batch.mkdir()
    for number in (1, 2, 3, 4):
        _write_run(batch, number)

    assert [run.name for run in render_storyboard._select_runs(batch / "run_002", None)] == ["run_002"]
    selected = render_storyboard._select_runs(batch, "1,3-4")
    assert [run.name for run in selected] == ["run_001", "run_003", "run_004"]


def test_shots_only_does_not_create_comfy_client(tmp_path, monkeypatch):
    batch = tmp_path / "batch"
    batch.mkdir()
    run = _write_run(batch, 1)
    events = []

    class FakeLLM:
        pass

    monkeypatch.setattr(render_storyboard, "create_provider_client", lambda *args: (FakeLLM(), "fake"))
    monkeypatch.setattr(
        render_storyboard,
        "build_shot_list",
        lambda run_dir, client, **_kwargs: events.append(("shots", run_dir, client))
        or SimpleNamespace(shots=[{"id": "01", "prompt_en": "frame"}]),
    )
    monkeypatch.setattr(render_storyboard, "ComfyUIImageGenerator", lambda **_kwargs: (_ for _ in ()).throw(AssertionError()))

    assert render_storyboard.main([str(run), "--shots-only"]) == 0
    assert events[0][0] == "shots"
    assert events[0][2] is not None


def test_images_only_skips_llm_and_existing_image_unless_force(tmp_path, monkeypatch):
    run = _write_run(tmp_path, 1)
    _write_shots(run, 1)
    image = run / "storyboard" / "shot_01.png"
    image.write_bytes(b"old")
    (run / "storyboard" / "render_manifest.json").write_text(
        json.dumps(
            {
                "shots": [
                    {
                        "id": "01",
                        "prompt": "frame 1",
                        "status": "success",
                        "success": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    calls = []

    class FakeComfy:
        def __init__(self, **_kwargs):
            pass

        def check_connection(self):
            pass

        def generate(self, _prompt, output_dir, stem, seed=None):
            calls.append((stem, seed))
            (output_dir / f"{stem}.png").write_bytes(b"new")
            return SimpleNamespace(path=output_dir / f"{stem}.png", seed=seed or 9)

        def free_memory(self):
            pass

    monkeypatch.setattr(render_storyboard, "create_provider_client", lambda *_args: (_ for _ in ()).throw(AssertionError()))
    monkeypatch.setattr(render_storyboard, "load_storyboard_profile", lambda _name: {"name": "fake", "width": 720, "height": 400, "workflow_path": "workflow.json", "model_files": []})
    monkeypatch.setattr(render_storyboard, "ComfyUIImageGenerator", FakeComfy)

    assert render_storyboard.main([str(run), "--images-only"]) == 0
    assert calls == []
    assert render_storyboard.main([str(run), "--images-only", "--force"]) == 0
    assert calls == [("shot_01", None)]


def test_changed_prompt_regenerates_and_manifest_matches_by_shot_id(tmp_path, monkeypatch):
    run = _write_run(tmp_path, 1)
    _write_shots(run, 2)
    storyboard = run / "storyboard"
    (storyboard / "shot_01.png").write_bytes(b"old-1")
    (storyboard / "shot_02.png").write_bytes(b"old-2")
    (storyboard / "render_manifest.json").write_text(
        json.dumps(
            {
                "shots": [
                    {"id": "01", "prompt": "frame 1", "status": "success"},
                    {"id": "02", "prompt": "frame 2", "status": "success"},
                ]
            }
        ),
        encoding="utf-8",
    )
    (storyboard / "shots.json").write_text(
        json.dumps(
            {
                "title": "作品",
                "unit": "stage",
                "shots_per_unit": 1,
                "style": "style",
                "shots": [
                    {"id": "02", "prompt_en": "frame 2"},
                    {"id": "01", "prompt_en": "changed frame 1"},
                ],
            }
        ),
        encoding="utf-8",
    )
    calls = []

    class FakeComfy:
        def __init__(self, **_kwargs):
            pass

        def check_connection(self):
            pass

        def generate(self, _prompt, output_dir, stem, seed=None):
            calls.append(stem)
            (output_dir / f"{stem}.png").write_bytes(b"new")
            return SimpleNamespace(path=output_dir / f"{stem}.png", seed=seed)

        def free_memory(self):
            pass

    monkeypatch.setattr(render_storyboard, "load_storyboard_profile", lambda _name: {"name": "fake", "width": 720, "height": 400, "workflow_path": "workflow.json", "model_files": []})
    monkeypatch.setattr(render_storyboard, "ComfyUIImageGenerator", FakeComfy)

    assert render_storyboard.main([str(run), "--images-only"]) == 0
    assert calls == ["shot_01"]
    manifest = json.loads((storyboard / "render_manifest.json").read_text(encoding="utf-8"))
    assert [(entry["id"], entry["status"]) for entry in manifest["shots"]] == [
        ("02", "skipped"),
        ("01", "success"),
    ]


def test_comfyui_url_uses_environment_default(monkeypatch):
    monkeypatch.setenv("COMFYUI_URL", "http://127.0.0.1:9999")
    args = render_storyboard._make_parser().parse_args(["run_001"])
    assert args.comfyui_url == "http://127.0.0.1:9999"


def test_seed_is_deterministic_and_one_failure_continues(tmp_path, monkeypatch):
    run = _write_run(tmp_path, 1)
    _write_shots(run, 2)
    calls = []

    class FakeComfy:
        def __init__(self, **_kwargs):
            pass

        def check_connection(self):
            pass

        def generate(self, _prompt, output_dir, stem, seed=None):
            calls.append((stem, seed))
            if stem == "shot_01":
                raise RuntimeError("fake image error")
            (output_dir / f"{stem}.png").write_bytes(b"PNG")
            return SimpleNamespace(path=output_dir / f"{stem}.png", seed=seed)

        def free_memory(self):
            pass

    monkeypatch.setattr(render_storyboard, "load_storyboard_profile", lambda _name: {"name": "fake", "width": 720, "height": 400, "workflow_path": "workflow.json", "model_files": []})
    monkeypatch.setattr(render_storyboard, "ComfyUIImageGenerator", FakeComfy)

    assert render_storyboard.main([str(run), "--images-only", "--seed", "42"]) == 1
    manifest = json.loads((run / "storyboard" / "render_manifest.json").read_text(encoding="utf-8"))
    assert [entry["status"] for entry in manifest["shots"]] == ["failed", "success"]
    expected = render_storyboard._derive_seed(42, run, "01")
    assert calls[0] == ("shot_01", expected)
    assert manifest["shots"][0]["error"] == "fake image error"


def test_ollama_release_happens_before_comfy(tmp_path, monkeypatch):
    run = _write_run(tmp_path, 1)
    events = []

    class FakeLLM:
        def release_model(self):
            events.append("release")

    class FakeComfy:
        def __init__(self, **_kwargs):
            events.append("init")

        def check_connection(self):
            events.append("check")

        def generate(self, _prompt, output_dir, stem, seed=None):
            events.append("generate")
            (output_dir / f"{stem}.png").write_bytes(b"PNG")
            return SimpleNamespace(path=output_dir / f"{stem}.png", seed=seed)

        def free_memory(self):
            events.append("free")

    monkeypatch.setattr(render_storyboard, "create_provider_client", lambda *_args: (FakeLLM(), "fake-model"))
    monkeypatch.setattr(
        render_storyboard,
        "build_shot_list",
        lambda run_dir, client, **_kwargs: SimpleNamespace(shots=[{"id": "01", "prompt_en": "frame"}]),
    )
    monkeypatch.setattr(render_storyboard, "load_storyboard_profile", lambda _name: {"name": "fake", "width": 720, "height": 400, "workflow_path": "workflow.json", "model_files": []})
    monkeypatch.setattr(render_storyboard, "ComfyUIImageGenerator", FakeComfy)

    assert render_storyboard.main([str(run)]) == 0
    assert events.index("release") < events.index("init") < events.index("check")


def test_connection_failure_is_actionable_and_does_not_free_memory(
    tmp_path, monkeypatch, capsys
):
    run = _write_run(tmp_path, 1)
    _write_shots(run, 1)
    events = []

    class FakeComfy:
        def __init__(self, **_kwargs):
            pass

        def check_connection(self):
            events.append("check")
            raise ComfyUIConnectionError("offline")

        def free_memory(self):
            events.append("free")

    monkeypatch.setattr(render_storyboard, "load_storyboard_profile", lambda _name: {"name": "fake", "width": 720, "height": 400, "workflow_path": "workflow.json", "model_files": []})
    monkeypatch.setattr(render_storyboard, "ComfyUIImageGenerator", FakeComfy)

    assert render_storyboard.main([str(run), "--images-only"]) == 1
    assert events == ["check"]
    assert "100-times-ai-heroes の python3 run_local.py 等で ComfyUI を起動してください。" in capsys.readouterr().err


def test_free_memory_failure_is_only_a_warning(tmp_path, monkeypatch, capsys):
    run = _write_run(tmp_path, 1)
    _write_shots(run, 1)

    class FakeComfy:
        def __init__(self, **_kwargs):
            pass

        def check_connection(self):
            pass

        def generate(self, _prompt, output_dir, stem, seed=None):
            (output_dir / f"{stem}.png").write_bytes(b"PNG")
            return SimpleNamespace(path=output_dir / f"{stem}.png", seed=seed)

        def free_memory(self):
            raise RuntimeError("free failed")

    monkeypatch.setattr(render_storyboard, "load_storyboard_profile", lambda _name: {"name": "fake", "width": 720, "height": 400, "workflow_path": "workflow.json", "model_files": []})
    monkeypatch.setattr(render_storyboard, "ComfyUIImageGenerator", FakeComfy)

    assert render_storyboard.main([str(run), "--images-only"]) == 0
    assert "ComfyUIのメモリ解放に失敗しました" in capsys.readouterr().err
