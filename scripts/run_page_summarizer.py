"""
Standalone runner for page_summarizer.
Explicitly loads .env before importing anything else.
Run: python scripts/run_page_summarizer.py [--mode on|dryrun] [--max-pages N] [--force]
"""
import sys
import os
import argparse
from pathlib import Path

# Force load .env FIRST, before any src imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env", override=True)

# Verify key loaded
key = os.environ.get("OPENAI_API_KEY", "")
print(f"[INFO] OPENAI_API_KEY loaded: {key[:12]}..." if key else "[WARN] No OPENAI_API_KEY found!")

from src.writeback.page_summarizer import run

parser = argparse.ArgumentParser()
parser.add_argument("--mode", default="on", choices=["dryrun", "on"])
parser.add_argument("--max-pages", type=int, default=None)
parser.add_argument("--force", action="store_true")
parser.add_argument("--concurrency", type=int, default=5)
args = parser.parse_args()

counts = run(
    mode=args.mode,
    max_pages=args.max_pages,
    force=args.force,
    concurrency=args.concurrency,
)
print(f"\nFinal: {counts}")
sys.exit(0 if counts.get("error", 0) == 0 else 1)
