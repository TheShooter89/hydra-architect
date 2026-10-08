import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "hydra" / "workflows" / "hydra" / "scripts"))

import jev


class JevClientTests(unittest.TestCase):
    def test_build_payload_includes_state_and_typed_questions(self):
        questions = {
            "urgent": {
                "type": "noul",
                "instructions": "Is this urgent?",
            }
        }

        payload = jev._build_payload("jev-1.13", "Payouts are failing", questions)

        self.assertEqual(
            payload,
            {
                "model": "jev-1.13",
                "state": "Payouts are failing",
                "questions": questions,
            },
        )

    def test_only_unambiguous_legacy_yes_no_strings_are_promoted(self):
        questions, errors = jev._normalize_questions(
            {
                "urgent": "Is this request urgent?",
                "category": "Which team should handle this?",
            }
        )

        self.assertEqual(questions["urgent"]["type"], "noul")
        self.assertEqual(questions["urgent"]["instructions"], "Is this request urgent?")
        self.assertIn("typed question", errors["category"])

    def test_normalizes_noul_choice_and_score_without_losing_api_fields(self):
        questions = {
            "urgent": {"type": "noul", "instructions": "Is it urgent?"},
            "team": {
                "type": "choice",
                "instructions": "Which team?",
                "criteria": {"billing": "Payments", "shipping": "Delivery"},
            },
            "severity": {
                "type": "score",
                "instructions": "How severe?",
                "criteria": ["Low", "Medium", "High"],
            },
        }
        response = {
            "model": "jev-1.13.0",
            "answers": {
                "urgent": {"type": "noul", "noul": 0.82},
                "team": {
                    "type": "choice",
                    "choice": "billing",
                    "probabilities": {"billing": 0.9, "shipping": 0.1},
                    "confidence": 0.8,
                },
                "severity": {
                    "type": "score",
                    "score": 1.05,
                    "legend": {"0": "Low", "1": "Medium", "2": "High"},
                    "probabilities": {"0": 0.1, "1": 0.8, "2": 0.1},
                    "confidence": 0.7,
                },
            },
            "usage": {"input_tokens": 300, "output_tokens": 20},
        }

        result = jev._normalize_response(response, questions, {}, "jev-1.13")

        self.assertEqual(result["source"], "zen-systemone")
        self.assertEqual(result["answers"]["urgent"]["answer"], "yes")
        self.assertEqual(result["answers"]["urgent"]["value"], 0.82)
        self.assertNotIn("confidence", result["answers"]["urgent"])
        self.assertEqual(result["answers"]["team"]["answer"], "billing")
        self.assertEqual(result["answers"]["team"]["probabilities"]["billing"], 0.9)
        self.assertEqual(result["answers"]["severity"]["answer"], "Medium")
        self.assertEqual(result["answers"]["severity"]["value"], 1.05)
        self.assertEqual(result["usage"]["input_tokens"], 300)

    def test_uses_zen_auth_entry_and_ignores_go_auth_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            auth_file = Path(directory) / "auth.json"
            auth_file.write_text(
                json.dumps(
                    {
                        "opencode": {"type": "api", "key": "zen-test-key"},
                        "opencode-go": {"type": "api", "key": "go-test-key"},
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(jev._jev_token(auth_file), "zen-test-key")
                os.environ["OPENCODE_API_KEY"] = "env-key"
                self.assertEqual(jev._jev_token(auth_file), "env-key")
                os.environ["JEV_API_TOKEN"] = "jev-override"
                self.assertEqual(jev._jev_token(auth_file), "jev-override")

                os.environ.pop("OPENCODE_API_KEY")
                os.environ.pop("JEV_API_TOKEN")
                auth_file.write_text(
                    json.dumps({"opencode-go": {"type": "api", "key": "go-test-key"}}),
                    encoding="utf-8",
                )
                self.assertIsNone(jev._jev_token(auth_file))

    def test_placeholder_is_explicit_and_has_no_fake_confidence(self):
        questions = {
            "urgent": {"type": "noul", "instructions": "Is it urgent?"},
        }

        result = jev._placeholder_response(questions, "jev-1.13")

        self.assertEqual(result["source"], "placeholder")
        self.assertEqual(result["answers"]["urgent"]["answer"], "unknown")
        self.assertIsNone(result["answers"]["urgent"]["confidence"])

    def test_retries_overloaded_response_and_sends_bearer_json(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def read(self):
                return b'{"model":"jev-1.13.0","answers":{},"usage":{}}'

        overloaded = urllib.error.HTTPError(
            "https://example.test/systemone",
            529,
            "Overloaded",
            {"Retry-After": "0"},
            io.BytesIO(b"try again"),
        )
        with patch("jev.urllib.request.urlopen", side_effect=[overloaded, FakeResponse()]) as urlopen:
            with patch("jev.time.sleep") as sleep:
                payload = {"model": "jev-1.13", "state": "test", "questions": {}}
                result = jev._post_json("https://example.test/systemone", "secret", payload)

        self.assertEqual(result["model"], "jev-1.13.0")
        self.assertEqual(urlopen.call_count, 2)
        request = urlopen.call_args_list[0].args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer secret")
        self.assertEqual(json.loads(request.data.decode("utf-8")), payload)
        sleep.assert_called_once_with(0)


if __name__ == "__main__":
    unittest.main()
