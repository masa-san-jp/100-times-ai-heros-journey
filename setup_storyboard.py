#!/usr/bin/env python3
"""ComfyUI とストーリーボード用モデルを導入する。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import venv
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence


PROJECT_ROOT = Path(__file__).resolve().parent
RUNTIME_DIR = PROJECT_ROOT / ".runtime"
DEFAULT_COMFYUI_DIR = RUNTIME_DIR / "ComfyUI"
DEFAULT_COMFYUI_VENV = RUNTIME_DIR / "comfyui-venv"
COMFYUI_REPOSITORY = "https://github.com/Comfy-Org/ComfyUI.git"
COMFYUI_REF = os.getenv("COMFYUI_REF", "v0.37.4")
DEFAULT_PROFILE = "qwen-image-2.1-turbo"
PROFILE_PATH = PROJECT_ROOT / "config" / "comfyui" / "storyboard_profiles.json"


class SetupError(RuntimeError):
    """セットアップを安全に続行できない場合のエラー。"""


def _python_executable(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _run(command: Sequence[Path | str], *, cwd: Optional[Path] = None, dry_run: bool = False) -> None:
    printable = " ".join(subprocess.list2cmdline([str(item)]) for item in command)
    print(f"$ {printable}")
    if dry_run:
        return
    try:
        subprocess.run([str(item) for item in command], cwd=cwd, check=True)
    except FileNotFoundError as exc:
        raise SetupError(f"コマンドが見つかりません: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        raise SetupError(f"コマンドに失敗しました (exit {exc.returncode}): {command[0]}") from exc


def _confirm(message: str, *, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        raise SetupError(f"確認が必要です。再実行時に --yes を指定してください: {message}")
    return input(f"{message} [y/N] ").strip().lower() in {"y", "yes"}


def _load_profile(name: str) -> Dict[str, Any]:
    try:
        payload = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SetupError(f"Storyboard profileを読み取れません: {PROFILE_PATH}") from exc
    profiles = payload.get("profiles") if isinstance(payload, dict) else None
    profile = profiles.get(name) if isinstance(profiles, dict) else None
    if not isinstance(profile, dict):
        raise SetupError(f"Unknown storyboard profile: {name}")
    return profile


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _size_bytes(value: str) -> int:
    text = str(value).strip().upper()
    units = {"GB": 1024**3, "GIB": 1024**3, "MB": 1024**2, "MIB": 1024**2}
    for unit, multiplier in units.items():
        if text.endswith(unit):
            return int(float(text[: -len(unit)]) * multiplier)
    return int(float(text))


def _download_file(
    url: str,
    destination: Path,
    expected_sha256: str,
    *,
    label: str,
    size: str = "",
    dry_run: bool = False,
) -> None:
    if destination.is_file() and _sha256(destination) == expected_sha256:
        print(f"OK: {label} is installed: {destination}")
        return
    if destination.exists():
        print(f"WARNING: SHA256が一致しないため再ダウンロードします: {destination}")
    if dry_run:
        print(f"Would download: {url}")
        print(f"  Size: {size or '不明'}")
        print(f"  Destination: {destination}")
        return

    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")
    try:
        request = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(request, timeout=60.0) as response, partial.open("wb") as output:
            digest = hashlib.sha256()
            while True:
                chunk = response.read(8 * 1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                digest.update(chunk)
        actual_sha256 = digest.hexdigest()
        if actual_sha256 != expected_sha256:
            raise SetupError(
                f"{label}のSHA256が一致しません。期待値={expected_sha256}, 実際={actual_sha256}"
            )
        os.replace(partial, destination)
        print(f"OK: installed: {destination}")
    except SetupError:
        partial.unlink(missing_ok=True)
        raise
    except (urllib.error.URLError, OSError) as exc:
        partial.unlink(missing_ok=True)
        raise SetupError(f"ダウンロードに失敗しました: {url}: {exc}") from exc


def _git_is_repository(path: Path) -> bool:
    return (path / ".git").exists()


def _git_describe(path: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "describe", "--tags", "--exact-match"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _ensure_comfyui_checkout(path: Path, *, dry_run: bool) -> None:
    if path.exists() and (path / "main.py").exists():
        print(f"OK: ComfyUI installation exists: {path}")
        if _git_is_repository(path):
            current = _git_describe(path)
            if current != COMFYUI_REF:
                print(
                    f"WARNING: ComfyUI is at {current or 'an untagged commit'}, "
                    f"but this project is verified with {COMFYUI_REF}.\n"
                    f"  To switch: git -C {path} fetch --depth 1 origin tag {COMFYUI_REF} "
                    f"&& git -C {path} checkout {COMFYUI_REF}"
                )
        return
    if path.exists() and not _git_is_repository(path) and any(path.iterdir()):
        raise SetupError(f"ComfyUIの導入先が空ではありません: {path}")
    if _git_is_repository(path):
        print(f"OK: ComfyUI checkout exists: {path}")
        return
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
    _run(
        ["git", "clone", "--depth", "1", "--branch", COMFYUI_REF, COMFYUI_REPOSITORY, path],
        dry_run=dry_run,
    )


def _create_venv(path: Path, *, dry_run: bool) -> Path:
    executable = _python_executable(path)
    if executable.exists():
        print(f"OK: virtual environment exists: {path}")
        return executable
    print(f"Creating virtual environment: {path}")
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        venv.EnvBuilder(with_pip=True, clear=False).create(path)
    return executable


def _ensure_comfyui_dependencies(
    path: Path,
    venv_dir: Path,
    *,
    dry_run: bool,
    update_deps: bool = False,
) -> Path:
    existing_python = _python_executable(venv_dir).exists()
    python = _create_venv(venv_dir, dry_run=dry_run)
    if existing_python and not update_deps:
        print(f"SKIP: dependencies in existing virtual environment: {venv_dir}")
        return python
    _run([python, "-m", "pip", "install", "--upgrade", "pip"], dry_run=dry_run)
    # The official ComfyUI guidance recommends a current PyTorch nightly for
    # Apple Silicon.  Installing it before requirements.txt prevents pip from
    # replacing the MPS-capable build with a CPU-only fallback.
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        _run(
            [
                python,
                "-m",
                "pip",
                "install",
                "--pre",
                "torch",
                "torchvision",
                "torchaudio",
                "--extra-index-url",
                "https://download.pytorch.org/whl/nightly/cpu",
            ],
            dry_run=dry_run,
        )
    _run([python, "-m", "pip", "install", "-r", path / "requirements.txt"], dry_run=dry_run)
    return python


def _license_confirm(profile: Mapping[str, Any], *, assume_yes: bool, dry_run: bool) -> None:
    name = profile.get("license_name", "不明")
    url = profile.get("license_url", "")
    note = profile.get("license_note", "")
    print(f"LICENSE: {name}" + (f" <{url}>" if url else ""))
    print("  注意: Qwen Research License、研究・評価目的に限られます。")
    if note:
        print(f"  {note}")
    if not _confirm(
        "ライセンスと注意事項を確認し、モデルおよびViggle派生物の導入を続行しますか?",
        assume_yes=assume_yes or dry_run,
    ):
        raise SetupError("ライセンスに同意しなかったため中止しました。")


def _profile_assets(profile: Mapping[str, Any], comfyui_dir: Path, *, skip_models: bool, dry_run: bool) -> None:
    if not skip_models:
        for item in profile.get("model_files", []):
            if not isinstance(item, Mapping):
                raise SetupError("model_filesの形式が不正です")
            destination = comfyui_dir / "models" / str(item["subdir"]) / str(item["filename"])
            _download_file(
                str(item["url"]),
                destination,
                str(item["sha256"]),
                label=f"model {item['filename']}",
                size=str(item.get("size", "")),
                dry_run=dry_run,
            )
    for item in profile.get("custom_nodes", []):
        if not isinstance(item, Mapping):
            raise SetupError("custom_nodesの形式が不正です")
        filename = Path(str(item["filename"]))
        if filename.name != str(item["filename"]):
            raise SetupError(f"custom nodeのファイル名が不正です: {filename}")
        _download_file(
            str(item["url"]),
            comfyui_dir / "custom_nodes" / filename,
            str(item["sha256"]),
            label=f"custom node {filename.name}",
            dry_run=dry_run,
        )


def _print_storage_summary(profile: Mapping[str, Any], comfyui_dir: Path) -> None:
    model_files = profile.get("model_files", [])
    total = sum(_size_bytes(str(item.get("size", "0"))) for item in model_files if isinstance(item, Mapping))
    free = shutil.disk_usage(comfyui_dir.parent if comfyui_dir.parent.exists() else PROJECT_ROOT).free
    print(f"モデル合計サイズ（導入済みのファイルはダウンロードしません）: 約 {total / 1024**3:.1f}GB")
    print(f"保存先の空き容量: {free / 1024**3:.1f}GB")
    if free < total:
        raise SetupError("ダウンロードに必要な空き容量が不足しています。")


def _storage_confirm(*, assume_yes: bool, dry_run: bool) -> None:
    if not _confirm(
        "表示したサイズと空き容量を確認し、ダウンロードを続行しますか?",
        assume_yes=assume_yes or dry_run,
    ):
        raise SetupError("容量確認を拒否したため中止しました。")


def _save_config(comfyui_dir: Path, comfyui_venv: Path, profile: str, *, dry_run: bool) -> None:
    if dry_run:
        print(f"Would write: {RUNTIME_DIR / 'comfyui.json'}")
        return
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    config_path = RUNTIME_DIR / "comfyui.json"
    config_path.write_text(
        json.dumps(
            {"comfyui_dir": str(comfyui_dir), "comfyui_venv": str(comfyui_venv), "profile": profile},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Saved: {config_path}")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ストーリーボード用ComfyUI環境をセットアップします。")
    parser.add_argument("--comfyui-dir", type=Path, default=DEFAULT_COMFYUI_DIR)
    parser.add_argument("--comfyui-venv", type=Path, default=DEFAULT_COMFYUI_VENV)
    parser.add_argument("--profile", default=DEFAULT_PROFILE)
    parser.add_argument("--skip-models", action="store_true")
    parser.add_argument("--yes", action="store_true", help="確認を自動承認する")
    parser.add_argument(
        "--update-deps",
        action="store_true",
        help="既存のComfyUI用venvにも依存パッケージを導入する",
    )
    parser.add_argument("--dry-run", action="store_true", help="変更せず、予定だけ表示する")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        profile = _load_profile(args.profile)
        comfyui_dir = args.comfyui_dir if args.comfyui_dir.is_absolute() else PROJECT_ROOT / args.comfyui_dir
        comfyui_venv = args.comfyui_venv if args.comfyui_venv.is_absolute() else PROJECT_ROOT / args.comfyui_venv
        print("Storyboard ComfyUI setup")
        if args.dry_run:
            print("DRY RUN: files, packages, and downloads will not be changed")
        _ensure_comfyui_checkout(comfyui_dir, dry_run=args.dry_run)
        _ensure_comfyui_dependencies(
            comfyui_dir,
            comfyui_venv,
            dry_run=args.dry_run,
            update_deps=args.update_deps,
        )
        _license_confirm(profile, assume_yes=args.yes, dry_run=args.dry_run)
        if not args.skip_models:
            _print_storage_summary(profile, comfyui_dir)
            _storage_confirm(assume_yes=args.yes, dry_run=args.dry_run)
        else:
            print("SKIP: model files")
        _profile_assets(profile, comfyui_dir, skip_models=args.skip_models, dry_run=args.dry_run)
        _save_config(comfyui_dir, comfyui_venv, args.profile, dry_run=args.dry_run)
        print("\nSetup complete.")
        return 0
    except (OSError, SetupError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
