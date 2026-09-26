#!/usr/bin/env python3
"""生成済みバッチを横断分析するCLI。"""

from __future__ import annotations

import argparse
import sys

from src.batch_analyzer import BatchAnalysisError, BatchAnalyzer
from src.llm_factory import create_provider_client
from src.ollama_client import OllamaClientError


def main() -> int:
    parser = argparse.ArgumentParser(
        description="生成済み作品群の決定的集計と横断的な振り返り"
    )
    parser.add_argument("batch_dir", help="分析対象のバッチディレクトリ")
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="LLMによる要約・横断解釈を省略する",
    )
    parser.add_argument(
        "--provider",
        choices=("ollama", "openai", "anthropic", "deepseek"),
        default="ollama",
        help="LLMプロバイダー（既定値: ollama）",
    )
    parser.add_argument("--model", default=None, help="使用するモデル名")
    parser.add_argument("--timeout", type=int, default=600, help="LLMのタイムアウト秒")
    parser.add_argument(
        "--num-ctx",
        type=int,
        default=32768,
        help="Ollamaのコンテキスト長（既定値: 32768）",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="既存のcross_summary.jsonを再利用せず再生成する",
    )
    args = parser.parse_args()
    if args.num_ctx < 1:
        parser.error("--num-ctxは1以上で指定してください")

    analyzer = BatchAnalyzer(
        args.batch_dir,
        provider=args.provider,
        model=args.model,
        timeout=args.timeout,
        num_ctx=args.num_ctx,
    )
    try:
        analyzer.validate_target()
    except BatchAnalysisError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    client = None
    if not args.no_llm:
        try:
            client, selected_model = create_provider_client(
                args.provider,
                args.model,
                args.timeout,
                num_ctx=args.num_ctx if args.provider == "ollama" else None,
            )
            if args.model is None and args.provider != "ollama":
                print(f"使用モデル: {selected_model}")
        except (OllamaClientError, ValueError) as exc:
            print(f"LLMクライアントの準備に失敗しました: {exc}", file=sys.stderr)
            if args.provider == "ollama":
                print(
                    "Ollamaサーバーが起動しているか（ollama serve）を確認してください。",
                    file=sys.stderr,
                )
            return 1

    analyzer.client = client
    try:
        report = analyzer.analyze(no_llm=args.no_llm, refresh=args.refresh)
    except BatchAnalysisError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    overview = report["overview"]
    print(
        f"バッチ分析完了: 対象 {overview['target_count']}件、"
        f"スキップ {overview['skipped_count']}件"
    )
    print(f"出力: {args.batch_dir}/batch_report.md")
    print(f"出力: {args.batch_dir}/batch_report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
