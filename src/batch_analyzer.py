"""生成済みバッチを決定的に集計し、任意でLLM横断解釈を行う。"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


SUMMARY_KEYS = (
    "protagonist_desire",
    "adversary_type",
    "central_loss",
    "ending",
    "key_motifs",
)
FREQUENCY_KEYS = ("want", "ability", "role", "narrative")
BODY_EXCLUSIONS = {
    "narrative_analysis.md",
    "world.md",
    "plot_skeleton.md",
    "visual_prompts.md",
}
DESIGN_PRINCIPLE = (
    "この分析は解釈を押し付けるためのものではありません。断定や診断をせず、"
    "本文中の実例に基づく傾向を示し、元ナラティブとの関係は問いの形で提示してください。"
)
DEFAULT_ANALYSIS_NUM_CTX = 32768
# gpt-ossの分析JSONに使う最大出力枠（既存CLIの設定）を確保する。
CONTEXT_OUTPUT_RESERVE_TOKENS = 8192
CONTEXT_INSTRUCTION_RESERVE_CHARS = 4000
ESTIMATED_CHARS_PER_TOKEN = 1  # 日本語は1文字≒1トークン以上になり得るため安全側に見積もる
MIN_ESTIMATED_BODY_CHARS = 200
TRUNCATION_MARKER = (
    "\n\n[本文はコンテキスト上限の目安に合わせ、冒頭と末尾を残して中略しています]\n\n"
)


class BatchAnalysisError(RuntimeError):
    """バッチ分析を開始できない場合のエラー。"""


@dataclass(frozen=True)
class CompletedRun:
    """分析対象として認められた1作品。"""

    number: int
    name: str
    path: Path
    metadata: Dict[str, Any]
    body_path: Path
    body_text: str

    @property
    def body_link(self) -> str:
        return self.body_path.relative_to(self.path.parent).as_posix()


class BatchAnalyzer:
    """バッチディレクトリの集計・横断解釈を担当する。"""

    def __init__(
        self,
        batch_dir: str | Path,
        client: Optional[Any] = None,
        provider: str = "ollama",
        model: Optional[str] = None,
        timeout: int = 600,
        num_ctx: Optional[int] = DEFAULT_ANALYSIS_NUM_CTX,
    ):
        self.batch_dir = Path(batch_dir)
        self.client = client
        self.provider = provider
        self.model = model
        self.timeout = timeout
        self.num_ctx = num_ctx

    def analyze(self, no_llm: bool = False, refresh: bool = False) -> Dict[str, Any]:
        """分析を実行し、JSONレポート相当の辞書を返して保存する。"""
        if not self.batch_dir.is_dir():
            raise BatchAnalysisError(
                f"バッチディレクトリが見つかりません: {self.batch_dir}"
            )

        manifest = _read_json_object(self.batch_dir / "batch_manifest.json")
        narrative = _read_json_object(self.batch_dir / "narrative.json")
        runs, skipped_names = self._discover_runs()
        if not runs:
            raise BatchAnalysisError(
                "完了済みrunが0件です。metadata.jsonと本文Markdownがあるrunを用意してください。"
            )

        report: Dict[str, Any] = {
            "overview": {
                "target_count": len(runs),
                "completed_count": len(runs),
                "skipped_count": len(skipped_names),
                "skipped_runs": skipped_names,
                "model": manifest.get("model", "記録なし"),
                "provider": manifest.get("provider", "記録なし"),
                "settings": manifest,
            },
            "works": [self._work_payload(run) for run in runs],
            "frequencies": self._frequency_payload(runs),
        }

        if no_llm:
            report["cross_analysis"] = {
                "enabled": False,
                "status": "省略",
                "summaries": [],
                "patterns": [],
            }
        else:
            client = self._get_client()
            summaries, successful = self._extract_summaries(
                runs, client, refresh=refresh
            )
            if successful:
                patterns, pattern_status = self._integrate_patterns(
                    successful, narrative, client
                )
            else:
                patterns, pattern_status = [], "生成失敗"
            report["cross_analysis"] = {
                "enabled": True,
                "status": pattern_status,
                "summaries": [
                    {"run": run.name, **summary}
                    for run, summary in zip(runs, summaries)
                ],
                "patterns": patterns,
            }

        self._write_reports(report, runs)
        return report

    def validate_target(self) -> None:
        """LLMクライアントを作る前に、分析対象があることを確認する。"""
        if not self.batch_dir.is_dir():
            raise BatchAnalysisError(
                f"バッチディレクトリが見つかりません: {self.batch_dir}"
            )
        runs, _skipped = self._discover_runs()
        if not runs:
            raise BatchAnalysisError(
                "完了済みrunが0件です。metadata.jsonと本文Markdownがあるrunを用意してください。"
            )

    def _discover_runs(self) -> Tuple[List[CompletedRun], List[str]]:
        runs: List[CompletedRun] = []
        skipped: List[str] = []
        candidates = sorted(
            (
                path
                for path in self.batch_dir.glob("run_*")
                if path.is_dir() and path.name[4:].isdigit()
            ),
            key=lambda path: (int(path.name[4:]), path.name),
        )

        for run_dir in candidates:
            metadata_path = run_dir / "metadata.json"
            body_paths = sorted(
                path
                for path in run_dir.glob("*.md")
                if path.name not in BODY_EXCLUSIONS
            )
            if not metadata_path.exists() or not body_paths:
                skipped.append(run_dir.name)
                continue
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                body_text = body_paths[0].read_text(encoding="utf-8")
            except (OSError, UnicodeError, json.JSONDecodeError):
                skipped.append(run_dir.name)
                continue
            if not isinstance(metadata, dict) or not body_text.strip():
                skipped.append(run_dir.name)
                continue
            runs.append(
                CompletedRun(
                    number=int(run_dir.name[4:]),
                    name=run_dir.name,
                    path=run_dir,
                    metadata=metadata,
                    body_path=body_paths[0],
                    body_text=body_text,
                )
            )
        return runs, skipped

    @staticmethod
    def _work_payload(run: CompletedRun) -> Dict[str, Any]:
        character_names = run.metadata.get("character_names", {})
        if not isinstance(character_names, Mapping):
            character_names = {}
        return {
            "run": run.name,
            "title": str(run.metadata.get("title", run.body_path.stem)),
            "plot_type": _plot_type_name(run.metadata.get("plot_type", "")),
            "protagonist": str(character_names.get("protagonist", "不明")),
            "body_markdown": run.body_link,
        }

    @staticmethod
    def _frequency_payload(runs: Sequence[CompletedRun]) -> Dict[str, List[Dict[str, Any]]]:
        values: Dict[str, Dict[str, List[str]]] = {
            key: {} for key in ("plot_type", *FREQUENCY_KEYS)
        }
        for run in runs:
            plot_name = _plot_type_name(run.metadata.get("plot_type", ""))
            _add_frequency(values["plot_type"], plot_name, run.name)
            selected = run.metadata.get("selected_elements", {})
            if not isinstance(selected, Mapping):
                continue
            for key in FREQUENCY_KEYS:
                value = selected.get(key)
                if value is None or not str(value).strip():
                    continue
                _add_frequency(values[key], str(value).strip(), run.name)

        result: Dict[str, List[Dict[str, Any]]] = {}
        for key, items in values.items():
            ordered = sorted(
                items.items(),
                key=lambda item: (-len(item[1]), item[0]),
            )
            result[key] = [
                {"value": value, "count": len(run_names), "runs": run_names}
                for value, run_names in ordered
            ]
        return result

    def _get_client(self) -> Any:
        if self.client is None:
            from .llm_factory import create_provider_client

            self.client, selected_model = create_provider_client(
                self.provider,
                self.model,
                self.timeout,
                num_ctx=self.num_ctx,
            )
            if self.model is None:
                self.model = selected_model
        return self.client

    def _extract_summaries(
        self,
        runs: Sequence[CompletedRun],
        client: Any,
        refresh: bool,
    ) -> Tuple[List[Dict[str, Any]], List[Tuple[CompletedRun, Dict[str, Any]]]]:
        summaries = []
        successful = []
        for run in runs:
            cache_path = run.path / "cross_summary.json"
            cached = None if refresh else _read_summary(cache_path)
            if cached is not None and not _is_failed_summary(cached):
                summaries.append(cached)
                successful.append((run, cached))
                continue

            prompt = _summary_prompt(run, self._body_for_prompt(run))
            result = _call_json_with_retry(
                client,
                prompt,
                _summary_system(),
                validator=_normalise_summary,
            )
            summary = _normalise_summary(result) if result is not None else None
            if summary is None:
                summary = _failed_summary()
                # 失敗結果を残さず、次回実行で必ず再抽出できるようにする。
                cache_path.unlink(missing_ok=True)
            else:
                cache_path.write_text(
                    json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                successful.append((run, summary))
            summaries.append(summary)
        return summaries, successful

    def _integrate_patterns(
        self,
        successful: Sequence[Tuple[CompletedRun, Mapping[str, Any]]],
        narrative: Mapping[str, Any],
        client: Any,
    ) -> Tuple[List[Dict[str, Any]], str]:
        runs = [run for run, _summary in successful]
        summaries = [summary for _run, summary in successful]
        prompt = _integration_prompt(runs, summaries, narrative)
        result = _call_json_with_retry(
            client,
            prompt,
            _integration_system(),
            validator=lambda value: _normalise_patterns(value, runs),
        )
        if result is None:
            return [], "生成失敗"
        patterns = _normalise_patterns(result, runs)
        if patterns is None:
            return [], "生成失敗"
        return patterns, "完了"

    def _write_reports(
        self,
        report: Mapping[str, Any],
        runs: Sequence[CompletedRun],
    ) -> None:
        (self.batch_dir / "batch_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (self.batch_dir / "batch_report.md").write_text(
            _render_markdown(report, runs),
            encoding="utf-8",
        )

    def _body_for_prompt(self, run: CompletedRun) -> str:
        if self.provider.lower() != "ollama" or self.num_ctx is None:
            return run.body_text

        limit = _estimated_body_char_limit(self.num_ctx)
        if len(run.body_text) <= limit:
            return run.body_text

        body = _truncate_body(run.body_text, limit)
        print(
            f"警告: {run.name} の本文を推定コンテキスト上限に合わせて中略しました "
            f"（{len(run.body_text)}文字 -> 約{limit}文字）。",
            file=sys.stderr,
        )
        return body


def analyze_batch(
    batch_dir: str | Path,
    *,
    no_llm: bool = False,
    refresh: bool = False,
    client: Optional[Any] = None,
    provider: str = "ollama",
    model: Optional[str] = None,
    timeout: int = 600,
    num_ctx: Optional[int] = DEFAULT_ANALYSIS_NUM_CTX,
) -> Dict[str, Any]:
    """バッチ分析の関数API。"""
    return BatchAnalyzer(
        batch_dir,
        client=client,
        provider=provider,
        model=model,
        timeout=timeout,
        num_ctx=num_ctx,
    ).analyze(no_llm=no_llm, refresh=refresh)


def _read_json_object(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _read_summary(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return _normalise_summary(value)


def _is_failed_summary(value: Mapping[str, Any]) -> bool:
    """旧実装が残した失敗キャッシュも成功要約として扱わない。"""
    return (
        all(value.get(key) == "生成失敗" for key in SUMMARY_KEYS[:-1])
        and value.get("key_motifs") == ["生成失敗"]
    )


def _estimated_body_char_limit(num_ctx: int) -> int:
    """出力・指示用の余裕を引いた本文文字数の概算上限。"""
    available_tokens = max(0, num_ctx - CONTEXT_OUTPUT_RESERVE_TOKENS)
    estimated = (
        available_tokens * ESTIMATED_CHARS_PER_TOKEN
        - CONTEXT_INSTRUCTION_RESERVE_CHARS
    )
    return max(MIN_ESTIMATED_BODY_CHARS, estimated)


def _truncate_body(text: str, limit: int) -> str:
    remaining = max(2, limit - len(TRUNCATION_MARKER))
    head = remaining // 2
    tail = remaining - head
    return text[:head] + TRUNCATION_MARKER + text[-tail:]


def _plot_type_name(value: Any) -> str:
    if isinstance(value, Mapping):
        name = value.get("name")
        if name is not None and str(name).strip():
            return str(name).strip()
    text = str(value).strip()
    if not text:
        return "不明"
    match = re.search(r"(?:^|\n)\s*-?\s*\*?\*?name\*?\*?\s*:\s*(.+)", text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text


def _add_frequency(table: Dict[str, List[str]], value: str, run_name: str) -> None:
    table.setdefault(value, []).append(run_name)


def _summary_system() -> str:
    return (
        "あなたは物語本文から観察可能な要約を抽出するアシスタントです。"
        + DESIGN_PRINCIPLE
        + "指定されたJSONオブジェクトだけを返してください。"
    )


def _summary_prompt(run: CompletedRun, body_text: str) -> str:
    return f"""次の作品（{run.name}）を本文に書かれている範囲だけで要約してください。

{DESIGN_PRINCIPLE}

次のJSONスキーマを厳守してください。
{{
  "protagonist_desire": "主人公が本当に求めたもの（短文）",
  "adversary_type": "敵対者が象徴するもの（短文）",
  "central_loss": "物語で失われた、または手放したもの（短文）",
  "ending": "結末の型（獲得、喪失、変容、帰還など）を短文で",
  "key_motifs": ["繰り返し現れるモチーフ", "最大5個"]
}}

本文:
---
{body_text}
---
"""


def _integration_system() -> str:
    return (
        "あなたは複数作品の観察結果を整理するアシスタントです。"
        + DESIGN_PRINCIPLE
        + "パターンは実例のあるものだけにし、診断名や断定的な人格評価は使わないでください。"
        + "指定されたJSONオブジェクトだけを返してください。"
    )


def _integration_prompt(
    runs: Sequence[CompletedRun],
    summaries: Sequence[Mapping[str, Any]],
    narrative: Mapping[str, Any],
) -> str:
    example_run = runs[0].name if runs else "run_XXX"
    summary_items = [
        {"run": run.name, **dict(summary)}
        for run, summary in zip(runs, summaries)
    ]
    return f"""次の作品要約を横断して、繰り返し現れるパターンを最大7件抽出してください。

{DESIGN_PRINCIPLE}
元ナラティブとの関係は、必ず問いの形の1文にしてください。問いは、元ナラティブの項目名
（例: 「失うのが怖いもの」「本当の願望」「日常」）に触れ、実例から考えられる問いとして書きます。
evidence_runs には次の実在run名だけを使い、存在しない番号は出力しないでください。
{json.dumps([run.name for run in runs], ensure_ascii=False)}

出力JSON:
{{
  "patterns": [
    {{
      "pattern": "短いパターン見出し",
      "evidence_runs": ["{example_run}"],
      "question": "元ナラティブとの関係を問う1文？"
    }}
  ]
}}

元ナラティブ:
{json.dumps(dict(narrative), ensure_ascii=False, indent=2)}

作品要約:
{json.dumps(summary_items, ensure_ascii=False, indent=2)}
"""


def _call_json_with_retry(
    client: Any,
    prompt: str,
    system: str,
    validator: Optional[Callable[[Mapping[str, Any]], Any]] = None,
) -> Optional[Dict[str, Any]]:
    """JSON応答を最大2回試し、形式不正時はNoneを返す。"""
    for _attempt in range(2):
        try:
            value = client.chat_json(
                prompt=prompt,
                system=system,
                temperature=0.2,
            )
            if isinstance(value, str):
                text = value.strip()
                if text.startswith("```"):
                    lines = text.splitlines()
                    if lines and lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                    text = "\n".join(lines).strip()
                value = json.loads(text)
            if not isinstance(value, dict):
                raise ValueError("LLM JSON response must be an object")
            if validator is not None and validator(value) is None:
                raise ValueError("LLM JSON response has an invalid schema")
            return value
        except Exception:
            continue
    return None


def _normalise_summary(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, Mapping):
        return None
    if not all(key in value for key in SUMMARY_KEYS):
        return None
    motifs = value.get("key_motifs")
    if isinstance(motifs, str):
        motifs = [motifs]
    if not isinstance(motifs, (list, tuple)):
        return None
    result: Dict[str, Any] = {}
    for key in SUMMARY_KEYS[:-1]:
        text = str(value.get(key, "")).strip()
        if not text:
            return None
        result[key] = text
    result["key_motifs"] = [str(item).strip() for item in motifs if str(item).strip()][:5]
    return result


def _failed_summary() -> Dict[str, Any]:
    return {
        "protagonist_desire": "生成失敗",
        "adversary_type": "生成失敗",
        "central_loss": "生成失敗",
        "ending": "生成失敗",
        "key_motifs": ["生成失敗"],
    }


def _normalise_patterns(
    value: Mapping[str, Any],
    runs: Sequence[CompletedRun],
) -> Optional[List[Dict[str, Any]]]:
    raw_patterns = value.get("patterns")
    if not isinstance(raw_patterns, list):
        return None
    actual_names = {run.name for run in runs}
    actual_by_number = {run.number: run.name for run in runs}
    patterns: List[Dict[str, Any]] = []
    for item in raw_patterns[:7]:
        if not isinstance(item, Mapping):
            return None
        pattern = str(item.get("pattern", "")).strip()
        question = str(item.get("question", "")).strip()
        if not pattern or not question:
            return None
        raw_evidence = item.get("evidence_runs", [])
        if not isinstance(raw_evidence, (list, tuple)):
            return None
        evidence: List[str] = []
        for raw_run in raw_evidence:
            canonical = _canonical_run_name(raw_run, actual_names, actual_by_number)
            if canonical and canonical not in evidence:
                evidence.append(canonical)
        patterns.append(
            {
                "pattern": pattern,
                "evidence_runs": evidence,
                "question": question,
            }
        )
    return patterns


def _canonical_run_name(
    value: Any,
    actual_names: Iterable[str],
    actual_by_number: Mapping[int, str],
) -> Optional[str]:
    names = set(actual_names)
    text = str(value).strip() if not isinstance(value, bool) else ""
    if text in names:
        return text
    match = re.fullmatch(r"(?:run[_ -]?)?(\d+)", text, re.IGNORECASE)
    if match:
        return actual_by_number.get(int(match.group(1)))
    if isinstance(value, int):
        return actual_by_number.get(value)
    return None


def _escape_table(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def _render_markdown(report: Mapping[str, Any], runs: Sequence[CompletedRun]) -> str:
    overview = report["overview"]
    lines = [
        "# バッチ横断分析レポート",
        "",
        "## A. 決定的集計",
        "",
        "### 概要",
        "",
        f"- 対象作品数: {overview['target_count']}",
        f"- スキップ数: {overview['skipped_count']}",
        f"- モデル: {overview['model']}",
        f"- プロバイダー: {overview['provider']}",
        "- 設定（batch_manifest.json）:",
        "",
        "```json",
        json.dumps(overview["settings"], ensure_ascii=False, indent=2),
        "```",
        "",
        "### 作品一覧",
        "",
        "| run番号 | タイトル | プロット形式 | 主人公 | 本文 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for run in runs:
        work = BatchAnalyzer._work_payload(run)
        lines.append(
            "| {run} | {title} | {plot} | {protagonist} | [Markdown]({link}) |".format(
                run=_escape_table(work["run"]),
                title=_escape_table(work["title"]),
                plot=_escape_table(work["plot_type"]),
                protagonist=_escape_table(work["protagonist"]),
                link=work["body_markdown"],
            )
        )

    lines.extend(["", "### 頻度表", ""])
    for key, items in report["frequencies"].items():
        lines.extend([
            f"#### {key}",
            "",
            "| 値 | 回数 | 該当run |",
            "| --- | ---: | --- |",
        ])
        if items:
            for item in items:
                lines.append(
                    f"| {_escape_table(item['value'])} | {item['count']} | "
                    f"{_escape_table(', '.join(item['runs']))} |"
                )
        else:
            lines.append("| （該当なし） | 0 | — |")
        lines.append("")

    cross = report["cross_analysis"]
    lines.extend(["## B. LLMによる横断解釈", ""])
    if not cross["enabled"]:
        lines.append("`--no-llm` により省略しました。")
        lines.append("")
        return "\n".join(lines)

    lines.extend(["### 作品ごとの要約", ""])
    lines.extend([
        "| run | 主人公の願い | 敵対者が象徴するもの | 中心的な喪失 | 結末 | モチーフ |",
        "| --- | --- | --- | --- | --- | --- |",
    ])
    for summary in cross["summaries"]:
        lines.append(
            "| {run} | {desire} | {adversary} | {loss} | {ending} | {motifs} |".format(
                run=_escape_table(summary["run"]),
                desire=_escape_table(summary["protagonist_desire"]),
                adversary=_escape_table(summary["adversary_type"]),
                loss=_escape_table(summary["central_loss"]),
                ending=_escape_table(summary["ending"]),
                motifs=_escape_table(", ".join(summary["key_motifs"])),
            )
        )
    lines.extend(["", "### 繰り返し現れるパターン", ""])
    if cross["status"] == "生成失敗":
        lines.extend(["生成失敗", ""])
    elif not cross["patterns"]:
        lines.extend(["（抽出されたパターンはありません）", ""])
    else:
        for index, pattern in enumerate(cross["patterns"], start=1):
            evidence = ", ".join(pattern["evidence_runs"]) or "該当runなし"
            lines.extend([
                f"#### {index}. {pattern['pattern']}",
                "",
                f"- 該当run: {evidence}",
                f"- 問い: {pattern['question']}",
                "",
            ])
    return "\n".join(lines)


__all__ = ["BatchAnalysisError", "BatchAnalyzer", "CompletedRun", "analyze_batch"]
