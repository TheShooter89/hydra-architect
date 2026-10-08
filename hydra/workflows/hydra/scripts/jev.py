#!/usr/bin/env python3
"""Jev client for Hydra, using OpenCode Zen's System One endpoint.

Credentials are resolved in this order:
1. JEV_API_TOKEN (environment or workflow .env)
2. OPENCODE_API_KEY
3. The existing OpenCode Zen credential in auth.json (provider "opencode")

The OpenCode Go credential is intentionally not used: Go does not expose the
System One Jev endpoint.
"""

import argparse
import datetime as dt
import email.utils
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
ACTIVE_FILE = ROOT / "profiles" / "active-profile.json"
DEFAULT_ENDPOINT = "https://opencode.ai/zen/v1/systemone"
DEFAULT_MODEL = "jev-1.13"
MAX_ATTEMPTS = 3
REQUEST_TIMEOUT_SECONDS = 30
MAX_RETRY_AFTER_SECONDS = 15

QUESTION_TYPES = {"noul", "choice", "score"}
YES_NO_QUESTION = re.compile(
    r"^\s*(?:is|are|was|were|do|does|did|should|can|could|would|will|"
    r"has|have|had|must|might|may)\b.+\?\s*$",
    re.IGNORECASE | re.DOTALL,
)


class JevError(Exception):
    """A user-facing Jev client or response error."""


def _load_dotenv():
    """Load the optional workflow .env without overriding the process env."""
    if not ENV_FILE.exists():
        return
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export ") :].strip()
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            if key and key not in os.environ:
                os.environ[key] = value


def _jev_model():
    """Read the model from the active profile, with a safe default."""
    try:
        active = json.loads(ACTIVE_FILE.read_text(encoding="utf-8"))
        profile_name = active.get("profile", "default")
        if not isinstance(profile_name, str) or Path(profile_name).name != profile_name:
            return DEFAULT_MODEL
        profile_path = ROOT / "profiles" / f"{profile_name}.json"
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        model = profile.get("jev", {}).get("model", DEFAULT_MODEL)
        return model.strip() if isinstance(model, str) and model.strip() else DEFAULT_MODEL
    except (OSError, json.JSONDecodeError, AttributeError, TypeError):
        return DEFAULT_MODEL


def _auth_file_candidates():
    paths = []
    explicit = os.environ.get("OPENCODE_AUTH_FILE")
    data_home = os.environ.get("XDG_DATA_HOME")
    if explicit:
        paths.append(Path(explicit).expanduser())
    if data_home:
        paths.append(Path(data_home).expanduser() / "opencode" / "auth.json")
    paths.append(Path.home() / ".local" / "share" / "opencode" / "auth.json")

    unique = []
    seen = set()
    for path in paths:
        if path not in seen:
            unique.append(path)
            seen.add(path)
    return unique


def _opencode_token(auth_file=None):
    """Read only the OpenCode Zen API token; never fall back to OpenCode Go."""
    paths = [Path(auth_file).expanduser()] if auth_file else _auth_file_candidates()
    for path in paths:
        try:
            auth = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            continue
        provider = auth.get("opencode") if isinstance(auth, dict) else None
        token = provider.get("key") if isinstance(provider, dict) else None
        if isinstance(token, str) and token.strip():
            return token.strip()
    return None


def _jev_token(auth_file=None):
    """Resolve credentials without printing or copying the stored Zen key."""
    for name in ("JEV_API_TOKEN", "OPENCODE_API_KEY"):
        token = os.environ.get(name)
        if token and token.strip():
            return token.strip()
    return _opencode_token(auth_file)


def _is_content(value):
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (dict, list)):
        return bool(value)
    return False


def _validate_question(question):
    if not isinstance(question, dict):
        raise ValueError("must be a typed question object")

    unknown = set(question) - {"type", "instructions", "criteria"}
    if unknown:
        raise ValueError(f"unsupported fields: {', '.join(sorted(unknown))}")

    question_type = question.get("type")
    if not isinstance(question_type, str) or question_type not in QUESTION_TYPES:
        raise ValueError("type must be one of: noul, choice, score")

    instructions = question.get("instructions")
    if not _is_content(instructions):
        raise ValueError("instructions must be a non-empty string, object, or array")

    normalized = {"type": question_type, "instructions": instructions}
    criteria = question.get("criteria")

    if question_type == "noul":
        if criteria is not None:
            if not isinstance(criteria, dict) or set(criteria) - {"true", "false"}:
                raise ValueError("noul criteria must contain only 'true' and/or 'false'")
            if any(not _is_content(value) for value in criteria.values()):
                raise ValueError("noul criteria values must be non-empty strings, objects, or arrays")
            normalized["criteria"] = criteria
    elif question_type == "choice":
        if not isinstance(criteria, dict) or not 1 <= len(criteria) <= 255:
            raise ValueError("choice questions need 1 to 255 criteria options")
        if any(
            value is not None and not _is_content(value)
            for value in criteria.values()
        ):
            raise ValueError("choice criteria must be strings, objects, arrays, or null")
        normalized["criteria"] = criteria
    else:
        if not isinstance(criteria, list) or not 2 <= len(criteria) <= 10:
            raise ValueError("score questions need 2 to 10 ordered criteria levels")
        if any(not _is_content(value) for value in criteria):
            raise ValueError("score criteria must be non-empty strings, objects, or arrays")
        normalized["criteria"] = criteria

    return normalized


def _normalize_questions(questions):
    """Validate typed questions and promote unambiguous legacy yes/no strings."""
    if not isinstance(questions, dict) or not questions:
        raise ValueError("questions must be a non-empty JSON object")

    normalized = {}
    errors = {}
    for name, question in questions.items():
        if not isinstance(name, str) or not name.strip():
            errors[str(name)] = "question id must be a non-empty string"
            continue

        candidate = question
        if isinstance(question, str):
            if YES_NO_QUESTION.match(question):
                candidate = {"type": "noul", "instructions": question}
            else:
                errors[name] = (
                    "legacy string is not an unambiguous yes/no question; "
                    "use a typed question with type, instructions, and criteria"
                )
                continue

        try:
            normalized[name] = _validate_question(candidate)
        except ValueError as exc:
            errors[name] = str(exc)

    return normalized, errors


def _build_payload(model, state, questions):
    return {"model": model, "state": state, "questions": questions}


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _normalize_answer(question, answer):
    if not isinstance(answer, dict):
        raise ValueError("answer is not an object")

    question_type = question["type"]
    if answer.get("type") != question_type:
        raise ValueError(f"expected a {question_type} answer")

    normalized = dict(answer)
    if question_type == "noul":
        value = answer.get("noul")
        if not _is_number(value) or not 0 <= value <= 1:
            raise ValueError("noul answer must be a number from 0 to 1")
        normalized["answer"] = "yes" if value >= 0.5 else "no"
        normalized["value"] = value
    elif question_type == "choice":
        value = answer.get("choice")
        if not isinstance(value, str):
            raise ValueError("choice answer must contain a string choice")
        if value not in question["criteria"]:
            raise ValueError("choice answer is not one of the supplied criteria options")
        normalized["answer"] = value
        normalized["value"] = value
    else:
        value = answer.get("score")
        legend = answer.get("legend")
        if not _is_number(value) or not math.isfinite(value):
            raise ValueError("score answer must contain a numeric score")
        if not isinstance(legend, dict) or not legend:
            raise ValueError("score answer must contain a legend")
        if value < 0 or value > len(legend) - 1:
            raise ValueError("score answer is outside its legend range")
        level = max(0, min(len(legend) - 1, math.floor(value + 0.5)))
        normalized["answer"] = legend.get(str(level))
        normalized["value"] = value

    return normalized


def _normalize_response(response, questions, errors, requested_model):
    if not isinstance(response, dict) or not isinstance(response.get("answers"), dict):
        raise JevError("Jev returned an invalid response: expected an answers object")

    answers = {}
    result_errors = dict(errors)
    for name, question in questions.items():
        if name not in response["answers"]:
            result_errors[name] = "Jev response omitted this question"
            continue
        try:
            answers[name] = _normalize_answer(question, response["answers"][name])
        except ValueError as exc:
            result_errors[name] = f"invalid Jev answer: {exc}"

    usage = response.get("usage")
    result = {
        "model": response.get("model", requested_model),
        "source": "zen-systemone",
        "answers": answers,
        "usage": usage if isinstance(usage, dict) else {},
    }
    if result_errors:
        result["errors"] = result_errors
    return result


def _placeholder_response(questions, model, errors=None, note=None):
    answers = {
        name: {
            "type": question["type"],
            "answer": "unknown",
            "value": None,
            "confidence": None,
            "note": note or "OpenCode Zen credentials are unavailable; Jev was not called.",
        }
        for name, question in questions.items()
    }
    result = {
        "model": model,
        "source": "placeholder",
        "answers": answers,
        "usage": {"input_tokens": 0, "output_tokens": 0},
    }
    if errors:
        result["errors"] = errors
    return result


def _retry_delay(headers, attempt):
    retry_after = headers.get("Retry-After") if headers else None
    if retry_after:
        try:
            delay = float(retry_after)
        except (TypeError, ValueError):
            try:
                retry_at = email.utils.parsedate_to_datetime(retry_after)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=dt.timezone.utc)
                delay = (retry_at - dt.datetime.now(dt.timezone.utc)).total_seconds()
            except (TypeError, ValueError, OverflowError):
                delay = 0
        return max(0, min(MAX_RETRY_AFTER_SECONDS, delay))
    return 1 if attempt == 1 else 4


def _http_error_detail(error):
    try:
        detail = error.read().decode("utf-8", errors="replace").strip()
    except Exception:
        detail = ""
    finally:
        error.close()
    return detail[:4000]


def _post_json(endpoint, token, payload):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    for attempt in range(1, MAX_ATTEMPTS + 1):
        request = urllib.request.Request(
            endpoint,
            data=data,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
                "User-Agent": "hydra-architect/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                body = response.read().decode("utf-8")
            try:
                parsed = json.loads(body)
            except json.JSONDecodeError as exc:
                raise JevError(f"Jev returned invalid JSON: {exc}") from exc
            if not isinstance(parsed, dict):
                raise JevError("Jev returned invalid JSON: expected an object")
            return parsed
        except urllib.error.HTTPError as exc:
            detail = _http_error_detail(exc)
            retryable = exc.code == 429 or 500 <= exc.code <= 599
            if retryable and attempt < MAX_ATTEMPTS:
                time.sleep(_retry_delay(exc.headers, attempt))
                continue
            suffix = f": {detail}" if detail else ""
            raise JevError(f"Jev HTTP {exc.code}{suffix}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if attempt < MAX_ATTEMPTS:
                time.sleep(_retry_delay(None, attempt))
                continue
            raise JevError(f"Jev request failed after {MAX_ATTEMPTS} attempts: {exc}") from exc

    raise JevError("Jev request failed after retries")


def _read_input(args, parser):
    if args.stdin_json:
        if args.state is not None or args.questions is not None:
            parser.error("--stdin-json cannot be combined with --state or --questions")
        try:
            payload = json.loads(sys.stdin.read())
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid stdin JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError("stdin JSON must be an object containing state and questions")
        state = payload.get("state")
        questions = payload.get("questions")
    else:
        if args.state is None or args.questions is None:
            parser.error("--state and --questions are required unless --stdin-json is used")
        state = args.state
        try:
            questions = json.loads(args.questions)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid questions JSON: {exc}") from exc

    if not isinstance(state, (str, dict, list)):
        raise ValueError("state must be a string, object, or array")
    if isinstance(state, str) and not state.strip():
        raise ValueError("state must not be empty")
    return state, questions


def main(argv=None):
    parser = argparse.ArgumentParser(description="Ask Jev a batch of typed questions")
    parser.add_argument(
        "--state",
        help="Context Jev evaluates (string; for object/array state use --stdin-json)",
    )
    parser.add_argument(
        "--questions",
        help='JSON object mapping IDs to typed questions, e.g. {"risk":{"type":"noul","instructions":"Is risk high?"}}',
    )
    parser.add_argument(
        "--stdin-json",
        action="store_true",
        help="Read a JSON object containing state and questions from stdin",
    )
    parser.add_argument("--print-raw", action="store_true", help="Print the unnormalized API response")
    args = parser.parse_args(argv)

    try:
        state, raw_questions = _read_input(args, parser)
        _load_dotenv()

        questions, errors = _normalize_questions(raw_questions)
        model = os.environ.get("JEV_MODEL", "").strip() or _jev_model()

        if not questions:
            result = {
                "model": model,
                "source": "validation",
                "answers": {},
                "usage": {"input_tokens": 0, "output_tokens": 0},
                "errors": errors,
            }
            print(json.dumps(result, ensure_ascii=False))
            return 0

        disabled = os.environ.get("JEV_DISABLE", "").strip().lower() in {"1", "true", "yes"}
        token = None if disabled else _jev_token()
        if disabled or not token:
            note = "JEV_DISABLE is enabled; Jev was not called." if disabled else None
            result = _placeholder_response(questions, model, errors, note=note)
            print(json.dumps(result, ensure_ascii=False))
            return 0

        endpoint = os.environ.get("JEV_ENDPOINT", "").strip() or DEFAULT_ENDPOINT
        payload = _build_payload(model, state, questions)
        response = _post_json(endpoint, token, payload)
        if args.print_raw:
            print(json.dumps(response, ensure_ascii=False))
            return 0

        result = _normalize_response(response, questions, errors, model)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
