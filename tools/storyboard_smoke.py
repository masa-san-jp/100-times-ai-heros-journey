"""ComfyUI のストーリーボード生成を手動確認する CLI。"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Optional, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.comfyui_client import (
    ComfyUIConfigurationError,
    ComfyUIConnectionError,
    ComfyUIImageGenerator,
    load_storyboard_profile,
)


DEFAULT_PROMPT = (
    "cinematic film still, a lone traveler standing beneath neon signs in a "
    "rain-soaked city at night, widescreen 16:9 composition, photorealistic, "
    "full frame without letterbox bars, no text, no watermark"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--width", type=int, help="生成幅（省略時は profile）")
    parser.add_argument("--height", type=int, help="生成高さ（省略時は profile）")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--out", type=Path, default=Path("output/storyboard"))
    parser.add_argument("--profile")
    parser.add_argument("--comfyui-url", default=os.getenv("COMFYUI_URL", "http://127.0.0.1:8188"))
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        profile = load_storyboard_profile(args.profile)
        generator = ComfyUIImageGenerator(
            base_url=args.comfyui_url,
            workflow_path=PROJECT_ROOT / profile["workflow_path"],
            model_files=profile.get("model_files"),
            width=args.width if args.width is not None else profile["width"],
            height=args.height if args.height is not None else profile["height"],
            timeout_seconds=profile.get("timeout_seconds", 600),
        )
        started = time.monotonic()
        result = generator.generate(
            args.prompt, args.out, "storyboard_smoke", seed=args.seed
        )
    except ComfyUIConnectionError as exc:
        print(f"{exc}\n100-times-ai-heroes の python3 run_local.py 等で ComfyUI を起動してください。", file=sys.stderr)
        return 1
    except (ComfyUIConfigurationError, OSError, RuntimeError, TimeoutError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"saved: {result.path}")
    print(f"seed: {result.seed}")
    print(f"seconds: {time.monotonic() - started:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
