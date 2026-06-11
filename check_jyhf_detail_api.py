#!/usr/bin/env python3
"""
Check whether the live JYHF detail endpoint is still reachable.

Default endpoint:
  https://app.txcfgl.com/api/app/subject/query/{subject_id}

Token source priority:
  1. --token
  2. JYHF_AUTH_TOKEN / AUTHORIZATION
  3. /tmp/jyhf_auth_token.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


TOKEN_FILE = Path("/tmp/jyhf_auth_token.json")
BASE_URL = "https://app.txcfgl.com/api/app"


def _load_token(cli_token: str | None) -> tuple[str, str]:
    if cli_token:
        return cli_token.strip(), "--token"

    env_token = (os.getenv("JYHF_AUTH_TOKEN") or os.getenv("AUTHORIZATION") or "").strip()
    if env_token:
        return env_token, "env"

    if TOKEN_FILE.exists():
        try:
            payload = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
            token = str(payload.get("token") or "").strip()
            if token:
                return token, str(TOKEN_FILE)
        except Exception:
            pass

    return "", "missing"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check JYHF detail endpoint reachability")
    parser.add_argument("--subject-id", required=True, help="Subject ID, e.g. 106")
    parser.add_argument("--token", help="Authorization token")
    parser.add_argument("--timeout", type=int, default=20, help="Request timeout seconds")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON response")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    token, token_source = _load_token(args.token)
    if not token:
        print("[ERROR] missing token")
        return 1
    print(f"[AUTH] source={token_source}")

    url = f"{BASE_URL}/subject/query/{args.subject_id}"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://app.txcfgl.com/",
        "Origin": "https://app.txcfgl.com",
        "Authorization": token,
    }
    req = urllib.request.Request(url, headers=headers, method="GET")

    try:
        with urllib.request.urlopen(req, timeout=args.timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            print(f"[HTTP] {resp.status} {resp.reason}")
            if args.pretty:
                try:
                    print(json.dumps(json.loads(body), ensure_ascii=False, indent=2))
                except Exception:
                    print(body)
            else:
                print(body[:1000])
            return 0
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"[HTTP] {e.code} {e.reason}")
        print(body[:1000])
        return 2
    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {e}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
