# crewai-twocaptcha

[![PyPI](https://img.shields.io/pypi/v/crewai-twocaptcha.svg)](https://pypi.org/project/crewai-twocaptcha/)
[![Python](https://img.shields.io/pypi/pyversions/crewai-twocaptcha.svg)](https://pypi.org/project/crewai-twocaptcha/)
[![CI](https://github.com/2captchar/crewai-twocaptcha/actions/workflows/ci.yml/badge.svg)](https://github.com/2captchar/crewai-twocaptcha/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/2captchar/crewai-twocaptcha/blob/main/LICENSE)

> **Languages:** **English** · [Русский](https://github.com/2captchar/crewai-twocaptcha/blob/main/README.ru.md)

`TwoCaptchaSolverTool` — a [CrewAI](https://github.com/crewAIInc/crewAI) tool that
solves captchas through the [2Captcha](https://2captcha.com/) service and
returns the solution token (e.g. `g-recaptcha-response`) to your agent.

## Supported captcha types

| `captcha_type` | 2Captcha method | Required input fields | Verified end-to-end |
| -------------- | --------------- | --------------------- | ------------------- |
| `recaptcha_v2` | `userrecaptcha`                | `website_url`, `sitekey` | ✔ |
| `recaptcha_v3` | `userrecaptcha` + `version=v3` | `website_url`, `sitekey`, `action` (optional `min_score`) | ✔ |
| `turnstile`    | `turnstile`                    | `website_url`, `sitekey` (optional `action`) | ✔ |
| `image`        | `base64`                       | `body` (base64-encoded image) | ✔ |
| `geetest`      | `geetest`                      | `website_url`, `gt`, `challenge` | unit-tested; live requires fresh `challenge` |

End-to-end verification is performed against the official 2Captcha demo pages;
reproduce it yourself with `scripts/live_check.py` (see below).

## Installation

```bash
pip install crewai-twocaptcha
```

Or with `uv`:

```bash
uv add crewai-twocaptcha
```

## Quick example

Set your 2Captcha API key:

```bash
export TWOCAPTCHA_API_KEY="your-2captcha-api-key"
```

Then use it like any other CrewAI tool:

```python
from crewai_twocaptcha import TwoCaptchaSolverTool

tool = TwoCaptchaSolverTool()

token = tool.run(
    captcha_type="recaptcha_v2",
    website_url="https://example.com/login",
    sitekey="6Lc_aCMTAAAAABx7u2N0D1XVhC2VB3b7C3oFqOAx",
)

print(token)  # -> g-recaptcha-response value
```

## Arguments

### Constructor

- `api_key` (`str`, optional): 2Captcha API key. Falls back to the
  `TWOCAPTCHA_API_KEY` environment variable.
- `config` (`TwoCaptchaConfig | dict`, optional): polling/timeouts override.

Config fields (with defaults):

| Field | Default | Description |
| ----- | ------- | ----------- |
| `poll_interval` | `10` | Seconds between result polls |
| `max_attempts`  | `30` | Maximum number of polls (≈5 min total by default) |
| `timeout`       | `20` | Per-request HTTP timeout, seconds |
| `api_base`      | `https://2captcha.com` | Base API URL |

### Environment variables

- `TWOCAPTCHA_API_KEY` — your [2Captcha](https://2captcha.com/enterpage) API key.

## Examples per captcha type

### reCAPTCHA v2

```python
tool.run(
    captcha_type="recaptcha_v2",
    website_url="https://example.com/login",
    sitekey="6Lc_aCMTAAAAABx7u2N0D1XVhC2VB3b7C3oFqOAx",
)
```

### reCAPTCHA v3

```python
tool.run(
    captcha_type="recaptcha_v3",
    website_url="https://example.com/submit",
    sitekey="6Lc_aCMTAAAAABx7u2N0D1XVhC2VB3b7C3oFqOAx",
    action="submit",
    min_score=0.7,
)
```

### Cloudflare Turnstile

```python
tool.run(
    captcha_type="turnstile",
    website_url="https://example.com/",
    sitekey="0x4AAAAAAAA1bXxxxxxxxxxx",
    action="login",  # optional
)
```

### Image (text) captcha

```python
import base64

with open("captcha.png", "rb") as fh:
    body = base64.b64encode(fh.read()).decode()

tool.run(captcha_type="image", body=body)
```

### GeeTest

```python
tool.run(
    captcha_type="geetest",
    website_url="https://example.com/",
    gt="f2ae6cadcf7886856696502e1d55e00c",
    challenge="12345678abcdefghij",
)
```

## Using inside a CrewAI agent

```python
from crewai import Agent, Crew, Task
from crewai_twocaptcha import TwoCaptchaSolverTool

solver = TwoCaptchaSolverTool()

scraper = Agent(
    role="Web Scraper",
    goal="Log into protected pages that require captcha solving.",
    backstory="An expert at automating captcha-gated workflows.",
    tools=[solver],
)

task = Task(
    description=(
        "Solve the reCAPTCHA on https://example.com/login with sitekey "
        "6Lc_aCMTAAAAABx7u2N0D1XVhC2VB3b7C3oFqOAx and return the token."
    ),
    expected_output="The g-recaptcha-response token as a plain string.",
    agent=scraper,
)

Crew(agents=[scraper], tasks=[task]).kickoff()
```

## Error handling

The tool raises exceptions instead of returning error strings (which would
otherwise be indistinguishable from a real token for the agent):

- `ValueError` — missing `TWOCAPTCHA_API_KEY`.
- `pydantic.ValidationError` — the input doesn't match the selected
  `captcha_type` (e.g. `recaptcha_v3` without `action`).
- `crewai_twocaptcha.TwoCaptchaError` — the 2Captcha API returned an error
  (`ERROR_WRONG_USER_KEY`, `ERROR_CAPTCHA_UNSOLVABLE`, …) or we exceeded
  `config.max_attempts * config.poll_interval` seconds.
- `requests.HTTPError` — non-2xx HTTP response from the API.

## Reproducing the end-to-end check

The repository ships with `scripts/live_check.py`, which runs every captcha
type against 2Captcha's official demo pages:

```bash
export TWOCAPTCHA_API_KEY="your-key"
python scripts/live_check.py
```

Total cost is roughly $0.01–0.02 per full run. Use `--no-image` to skip the
image case or `--geetest GT CHALLENGE` to test GeeTest with a fresh challenge
copied from your browser DevTools.

## Links

- 2Captcha API reference: <https://2captcha.com/2captcha-api>
- Get an API key: <https://2captcha.com/enterpage>
- CrewAI: <https://github.com/crewAIInc/crewAI>
- Publishing custom tools guide: <https://docs.crewai.com/en/guides/tools/publish-custom-tools>

## License

MIT — see [LICENSE](https://github.com/2captchar/crewai-twocaptcha/blob/main/LICENSE).
