"""
Main pipeline entry point.

Usage:
    python -m src.pipeline.run_pipeline [OPTIONS]

Options:
    --from-step INT       Start from step N (1-7, default: 1)
    --to-step INT         Stop after step N (1-7, default: 7)
    --max-pages INT       Limit pages fetched (for testing)
    --cluster-method STR  'hdbscan' or 'kmeans'
    --provider STR        'openai', 'anthropic', or 'fallback'
    --writeback-mode STR  'off', 'dryrun', or 'on'
    --dedupe-threshold F  Cosine similarity threshold (0.0-1.0)
    --force               Ignore all caches and re-run everything
    --help                Show this help message
"""
from __future__ import annotations

import argparse
import sys
from typing import Optional

from src.utils.logger import get_logger

logger = get_logger("pipeline.main")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Notion Journal Loops — Emotional Pattern Analysis Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--from-step", type=int, default=1, metavar="N",
                        help="Start from step N (1-7)")
    parser.add_argument("--to-step", type=int, default=7, metavar="N",
                        help="Stop after step N (1-7)")
    parser.add_argument("--max-pages", type=int, default=None, metavar="N",
                        help="Limit number of pages fetched (for testing)")
    parser.add_argument("--cluster-method", type=str, default=None,
                        choices=["hdbscan", "kmeans"],
                        help="Clustering method")
    parser.add_argument("--provider", type=str, default=None,
                        choices=["openai", "anthropic", "fallback"],
                        help="LLM provider")
    parser.add_argument("--writeback-mode", type=str, default=None,
                        choices=["off", "dryrun", "on"],
                        help="Writeback mode (default: off)")
    parser.add_argument("--dedupe-threshold", type=float, default=None,
                        metavar="F",
                        help="Cosine similarity threshold for deduplication")
    parser.add_argument("--force", action="store_true",
                        help="Ignore all caches and re-run")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    from_step = args.from_step
    to_step = args.to_step

    if from_step < 1 or to_step > 7 or from_step > to_step:
        logger.error(f"Invalid step range: {from_step}-{to_step}. Must be 1-7.")
        return 1

    logger.info(f"Running pipeline steps {from_step} to {to_step}")

    # Override config from CLI args
    if args.writeback_mode:
        import os
        os.environ["WRITEBACK_MODE"] = args.writeback_mode
    if args.cluster_method:
        import os
        os.environ["CLUSTER_METHOD"] = args.cluster_method
    if args.dedupe_threshold is not None:
        import os
        os.environ["DUP_SIM_THRESHOLD"] = str(args.dedupe_threshold)

    # Pipeline state
    pages = None
    chunks = None
    embeddings = None
    chunk_ids = None
    cluster_assignments = None
    summaries = None
    duplicates = None

    try:
        # ── Step 1: Fetch ────────────────────────────────────────────────────
        if from_step <= 1 <= to_step:
            from src.pipeline import step1_fetch
            pages = step1_fetch.run(
                max_pages=args.max_pages,
                force=args.force,
            )

        # ── Step 2: Chunk ────────────────────────────────────────────────────
        if from_step <= 2 <= to_step:
            from src.pipeline import step2_chunk
            chunks = step2_chunk.run(
                pages=pages,
                force=args.force,
            )

        # ── Step 3: Embed ────────────────────────────────────────────────────
        if from_step <= 3 <= to_step:
            from src.pipeline import step3_embed
            embeddings, chunk_ids = step3_embed.run(
                chunks=chunks,
                provider_name=args.provider,
                force=args.force,
            )

        # ── Step 4: Cluster ──────────────────────────────────────────────────
        if from_step <= 4 <= to_step:
            from src.pipeline import step4_cluster
            cluster_assignments = step4_cluster.run(
                embeddings=embeddings,
                chunk_ids=chunk_ids,
                chunks=chunks,
                method=args.cluster_method,
                force=args.force,
            )

        # ── Step 5: Summarize ────────────────────────────────────────────────
        if from_step <= 5 <= to_step:
            from src.pipeline import step5_summarize
            summaries = step5_summarize.run(
                cluster_assignments=cluster_assignments,
                provider_name=args.provider,
                force=args.force,
            )

        # ── Step 6: Dedupe ───────────────────────────────────────────────────
        if from_step <= 6 <= to_step:
            from src.pipeline import step6_dedupe
            duplicates = step6_dedupe.run(
                cluster_assignments=cluster_assignments,
                embeddings=embeddings,
                chunk_ids=chunk_ids,
                threshold=args.dedupe_threshold,
                force=args.force,
            )

        # ── Step 7: Report ───────────────────────────────────────────────────
        if from_step <= 7 <= to_step:
            from src.config import WRITEBACK_MODE
            from src.pipeline import step7_report
            step7_report.run(
                summaries=summaries,
                cluster_assignments=cluster_assignments,
                duplicates=duplicates,
                writeback_mode=args.writeback_mode or WRITEBACK_MODE,
                force=args.force,
            )

        logger.info("Pipeline completed successfully!")
        return 0

    except FileNotFoundError as e:
        logger.error(f"Missing prerequisite: {e}")
        logger.info("Tip: Run from step 1 to generate all required data.")
        return 1
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        return 1
    except KeyboardInterrupt:
        logger.info("Pipeline interrupted by user.")
        return 130
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
