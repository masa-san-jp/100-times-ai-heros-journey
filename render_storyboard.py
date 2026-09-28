#!/usr/bin/env python3
"""完成済みの物語からショットリストと画像を一括生成するCLI。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set

from src.batch_analyzer import BatchAnalyzer, CompletedRun
from src.comfyui_client import (
    ComfyUIConfigurationError,
    ComfyUIConnectionError,
    ComfyUIImageGenerator,
    load_storyboard_profile,
)
from src.llm_factory import create_provider_client
from src.storyboard import (
    ALLOWED_ROLES,
    DEFAULT_STYLE,
    StoryboardError,
    _appearance_without_mood,
    _parse_visual_prompts,
    build_shot_list,
    has_failed_shots,
    read_shot_list,
)
from src.storyboard_sheet import DEFAULT_COLUMNS, write_storyboard_outputs


ESTIMATED_SECONDS_PER_IMAGE = 55.0
RUN_NAME_PREFIX = "run_"


class RenderStoryboardError(RuntimeError):
    """ストーリーボード生成を開始できない場合のエラー。"""


def _is_run_name(name: str) -> bool:
    return name.startswith(RUN_NAME_PREFIX) and name[4:].isdigit()


def _completed_runs(path: Path) -> List[CompletedRun]:
    if not path.is_dir():
        raise RenderStoryboardError(f"対象ディレクトリが見つかりません: {path}")

    if _is_run_name(path.name):
        runs, _skipped = BatchAnalyzer(path.parent)._discover_runs()
        selected = [run for run in runs if run.path == path]
        if not selected:
            raise RenderStoryboardError(
                f"未完成runのため対象外です（metadata.jsonと本文Markdownが必要です）: {path.name}"
            )
        return selected

    runs, _skipped = BatchAnalyzer(path)._discover_runs()
    if not runs:
        raise RenderStoryboardError(
            f"完了済みrunが0件です（metadata.jsonと本文Markdownが必要です）: {path}"
        )
    return runs


def _parse_run_selection(value: Optional[str]) -> Optional[Set[int]]:
    if value is None:
        return None
    selected: Set[int] = set()
    for part in value.split(","):
        token = part.strip()
        if not token:
            raise ValueError("--runsには空の指定を含められません")
        if "-" in token:
            pieces = token.split("-")
            if len(pieces) != 2 or not all(piece.isdigit() for piece in pieces):
                raise ValueError(f"不正なrun範囲です: {token}")
            start, end = (int(piece) for piece in pieces)
            if start < 1 or end < start:
                raise ValueError(f"不正なrun範囲です: {token}")
            selected.update(range(start, end + 1))
        elif token.isdigit() and int(token) > 0:
            selected.add(int(token))
        else:
            raise ValueError(f"不正なrun番号です: {token}")
    return selected


def _select_runs(path: Path, runs_option: Optional[str]) -> List[CompletedRun]:
    runs = _completed_runs(path)
    selected_numbers = _parse_run_selection(runs_option)
    if selected_numbers is None:
        return runs
    selected = [run for run in runs if run.number in selected_numbers]
    missing = sorted(selected_numbers - {run.number for run in selected})
    if missing:
        raise RenderStoryboardError(
            "指定されたrunが見つからないか未完了です: "
            + ", ".join(f"run_{number:03d}" for number in missing)
        )
    return selected


def _needs_shot_client(run: CompletedRun, args: argparse.Namespace) -> bool:
    if args.images_only or args.rebuild_prompts:
        return False
    shots_path = run.path / "storyboard" / "shots.json"
    if args.rebuild_prompts or args.refresh_shots or not shots_path.exists():
        return True
    try:
        return has_failed_shots(read_shot_list(run.path))
    except StoryboardError:
        return True


def _read_cached_shots(run: CompletedRun) -> Any:
    path = run.path / "storyboard" / "shots.json"
    if not path.exists():
        raise RenderStoryboardError(
            f"--images-onlyには既存のshots.jsonが必要です: {run.path}"
        )
    try:
        return read_shot_list(run.path)
    except StoryboardError as exc:
        raise RenderStoryboardError(str(exc)) from exc


def _write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        os.replace(temporary, path)
    except OSError:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _derive_seed(base_seed: Optional[int], run_dir: Path, shot_id: str) -> Optional[int]:
    if base_seed is None:
        return None
    source = f"{base_seed}:{run_dir.name}:{shot_id}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(source).digest()[:8], "big") % 2**63


def _model_filenames(profile: Mapping[str, Any]) -> List[str]:
    names = []
    for item in profile.get("model_files", []):
        if isinstance(item, Mapping) and item.get("filename"):
            names.append(str(item["filename"]))
        elif isinstance(item, str):
            names.append(item)
    return names


def _resolve_workflow_path(profile: Mapping[str, Any]) -> Path:
    workflow = Path(str(profile["workflow_path"]))
    return workflow if workflow.is_absolute() else Path(__file__).resolve().parent / workflow


def _resolve_reference_workflow_path(profile: Mapping[str, Any]) -> Optional[Path]:
    workflow_value = profile.get("reference_workflow_path")
    if not workflow_value:
        return None
    workflow = Path(str(workflow_value))
    return workflow if workflow.is_absolute() else Path(__file__).resolve().parent / workflow


def _character_ref_mode(args: argparse.Namespace) -> str:
    value = getattr(args, "character_refs", "off")
    if value is True:
        return "all"
    if value in (False, None):
        return "off"
    return str(value)


def _shot_uses_character_references(shot: Mapping[str, Any], mode: str) -> bool:
    if mode == "all":
        return True
    return mode == "closeup" and shot.get("shot_size") in {"close_up", "medium"}


def _reference_roles(
    shots: Sequence[Mapping[str, Any]], mode: str = "all"
) -> List[str]:
    present = {
        str(role).strip()
        for shot in shots
        if _shot_uses_character_references(shot, mode)
        for role in shot.get("characters", [])
        if str(role).strip() in ALLOWED_ROLES
    }
    return [role for role in ALLOWED_ROLES if role in present]


def _character_reference_prompt(appearance: str) -> str:
    appearance = _appearance_without_mood(appearance).strip()
    suffix = (
        "Full body, single character, standing, plain white background, "
        "photorealistic, no text or watermark."
    )
    return f"{appearance} {suffix}" if appearance else suffix


def _read_character_visual_prompts(run_dir: Path) -> Dict[str, str]:
    path = run_dir / "visual_prompts.md"
    try:
        prompts = _parse_visual_prompts(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as exc:
        raise RenderStoryboardError(f"visual_prompts.mdを読み取れません: {path}") from exc
    if not prompts:
        raise RenderStoryboardError(f"visual_prompts.mdに外見文がありません: {path}")
    return prompts


def _prepare_character_references(
    run: CompletedRun,
    shots: Sequence[Mapping[str, Any]],
    generator: Any,
    profile: Mapping[str, Any],
    args: argparse.Namespace,
) -> Dict[str, Path]:
    mode = _character_ref_mode(args)
    if mode == "off":
        return {}
    roles = _reference_roles(shots, mode)
    if not roles:
        return {}
    if not profile.get("reference_workflow_path"):
        print(
            "警告: このComfyUI profileには参照workflowがないため、参照なしで続行します。",
            file=sys.stderr,
        )
        return {}
    reference_dir = run.path / "storyboard" / "characters"
    references: Dict[str, Path] = {}
    missing_roles = [
        role for role in roles if not (reference_dir / f"{role}.png").exists()
    ]
    prompts = _read_character_visual_prompts(run.path) if missing_roles else {}
    try:
        for role in roles:
            path = reference_dir / f"{role}.png"
            if not path.exists():
                if role not in prompts:
                    raise RenderStoryboardError(
                        f"visual_prompts.mdに{role}の外見文がありません: {run.path}"
                    )
                generator.generate(
                    _character_reference_prompt(prompts[role]),
                    reference_dir,
                    role,
                    seed=_derive_seed(args.seed, run.path, f"character-{role}"),
                    width=int(profile.get("reference_width", 448)),
                    height=int(profile.get("reference_height", 768)),
                )
            references[role] = path
    except ComfyUIConfigurationError as exc:
        print(
            f"警告: ComfyUIの参照workflowを使えないため、参照なしで続行します: {exc}",
            file=sys.stderr,
        )
        return {}
    return references


def _shot_reference_paths(
    shot: Mapping[str, Any], references: Mapping[str, Path], mode: str = "all"
) -> List[Path]:
    if not _shot_uses_character_references(shot, mode):
        return []
    return [
        references[role]
        for role in shot.get("characters", [])
        if str(role) in references
    ][:2]


def _shot_render_prompt(shot: Mapping[str, Any], reference_paths: Sequence[Path]) -> str:
    prompt = str(shot.get("prompt_en", ""))
    if not reference_paths:
        return prompt
    roles = [
        str(role)
        for role in shot.get("characters", [])
        if str(role) in {path.stem for path in reference_paths}
    ][:2]
    prefix = " ".join(
        f"The {role} is the person in image {index}." for index, role in enumerate(roles, 1)
    )
    return f"{prefix} {prompt}".strip()


def _new_manifest(
    profile: Mapping[str, Any],
    shots: Sequence[Mapping[str, Any]],
    run_dir: Path,
    seed: Optional[int],
    references: Optional[Mapping[str, Path]] = None,
    mode: str = "all",
) -> Dict[str, Any]:
    references = references or {}
    entries = []
    for index, shot in enumerate(shots, start=1):
        shot_id = str(shot.get("id") or f"{index:02d}")
        shot_references = _shot_reference_paths(shot, references, mode)
        entries.append(
            {
                "id": shot_id,
                "filename": f"shot_{shot_id}.png",
                "seed": _derive_seed(seed, run_dir, shot_id),
                "shot_size": shot.get("shot_size"),
                "prompt": _shot_render_prompt(shot, shot_references),
                "references": [f"characters/{path.name}" for path in shot_references],
                "references_used": bool(shot_references),
                "elapsed_seconds": None,
                "duration_seconds": None,
                "success": None,
                "status": "pending",
                "error": None,
            }
        )
    return {
        "profile": profile["name"],
        "model_files": _model_filenames(profile),
        "width": profile["width"],
        "height": profile["height"],
        "character_references": {
            role: f"characters/{path.name}" for role, path in references.items()
        },
        "shots": entries,
    }


def _load_manifest(path: Path) -> Optional[Dict[str, Any]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _shot_id(index: int, shot: Mapping[str, Any]) -> str:
    return str(shot.get("id") or f"{index + 1:02d}")


def _shot_entry(
    manifest: Dict[str, Any],
    index: int,
    shot: Mapping[str, Any],
    references: Optional[Mapping[str, Path]] = None,
    mode: str = "all",
) -> Dict[str, Any]:
    entries = manifest.setdefault("shots", [])
    while len(entries) <= index:
        entries.append({})
    entry = entries[index]
    if not isinstance(entry, dict):
        entry = {}
        entries[index] = entry
    shot_id = _shot_id(index, shot)
    shot_references = _shot_reference_paths(shot, references or {}, mode)
    entry.update(
        {
            "id": shot_id,
            "filename": f"shot_{shot_id}.png",
            "shot_size": shot.get("shot_size"),
            "prompt": _shot_render_prompt(shot, shot_references),
            "references": [f"characters/{path.name}" for path in shot_references],
            "references_used": bool(shot_references),
        }
    )
    return entry


def _can_skip_image(
    storyboard_dir: Path,
    shot: Mapping[str, Any],
    index: int,
    old_entries: Mapping[str, Mapping[str, Any]],
    force: bool,
    prompt: Optional[str] = None,
    references: Optional[Sequence[str]] = None,
) -> bool:
    if force:
        return False
    shot_id = _shot_id(index, shot)
    image_path = storyboard_dir / f"shot_{shot_id}.png"
    old_entry = old_entries.get(shot_id)
    return bool(
        image_path.exists()
        and old_entry
        and old_entry.get("status") in ("success", "skipped")
        and old_entry.get("prompt")
        == (prompt if prompt is not None else str(shot.get("prompt_en", "")))
        and list(old_entry.get("references", [])) == list(references or [])
    )


def _print_progress(
    run_name: str,
    index: int,
    total: int,
    shot_id: str,
    result: str,
    elapsed: float,
    durations: Sequence[float],
) -> None:
    average = sum(durations[-5:]) / len(durations[-5:]) if durations else 0.0
    remaining = max(total - index, 0)
    eta = average * remaining
    print(
        f"[{run_name} {index}/{total}] shot_{shot_id} {result} "
        f"経過 {elapsed:.1f}s、残り推定 {eta:.1f}s",
        flush=True,
    )


def _render_run(
    run: CompletedRun,
    shot_list: Any,
    generator: Any,
    profile: Mapping[str, Any],
    args: argparse.Namespace,
) -> int:
    storyboard_dir = run.path / "storyboard"
    manifest_path = storyboard_dir / "render_manifest.json"
    mode = _character_ref_mode(args)
    references = _prepare_character_references(run, shot_list.shots, generator, profile, args)
    existing = _load_manifest(manifest_path)
    old_entries: Dict[str, Mapping[str, Any]] = {}
    if existing and isinstance(existing.get("shots"), list):
        old_entries = {
            str(item["id"]): item
            for item in existing["shots"]
            if isinstance(item, Mapping) and item.get("id") is not None
        }
    manifest = _new_manifest(profile, shot_list.shots, run.path, args.seed, references, mode)
    for entry in manifest["shots"]:
        old_entry = old_entries.get(str(entry["id"]))
        if old_entry:
            for key in (
                "seed",
                "elapsed_seconds",
                "duration_seconds",
                "success",
                "status",
                "error",
            ):
                if key in old_entry:
                    entry[key] = old_entry[key]
    _write_json_atomic(manifest_path, manifest)

    durations: List[float] = []
    failures = 0
    started = time.monotonic()
    total = len(shot_list.shots)
    for index, shot in enumerate(shot_list.shots):
        entry = _shot_entry(manifest, index, shot, references, mode)
        shot_id = str(entry["id"])
        shot_references = _shot_reference_paths(shot, references, mode)
        render_prompt = _shot_render_prompt(shot, shot_references)
        reference_manifest_paths = [f"characters/{path.name}" for path in shot_references]
        if shot.get("status") == "failed":
            failures += 1
            entry.update(
                {
                    "success": False,
                    "status": "failed",
                    "elapsed_seconds": 0.0,
                    "duration_seconds": 0.0,
                    "error": str(shot.get("error", "ショット生成に失敗しました")),
                }
            )
            _write_json_atomic(manifest_path, manifest)
            _print_progress(run.name, index + 1, total, shot_id, "failed", time.monotonic() - started, durations)
            continue

        if _can_skip_image(
            storyboard_dir,
            shot,
            index,
            old_entries,
            args.force,
            prompt=render_prompt,
            references=reference_manifest_paths,
        ):
            entry["success"] = True
            entry["status"] = "skipped"
            entry["error"] = None
            if entry.get("elapsed_seconds") is None:
                entry["elapsed_seconds"] = 0.0
            if entry.get("duration_seconds") is None:
                entry["duration_seconds"] = 0.0
            _write_json_atomic(manifest_path, manifest)
            _print_progress(run.name, index + 1, total, shot_id, "skip", time.monotonic() - started, durations)
            continue

        shot_started = time.monotonic()
        planned_seed = _derive_seed(args.seed, run.path, shot_id)
        try:
            generate_kwargs: Dict[str, Any] = {"seed": planned_seed}
            if shot_references:
                generate_kwargs["reference_images"] = shot_references
            generated = generator.generate(
                render_prompt,
                storyboard_dir,
                f"shot_{shot_id}",
                **generate_kwargs,
            )
            elapsed = time.monotonic() - shot_started
            entry.update(
                {
                    "seed": getattr(generated, "seed", planned_seed),
                    "elapsed_seconds": elapsed,
                    "duration_seconds": elapsed,
                    "success": True,
                    "status": "success",
                    "error": None,
                }
            )
            durations.append(elapsed)
            result = "完了"
        except Exception as exc:
            elapsed = time.monotonic() - shot_started
            failures += 1
            entry.update(
                {
                    "seed": planned_seed,
                    "elapsed_seconds": elapsed,
                    "duration_seconds": elapsed,
                    "success": False,
                    "status": "failed",
                    "error": str(exc),
                }
            )
            result = "failed"
        _write_json_atomic(manifest_path, manifest)
        _print_progress(run.name, index + 1, total, shot_id, result, time.monotonic() - started, durations)
    return failures


def _print_dry_run(runs: Sequence[CompletedRun], shot_lists: Mapping[Path, Any], args: argparse.Namespace) -> None:
    pending = 0
    mode = _character_ref_mode(args)
    for run in runs:
        shot_list = shot_lists[run.path]
        references = {
            role: run.path / "storyboard" / "characters" / f"{role}.png"
            for role in _reference_roles(shot_list.shots, mode)
        }
        manifest = _load_manifest(run.path / "storyboard" / "render_manifest.json") or {}
        old_entries = {
            str(item["id"]): item
            for item in manifest.get("shots", [])
            if isinstance(item, Mapping) and item.get("id") is not None
        }
        for index, shot in enumerate(shot_list.shots, start=1):
            shot_id = _shot_id(index - 1, shot)
            shot_references = _shot_reference_paths(shot, references, mode)
            render_prompt = _shot_render_prompt(shot, shot_references)
            reference_manifest_paths = [f"characters/{path.name}" for path in shot_references]
            if shot.get("status") == "failed" or _can_skip_image(
                run.path / "storyboard",
                shot,
                index - 1,
                old_entries,
                args.force,
                prompt=render_prompt,
                references=reference_manifest_paths,
            ):
                continue
            pending += 1
            print(f"[{run.name} {index}/{len(shot_list.shots)}] shot_{shot_id}: {render_prompt}")
    print(f"生成予定ショット数: {pending}")
    print(f"推定所要時間: {pending * ESTIMATED_SECONDS_PER_IMAGE:.0f}秒（約55秒/枚で概算）")


def _write_storyboard_outputs(
    runs: Sequence[CompletedRun], shot_lists: Mapping[Path, Any], columns: int
) -> None:
    for run in runs:
        write_storyboard_outputs(run.path, shot_lists[run.path], columns=columns)


def _make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="完成済みrunからストーリーボード画像を生成")
    parser.add_argument("target", help="runディレクトリまたはバッチディレクトリ")
    parser.add_argument("--runs", help="バッチ内のrun番号（例: 1,3-5）")
    parser.add_argument("--shots-only", action="store_true", help="ショットリストだけを生成する")
    parser.add_argument("--images-only", action="store_true", help="既存shots.jsonから画像だけを生成する")
    parser.add_argument("--unit", choices=("auto", "chapter", "stage"), default="auto")
    parser.add_argument("--shots-per-unit", type=int, default=1)
    parser.add_argument("--style", default=DEFAULT_STYLE)
    parser.add_argument("--refresh-shots", action="store_true")
    parser.add_argument("--rebuild-prompts", action="store_true")
    parser.add_argument("--provider", choices=("ollama", "openai", "anthropic", "deepseek"), default="ollama")
    parser.add_argument("--model", default=None)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument(
        "--comfyui-url",
        default=os.getenv("COMFYUI_URL", "http://127.0.0.1:8188"),
        help="ComfyUI URL（既定値: COMFYUI_URL、未設定時は http://127.0.0.1:8188）",
    )
    parser.add_argument("--profile", default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument(
        "--character-refs",
        nargs="?",
        const="all",
        choices=("off", "closeup", "all"),
        default="closeup",
        help="キャラクター参照の範囲（既定: closeup、値なし: all）",
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--sheet-columns",
        type=int,
        default=DEFAULT_COLUMNS,
        help=f"ストーリーボードシートの列数（既定値: {DEFAULT_COLUMNS}）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="生成予定を表示して終了（shots.jsonがないrunはLLMで作成）",
    )
    return parser


def run(args: argparse.Namespace) -> int:
    path = Path(args.target)
    runs = _select_runs(path, args.runs)
    if args.shots_per_unit < 1:
        raise RenderStoryboardError("--shots-per-unitは1以上で指定してください")
    if args.timeout < 1:
        raise RenderStoryboardError("--timeoutは1以上で指定してください")
    if args.sheet_columns < 1:
        raise RenderStoryboardError("--sheet-columnsは1以上で指定してください")

    llm_client = None
    selected_model = "cache"
    if not args.images_only:
        if any(_needs_shot_client(run, args) for run in runs):
            llm_client, selected_model = create_provider_client(
                args.provider, args.model, args.timeout
            )

    shot_lists: Dict[Path, Any] = {}
    for run_info in runs:
        if args.images_only:
            shot_lists[run_info.path] = _read_cached_shots(run_info)
        else:
            shot_lists[run_info.path] = build_shot_list(
                run_info.path,
                llm_client,
                unit=args.unit,
                shots_per_unit=args.shots_per_unit,
                style=args.style,
                refresh=args.refresh_shots,
                rebuild_prompts=args.rebuild_prompts,
            )
    print(f"ショットリスト準備完了: {len(runs)}作品（{selected_model}）")

    if args.shots_only:
        _write_storyboard_outputs(runs, shot_lists, args.sheet_columns)
        return 1 if any(
            shot.get("status") == "failed"
            for shot_list in shot_lists.values()
            for shot in shot_list.shots
        ) else 0
    if args.dry_run:
        _print_dry_run(runs, shot_lists, args)
        return 1 if any(
            shot.get("status") == "failed"
            for shot_list in shot_lists.values()
            for shot in shot_list.shots
        ) else 0

    if llm_client is not None and args.provider == "ollama":
        release = getattr(llm_client, "release_model", None)
        if release is None:
            release = getattr(llm_client, "unload_model", None)
        if release is not None:
            release()

    profile = load_storyboard_profile(args.profile)
    generator = ComfyUIImageGenerator(
        base_url=args.comfyui_url,
        workflow_path=_resolve_workflow_path(profile),
        reference_workflow_path=_resolve_reference_workflow_path(profile),
        reference_encode_resolution=(
            int(profile["reference_encode_resolution"])
            if profile.get("reference_encode_resolution") is not None
            else None
        ),
        model_files=profile.get("model_files", []),
        width=int(profile["width"]),
        height=int(profile["height"]),
        timeout_seconds=float(profile.get("timeout_seconds", 600)),
    )
    try:
        generator.check_connection()
    except ComfyUIConnectionError as exc:
        print(
            f"{exc}\n100-times-ai-heroes の python3 run_local.py 等で ComfyUI を起動してください。",
            file=sys.stderr,
        )
        return 1
    except Exception as exc:
        raise RenderStoryboardError(f"ComfyUIへの接続確認に失敗しました: {exc}") from exc

    failures = 0
    try:
        for run_info in runs:
            failures += _render_run(run_info, shot_lists[run_info.path], generator, profile, args)
    except Exception as exc:
        raise RenderStoryboardError(f"ComfyUI画像生成を開始できません: {exc}") from exc
    finally:
        try:
            generator.free_memory()
        except Exception as exc:
            print(f"警告: ComfyUIのメモリ解放に失敗しました: {exc}", file=sys.stderr)

    _write_storyboard_outputs(runs, shot_lists, args.sheet_columns)

    print(f"画像生成完了: 失敗 {failures}件")
    return 1 if failures else 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _make_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except (RenderStoryboardError, StoryboardError, ValueError) as exc:
        print(f"ストーリーボード生成に失敗しました: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
