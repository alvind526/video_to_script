"""
One-time (online) helper: download the Whisper model into models/<size>/.

After this succeeds, run app.py fully offline — it never contacts the network.

Usage:
  python download_model.py           # downloads "base" (~140 MB)
  python download_model.py tiny      # smaller / faster
  python download_model.py small     # more accurate
"""

from __future__ import annotations

import argparse
import os
import sys

APP_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(APP_DIR, "models")
DEFAULT_SIZE = "base"
KNOWN = (
    "tiny", "tiny.en", "base", "base.en", "small", "small.en",
    "medium", "medium.en", "large-v1", "large-v2", "large-v3", "large",
)
REQUIRED = ("model.bin", "config.json", "tokenizer.json", "vocabulary.txt")


def is_ready(path: str) -> bool:
    return all(os.path.isfile(os.path.join(path, name)) for name in REQUIRED)


def main() -> int:
    parser = argparse.ArgumentParser(description="Download a Whisper model for offline use.")
    parser.add_argument(
        "size",
        nargs="?",
        default=DEFAULT_SIZE,
        help=f"Model size (default: {DEFAULT_SIZE}). Examples: {', '.join(KNOWN[:6])}, …",
    )
    args = parser.parse_args()
    size = args.size
    out_dir = os.path.join(MODELS_DIR, size)

    if is_ready(out_dir):
        print(f"Already present: {out_dir}")
        print("Nothing to download. You can run:  python app.py")
        return 0

    try:
        from faster_whisper import download_model
    except ImportError:
        print("Install dependencies first:  pip install -r requirements.txt", file=sys.stderr)
        return 1

    print(f"Downloading '{size}' into {out_dir} …")
    print("(Needs internet this once. Afterward the app is fully offline.)")
    os.makedirs(MODELS_DIR, exist_ok=True)
    # Clear offline flags so this script can reach Hugging Face.
    for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_DATASETS_OFFLINE"):
        os.environ.pop(key, None)

    path = download_model(size, output_dir=out_dir)
    if not is_ready(path):
        print(f"Download finished but model files look incomplete in:\n  {path}", file=sys.stderr)
        return 1

    print(f"Ready: {path}")
    print("You can now run offline:  python app.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
