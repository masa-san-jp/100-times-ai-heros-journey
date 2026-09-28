"""完成済みの物語からショットリストを生成する。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .batch_analyzer import (
    BODY_EXCLUSIONS,
    _call_json_with_retry,
    _estimated_body_char_limit,
    _truncate_body,
)
from .llm_factory import create_provider_client


ALLOWED_ROLES = ("protagonist", "messenger", "supporter", "adversary")
SHOT_PLAN_PATH = Path(__file__).resolve().parent.parent / "config" / "storyboard" / "shot_plan.json"
DEFAULT_STYLE = (
    "cinematic film still, widescreen 16:9 composition, photorealistic, "
    "dramatic natural lighting, film grain, "
    "no text, no watermark, full frame without letterbox bars"
)


class StoryboardError(RuntimeError):
    """ショットリストを作れない入力または設定。"""


@dataclass
class ShotList:
    """保存・表示するショットリスト。"""

    title: str
    unit: str
    shots_per_unit: int
    style: str
    shots: List[Dict[str, Any]]
    run_dir: Path

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "unit": self.unit,
            "shots_per_unit": self.shots_per_unit,
            "style": self.style,
            "shots": self.shots,
        }


@dataclass(frozen=True)
class _Stage:
    number: int
    name: str
    description: str


@dataclass(frozen=True)
class _Chapter:
    number: int
    title: str
    body: str


@dataclass(frozen=True)
class _RunInput:
    run_dir: Path
    title: str
    plot: Tuple[_Stage, ...]
    chapters: Tuple[_Chapter, ...]
    character_names: Mapping[str, str]
    visual_prompts: Mapping[str, str]
    chapter_count: Optional[int]


def _load_shot_plan() -> Mapping[str, Any]:
    try:
        value = json.loads(SHOT_PLAN_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise StoryboardError(f"ショットサイズ設定を読み取れません: {SHOT_PLAN_PATH}") from exc
    if not isinstance(value, Mapping):
        raise StoryboardError(f"ショットサイズ設定の形式が不正です: {SHOT_PLAN_PATH}")
    return value


SHOT_PLAN = _load_shot_plan()
SHOT_SIZES = tuple(str(item) for item in SHOT_PLAN.get("shot_sizes", ()))
SHOT_PROMPT_PHRASES = {
    str(key): str(value)
    for key, value in SHOT_PLAN.get("prompt_phrases", {}).items()
}


def build_shot_list(
    run_dir: str | Path,
    client: Any,
    *,
    unit: str = "auto",
    shots_per_unit: int = 1,
    style: str = DEFAULT_STYLE,
    refresh: bool = False,
    rebuild_prompts: bool = False,
) -> ShotList:
    """完成済みrunの章またはプロット段階からショットリストを作る。

    ``shots.json`` は、再生成を明示しない限りそのまま再利用する。
    ``rebuild_prompts`` の場合だけ、保存済みの構造化項目からプロンプトを
    作り直して保存する。
    """
    run_path = Path(run_dir)
    if unit not in ("auto", "chapter", "stage"):
        raise ValueError("unit must be one of: auto, chapter, stage")
    if not isinstance(shots_per_unit, int) or isinstance(shots_per_unit, bool) or shots_per_unit < 1:
        raise ValueError("shots_per_unit must be a positive integer")
    if not isinstance(style, str) or not style.strip():
        raise ValueError("style must be a non-empty string")

    storyboard_dir = run_path / "storyboard"
    shots_path = storyboard_dir / "shots.json"

    if shots_path.exists() and (not refresh or rebuild_prompts):
        cached = _read_shot_list(shots_path, run_path)
        if rebuild_prompts:
            source = _read_run_input(run_path)
            selected_unit = _cached_unit(source, cached.unit)
            unit_indexes: Dict[int, int] = {}
            for shot in cached.shots:
                if shot.get("status") == "failed":
                    continue
                unit_number = shot.get(selected_unit)
                shot_index = unit_indexes.get(unit_number, 0)
                unit_indexes[unit_number] = shot_index + 1
                plan_stage, shot_size = _shot_size_for_cached_shot(
                    shot, cached, source, shot_index
                )
                shot["plan_stage"] = plan_stage
                shot["shot_size"] = shot_size
                shot["characters"] = _normalise_characters(shot.get("characters", []))
                shot["prompt_en"] = _build_prompt(shot, source.visual_prompts, style)
            cached.style = style
            cached.unit = selected_unit
            _write_outputs(cached)
            return cached

        failed_units = _failed_units(cached)
        if not failed_units:
            if not (storyboard_dir / "shots.md").exists():
                _write_markdown(cached)
            return cached
        source = _read_run_input(run_path)
        selected_unit = _cached_unit(source, cached.unit)
        if client is None:
            raise StoryboardError("失敗ユニットの再生成にはLLMクライアントが必要です。")
        shots = _retry_failed_units(
            cached,
            source,
            selected_unit,
            failed_units,
            client,
            cached.style,
        )
        cached.shots = shots
        _write_outputs(cached)
        return cached

    if rebuild_prompts and not shots_path.exists():
        raise StoryboardError(
            "--rebuild-prompts は既存の storyboard/shots.json が必要です。"
        )

    source = _read_run_input(run_path)
    selected_unit = _select_unit(source, unit)
    if client is None:
        raise StoryboardError("ショット生成にはLLMクライアントが必要です。")
    units = _units_for(source, selected_unit)
    shots: List[Dict[str, Any]] = []
    for unit_number, unit_label, body in units:
        shots.extend(
            _generate_unit_shots(
                source,
                selected_unit,
                unit_number,
                unit_label,
                body,
                shots_per_unit,
                client,
                style,
            )
        )

    result = ShotList(
        title=source.title,
        unit=selected_unit,
        shots_per_unit=shots_per_unit,
        style=style,
        shots=_assign_ids(shots),
        run_dir=run_path,
    )
    _write_outputs(result)
    return result


def _read_run_input(run_dir: Path) -> _RunInput:
    if not run_dir.is_dir():
        raise StoryboardError(f"runディレクトリが見つかりません: {run_dir}")

    metadata_path = run_dir / "metadata.json"
    if not metadata_path.exists():
        raise StoryboardError(
            f"未完成runのため対象外です（metadata.jsonがありません）: {run_dir.name}"
        )
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise StoryboardError(f"metadata.jsonを読み取れません: {metadata_path}") from exc
    if not isinstance(metadata, dict):
        raise StoryboardError(f"metadata.jsonがオブジェクトではありません: {metadata_path}")

    body_paths = sorted(
        path
        for path in run_dir.glob("*.md")
        if path.name not in BODY_EXCLUSIONS
    )
    if not body_paths:
        raise StoryboardError(
            f"未完成runのため対象外です（本文Markdownがありません）: {run_dir.name}"
        )
    body_path = body_paths[0]
    try:
        body = body_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise StoryboardError(f"本文Markdownを読み取れません: {body_path}") from exc
    if not body.strip():
        raise StoryboardError(f"本文Markdownが空です: {body_path}")

    title = _parse_title(body)
    if not title:
        raise StoryboardError("本文Markdownの1行目から作品タイトルを読み取れません。")
    plot = tuple(_parse_plot(body))
    if not plot:
        raise StoryboardError(
            "プロット節の段階が0件のため、章・段階どちらのユニットも作れません。"
        )
    chapters = tuple(_parse_chapters(body))

    character_names = metadata.get("character_names")
    if not isinstance(character_names, Mapping):
        raise StoryboardError("metadata.jsonのcharacter_namesを辞書として読み取れません。")
    missing_names = [role for role in ALLOWED_ROLES if not str(character_names.get(role, "")).strip()]
    if missing_names:
        raise StoryboardError(
            "metadata.jsonのcharacter_namesに不足があります: " + ", ".join(missing_names)
        )

    visual_path = run_dir / "visual_prompts.md"
    if not visual_path.exists():
        raise StoryboardError(f"visual_prompts.mdがありません: {run_dir}")
    try:
        visual_text = visual_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise StoryboardError(f"visual_prompts.mdを読み取れません: {visual_path}") from exc
    visual_prompts = _parse_visual_prompts(visual_text)
    missing_visuals = [role for role in ALLOWED_ROLES if role not in visual_prompts]
    if missing_visuals:
        raise StoryboardError(
            "visual_prompts.mdに外見文が不足しています: " + ", ".join(missing_visuals)
        )

    chapter_count = metadata.get("chapter_count")
    if chapters:
        if (
            not isinstance(chapter_count, int)
            or isinstance(chapter_count, bool)
            or chapter_count < 1
        ):
            print(
                "警告: metadata.jsonのchapter_countが不正です。"
                f" 本文から読み取った{len(chapters)}章を使います。",
                file=sys.stderr,
            )
        elif chapter_count != len(chapters):
            print(
                "警告: metadata.jsonのchapter_countと本文の章数が一致しません。"
                f" 本文から読み取った{len(chapters)}章を使います。",
                file=sys.stderr,
            )

    return _RunInput(
        run_dir=run_dir,
        title=title,
        plot=plot,
        chapters=chapters,
        character_names={role: str(character_names[role]).strip() for role in ALLOWED_ROLES},
        visual_prompts=visual_prompts,
        chapter_count=chapter_count if isinstance(chapter_count, int) else None,
    )


def _parse_title(body: str) -> str:
    first_line = body.lstrip("\ufeff").splitlines()[0] if body.splitlines() else ""
    match = re.match(r"^\s*#\s+(.+?)\s*$", first_line)
    return match.group(1).strip() if match else ""


def _parse_plot(body: str) -> List[_Stage]:
    lines = body.splitlines()
    start = next(
        (index + 1 for index, line in enumerate(lines) if re.match(r"^##\s+プロット\s*$", line.strip())),
        None,
    )
    if start is None:
        return []

    stages: List[_Stage] = []
    current_number: Optional[int] = None
    current_name = ""
    current_description: List[str] = []
    for line in lines[start:]:
        if re.match(r"^#\s+第\d+章", line):
            break
        if re.match(r"^##\s+メタ情報", line):
            break
        if "【各段階の詳細】" in line:
            break
        match = re.match(r"^\s*(\d+)\.\s+(?:\*\*)?(.+?)(?:\*\*)?\s*$", line)
        if match:
            if current_number is not None:
                stages.append(_make_stage(current_number, current_name, current_description))
            current_number = int(match.group(1))
            current_name = match.group(2).strip().strip("*").strip()
            current_description = []
            continue
        if current_number is not None:
            current_description.append(line)
    if current_number is not None:
        stages.append(_make_stage(current_number, current_name, current_description))
    return [stage for stage in stages if stage.name and stage.description]


def _make_stage(number: int, name: str, description: Sequence[str]) -> _Stage:
    text = "\n".join(description).strip()
    return _Stage(number=number, name=name, description=text)


def _parse_chapters(body: str) -> List[_Chapter]:
    lines = body.splitlines()
    headings = [
        (index, match)
        for index, line in enumerate(lines)
        if (match := re.match(r"^#\s*第(\d+)章\s*(?:[:：]\s*)?(.*?)\s*$", line))
    ]
    chapters: List[_Chapter] = []
    for heading_index, (line_index, match) in enumerate(headings):
        end = headings[heading_index + 1][0] if heading_index + 1 < len(headings) else len(lines)
        for index in range(line_index + 1, end):
            if re.match(r"^##\s+メタ情報", lines[index]):
                end = index
                break
        chapter_body = "\n".join(lines[line_index + 1:end]).strip()
        chapters.append(
            _Chapter(number=int(match.group(1)), title=match.group(2).strip(), body=chapter_body)
        )
    return chapters


def _parse_visual_prompts(text: str) -> Dict[str, str]:
    lines = text.splitlines()
    headings = [
        (index, match.group(1).strip())
        for index, line in enumerate(lines)
        if (match := re.match(r"^##\s+(\S+)\s*$", line))
        and match.group(1).strip() in ALLOWED_ROLES
    ]
    prompts: Dict[str, str] = {}
    for position, (line_index, role) in enumerate(headings):
        end = headings[position + 1][0] if position + 1 < len(headings) else len(lines)
        paragraph: List[str] = []
        for line in lines[line_index + 1:end]:
            if not paragraph and not line.strip():
                continue
            if paragraph and not line.strip():
                break
            paragraph.append(line)
        value = "\n".join(paragraph).strip()
        if value:
            prompts[role] = value
    return prompts


def _select_unit(source: _RunInput, requested: str) -> str:
    if requested == "auto":
        return "chapter" if source.chapters else "stage"
    if requested == "chapter" and not source.chapters:
        raise StoryboardError("--unit chapter は章本文がないrunでは使えません。")
    return requested


def _units_for(source: _RunInput, selected_unit: str) -> List[Tuple[int, str, str]]:
    if selected_unit == "chapter":
        return [(chapter.number, f"第{chapter.number}章: {chapter.title}", chapter.body) for chapter in source.chapters]
    return [(stage.number, f"{stage.number}. {stage.name}", stage.description) for stage in source.plot]


def _stage_plan(stage_count: int) -> List[str]:
    configured = SHOT_PLAN.get("stage_plans", {}).get(str(stage_count))
    if isinstance(configured, list) and len(configured) == stage_count:
        return [str(size) for size in configured]
    if stage_count < 1:
        raise StoryboardError("プロット段階数が1未満です。")
    twelve_stage_plan = SHOT_PLAN.get("stage_plans", {}).get("12")
    if not isinstance(twelve_stage_plan, list) or len(twelve_stage_plan) != 12:
        raise StoryboardError(f"12段階のショットサイズ設定が不正です: {SHOT_PLAN_PATH}")
    return [
        str(twelve_stage_plan[min(12, max(1, round((index - 0.5) / stage_count * 12 + 0.5))) - 1])
        for index in range(1, stage_count + 1)
    ]


def _plan_stage_for_unit(
    selected_unit: str, unit_number: int, unit_count: int, stage_count: int
) -> int:
    if selected_unit == "stage":
        return max(1, min(stage_count, unit_number))
    return max(1, min(stage_count, round((unit_number - 0.5) / unit_count * stage_count + 0.5)))


def _shot_sizes_for_unit(
    selected_unit: str, unit_number: int, unit_count: int, stage_count: int, shots_per_unit: int
) -> Tuple[int, List[str]]:
    plan_stage = _plan_stage_for_unit(selected_unit, unit_number, unit_count, stage_count)
    base_size = _stage_plan(stage_count)[plan_stage - 1]
    base_index = SHOT_SIZES.index(base_size)
    sizes = []
    for shot_index in range(shots_per_unit):
        if shot_index == 0:
            size_index = base_index
        else:
            direction = 1 if shot_index % 2 else -1
            size_index = max(0, min(len(SHOT_SIZES) - 1, base_index + direction))
        sizes.append(SHOT_SIZES[size_index])
    return plan_stage, sizes


def _shot_size_for_cached_shot(
    shot: Mapping[str, Any], cached: ShotList, source: _RunInput, shot_index: int
) -> Tuple[int, str]:
    unit_number = shot.get(cached.unit)
    if not isinstance(unit_number, int) or isinstance(unit_number, bool):
        raise StoryboardError(f"shots.jsonの{cached.unit}番号が不正です。")
    unit_count = len(source.chapters) if cached.unit == "chapter" else len(source.plot)
    plan_stage, sizes = _shot_sizes_for_unit(
        cached.unit,
        unit_number,
        unit_count,
        len(source.plot),
        cached.shots_per_unit,
    )
    return plan_stage, sizes[min(shot_index, len(sizes) - 1)]


def _cached_unit(source: _RunInput, cached_unit: str) -> str:
    if cached_unit not in ("chapter", "stage"):
        raise StoryboardError(f"shots.jsonのunitが不正です: {cached_unit}")
    if cached_unit == "chapter" and not source.chapters:
        raise StoryboardError("shots.jsonは章単位ですが、本文に章がありません。")
    return cached_unit


def _failed_units(cached: ShotList) -> set[int]:
    failed: set[int] = set()
    for shot in cached.shots:
        if shot.get("status") != "failed":
            continue
        value = shot.get(cached.unit)
        if isinstance(value, int) and not isinstance(value, bool):
            failed.add(value)
    return failed


def _retry_failed_units(
    cached: ShotList,
    source: _RunInput,
    selected_unit: str,
    failed_units: set[int],
    client: Any,
    style: str,
) -> List[Dict[str, Any]]:
    units = {
        number: (label, body)
        for number, label, body in _units_for(source, selected_unit)
    }
    regenerated: Dict[int, List[Dict[str, Any]]] = {}
    for number in failed_units:
        if number not in units:
            raise StoryboardError(
                f"shots.jsonの失敗ユニットが入力本文にありません: {selected_unit}={number}"
            )
        label, body = units[number]
        regenerated[number] = _generate_unit_shots(
            source,
            selected_unit,
            number,
            label,
            body,
            cached.shots_per_unit,
            client,
            style,
        )

    result: List[Dict[str, Any]] = []
    inserted: set[int] = set()
    kept_ids = True
    for shot in cached.shots:
        value = shot.get(selected_unit)
        if value not in failed_units:
            result.append(shot)
            continue
        if value in inserted:
            continue
        replacement = regenerated[value]
        old_ids = [
            item.get("id")
            for item in cached.shots
            if item.get(selected_unit) == value and item.get("status") == "failed"
        ]
        if len(replacement) == len(old_ids):
            for item, old_id in zip(replacement, old_ids):
                item["id"] = old_id
        else:
            kept_ids = False
        result.extend(replacement)
        inserted.add(value)
    if not kept_ids:
        result = _assign_ids(result)
    return result


def _generate_unit_shots(
    source: _RunInput,
    selected_unit: str,
    unit_number: int,
    unit_label: str,
    body: str,
    shots_per_unit: int,
    client: Any,
    style: str,
) -> List[Dict[str, Any]]:
    prompt_body = _body_for_prompt(body, client)
    unit_count = len(source.chapters) if selected_unit == "chapter" else len(source.plot)
    plan_stage, shot_sizes = _shot_sizes_for_unit(
        selected_unit,
        unit_number,
        unit_count,
        len(source.plot),
        shots_per_unit,
    )
    prompt = _shot_prompt(
        source,
        selected_unit,
        unit_number,
        unit_label,
        prompt_body,
        shots_per_unit,
        plan_stage,
        shot_sizes,
    )
    response = _call_json_with_retry(
        client,
        prompt,
        _shot_system(),
        validator=_valid_shot_response,
    )
    if response is None:
        return [
            _failed_shot(
                selected_unit,
                unit_number,
                unit_label,
                "JSON応答の取得または検証に失敗しました",
                plan_stage,
                shot_sizes[0],
            )
        ]

    raw_shots = _raw_shots(response)
    if len(raw_shots) != shots_per_unit:
        print(
            f"警告: {unit_label} のショット数が指定値と異なります "
            f"（指定={shots_per_unit}, 取得={len(raw_shots)}）。補正しません。",
            file=sys.stderr,
        )
    result = []
    for shot_index, raw_shot in enumerate(raw_shots):
        shot = _normalise_shot(raw_shot, selected_unit, unit_number, unit_label)
        shot["plan_stage"] = plan_stage
        shot["shot_size"] = shot_sizes[min(shot_index, len(shot_sizes) - 1)]
        shot["prompt_en"] = _build_prompt(shot, source.visual_prompts, style)
        result.append(shot)
    return result


def _body_for_prompt(body: str, client: Any) -> str:
    config = getattr(client, "config", None)
    num_ctx = getattr(config, "num_ctx", None)
    if not isinstance(num_ctx, int) or num_ctx < 1 or len(body) <= _estimated_body_char_limit(num_ctx):
        return body
    limit = _estimated_body_char_limit(num_ctx)
    print(
        f"警告: ユニット本文を推定コンテキスト上限に合わせて中略しました "
        f"（{len(body)}文字 -> 約{limit}文字）。",
        file=sys.stderr,
    )
    return _truncate_body(body, limit)


def _shot_system() -> str:
    return (
        "あなたは物語の絵コンテ台本を作るアシスタントです。"
        "指定されたJSONオブジェクトだけを返してください。"
        "prompt_enは出力せず、画像プロンプトはPython側で組み立てます。"
    )


def _shot_prompt(
    source: _RunInput,
    selected_unit: str,
    unit_number: int,
    unit_label: str,
    body: str,
    shots_per_unit: int,
    plan_stage: int,
    shot_sizes: Sequence[str],
) -> str:
    plot = [
        {"stage": stage.number, "name": stage.name, "description": stage.description}
        for stage in source.plot
    ]
    characters = [
        {
            "role": role,
            "name": source.character_names[role],
            "appearance": source.visual_prompts[role],
        }
        for role in ALLOWED_ROLES
    ]
    shot_size_lines = "\n".join(
        f"ショット{index + 1}: shot_size: {size}"
        for index, size in enumerate(shot_sizes)
    )
    return f"""作品タイトル: {source.title}

プロット全体:
{json.dumps(plot, ensure_ascii=False, indent=2)}

登場人物（役割・名前・外見文）:
{json.dumps(characters, ensure_ascii=False, indent=2)}

対象ユニット: {selected_unit} / {unit_label}
plan_stage: {plan_stage}
対象ユニット本文:
---
{body}
---

対象ユニットからショットを{shots_per_unit}件作成してください。title_ja と caption_ja は日本語で書いてください。
各ショットの shot_size はPython側で次の値に決定済みです。このサイズで成立する場面の setting / action を書いてください。
{shot_size_lines}
extreme_long / long は風景・建物・天候・群衆などの環境を主役にし、人物は画面の中で小さくしてください。
close_up は表情や手元などの一点に絞ってください。full / medium は指定された画面範囲に合わせてください。
setting / action / camera / mood は必ず英語で書いてください。camera と mood には映画撮影用語を使ってください。
camera にはショットサイズを表す語を含めず、アングル・レンズ・カメラの動きだけを書いてください。ショットサイズは shot_size が正です。
action の中で人物を指すときは名前を使わず、必ず the protagonist / the messenger / the supporter / the adversary の呼び名を使ってください。
各ショットには、次のJSONキーだけを使ってください。
{{
  "shots": [
    {{
      "title_ja": "静かな川辺",
      "caption_ja": "主人公は夜明けの川辺で、決意を新たにする。",
      "characters": ["protagonist"],
      "setting": "quiet riverside at dawn, clear sky",
      "action": "the protagonist looks across the river while the supporter watches from behind",
      "camera": "low angle, 35mm lens, slow dolly",
      "mood": "cool blue pre-dawn light gradually warming to golden hour"
    }}
  ]
}}
charactersには protagonist / messenger / supporter / adversary の役割名だけを入れ、1ショット0〜2人を目安にしてください。
"""


def _valid_shot_response(value: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
    if not isinstance(value, Mapping):
        return None
    raw = value.get("shots")
    if not isinstance(raw, list):
        return None
    if not all(isinstance(item, Mapping) for item in raw):
        return None
    return value


def _raw_shots(value: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    raw = value.get("shots", [])
    return [item for item in raw if isinstance(item, Mapping)]


def _normalise_shot(
    value: Mapping[str, Any],
    selected_unit: str,
    unit_number: int,
    unit_label: str,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {selected_unit: unit_number}
    title = str(value.get("title_ja", "")).strip() or f"{unit_label}の場面"
    action = _text_value(value.get("action", ""))
    result.update(
        {
            "title_ja": title,
            "caption_ja": str(value.get("caption_ja", "")).strip() or action,
            "characters": _normalise_characters(value.get("characters", [])),
            "setting": _text_value(value.get("setting", "")),
            "action": action,
            "camera": _text_value(value.get("camera", "")),
            "mood": _text_value(value.get("mood", "")),
            "prompt_en": "",
        }
    )
    return result


def _text_value(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Mapping) or isinstance(value, (list, tuple)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value).strip() if value is not None else ""


def _normalise_characters(value: Any) -> List[str]:
    if not isinstance(value, (list, tuple)):
        return []
    characters: List[str] = []
    for item in value:
        role = str(item).strip()
        if role in ALLOWED_ROLES and role not in characters:
            characters.append(role)
    if len(characters) <= 2:
        return characters
    if "protagonist" in characters:
        return ["protagonist", next(role for role in characters if role != "protagonist")]
    return characters[:2]


def _build_prompt(
    shot: Mapping[str, Any],
    visual_prompts: Mapping[str, str],
    style: str,
) -> str:
    shot_size = str(shot.get("shot_size", "")).strip()
    prompt_phrase = SHOT_PROMPT_PHRASES.get(shot_size)
    parts = [prompt_phrase] if prompt_phrase else []
    setting = str(shot.get("setting", "")).strip()
    action = str(shot.get("action", "")).strip()
    camera = str(shot.get("camera", "")).strip()
    mood = str(shot.get("mood", "")).strip()
    if setting:
        parts.append(setting)
    if action:
        parts.append(action)
    if camera:
        parts.append(f"Camera: {camera}")
    if mood:
        parts.append(f"Mood and lighting: {mood}")
    for role in _normalise_characters(shot.get("characters", [])):
        appearance = _appearance_without_mood(visual_prompts.get(role, ""))
        if shot_size in {"extreme_long", "long", "full"}:
            appearance = _first_sentences(appearance, 2)
        if appearance:
            parts.append(f"The {role}: {appearance}")
    parts.append(style.strip())
    return ", ".join(parts)


def _appearance_without_mood(text: str) -> str:
    """外見文からショットごとに変わる雰囲気・照明の文を除く。"""
    parts = re.split(r"(?<=\.\s)", text.strip())
    kept = [
        part
        for part in parts
        if not re.match(r"^\s*(?:Atmosphere|Lighting):", part)
    ]
    return "".join(kept).strip()


def _first_sentences(text: str, count: int) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return " ".join(sentences[:count]).strip()


def _failed_shot(
    selected_unit: str,
    unit_number: int,
    unit_label: str,
    error: str,
    plan_stage: Optional[int] = None,
    shot_size: Optional[str] = None,
) -> Dict[str, Any]:
    result = {
        selected_unit: unit_number,
        "title_ja": f"{unit_label}（生成失敗）",
        "caption_ja": "このユニットのショットは生成できませんでした。",
        "characters": [],
        "setting": "",
        "action": "",
        "camera": "",
        "mood": "",
        "prompt_en": "",
        "status": "failed",
        "error": error,
    }
    if plan_stage is not None:
        result["plan_stage"] = plan_stage
    if shot_size is not None:
        result["shot_size"] = shot_size
    return result


def _assign_ids(shots: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result = []
    for index, shot in enumerate(shots, start=1):
        item = dict(shot)
        item["id"] = f"{index:02d}"
        result.append(item)
    return result


def _read_shot_list(path: Path, run_dir: Path) -> ShotList:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise StoryboardError(f"shots.jsonを読み取れません: {path}") from exc
    if not isinstance(value, Mapping) or not isinstance(value.get("shots"), list):
        raise StoryboardError(f"shots.jsonの形式が不正です: {path}")
    try:
        shots_per_unit = int(value.get("shots_per_unit", 1))
    except (TypeError, ValueError) as exc:
        raise StoryboardError(f"shots.jsonのshots_per_unitが不正です: {path}") from exc
    if shots_per_unit < 1:
        raise StoryboardError(f"shots.jsonのshots_per_unitが不正です: {path}")
    return ShotList(
        title=str(value.get("title", "")),
        unit=str(value.get("unit", "auto")),
        shots_per_unit=shots_per_unit,
        style=str(value.get("style", DEFAULT_STYLE)),
        shots=[dict(item) for item in value["shots"] if isinstance(item, Mapping)],
        run_dir=run_dir,
    )


def read_shot_list(run_dir: str | Path) -> ShotList:
    """既存のrunから保存済みショットリストを読み込む。"""
    run_path = Path(run_dir)
    return _read_shot_list(run_path / "storyboard" / "shots.json", run_path)


def has_failed_shots(shot_list: ShotList) -> bool:
    """ショットリストにLLM生成失敗のショットが含まれるか返す。"""
    return bool(_failed_units(shot_list))


def _write_outputs(result: ShotList) -> None:
    storyboard_dir = result.run_dir / "storyboard"
    storyboard_dir.mkdir(parents=True, exist_ok=True)
    (storyboard_dir / "shots.json").write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_markdown(result)


def _write_markdown(result: ShotList) -> None:
    lines = [f"# ショットリスト: {result.title}", ""]
    for shot in result.shots:
        shot_id = shot.get("id", "??")
        label = "生成失敗" if shot.get("status") == "failed" else str(shot.get("title_ja", ""))
        lines.extend([f"## {shot_id}. {label}", ""])
        if shot.get("status") == "failed":
            lines.extend([f"- エラー: {shot.get('error', '不明')}", ""])
            continue
        unit_label = "章" if result.unit == "chapter" else "段階"
        lines.extend(
            [
                f"- {unit_label}: {shot.get(result.unit, '')}",
                f"- キャプション: {shot.get('caption_ja', '')}",
                f"- 登場人物: {', '.join(shot.get('characters', [])) or 'なし'}",
                f"- カメラ: {shot.get('shot_size', '')} / {shot.get('camera', '')}",
                "",
            ]
        )
    (result.run_dir / "storyboard" / "shots.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="完成済みrunからショットリストを生成")
    parser.add_argument("run_dir", help="完成済みrunのディレクトリ")
    parser.add_argument("--provider", choices=("ollama", "openai", "anthropic", "deepseek"), default="ollama")
    parser.add_argument("--model", default=None)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--unit", choices=("auto", "chapter", "stage"), default="auto")
    parser.add_argument("--shots-per-unit", type=int, default=1)
    parser.add_argument("--style", default=DEFAULT_STYLE)
    parser.add_argument("--refresh-shots", action="store_true")
    parser.add_argument("--rebuild-prompts", action="store_true")
    args = parser.parse_args(argv)
    if args.shots_per_unit < 1:
        parser.error("--shots-per-unitは1以上で指定してください")

    try:
        shots_path = Path(args.run_dir) / "storyboard" / "shots.json"
        has_failed_cache = False
        if shots_path.exists() and not args.rebuild_prompts:
            try:
                has_failed_cache = bool(
                    _failed_units(_read_shot_list(shots_path, Path(args.run_dir)))
                )
            except StoryboardError:
                pass
        needs_client = not args.rebuild_prompts and (
            args.refresh_shots or not shots_path.exists() or has_failed_cache
        )
        if needs_client:
            client, selected_model = create_provider_client(
                args.provider, args.model, args.timeout
            )
        else:
            client, selected_model = None, "cache"
        result = build_shot_list(
            args.run_dir,
            client,
            unit=args.unit,
            shots_per_unit=args.shots_per_unit,
            style=args.style,
            refresh=args.refresh_shots,
            rebuild_prompts=args.rebuild_prompts,
        )
    except Exception as exc:
        print(f"ショットリスト生成に失敗しました: {exc}", file=sys.stderr)
        return 1

    model_label = selected_model if selected_model != "cache" else "キャッシュ再利用"
    print(f"ショットリスト生成完了: {len(result.shots)}件（{model_label}）")
    print(f"出力: {args.run_dir}/storyboard/shots.json")
    print(f"出力: {args.run_dir}/storyboard/shots.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_STYLE",
    "ShotList",
    "StoryboardError",
    "build_shot_list",
    "has_failed_shots",
    "read_shot_list",
]
