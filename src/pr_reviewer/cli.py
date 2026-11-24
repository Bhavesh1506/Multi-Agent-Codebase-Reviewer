"""Local review and offline evaluation commands."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from pr_reviewer.config import Settings
from pr_reviewer.pipeline.orchestrator import ReviewOrchestrator


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="diffpulse")
    subcommands = parser.add_subparsers(dest="command", required=True)
    review = subcommands.add_parser("review", help="review a local unified diff")
    review.add_argument("diff", help="diff file path, or - for stdin")
    review.add_argument("--root", type=Path, default=Path.cwd(), help="repository working tree")
    review.add_argument("--mock", action="store_true", help="offline deterministic provider")
    evaluation = subcommands.add_parser("eval", help="run offline benchmark fixtures")
    evaluation.add_argument("--mock", action="store_true", help="offline deterministic provider")
    evaluation.add_argument("--json", action="store_true", help="machine-readable metrics")
    args = parser.parse_args(argv)
    settings = Settings(llm_provider="mock") if args.mock else Settings()
    if args.command == "review":
        try:
            diff_text = sys.stdin.read() if args.diff == "-" else Path(args.diff).read_text(encoding="utf-8")
            result = asyncio.run(ReviewOrchestrator(args.root, settings=settings).review_diff(diff_text))
        except (OSError, ValueError) as exc:
            parser.exit(2, f"diffpulse: {exc}\n")
        print(result.model_dump_json(indent=2))
        return 0
    from pr_reviewer.eval.runner import run_benchmark

    metrics = asyncio.run(run_benchmark(settings=settings))
    if args.json:
        print(metrics.model_dump_json(indent=2))
    else:
        print(
            f"precision={metrics.precision:.3f} recall={metrics.recall:.3f} "
            f"false_positive_rate={metrics.false_positive_rate:.3f} "
            f"tokens={metrics.token_count} latency_seconds={metrics.latency_seconds:.3f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
