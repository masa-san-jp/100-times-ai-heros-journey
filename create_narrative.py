#!/usr/bin/env python3
"""13の問いに答えてナラティブJSONを作成するCLI。"""

from __future__ import annotations

import argparse
from typing import Optional, Sequence

from src.narrative_interview import run_interview


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="対話式にナラティブJSONを作成します")
    parser.add_argument(
        "--out",
        default="narrative.json",
        help="出力先（既定: narrative.json）",
    )
    parser.add_argument(
        "--from",
        dest="from_path",
        default=None,
        help="既存JSONを読み込んで編集モードで開始する",
    )
    args = parser.parse_args(argv)
    return run_interview(output_path=args.out, from_path=args.from_path)


if __name__ == "__main__":
    raise SystemExit(main())
