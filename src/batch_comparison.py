"""物語構造の異なる複数バッチを並べて比べる（LLMを使わない決定的な比較）。"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .batch_analyzer import (
    FREQUENCY_KEYS,
    BatchAnalysisError,
    BatchAnalyzer,
    _escape_table,
    _read_json_object,
)
from .plot_generator import STORY_STRUCTURES

REPORT_MD = "comparison_report.md"
REPORT_JSON = "comparison_report.json"


def compare_batches(
    batch_dirs: Sequence[str | Path],
    output_dir: Optional[str | Path] = None,
    allow_different_narratives: bool = False,
) -> Dict[str, Any]:
    """複数バッチの比較レポートを作って保存し、JSON相当の辞書を返す。

    Args:
        batch_dirs: 比べるバッチディレクトリ（2つ以上）。
        output_dir: レポートの保存先。未指定なら ``output/comparison_<日時>``。
        allow_different_narratives: 元ナラティブが異なるバッチの比較を許すか。
    """
    paths = [Path(path) for path in batch_dirs]
    if len(paths) < 2:
        raise BatchAnalysisError("比べるバッチを2つ以上指定してください。")
    if len({path.resolve() for path in paths}) != len(paths):
        raise BatchAnalysisError("同じバッチが重複して指定されています。")

    out = Path(output_dir) if output_dir else Path("output") / (
        "comparison_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    )

    batches = [_batch_payload(path, out) for path in paths]
    narratives = [_read_json_object(path / "narrative.json") for path in paths]
    same_narrative = all(narratives) and all(n == narratives[0] for n in narratives)
    if not same_narrative and not allow_different_narratives:
        raise BatchAnalysisError(
            "バッチの元ナラティブ（narrative.json）が一致しないか、記録がありません。"
            "それでも比べる場合は --allow-different-narratives を指定してください。"
        )

    report: Dict[str, Any] = {
        "same_narrative": same_narrative,
        "batches": batches,
        "element_frequencies": _element_frequencies(batches),
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / REPORT_JSON).write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out / REPORT_MD).write_text(_render_markdown(report), encoding="utf-8")
    report["output_dir"] = str(out)
    return report


def _batch_payload(path: Path, out: Path) -> Dict[str, Any]:
    if not path.is_dir():
        raise BatchAnalysisError(f"バッチディレクトリが見つかりません: {path}")
    analyzer = BatchAnalyzer(path)
    runs, skipped = analyzer._discover_runs()
    if not runs:
        raise BatchAnalysisError(f"完了済みrunが0件です: {path}")

    manifest = _read_json_object(path / "batch_manifest.json")
    structure = manifest.get("structure")
    if not structure:
        count = manifest.get("journey_stage_count")
        structure = f"journey-{count}" if count in (11, 12) else "記録なし"
    known = STORY_STRUCTURES.get(structure)

    works = []
    chapter_counts = []
    for run in runs:
        work = BatchAnalyzer._work_payload(run)
        chapters = run.metadata.get("chapter_count")
        if isinstance(chapters, int) and not isinstance(chapters, bool):
            chapter_counts.append(chapters)
        work["chapter_count"] = chapters if isinstance(chapters, int) else None
        # レポートの保存先から本文へのリンクにする。
        work["body_markdown"] = Path(
            os.path.relpath(run.body_path.absolute(), out.absolute())
        ).as_posix()
        works.append(work)

    frequencies = BatchAnalyzer._frequency_payload(runs)
    return {
        "name": path.name,
        "path": str(path),
        "structure": structure,
        "structure_label": known.label if known else "不明",
        # 作品ごとに段を選ぶ構造（プロップの31機能）は段数が作品ごとに違う。段の一覧は候補の全体。
        "stage_count": (
            "作品ごと" if known and known.per_work
            else known.stage_count if known else manifest.get("journey_stage_count")
        ),
        "stage_names": [s["name"] for s in known.stages] if known else [],
        "model": manifest.get("model", "記録なし"),
        "provider": manifest.get("provider", "記録なし"),
        "work_count": len(runs),
        "skipped_count": len(skipped),
        "average_chapter_count": (
            round(sum(chapter_counts) / len(chapter_counts), 1) if chapter_counts else None
        ),
        "plot_types": [
            {"value": item["value"], "count": item["count"]}
            for item in frequencies["plot_type"]
        ],
        "selected_elements": {
            key: {item["value"]: item["count"] for item in frequencies[key]}
            for key in FREQUENCY_KEYS
        },
        "works": works,
    }


def _element_frequencies(batches: Sequence[Mapping[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """要素ごとに、各バッチでの出現回数を横に並べる。"""
    result: Dict[str, List[Dict[str, Any]]] = {}
    for key in FREQUENCY_KEYS:
        values = sorted(
            {value for batch in batches for value in batch["selected_elements"][key]}
        )
        rows = [
            {
                "value": value,
                "counts": [batch["selected_elements"][key].get(value, 0) for batch in batches],
            }
            for value in values
        ]
        rows.sort(key=lambda row: (-sum(row["counts"]), row["value"]))
        result[key] = rows
    return result


def _render_markdown(report: Mapping[str, Any]) -> str:
    batches = report["batches"]
    names = [_escape_table(batch["name"]) for batch in batches]
    lines = [
        "# 物語構造の比較レポート",
        "",
        "LLMを使わない決定的な集計です。構造の良し悪しは判定していません。",
        "",
        "- 元ナラティブ: "
        + ("すべてのバッチで一致" if report["same_narrative"] else "一致しない（指定により比較）"),
        "",
        "## 概要",
        "",
        "| 項目 | " + " | ".join(names) + " |",
        "| --- |" + " --- |" * len(batches),
    ]

    def row(label: str, values: Sequence[Any]) -> None:
        lines.append(
            f"| {label} | " + " | ".join(_escape_table(v) for v in values) + " |"
        )

    row("構造", [f"{b['structure']}（{b['structure_label']}）" for b in batches])
    row("段数", [b["stage_count"] if b["stage_count"] is not None else "不明" for b in batches])
    row("作品数", [b["work_count"] for b in batches])
    row("スキップ数", [b["skipped_count"] for b in batches])
    row(
        "平均章数",
        [b["average_chapter_count"] if b["average_chapter_count"] is not None else "不明" for b in batches],
    )
    row(
        "プロット形式",
        [", ".join(f"{p['value']}×{p['count']}" for p in b["plot_types"]) or "—" for b in batches],
    )
    row("モデル", [b["model"] for b in batches])

    lines.extend(["", "## 構造の段", ""])
    for batch in batches:
        stages = " → ".join(batch["stage_names"]) or "（定義が見つかりません）"
        lines.append(f"- {_escape_table(batch['name'])}: {stages}")

    lines.extend(["", "## 選ばれた要素の頻度", ""])
    for key, rows in report["element_frequencies"].items():
        lines.extend([
            f"### {key}",
            "",
            "| 値 | " + " | ".join(names) + " |",
            "| --- |" + " ---: |" * len(batches),
        ])
        if rows:
            for item in rows:
                row(_escape_table(item["value"]), item["counts"])
        else:
            lines.append("| （該当なし） |" + " 0 |" * len(batches))
        lines.append("")

    lines.extend(["## 作品一覧", ""])
    for batch in batches:
        lines.extend([
            f"### {_escape_table(batch['name'])}（{batch['structure']}）",
            "",
            "| run | タイトル | プロット形式 | 主人公 | 章数 | 本文 |",
            "| --- | --- | --- | --- | ---: | --- |",
        ])
        for work in batch["works"]:
            lines.append(
                "| {run} | {title} | {plot} | {protagonist} | {chapters} | [Markdown]({link}) |".format(
                    run=_escape_table(work["run"]),
                    title=_escape_table(work["title"]),
                    plot=_escape_table(work["plot_type"]),
                    protagonist=_escape_table(work["protagonist"]),
                    chapters=work["chapter_count"] if work["chapter_count"] is not None else "不明",
                    link=work["body_markdown"],
                )
            )
        lines.append("")
    return "\n".join(lines)


__all__ = ["compare_batches", "REPORT_MD", "REPORT_JSON"]
