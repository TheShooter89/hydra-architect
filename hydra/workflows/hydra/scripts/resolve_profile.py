#!/usr/bin/env python3
"""Resolve a Hydra model profile with inheritance, tiers, and policy validation."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROFILES_DIR = ROOT / "profiles"
ACTIVE_FILE = PROFILES_DIR / "active-profile.json"

ROLES = [
    "orchestrator",
    "explorer",
    "researcher",
    "test-scout",
    "architect",
    "implementer",
    "code-reviewer",
    "security-reviewer",
    "test-reviewer",
    "adjudicator",
    "final-verifier",
]


def load_profile(name):
    path = PROFILES_DIR / f"{name}.json"
    if not path.exists():
        raise ValueError(f"Profile '{name}' not found at {path}")
    with open(path, "r", encoding="utf-8") as f:
        profile = json.load(f)

    base = {}
    parent = profile.get("extends")
    if parent:
        base = load_profile(parent)

    merged = dict(base)
    for key, value in profile.items():
        if key == "extends":
            continue
        if isinstance(value, dict) and key in ("roles", "tiers", "policy", "jev"):
            merged[key] = {**(base.get(key) or {}), **value}
        else:
            merged[key] = value

    # tier_overrides are applied on top of the merged tiers
    tier_overrides = profile.get("tier_overrides")
    if tier_overrides:
        merged["tiers"] = {**(merged.get("tiers") or {}), **tier_overrides}

    return merged


def resolve_role_model(role, effective):
    tiers = effective.get("tiers") or {}
    roles = effective.get("roles") or {}
    value = roles.get(role)
    if value is None:
        return None
    if value in tiers:
        return tiers[value]
    return value


def validate_policy(name, models, policy):
    if policy.get("allow_paid_models") is False:
        verified = set(policy.get("verified_free_models") or [])
        for role, model in models.items():
            if model not in verified:
                raise ValueError(
                    f"Profile '{name}' forbids paid models, but role '{role}' "
                    f"uses unverified model '{model}'. Add it to verified_free_models or switch profile."
                )

    if policy.get("allow_preview_models") is False:
        for role, model in models.items():
            if "preview" in model.lower():
                raise ValueError(
                    f"Profile '{name}' forbids preview models, but role '{role}' uses '{model}'."
                )


def resolve(name):
    effective = load_profile(name)
    models = {role: resolve_role_model(role, effective) for role in ROLES}

    missing = [role for role, model in models.items() if model is None]
    if missing:
        raise ValueError(f"Profile '{name}' is missing models for roles: {missing}")

    policy = effective.get("policy") or {}
    validate_policy(name, models, policy)

    return {
        "name": name,
        "description": effective.get("description", ""),
        "models": models,
        "jev": effective.get("jev") or {},
        "policy": policy,
    }


def main():
    parser = argparse.ArgumentParser(description="Resolve and manage Hydra model profiles")
    parser.add_argument("--active", action="store_true", help="Resolve the active profile")
    parser.add_argument("--set", metavar="PROFILE", help="Set and validate the active profile")
    parser.add_argument("--show", metavar="PROFILE", help="Show a profile")
    parser.add_argument("--diff", nargs=2, metavar=("A", "B"), help="Diff two profiles")
    args = parser.parse_args()

    try:
        if args.active:
            active = {"profile": "default"}
            if ACTIVE_FILE.exists():
                active = json.loads(ACTIVE_FILE.read_text(encoding="utf-8"))
            print(json.dumps(resolve(active.get("profile", "default"))))
        elif args.set:
            resolved = resolve(args.set)
            ACTIVE_FILE.write_text(
                json.dumps({"profile": args.set}, indent=2) + "\n", encoding="utf-8"
            )
            print(json.dumps(resolved))
        elif args.show:
            print(json.dumps(resolve(args.show)))
        elif args.diff:
            a = resolve(args.diff[0])
            b = resolve(args.diff[1])
            diffs = {}
            for role in ROLES:
                if a["models"][role] != b["models"][role]:
                    diffs[role] = {"from": a["models"][role], "to": b["models"][role]}
            print(
                json.dumps(
                    {"from": a["name"], "to": b["name"], "diffs": diffs},
                    indent=2,
                )
            )
        else:
            parser.print_help()
            sys.exit(1)
    except ValueError as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
