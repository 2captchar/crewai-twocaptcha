"""Tests for crewai_twocaptcha.TwoCaptchaSolverTool.

All network calls (``requests.post`` / ``requests.get``) are mocked — these
tests never hit the real 2Captcha API. Polling delays are eliminated by
patching ``time.sleep``.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from crewai_twocaptcha import (
    TwoCaptchaConfig,
    TwoCaptchaError,
    TwoCaptchaSolverInput,
    TwoCaptchaSolverTool,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TWOCAPTCHA_API_KEY", raising=False)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip all real sleeping so the polling loop is instantaneous."""
    monkeypatch.setattr("crewai_twocaptcha.tool.time.sleep", lambda *_a, **_kw: None)


@pytest.fixture
def fast_tool() -> TwoCaptchaSolverTool:
    """Tool with small polling budget so timeout tests terminate quickly."""
    return TwoCaptchaSolverTool(
        api_key="test-key",
        config=TwoCaptchaConfig(poll_interval=1, max_attempts=3, timeout=1),
    )


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


def test_initialization_with_explicit_key() -> None:
    tool = TwoCaptchaSolverTool(api_key="abc")
    assert tool.api_key == "abc"
    assert tool.name == "2Captcha Solver"
    assert tool.args_schema is TwoCaptchaSolverInput


def test_initialization_reads_env_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TWOCAPTCHA_API_KEY", "env-key")
    tool = TwoCaptchaSolverTool()
    assert tool.api_key == "env-key"


def test_initialization_accepts_config_dict() -> None:
    tool = TwoCaptchaSolverTool(
        api_key="k",
        config={"poll_interval": 1, "max_attempts": 2, "timeout": 3},
    )
    assert tool.config.poll_interval == 1
    assert tool.config.max_attempts == 2
    assert tool.config.timeout == 3


def test_missing_api_key_raises_value_error() -> None:
    tool = TwoCaptchaSolverTool()
    assert tool.api_key is None
    with pytest.raises(ValueError, match="TWOCAPTCHA_API_KEY"):
        tool._run(
            captcha_type="recaptcha_v2",
            website_url="http://x",
            sitekey="sk",
        )


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_validation_recaptcha_v2_requires_sitekey() -> None:
    with pytest.raises(ValidationError):
        TwoCaptchaSolverInput(captcha_type="recaptcha_v2", website_url="http://x")


def test_validation_recaptcha_v3_requires_action() -> None:
    with pytest.raises(ValidationError, match="action"):
        TwoCaptchaSolverInput(
            captcha_type="recaptcha_v3",
            website_url="http://x",
            sitekey="sk",
        )


def test_validation_image_requires_body() -> None:
    with pytest.raises(ValidationError, match="body"):
        TwoCaptchaSolverInput(captcha_type="image")


def test_validation_geetest_requires_challenge() -> None:
    with pytest.raises(ValidationError, match="challenge"):
        TwoCaptchaSolverInput(
            captcha_type="geetest",
            website_url="http://x",
            gt="gt-val",
        )


# ---------------------------------------------------------------------------
# _build_payload per captcha_type
# ---------------------------------------------------------------------------


def test_build_payload_recaptcha_v2() -> None:
    inp = TwoCaptchaSolverInput(
        captcha_type="recaptcha_v2", website_url="http://x", sitekey="sk"
    )
    p = TwoCaptchaSolverTool._build_payload("key", inp)
    assert p["method"] == "userrecaptcha"
    assert p["googlekey"] == "sk"
    assert p["pageurl"] == "http://x"
    assert p["key"] == "key"
    assert p["json"] == 1
    assert "version" not in p


def test_build_payload_recaptcha_v3() -> None:
    inp = TwoCaptchaSolverInput(
        captcha_type="recaptcha_v3",
        website_url="http://x",
        sitekey="sk",
        action="login",
        min_score=0.7,
    )
    p = TwoCaptchaSolverTool._build_payload("key", inp)
    assert p["method"] == "userrecaptcha"
    assert p["version"] == "v3"
    assert p["action"] == "login"
    assert p["min_score"] == 0.7
    assert p["googlekey"] == "sk"


def test_build_payload_turnstile_with_action() -> None:
    inp = TwoCaptchaSolverInput(
        captcha_type="turnstile",
        website_url="http://x",
        sitekey="sk",
        action="login",
    )
    p = TwoCaptchaSolverTool._build_payload("key", inp)
    assert p["method"] == "turnstile"
    assert p["sitekey"] == "sk"
    assert p["pageurl"] == "http://x"
    assert p["action"] == "login"


def test_build_payload_turnstile_without_action() -> None:
    inp = TwoCaptchaSolverInput(
        captcha_type="turnstile", website_url="http://x", sitekey="sk"
    )
    p = TwoCaptchaSolverTool._build_payload("key", inp)
    assert p["method"] == "turnstile"
    assert "action" not in p


def test_build_payload_image() -> None:
    inp = TwoCaptchaSolverInput(captcha_type="image", body="BASE64DATA==")
    p = TwoCaptchaSolverTool._build_payload("key", inp)
    assert p["method"] == "base64"
    assert p["body"] == "BASE64DATA=="


def test_build_payload_geetest() -> None:
    inp = TwoCaptchaSolverInput(
        captcha_type="geetest",
        website_url="http://x",
        gt="gt-val",
        challenge="ch-val",
    )
    p = TwoCaptchaSolverTool._build_payload("key", inp)
    assert p["method"] == "geetest"
    assert p["gt"] == "gt-val"
    assert p["challenge"] == "ch-val"
    assert p["pageurl"] == "http://x"


# ---------------------------------------------------------------------------
# _run: end-to-end with mocked HTTP
# ---------------------------------------------------------------------------


def _mock_response(json_payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = json_payload
    resp.raise_for_status.return_value = None
    return resp


def test_run_success_returns_token(fast_tool: TwoCaptchaSolverTool) -> None:
    submit_resp = _mock_response({"status": 1, "request": "task-42"})
    poll_resp = _mock_response({"status": 1, "request": "SOLVED-TOKEN"})

    with patch("crewai_twocaptcha.tool.requests.post", return_value=submit_resp) as mp, patch(
        "crewai_twocaptcha.tool.requests.get", return_value=poll_resp
    ) as mg:
        token = fast_tool._run(
            captcha_type="recaptcha_v2",
            website_url="http://example.com",
            sitekey="sk",
        )

    assert token == "SOLVED-TOKEN"
    assert mp.call_count == 1
    assert mg.call_count == 1


def test_run_submit_error_raises(fast_tool: TwoCaptchaSolverTool) -> None:
    submit_resp = _mock_response({"status": 0, "request": "ERROR_WRONG_USER_KEY"})

    with (
        patch("crewai_twocaptcha.tool.requests.post", return_value=submit_resp),
        pytest.raises(TwoCaptchaError, match="ERROR_WRONG_USER_KEY"),
    ):
        fast_tool._run(
            captcha_type="recaptcha_v2",
            website_url="http://x",
            sitekey="sk",
        )


def test_run_poll_error_raises(fast_tool: TwoCaptchaSolverTool) -> None:
    submit_resp = _mock_response({"status": 1, "request": "task-1"})
    poll_resp = _mock_response({"status": 0, "request": "ERROR_CAPTCHA_UNSOLVABLE"})

    with patch("crewai_twocaptcha.tool.requests.post", return_value=submit_resp), patch(
        "crewai_twocaptcha.tool.requests.get", return_value=poll_resp
    ), pytest.raises(TwoCaptchaError, match="ERROR_CAPTCHA_UNSOLVABLE"):
        fast_tool._run(
            captcha_type="turnstile",
            website_url="http://x",
            sitekey="sk",
        )


def test_run_timeout_raises(fast_tool: TwoCaptchaSolverTool) -> None:
    submit_resp = _mock_response({"status": 1, "request": "task-1"})
    not_ready = _mock_response({"status": 0, "request": "CAPCHA_NOT_READY"})

    with patch("crewai_twocaptcha.tool.requests.post", return_value=submit_resp), patch(
        "crewai_twocaptcha.tool.requests.get", return_value=not_ready
    ) as mg, pytest.raises(TwoCaptchaError, match="Timed out"):
        fast_tool._run(
            captcha_type="turnstile",
            website_url="http://x",
            sitekey="sk",
        )

    # polled exactly max_attempts times (3 in the fixture)
    assert mg.call_count == fast_tool.config.max_attempts
