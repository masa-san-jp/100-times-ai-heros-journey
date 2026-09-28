"""ComfyUI クライアントの偽 API テスト。"""

import json
from pathlib import Path

import pytest

from src.comfyui_client import (
    ComfyUIConfigurationError,
    ComfyUIError,
    ComfyUITimeoutError,
    ComfyUIImageGenerator,
    load_storyboard_profile,
)
from tools import storyboard_smoke


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / "config/comfyui/storyboard_qwen_image_2_1_turbo_api_workflow.json"
REFERENCE_WORKFLOW = ROOT / "config/comfyui/storyboard_qwen_image_2_1_turbo_reference_api_workflow.json"
MODEL_FILES = load_storyboard_profile()["model_files"]


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
        self.closed = False

    def read(self):
        return self.payload if isinstance(self.payload, bytes) else json.dumps(self.payload).encode()

    def close(self):
        self.closed = True


def make_generator(opener, **kwargs):
    return ComfyUIImageGenerator(
        "http://127.0.0.1:8188",
        WORKFLOW,
        model_files=MODEL_FILES,
        opener=opener,
        **kwargs,
    )


def test_non_local_urls_are_rejected():
    for url in ("https://127.0.0.1:8188", "http://192.0.2.1:8188"):
        with pytest.raises(ComfyUIConfigurationError):
            ComfyUIImageGenerator(url, WORKFLOW, model_files=MODEL_FILES)


def test_workflow_injects_prompt_seed_dimensions_and_model_files():
    generator = make_generator(lambda *_args, **_kwargs: None)

    workflow = generator.build_workflow("a test frame", 123, width=720, height=400)

    assert workflow["4"]["inputs"]["prompt"] == "a test frame"
    assert workflow["14"]["inputs"]["noise_seed"] == 123
    assert workflow["5"]["inputs"]["width"] == 720
    assert workflow["5"]["inputs"]["height"] == 400
    assert workflow["1"]["inputs"]["unet_name"] == "qwen_image_2.1_bf16.safetensors"
    assert workflow["10"]["inputs"]["lora_name"] == (
        "Qwen-Image-2.1-viggle-turbo-v0.2.1-6step-lora-r128.safetensors"
    )


def test_reference_workflow_connects_one_or_two_images():
    generator = ComfyUIImageGenerator(
        "http://127.0.0.1:8188",
        WORKFLOW,
        reference_workflow_path=REFERENCE_WORKFLOW,
        reference_encode_resolution=512,
        model_files=MODEL_FILES,
        opener=lambda *_args, **_kwargs: None,
    )

    one = generator.build_workflow(
        "solo",
        1,
        workflow_path=REFERENCE_WORKFLOW,
        reference_images=["protagonist.png"],
    )
    assert one["18"]["inputs"]["images.image_1"] == ["26", 0]
    assert "images.image_2" not in one["18"]["inputs"]
    assert one["18"]["inputs"]["resolution"] == 512

    two = generator.build_workflow(
        "duo",
        2,
        workflow_path=REFERENCE_WORKFLOW,
        reference_images=["protagonist.png", "supporter.png"],
    )
    assert two["18"]["inputs"]["images.image_1"] == ["26", 0]
    assert two["18"]["inputs"]["images.image_2"] == ["27", 0]
    assert two["27"]["inputs"]["image"] == "supporter.png"


def test_missing_required_workflow_node_is_configuration_error(tmp_path):
    payload = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    del payload["10"]
    path = tmp_path / WORKFLOW.name
    path.write_text(json.dumps(payload), encoding="utf-8")
    generator = make_generator(lambda *_args, **_kwargs: None)
    generator.workflow_path = path

    with pytest.raises(ComfyUIConfigurationError, match="node 10"):
        generator.build_workflow("frame", 1)


def test_history_success_downloads_and_saves_image(tmp_path):
    requests = []

    def opener(request, timeout):
        requests.append((request.full_url, timeout))
        if request.full_url.endswith("/prompt"):
            return FakeResponse({"prompt_id": "abc"})
        if "/history/abc" in request.full_url:
            return FakeResponse({"abc": {"status": {"status_str": "success"}, "outputs": {"9": {"images": [{"filename": "x.png"}]}}}})
        return FakeResponse(b"PNG")

    generator = make_generator(opener, seed_factory=lambda: 99)
    result = generator.generate("frame", tmp_path, "one")

    assert result.seed == 99
    assert result.path.read_bytes() == b"PNG"
    assert any(url.endswith("/prompt") for url, _timeout in requests)


def test_generate_uses_explicit_seed_without_seed_factory(tmp_path):
    def opener(request, timeout):
        if request.full_url.endswith("/prompt"):
            return FakeResponse({"prompt_id": "explicit"})
        if "/history/explicit" in request.full_url:
            return FakeResponse({"explicit": {"status": {"status_str": "success"}, "outputs": {"9": {"images": [{"filename": "x.png"}]}}}})
        return FakeResponse(b"PNG")

    generator = make_generator(opener, seed_factory=lambda: pytest.fail("factory must not be called"))
    result = generator.generate("frame", tmp_path, "explicit", seed=123)

    assert result.seed == 123


def test_history_error_raises():
    def opener(request, timeout):
        if request.full_url.endswith("/prompt"):
            return FakeResponse({"prompt_id": "failed"})
        return FakeResponse({"failed": {"status": {"status_str": "error", "messages": ["bad node"]}}})

    generator = make_generator(opener)
    with pytest.raises(ComfyUIError, match="failed"):
        generator.generate("frame", Path("unused"), "one")


def test_history_timeout_uses_injected_clock_and_sleeper():
    current = [0.0]

    def clock():
        return current[0]

    def sleeper(seconds):
        current[0] += seconds

    def opener(request, timeout):
        if request.full_url.endswith("/prompt"):
            return FakeResponse({"prompt_id": "waiting"})
        return FakeResponse({})

    generator = make_generator(
        opener,
        timeout_seconds=2,
        poll_interval_seconds=1,
        clock=clock,
        sleeper=sleeper,
    )
    with pytest.raises(ComfyUITimeoutError):
        generator.generate("frame", Path("unused"), "one")


def test_failed_atomic_save_removes_tmp(tmp_path, monkeypatch):
    generator = make_generator(lambda *_args, **_kwargs: None)
    destination = tmp_path / "one.png"
    temporary = tmp_path / "one.png.tmp"

    def fail_replace(_source, _destination):
        raise OSError("disk full")

    monkeypatch.setattr("src.comfyui_client.os.replace", fail_replace)
    with pytest.raises(ComfyUIError):
        generator._save_image_bytes(b"PNG", tmp_path, "one")
    assert not destination.exists()
    assert not temporary.exists()


def test_invalid_or_unknown_profile_is_configuration_error(tmp_path):
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")
    with pytest.raises(ComfyUIConfigurationError):
        load_storyboard_profile(path=invalid)

    valid = tmp_path / "valid.json"
    valid.write_text(json.dumps({"default_profile": "known", "profiles": {}}), encoding="utf-8")
    with pytest.raises(ComfyUIConfigurationError, match="Unknown"):
        load_storyboard_profile("unknown", valid)


def test_smoke_cli_parses_options_and_calls_fake_client(tmp_path, monkeypatch, capsys):
    calls = {}

    class FakeClient:
        def __init__(self, **kwargs):
            calls["init"] = kwargs
            self.seed_factory = None

        def generate(self, prompt, output_dir, filename_stem, seed=None):
            calls["generate"] = (prompt, output_dir, filename_stem, seed)
            return type("Result", (), {"path": output_dir / "storyboard_smoke.png", "seed": 7})()

    monkeypatch.setattr(storyboard_smoke, "ComfyUIImageGenerator", FakeClient)
    monkeypatch.setattr(
        storyboard_smoke,
        "load_storyboard_profile",
        lambda _name: {
            "width": 720,
            "height": 400,
            "timeout_seconds": 600,
            "workflow_path": "config/comfyui/workflow.json",
            "model_files": [],
        },
    )

    assert storyboard_smoke.main(
        ["--width", "720", "--height", "400", "--seed", "7", "--out", str(tmp_path)]
    ) == 0
    assert calls["init"]["width"] == 720
    assert calls["init"]["height"] == 400
    assert calls["generate"] == (
        storyboard_smoke.DEFAULT_PROMPT,
        tmp_path,
        "storyboard_smoke",
        7,
    )
    assert "seed: 7" in capsys.readouterr().out
