#!/usr/bin/env python3
"""物語構造の異なる複数バッチを並べて比べるCLI（LLMは使わない）。"""

from __future__ import annotations

import argparse
import sys

from src.batch_analyzer import BatchAnalysisError
from src.batch_comparison import REPORT_JSON, REPORT_MD, compare_batches


def main() -> int:
    parser = argparse.ArgumentParser(
        description="物語構造の異なる複数バッチを並べて比べる"
    )
    parser.add_argument("batch_dirs", nargs="+", help="比べるバッチディレクトリ（2つ以上）")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="レポートの保存先（既定値: output/comparison_<日時>）",
    )
    parser.add_argument(
        "--allow-different-narratives",
        action="store_true",
        help="元ナラティブが異なるバッチでも比べる",
    )
    args = parser.parse_args()

    try:
        report = compare_batches(
            args.batch_dirs,
            output_dir=args.output_dir,
            allow_different_narratives=args.allow_different_narratives,
        )
    except BatchAnalysisError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    for batch in report["batches"]:
        print(f"- {batch['name']}: {batch['structure']}、{batch['work_count']}作品")
    print(f"出力: {report['output_dir']}/{REPORT_MD}")
    print(f"出力: {report['output_dir']}/{REPORT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
