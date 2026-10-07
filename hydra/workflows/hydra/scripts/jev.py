#!/usr/bin/env python3
"""Jev client for Hydra.

Reads credentials from .opencode/agents/workflows/hydra/.env if present,
then falls back to environment variables.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
ACTIVE_FILE = ROOT / "profiles" / "active-profile.json"


def _load_dotenv():
    if not ENV_FILE.exists():
        return
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'\"\n")
            if key and key not in os.environ:
                os.environ[key] = value


def _jev_model():
    default = "jev-1.13"
    if not ACTIVE_FILE.exists():
        return default
    active = json.loads(ACTIVE_FILE.read_text(encoding="utf-8"))
    profile_name = active.get("profile", "default")
    profile_path = ROOT / "profiles" / f"{profile_name}.json"
    if not profile_path.exists():
        return default
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    return profile.get("jev", {}).get("model", default)


def _placeholder_response(questions):
    return {
        name: {
            "answer": "unknown",
            "confidence": 0.5,
            "note": "JEV_ENDPOINT/JEV_API_TOKEN not configured; this is a placeholder response.",
        }
        for name, text in questions.items()
    }


def main():
    parser = argparse.ArgumentParser(description="Ask Jev a batch of typed questions")
    parser.add_argument(
        "--questions",
        required=True,
        help='JSON object mapping question names to question text, e.g. {"risk":"high or low?"}',
    )
    args = parser.parse_args()

    _load_dotenv()

    try:
        questions = json.loads(args.questions)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON: {e}"}), file=sys.stderr)
        sys.exit(1)

    endpoint = os.environ.get("JEV_ENDPOINT")
    token = os.environ.get("JEV_API_TOKEN")
    model = _jev_model()

    if not endpoint or not token:
        print(json.dumps(_placeholder_response(questions)))
        return

    payload = json.dumps({"model": model, "questions": questions}).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            print(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(
            json.dumps({"error": f"Jev HTTP {e.code}: {e.read().decode('utf-8')}"}),
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
