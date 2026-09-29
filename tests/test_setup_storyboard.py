"""setup_storyboard.py の偽ダウンロード・偽コマンドテスト。"""

import hashlib
import json
from types import SimpleNamespace
from pathlib import Path

import pytest

import setup_storyboard


def _profile(*, with_model=True, with_custom_node=True):
    return {
        "license_name": "Test License",
        "license_url": "https://example.invalid/license",
        "license_note": "研究・評価目的のみ",
        "model_files": (
            [
                {
                    "subdir": "diffusion_models",
                    "filename": "model.safetensors",
                    "url": "https://example.invalid/model",
                    "sha256": "expected-model",
                    "size": "1MB",
                }
            ]
            if with_model
            else []
        ),
        "custom_nodes": (
            [
                {
                    "filename": "viggle_turbo.py",
                    "url": "https://example.invalid/node",
                    "sha256": "expected-node",
                }
            ]
            if with_custom_node
            else []
        ),
    }


class _Response:
    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self, _size=-1):
        payload, self.payload = self.payload, b""
        return payload


def _stub_setup(monkeypatch, tmp_path, profile):
    runtime_dir = tmp_path / "runtime"
    monkeypatch.setattr(setup_storyboard, "RUNTIME_DIR", runtime_dir)
    monkeypatch.setattr(setup_storyboard, "_load_profile", lambda _name: profile)
    monkeypatch.setattr(setup_storyboard, "_ensure_comfyui_checkout", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        setup_storyboard,
        "_ensure_comfyui_dependencies",
        lambda path, venv_dir, **_kwargs: venv_dir / "bin" / "python",
    )
    return runtime_dir


def test_existing_hash_skips_and_mismatch_redownloads(tmp_path, monkeypatch):
    destination = tmp_path / "model.bin"
    matching = b"matching"
    destination.write_bytes(matching)
    expected = hashlib.sha256(matching).hexdigest()
    monkeypatch.setattr(
        setup_storyboard.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: pytest.fail("matching file was downloaded"),
    )
    setup_storyboard._download_file("https://example.invalid", destination, expected, label="model")

    replacement = b"replacement"
    monkeypatch.setattr(
        setup_storyboard.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _Response(replacement),
    )
    setup_storyboard._download_file(
        "https://example.invalid",
        destination,
        hashlib.sha256(replacement).hexdigest(),
        label="model",
    )
    assert destination.read_bytes() == replacement
    assert not destination.with_name("model.bin.part").exists()


def test_hash_mismatch_removes_partial_file(tmp_path, monkeypatch):
    destination = tmp_path / "model.bin"
    monkeypatch.setattr(
        setup_storyboard.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _Response(b"wrong"),
    )
    with pytest.raises(setup_storyboard.SetupError, match="SHA256"):
        setup_storyboard._download_file(
            "https://example.invalid", destination, "0" * 64, label="model"
        )
    assert not destination.exists()
    assert not destination.with_name("model.bin.part").exists()


def test_license_rejection_downloads_nothing(tmp_path, monkeypatch):
    profile = _profile()
    runtime_dir = _stub_setup(monkeypatch, tmp_path, profile)
    downloads = []
    monkeypatch.setattr(setup_storyboard, "_download_file", lambda *args, **kwargs: downloads.append(args))
    monkeypatch.setattr(setup_storyboard.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr("builtins.input", lambda _prompt: "n")

    result = setup_storyboard.main(
        [
            "--comfyui-dir",
            str(tmp_path / "ComfyUI"),
            "--comfyui-venv",
            str(tmp_path / "venv"),
        ]
    )
    assert result == 1
    assert downloads == []
    assert not runtime_dir.exists()


def test_command_execution_uses_fake_subprocess(monkeypatch):
    calls = []
    monkeypatch.setattr(
        setup_storyboard.subprocess,
        "run",
        lambda command, **kwargs: calls.append((command, kwargs)),
    )
    setup_storyboard._run(["git", "clone", "--depth", "1"], dry_run=False)
    assert calls == [(["git", "clone", "--depth", "1"], {"cwd": None, "check": True})]


def test_dry_run_does_not_create_files(tmp_path, monkeypatch):
    profile = _profile()
    runtime_dir = _stub_setup(monkeypatch, tmp_path, profile)
    comfyui_dir = tmp_path / "ComfyUI"
    result = setup_storyboard.main(
        ["--comfyui-dir", str(comfyui_dir), "--comfyui-venv", str(tmp_path / "venv"), "--yes", "--dry-run"]
    )
    assert result == 0
    assert not comfyui_dir.exists()
    assert not runtime_dir.exists()


def test_skip_models_downloads_custom_node_only_and_saves_config(tmp_path, monkeypatch):
    profile = _profile()
    runtime_dir = _stub_setup(monkeypatch, tmp_path, profile)
    downloads = []

    def fake_download(url, destination, expected_sha256, **_kwargs):
        downloads.append(destination)

    monkeypatch.setattr(setup_storyboard, "_download_file", fake_download)
    comfyui_dir = tmp_path / "ComfyUI"
    comfyui_venv = tmp_path / "venv"
    assert setup_storyboard.main(
        [
            "--comfyui-dir",
            str(comfyui_dir),
            "--comfyui-venv",
            str(comfyui_venv),
            "--skip-models",
            "--yes",
        ]
    ) == 0
    assert downloads == [comfyui_dir / "custom_nodes" / "viggle_turbo.py"]
    config = json.loads((runtime_dir / "comfyui.json").read_text(encoding="utf-8"))
    assert config == {
        "comfyui_dir": str(comfyui_dir),
        "comfyui_venv": str(comfyui_venv),
        "profile": "qwen-image-2.1-turbo",
    }


def test_darwin_arm64_installs_nightly_before_requirements(tmp_path, monkeypatch):
    commands = []
    python = tmp_path / "venv" / "bin" / "python"
    monkeypatch.setattr(setup_storyboard, "_create_venv", lambda *_args, **_kwargs: python)
    monkeypatch.setattr(setup_storyboard.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(setup_storyboard.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(
        setup_storyboard,
        "_run",
        lambda command, **_kwargs: commands.append([str(item) for item in command]),
    )

    setup_storyboard._ensure_comfyui_dependencies(
        tmp_path / "ComfyUI", tmp_path / "venv", dry_run=False
    )
    nightly_index = next(index for index, command in enumerate(commands) if "torchvision" in command)
    requirements_index = next(
        index
        for index, command in enumerate(commands)
        if any("requirements.txt" in item for item in command)
    )
    assert nightly_index < requirements_index


def test_existing_venv_skips_dependencies_by_default(tmp_path, monkeypatch, capsys):
    venv_dir = tmp_path / "venv"
    python = venv_dir / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        setup_storyboard,
        "_run",
        lambda *_args, **_kwargs: pytest.fail("existing venv dependencies were changed"),
    )

    setup_storyboard._ensure_comfyui_dependencies(
        tmp_path / "ComfyUI", venv_dir, dry_run=False
    )
    assert "existing virtual environment" in capsys.readouterr().out


def test_update_deps_installs_into_existing_venv(tmp_path, monkeypatch):
    venv_dir = tmp_path / "venv"
    python = venv_dir / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    commands = []
    monkeypatch.setattr(setup_storyboard.platform, "system", lambda: "Linux")
    monkeypatch.setattr(setup_storyboard.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(
        setup_storyboard,
        "_run",
        lambda command, **_kwargs: commands.append([str(item) for item in command]),
    )

    setup_storyboard._ensure_comfyui_dependencies(
        tmp_path / "ComfyUI", venv_dir, dry_run=False, update_deps=True
    )
    assert len(commands) == 2
    assert commands[0][0:4] == [str(python), "-m", "pip", "install"]


def test_new_venv_installs_dependencies(tmp_path, monkeypatch):
    venv_dir = tmp_path / "venv"
    python = venv_dir / "bin" / "python"
    commands = []
    monkeypatch.setattr(setup_storyboard.platform, "system", lambda: "Linux")
    monkeypatch.setattr(setup_storyboard.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(setup_storyboard, "_create_venv", lambda *_args, **_kwargs: python)
    monkeypatch.setattr(
        setup_storyboard,
        "_run",
        lambda command, **_kwargs: commands.append([str(item) for item in command]),
    )

    setup_storyboard._ensure_comfyui_dependencies(
        tmp_path / "ComfyUI", venv_dir, dry_run=False
    )
    assert len(commands) == 2
