"""Storyboard 用 ComfyUI の自動起動と終了処理。"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = PROJECT_ROOT / ".runtime"
DEFAULT_CONFIG_PATH = RUNTIME_DIR / "comfyui.json"
COMFYUI_START_TIMEOUT = 120.0


class ComfyUIRuntimeError(RuntimeError):
    """ComfyUI の導入情報または起動に関するエラー。"""


def is_available(url: str, *, timeout: float = 2.0) -> bool:
    """ComfyUI の system_stats endpoint に接続できるか確認する。"""
    try:
        with urllib.request.urlopen(
            f"{url.rstrip('/')}/system_stats", timeout=timeout
        ):
            return True
    except (urllib.error.URLError, OSError):
        return False


def _read_config(path: Path) -> Dict[str, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ComfyUIRuntimeError(f"ComfyUI設定を読み取れません: {path}") from exc
    if not isinstance(payload, dict):
        raise ComfyUIRuntimeError(f"ComfyUI設定が不正です: {path}")
    values = {}
    for key in ("comfyui_dir", "comfyui_venv"):
        value = payload.get(key)
        if not isinstance(value, str) or not value:
            raise ComfyUIRuntimeError(f"ComfyUI設定に{key}がありません: {path}")
        values[key] = value
    return values


def _resolve_path(value: str, *, base_dir: Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else base_dir / path


def _python_executable(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _wait_for(url: str, *, timeout: float = COMFYUI_START_TIMEOUT) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if is_available(url):
            return
        time.sleep(1.0)
    raise ComfyUIRuntimeError(
        f"ComfyUIを起動できませんでした（{timeout:.0f}秒経過）。"
        "ログを確認してください: .runtime/comfyui.log"
    )


class ComfyUIRuntime:
    """必要な場合だけ ComfyUI を起動し、自分で起動したプロセスだけ停止する。"""

    def __init__(
        self,
        url: str,
        *,
        config_path: Optional[Path] = None,
        project_root: Optional[Path] = None,
        start_timeout: float = COMFYUI_START_TIMEOUT,
    ):
        self.url = url
        self.config_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        self.project_root = Path(project_root) if project_root else PROJECT_ROOT
        self.start_timeout = start_timeout
        self.process: Optional[subprocess.Popen[Any]] = None
        self._log_file: Optional[Any] = None

    @property
    def started_by_us(self) -> bool:
        return self.process is not None

    def start(self) -> None:
        if is_available(self.url):
            print("Using existing ComfyUI server")
            return
        if not self.config_path.exists():
            raise ComfyUIRuntimeError(
                "ComfyUIに接続できません。"
                "`python setup_storyboard.py` で導入してください。"
                "既存のComfyUIを使う場合は `--comfyui-dir` で指定できます。"
            )

        config = _read_config(self.config_path)
        comfyui_dir = _resolve_path(config["comfyui_dir"], base_dir=self.project_root)
        comfyui_venv = _resolve_path(config["comfyui_venv"], base_dir=self.project_root)
        python = _python_executable(comfyui_venv)
        main_py = comfyui_dir / "main.py"
        if not comfyui_dir.is_dir() or not main_py.is_file() or not python.is_file():
            raise ComfyUIRuntimeError(
                "ComfyUIの導入先または専用Pythonが見つかりません。"
                "`python setup_storyboard.py` で導入してください。"
                "既存のComfyUIを使う場合は `--comfyui-dir` で指定できます。"
            )

        log_path = self.config_path.parent / "comfyui.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._log_file = log_path.open("a", encoding="utf-8")
            environment = os.environ.copy()
            environment.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
            self.process = subprocess.Popen(
                [
                    str(python),
                    "main.py",
                    "--listen",
                    "127.0.0.1",
                    "--port",
                    "8188",
                    "--disable-api-nodes",
                    "--preview-method",
                    "none",
                ],
                cwd=str(comfyui_dir),
                env=environment,
                stdout=self._log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            _wait_for(self.url, timeout=self.start_timeout)
        except (OSError, subprocess.SubprocessError) as exc:
            self.stop()
            raise ComfyUIRuntimeError(f"ComfyUIの起動に失敗しました: {exc}") from exc
        except ComfyUIRuntimeError:
            self.stop()
            raise
        print("Started ComfyUI server")

    def stop(self) -> None:
        process = self.process
        self.process = None
        try:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10.0)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10.0)
        except (OSError, subprocess.SubprocessError) as exc:
            print(f"警告: ComfyUIの停止に失敗しました: {exc}")
        finally:
            if self._log_file is not None:
                self._log_file.close()
                self._log_file = None

    def __enter__(self) -> "ComfyUIRuntime":
        self.start()
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _traceback: Any) -> None:
        self.stop()
