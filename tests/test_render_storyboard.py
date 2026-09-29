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
    error = capsys.readouterr().err
    assert "python setup_storyboard.py" in error
    assert "--comfyui-dir" in error


def test_start_comfyui_never_does_not_start_when_connection_fails(tmp_path, monkeypatch):
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

    class FakeRuntime:
        def __init__(self, *_args, **_kwargs):
            pass

        def start(self):
            events.append("start")

        def stop(self):
            events.append("stop")

    monkeypatch.setattr(render_storyboard, "load_storyboard_profile", lambda _name: {
        "name": "fake", "width": 720, "height": 400,
        "workflow_path": "workflow.json", "model_files": [],
    })
    monkeypatch.setattr(render_storyboard, "ComfyUIImageGenerator", FakeComfy)
    monkeypatch.setattr(render_storyboard.comfyui_runtime, "ComfyUIRuntime", FakeRuntime)

    assert render_storyboard.main([str(run), "--images-only", "--start-comfyui", "never"]) == 1
    assert events == ["check", "stop"]


def test_start_comfyui_auto_starts_and_stops_on_completion(tmp_path, monkeypatch):
    run = _write_run(tmp_path, 1)
    _write_shots(run, 1)
    events = []

    class FakeComfy:
        def __init__(self, **_kwargs):
            self.checks = 0

        def check_connection(self):
            self.checks += 1
            events.append(f"check-{self.checks}")
            if self.checks == 1:
                raise ComfyUIConnectionError("offline")

        def generate(self, _prompt, output_dir, stem, seed=None):
            events.append("generate")
            (output_dir / f"{stem}.png").write_bytes(b"PNG")
            return SimpleNamespace(path=output_dir / f"{stem}.png", seed=seed)

        def free_memory(self):
            events.append("free")

    class FakeRuntime:
        def __init__(self, *_args, **_kwargs):
            pass

        def start(self):
            events.append("start")

        def stop(self):
            events.append("stop")

    monkeypatch.setattr(render_storyboard, "load_storyboard_profile", lambda _name: {
        "name": "fake", "width": 720, "height": 400,
        "workflow_path": "workflow.json", "model_files": [],
    })
    monkeypatch.setattr(render_storyboard, "ComfyUIImageGenerator", FakeComfy)
    monkeypatch.setattr(render_storyboard.comfyui_runtime, "ComfyUIRuntime", FakeRuntime)

    assert render_storyboard.main([str(run), "--images-only", "--start-comfyui", "auto"]) == 0
    assert events == ["check-1", "start", "check-2", "generate", "free", "stop"]


def test_shots_only_and_dry_run_do_not_create_runtime(tmp_path, monkeypatch):
    run = _write_run(tmp_path, 1)
    _write_shots(run, 1)
    monkeypatch.setattr(
        render_storyboard.comfyui_runtime,
        "ComfyUIRuntime",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("runtime started")),
    )
    monkeypatch.setattr(render_storyboard, "write_storyboard_outputs", lambda *args, **kwargs: None)

    assert render_storyboard.main([str(run), "--images-only", "--dry-run"]) == 0
    assert render_storyboard.main([str(run), "--shots-only"]) == 0


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


def test_character_refs_select_zero_one_two_and_reuse_existing(tmp_path, monkeypatch):
    run = _write_run(tmp_path, 1)
    storyboard = run / "storyboard"
    storyboard.mkdir()
    (run / "visual_prompts.md").write_text(
        "\n".join(
            [
                "## protagonist",
                "Age: 22, dark hair. Atmosphere: calm. Lighting: soft.",
                "",
                "## supporter",
                "Age: 24, silver hair. Atmosphere: kind. Lighting: warm.",
            ]
        ),
        encoding="utf-8",
    )
    shots = [
        {"id": "01", "prompt_en": "landscape", "characters": []},
        {"id": "02", "prompt_en": "solo", "characters": ["protagonist"]},
        {"id": "03", "prompt_en": "duo", "characters": ["protagonist", "supporter"]},
    ]
    (storyboard / "shots.json").write_text(json.dumps({"shots": shots}), encoding="utf-8")
    calls = []

    class FakeComfy:
        def __init__(self, **_kwargs):
            pass

        def check_connection(self):
            pass

        def generate(self, prompt, output_dir, stem, seed=None, **kwargs):
            calls.append((prompt, stem, kwargs.get("reference_images")))
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / f"{stem}.png").write_bytes(b"PNG")
            return SimpleNamespace(path=output_dir / f"{stem}.png", seed=seed)

        def free_memory(self):
            pass

    profile = {
        "name": "fake",
        "width": 720,
        "height": 400,
        "workflow_path": "workflow.json",
        "reference_workflow_path": "reference.json",
        "reference_width": 448,
        "reference_height": 768,
        "reference_encode_resolution": 512,
        "model_files": [],
    }
    monkeypatch.setattr(render_storyboard, "load_storyboard_profile", lambda _name: profile)
    monkeypatch.setattr(render_storyboard, "ComfyUIImageGenerator", FakeComfy)

    assert render_storyboard.main([str(run), "--images-only", "--character-refs"]) == 0
    assert [item[1] for item in calls] == ["protagonist", "supporter", "shot_01", "shot_02", "shot_03"]
    assert calls[2][2] is None
    assert [path.name for path in calls[3][2]] == ["protagonist.png"]
    assert [path.name for path in calls[4][2]] == ["protagonist.png", "supporter.png"]
    assert "The protagonist is the person in image 1." in calls[3][0]
    assert "The supporter is the person in image 2." in calls[4][0]
    assert "Atmosphere:" not in calls[0][0]
    assert "Lighting:" not in calls[0][0]
    manifest = json.loads((storyboard / "render_manifest.json").read_text(encoding="utf-8"))
    assert [entry["references"] for entry in manifest["shots"]] == [
        [],
        ["characters/protagonist.png"],
        ["characters/protagonist.png", "characters/supporter.png"],
    ]

    calls.clear()
    assert render_storyboard.main([str(run), "--images-only", "--character-refs"]) == 0
    assert calls == []


def test_character_ref_modes_filter_shots_and_reference_roles(tmp_path, monkeypatch):
    calls = []

    class FakeComfy:
        def __init__(self, **_kwargs):
            pass

        def check_connection(self):
            pass

        def generate(self, _prompt, output_dir, stem, seed=None, **kwargs):
            calls.append((stem, kwargs.get("reference_images")))
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / f"{stem}.png").write_bytes(b"PNG")
            return SimpleNamespace(path=output_dir / f"{stem}.png", seed=seed)

        def free_memory(self):
            pass

    profile = {
        "name": "fake",
        "width": 720,
        "height": 400,
        "workflow_path": "workflow.json",
        "reference_workflow_path": "reference.json",
        "reference_width": 448,
        "reference_height": 768,
        "model_files": [],
    }
    monkeypatch.setattr(render_storyboard, "load_storyboard_profile", lambda _name: profile)
    monkeypatch.setattr(render_storyboard, "ComfyUIImageGenerator", FakeComfy)
    monkeypatch.setattr(render_storyboard, "write_storyboard_outputs", lambda *args, **kwargs: None)

    for mode, option, expected_refs, expected_roles in (
        ("off", ["--character-refs", "off"], [[], [], [], []], []),
        (
            "closeup",
            ["--character-refs", "closeup"],
            [[], ["protagonist.png"], ["supporter.png"], []],
            ["protagonist", "supporter"],
        ),
        (
            "all",
            ["--character-refs", "all"],
            [["protagonist.png"], ["protagonist.png"], ["supporter.png"], ["adversary.png"]],
            ["protagonist", "supporter", "adversary"],
        ),
    ):
        run = _write_run(tmp_path, {"off": 1, "closeup": 2, "all": 3}[mode])
        storyboard = run / "storyboard"
        storyboard.mkdir()
        (run / "visual_prompts.md").write_text(
            "\n".join(
                [
                    "## protagonist",
                    "Age: 22, dark hair.",
                    "",
                    "## supporter",
                    "Age: 24, silver hair.",
                    "",
                    "## adversary",
                    "Age: 30, red hair.",
                ]
            ),
            encoding="utf-8",
        )
        shots = [
            {"id": "01", "prompt_en": "long", "shot_size": "long", "characters": ["protagonist"]},
            {"id": "02", "prompt_en": "medium", "shot_size": "medium", "characters": ["protagonist"]},
            {"id": "03", "prompt_en": "close", "shot_size": "close_up", "characters": ["supporter"]},
            {"id": "04", "prompt_en": "full", "shot_size": "full", "characters": ["adversary"]},
        ]
        (storyboard / "shots.json").write_text(json.dumps({"shots": shots}), encoding="utf-8")
        calls.clear()
        assert render_storyboard.main([str(run), "--images-only", *option]) == 0
        reference_calls = calls[: len(expected_roles)]
        assert [stem for stem, _refs in reference_calls] == expected_roles
        shot_calls = calls[len(expected_roles) :]
        assert [[path.name for path in refs] if refs else [] for _stem, refs in shot_calls] == expected_refs
        manifest = json.loads((storyboard / "render_manifest.json").read_text(encoding="utf-8"))
        assert [entry["shot_size"] for entry in manifest["shots"]] == [
            "long", "medium", "close_up", "full"
        ]
        assert [entry["references_used"] for entry in manifest["shots"]] == [
            bool(refs) for refs in expected_refs
        ]


def test_character_refs_default_and_missing_reference_workflow_warns(tmp_path, monkeypatch, capsys):
    run = _write_run(tmp_path, 1)
    storyboard = run / "storyboard"
    storyboard.mkdir()
    (storyboard / "shots.json").write_text(
        json.dumps(
            {
                "shots": [
                    {"id": "01", "prompt_en": "long", "shot_size": "long", "characters": ["protagonist"]},
                    {"id": "02", "prompt_en": "close", "shot_size": "close_up", "characters": ["protagonist"]},
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

        def generate(self, _prompt, output_dir, stem, seed=None, **kwargs):
            calls.append(kwargs.get("reference_images"))
            (output_dir / f"{stem}.png").write_bytes(b"PNG")
            return SimpleNamespace(path=output_dir / f"{stem}.png", seed=seed)

        def free_memory(self):
            pass

    monkeypatch.setattr(
        render_storyboard,
        "load_storyboard_profile",
        lambda _name: {
            "name": "fake",
            "width": 720,
            "height": 400,
            "workflow_path": "workflow.json",
            "model_files": [],
        },
    )
    monkeypatch.setattr(render_storyboard, "ComfyUIImageGenerator", FakeComfy)
    monkeypatch.setattr(render_storyboard, "write_storyboard_outputs", lambda *args, **kwargs: None)

    args = render_storyboard._make_parser().parse_args([str(run)])
    assert args.character_refs == "closeup"
    assert render_storyboard._make_parser().parse_args(
        [str(run), "--character-refs"]
    ).character_refs == "all"
    assert render_storyboard.main([str(run), "--images-only"]) == 0
    assert calls == [None, None]
    assert "参照workflowがないため、参照なしで続行します" in capsys.readouterr().err
