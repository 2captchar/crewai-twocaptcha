"""Live end-to-end check against the real 2Captcha API.

Usage:
    set TWOCAPTCHA_API_KEY=xxx            # cmd.exe
    $env:TWOCAPTCHA_API_KEY = "xxx"       # PowerShell
    export TWOCAPTCHA_API_KEY=xxx         # bash
    python scripts/live_check.py

This script is intentionally NOT part of pytest: it performs real HTTP calls
and spends real money on your 2Captcha balance (~$0.003 per solve for the
token-based captchas, slightly more for image).

All cases use official 2Captcha demo pages, so no extra setup is required.
GeeTest is skipped by default because its ``challenge`` value is dynamic and
has to be scraped from a headless browser; run with ``--geetest GT CHALLENGE``
to test it with values copied from your browser DevTools.

Exit code:
    0 — all selected cases passed
    1 — at least one case failed
    2 — missing/invalid API key
"""

from __future__ import annotations

import argparse
import base64
import os
import sys
import time

import requests

from crewai_twocaptcha import (
    TwoCaptchaConfig,
    TwoCaptchaError,
    TwoCaptchaSolverTool,
)

TEST_IMAGE_URL = (
    "https://raw.githubusercontent.com/2captcha/2captcha-python/master/"
    "examples/images/normal.jpg"
)


def _fetch_test_image_b64() -> str:
    resp = requests.get(TEST_IMAGE_URL, timeout=30)
    resp.raise_for_status()
    return base64.b64encode(resp.content).decode("ascii")


def _build_cases(args: argparse.Namespace) -> list[dict[str, object]]:
    cases: list[dict[str, object]] = [
        {
            "label": "reCAPTCHA v2",
            "payload": {
                "captcha_type": "recaptcha_v2",
                "website_url": "https://2captcha.com/demo/recaptcha-v2",
                "sitekey": "6LfD3PIbAAAAAJs_eEHvoOl75_83eXSqpPSRFJ_u",
            },
        },
        {
            "label": "reCAPTCHA v3",
            "payload": {
                "captcha_type": "recaptcha_v3",
                "website_url": "https://2captcha.com/demo/recaptcha-v3",
                "sitekey": "6LfB5_IbAAAAAMCtsjEHEHKqcB9iQocwwxTiihJu",
                "action": "demo_action",
                "min_score": 0.3,
            },
        },
        {
            "label": "Cloudflare Turnstile",
            "payload": {
                "captcha_type": "turnstile",
                "website_url": "https://2captcha.com/demo/cloudflare-turnstile",
                "sitekey": "3x00000000000000000000FF",
            },
        },
    ]

    if not args.no_image:
        print("Fetching test image for 'image' case ...", flush=True)
        img_b64 = _fetch_test_image_b64()
        cases.append(
            {
                "label": "Image (normal) captcha",
                "payload": {"captcha_type": "image", "body": img_b64},
            }
        )

    if args.geetest:
        gt, challenge = args.geetest
        cases.append(
            {
                "label": "GeeTest (manual challenge)",
                "payload": {
                    "captcha_type": "geetest",
                    "website_url": "https://2captcha.com/demo/geetest",
                    "gt": gt,
                    "challenge": challenge,
                },
            }
        )

    return cases


def _run_case(tool: TwoCaptchaSolverTool, case: dict[str, object]) -> bool:
    label = case["label"]
    payload: dict[str, object] = case["payload"]  # type: ignore[assignment]

    print(f"\n=== {label} ===")
    for k, v in payload.items():
        if k == "body":
            print(f"  {k:12s}: <base64, {len(v)} chars>")  # type: ignore[arg-type]
        else:
            print(f"  {k:12s}: {v}")

    started = time.monotonic()
    try:
        result = tool._run(**payload)
    except TwoCaptchaError as exc:
        print(f"  FAIL: {exc}")
        return False
    except Exception as exc:
        print(f"  FAIL (unexpected): {type(exc).__name__}: {exc}")
        return False

    elapsed = time.monotonic() - started
    preview = result[:70] + ("..." if len(result) > 70 else "")
    print(f"  OK in {elapsed:5.1f}s  ({len(result)} chars)")
    print(f"  token: {preview}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--no-image",
        action="store_true",
        help="Skip the 'image' captcha case (avoids downloading a test image).",
    )
    parser.add_argument(
        "--geetest",
        nargs=2,
        metavar=("GT", "CHALLENGE"),
        help=(
            "Enable GeeTest case with gt + fresh challenge copied from your "
            "browser DevTools on https://2captcha.com/demo/geetest. The "
            "challenge expires in ~2 minutes, so run this quickly."
        ),
    )
    args = parser.parse_args()

    if not os.getenv("TWOCAPTCHA_API_KEY"):
        print("ERROR: TWOCAPTCHA_API_KEY is not set.", file=sys.stderr)
        return 2

    tool = TwoCaptchaSolverTool(
        config=TwoCaptchaConfig(poll_interval=5, max_attempts=60, timeout=30),
    )
    print(f"Tool: {tool.name}")
    print(f"Args schema: {list(tool.args_schema.model_fields)}")

    cases = _build_cases(args)
    passed = sum(1 for c in cases if _run_case(tool, c))

    print(f"\nDone: {passed}/{len(cases)} passed")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
