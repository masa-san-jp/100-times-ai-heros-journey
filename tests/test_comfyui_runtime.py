"""ComfyUI 自動起動の偽HTTP・偽プロセステスト。"""

import json
from pathlib import Path

import pytest

from src import comfyui_runtime


class _Process:
    def __init__(self, events):
        self.events = events
        self.returncode = None

    def poll(self):
        return self.returncode

    def terminate(self):
        self.events.append("terminate")
        self.returncode = 0

    def kill(self):
        self.events.append("kill")
        self.returncode = -9

    def wait(self, timeout=None):
        self.events.append(("wait", timeout))
        return self.returncode


def _runtime_files(tmp_path: Path):
    comfyui_dir = tmp_path / "ComfyUI"
    venv_dir = tmp_path / "venv"
    comfyui_dir.mkdir()
    (comfyui_dir / "main.py").write_text("", encoding="utf-8")
    python = venv_dir / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    config = tmp_path / "comfyui.json"
    config.write_text(
        json.dumps({"comfyui_dir": str(comfyui_dir), "comfyui_venv": str(venv_dir)}),
        encoding="utf-8",
    )
    return config


def test_connected_server_is_not_started_or_stopped(tmp_path, monkeypatch):
    config = _runtime_files(tmp_path)
    events = []
    monkeypatch.setattr(comfyui_runtime, "is_available", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        comfyui_runtime.subprocess,
        "Popen",
        lambda *_args, **_kwargs: pytest.fail("connected server was started"),
    )
    runtime = comfyui_runtime.ComfyUIRuntime(
        "http://127.0.0.1:8188", config_path=config, project_root=tmp_path
    )
    runtime.start()
    runtime.stop()
    assert events == []
    assert not runtime.started_by_us


def test_unconnected_server_starts_with_localhost_options_and_stops(tmp_path, monkeypatch):
    config = _runtime_files(tmp_path)
    events = []
    process = _Process(events)
    availability = iter((False, True))
    monkeypatch.setattr(
        comfyui_runtime,
        "is_available",
        lambda *_args, **_kwargs: next(availability),
    )
    calls = []
    monkeypatch.setattr(
        comfyui_runtime.subprocess,
        "Popen",
        lambda command, **kwargs: calls.append((command, kwargs)) or process,
    )
    runtime = comfyui_runtime.ComfyUIRuntime(
        "http://127.0.0.1:8188", config_path=config, project_root=tmp_path
    )
    runtime.start()
    runtime.stop()
    command, kwargs = calls[0]
    assert command[1:] == [
        "main.py",
        "--listen",
        "127.0.0.1",
        "--port",
        "8188",
        "--disable-api-nodes",
        "--preview-method",
        "none",
    ]
    assert kwargs["cwd"] == str(tmp_path / "ComfyUI")
    assert events[0] == "terminate"


def test_missing_config_has_setup_and_existing_directory_guidance(tmp_path, monkeypatch):
    monkeypatch.setattr(comfyui_runtime, "is_available", lambda *_args, **_kwargs: False)
    runtime = comfyui_runtime.ComfyUIRuntime(
        "http://127.0.0.1:8188", config_path=tmp_path / "missing.json", project_root=tmp_path
    )
    with pytest.raises(comfyui_runtime.ComfyUIRuntimeError) as error:
        runtime.start()
    assert "python setup_storyboard.py" in str(error.value)
    assert "--comfyui-dir" in str(error.value)
    assert "100-times-ai-heroes" not in str(error.value)


def test_start_exception_stops_process_and_timeout_stops_process(tmp_path, monkeypatch):
    config = _runtime_files(tmp_path)
    events = []
    process = _Process(events)
    monkeypatch.setattr(comfyui_runtime, "is_available", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(comfyui_runtime.subprocess, "Popen", lambda *_args, **_kwargs: process)
    monkeypatch.setattr(
        comfyui_runtime,
        "_wait_for",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            comfyui_runtime.ComfyUIRuntimeError("timeout")
        ),
    )
    runtime = comfyui_runtime.ComfyUIRuntime(
        "http://127.0.0.1:8188", config_path=config, project_root=tmp_path
    )
    with pytest.raises(comfyui_runtime.ComfyUIRuntimeError, match="timeout"):
        runtime.start()
    assert "terminate" in events
    assert not runtime.started_by_us


def test_start_timeout_stops_process(tmp_path, monkeypatch):
    config = _runtime_files(tmp_path)
    events = []
    process = _Process(events)
    monkeypatch.setattr(comfyui_runtime, "is_available", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(comfyui_runtime.subprocess, "Popen", lambda *_args, **_kwargs: process)
    runtime = comfyui_runtime.ComfyUIRuntime(
        "http://127.0.0.1:8188",
        config_path=config,
        project_root=tmp_path,
        start_timeout=0,
    )
    with pytest.raises(comfyui_runtime.ComfyUIRuntimeError, match="0秒"):
        runtime.start()
    assert "terminate" in events
