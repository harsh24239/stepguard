"""Inspect configuration without exposing secrets; optionally make one tiny call.

Run from the project root: python -m scripts.check_provider [--live]
No assembly media is sent. --live can consume a small amount of provider quota.
"""

import argparse
import os

from backend import meta_client
from backend.model_errors import ModelError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Make a minimal Gemini JSON request to check access.")
    args = parser.parse_args()
    print("Provider:", meta_client.MODEL_PROVIDER)
    print("Mode:", "MOCK" if meta_client.MOCK_MODE else "LIVE")
    print("Adapter configuration:", "ready" if meta_client.adapters_ready() else "not ready")
    if not args.live:
        print("No network request made. Configuration alone does not verify a key or quota.")
        return 0
    if meta_client.MOCK_MODE:
        print("Live check refused: set MOCK_MODE=false and restart the command.")
        return 2
    if meta_client.MODEL_PROVIDER != "gemini":
        print("Live check unavailable: the Meta adapters are not implemented yet.")
        return 2
    from backend import gemini_client
    try:
        # One attempt; keep diagnostic latency and cost bounded. Never print
        # arbitrary provider output, exception text, or request headers.
        os.environ["MODEL_MAX_RETRIES"] = "0"
        os.environ["MODEL_TIMEOUT_SECONDS"] = "10"
        response = gemini_client._generate(
            'Return {"ok":true}.', {"text": "Connection check."},
            {"type": "object", "properties": {"ok": {"type": "boolean"}},
             "required": ["ok"], "additionalProperties": False}, "connection_check")
        if response != {"ok": True}:
            print("Provider responded, but the expected JSON contract was not confirmed.")
            return 1
        print("Live access confirmed. This does not verify PDF/image/audio compatibility or assembly accuracy.")
        return 0
    except ModelError as error:
        print("Live access not confirmed. Sanitized application status:", error.status)
        print("Check network access, model availability, API permissions, and quota in your provider dashboard.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
