"""TwoCaptchaSolverTool — CrewAI tool for the 2Captcha solving service.

Supports reCAPTCHA v2, reCAPTCHA v3, Cloudflare Turnstile, image (base64)
and GeeTest captchas via the classic 2Captcha HTTP API
(``in.php`` / ``res.php``).

API reference: https://2captcha.com/2captcha-api
"""

from __future__ import annotations

import os
import time
from typing import Any, Literal

import requests
from crewai.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field, model_validator

try:
    from crewai.tools import EnvVar  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - older crewai versions
    EnvVar = None  # type: ignore[assignment]


CaptchaType = Literal[
    "recaptcha_v2",
    "recaptcha_v3",
    "turnstile",
    "image",
    "geetest",
]


class TwoCaptchaError(RuntimeError):
    """Raised when 2Captcha returns an API-level error or times out."""


class TwoCaptchaSolverInput(BaseModel):
    """Input schema for TwoCaptchaSolverTool.

    Required fields depend on ``captcha_type``:

    * ``recaptcha_v2`` — ``website_url``, ``sitekey``
    * ``recaptcha_v3`` — ``website_url``, ``sitekey``, ``action``
    * ``turnstile``    — ``website_url``, ``sitekey``
    * ``image``        — ``body`` (base64-encoded image bytes)
    * ``geetest``      — ``website_url``, ``gt``, ``challenge``
    """

    captcha_type: CaptchaType = Field(
        description="Captcha family to solve: recaptcha_v2 | recaptcha_v3 | turnstile | image | geetest.",
    )
    website_url: str | None = Field(
        default=None,
        description="Full URL of the page hosting the captcha (not needed for 'image').",
    )
    sitekey: str | None = Field(
        default=None,
        description="Captcha sitekey (data-sitekey/googlekey) for reCAPTCHA and Turnstile.",
    )
    action: str | None = Field(
        default=None,
        description="Action name for reCAPTCHA v3 (and optional for Turnstile).",
    )
    min_score: float | None = Field(
        default=0.3,
        description="Minimum acceptable score for reCAPTCHA v3 (0.1 - 0.9).",
    )
    body: str | None = Field(
        default=None,
        description="Base64-encoded image body for 'image' (normal/text) captchas.",
    )
    gt: str | None = Field(
        default=None,
        description="GeeTest public key (``gt`` parameter).",
    )
    challenge: str | None = Field(
        default=None,
        description="GeeTest dynamic challenge token.",
    )

    @model_validator(mode="after")
    def _validate_required_for_type(self) -> TwoCaptchaSolverInput:
        t = self.captcha_type
        missing: list[str] = []

        if t in {"recaptcha_v2", "recaptcha_v3", "turnstile"}:
            if not self.website_url:
                missing.append("website_url")
            if not self.sitekey:
                missing.append("sitekey")
        if t == "recaptcha_v3" and not self.action:
            missing.append("action")
        if t == "image" and not self.body:
            missing.append("body")
        if t == "geetest":
            if not self.website_url:
                missing.append("website_url")
            if not self.gt:
                missing.append("gt")
            if not self.challenge:
                missing.append("challenge")

        if missing:
            raise ValueError(
                f"captcha_type='{t}' requires: {', '.join(missing)}"
            )
        return self


class TwoCaptchaConfig(BaseModel):
    """Runtime configuration for polling and HTTP timeouts."""

    poll_interval: int = Field(default=10, ge=1, description="Seconds between result polls.")
    max_attempts: int = Field(default=30, ge=1, description="Maximum number of polls.")
    timeout: int = Field(default=20, ge=1, description="Per-request HTTP timeout, seconds.")
    api_base: str = Field(
        default="https://2captcha.com",
        description="Base URL of the 2Captcha API.",
    )


def _build_env_vars() -> list[Any]:
    if EnvVar is None:
        return []
    return [
        EnvVar(
            name="TWOCAPTCHA_API_KEY",
            description="API key for the 2Captcha service.",
            required=True,
        ),
    ]


class TwoCaptchaSolverTool(BaseTool):
    """Solve captchas through the 2Captcha service.

    Environment variables:

    * ``TWOCAPTCHA_API_KEY`` — your 2Captcha account API key.

    Example::

        from crewai_twocaptcha import TwoCaptchaSolverTool

        tool = TwoCaptchaSolverTool()
        token = tool.run(
            captcha_type="recaptcha_v2",
            website_url="https://example.com/login",
            sitekey="6Lc_aCMTAAAAABx7u2N0D1XVhC2VB3b7C3oFqOAx",
        )
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, validate_assignment=True)

    name: str = "2Captcha Solver"
    description: str = (
        "Solve captchas via the 2Captcha service. Supported captcha_type values: "
        "'recaptcha_v2', 'recaptcha_v3', 'turnstile', 'image', 'geetest'. "
        "Returns the solution token (e.g. g-recaptcha-response) as a string. "
        "Requires the TWOCAPTCHA_API_KEY environment variable or api_key constructor arg."
    )
    args_schema: type[BaseModel] = TwoCaptchaSolverInput

    package_dependencies: list[str] = Field(default_factory=lambda: ["requests"])
    env_vars: list[Any] = Field(default_factory=_build_env_vars)

    config: TwoCaptchaConfig = Field(default_factory=TwoCaptchaConfig)
    api_key: str | None = Field(default=None, description="2Captcha API key override.")

    def __init__(
        self,
        api_key: str | None = None,
        config: TwoCaptchaConfig | dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        if isinstance(config, dict):
            config = TwoCaptchaConfig(**config)
        elif config is None:
            config = TwoCaptchaConfig()

        resolved_key = api_key or os.getenv("TWOCAPTCHA_API_KEY")
        super().__init__(api_key=resolved_key, config=config, **kwargs)

    @staticmethod
    def _build_payload(api_key: str, inp: TwoCaptchaSolverInput) -> dict[str, Any]:
        """Map a validated input into a 2Captcha ``in.php`` payload."""
        payload: dict[str, Any] = {"key": api_key, "json": 1}

        if inp.captcha_type == "recaptcha_v2":
            payload.update(
                method="userrecaptcha",
                googlekey=inp.sitekey,
                pageurl=inp.website_url,
            )
        elif inp.captcha_type == "recaptcha_v3":
            payload.update(
                method="userrecaptcha",
                version="v3",
                googlekey=inp.sitekey,
                pageurl=inp.website_url,
                action=inp.action,
                min_score=inp.min_score if inp.min_score is not None else 0.3,
            )
        elif inp.captcha_type == "turnstile":
            payload.update(
                method="turnstile",
                sitekey=inp.sitekey,
                pageurl=inp.website_url,
            )
            if inp.action:
                payload["action"] = inp.action
        elif inp.captcha_type == "image":
            payload.update(method="base64", body=inp.body)
        elif inp.captcha_type == "geetest":
            payload.update(
                method="geetest",
                gt=inp.gt,
                challenge=inp.challenge,
                pageurl=inp.website_url,
            )
        return payload

    def _submit(self, payload: dict[str, Any]) -> str:
        """Submit a task to ``in.php`` and return the task id."""
        res = requests.post(
            f"{self.config.api_base}/in.php",
            data=payload,
            timeout=self.config.timeout,
        )
        res.raise_for_status()
        data = res.json()
        if data.get("status") != 1:
            raise TwoCaptchaError(f"Submit failed: {data.get('request')}")
        return str(data.get("request"))

    def _poll(self, task_id: str) -> str:
        """Poll ``res.php`` until the task is solved or we give up."""
        assert self.api_key, "api_key must be set before polling"
        params = {
            "key": self.api_key,
            "action": "get",
            "id": task_id,
            "json": 1,
        }
        url = f"{self.config.api_base}/res.php"

        for _ in range(self.config.max_attempts):
            time.sleep(self.config.poll_interval)
            res = requests.get(url, params=params, timeout=self.config.timeout)
            res.raise_for_status()
            data = res.json()

            if data.get("status") == 1:
                return str(data.get("request"))

            request = data.get("request")
            if request != "CAPCHA_NOT_READY":
                raise TwoCaptchaError(f"Solve failed: {request}")

        raise TwoCaptchaError(
            f"Timed out after {self.config.max_attempts * self.config.poll_interval}s "
            f"waiting for 2Captcha solution (task_id={task_id})."
        )

    def _run(self, **kwargs: Any) -> str:
        if not self.api_key:
            raise ValueError(
                "TWOCAPTCHA_API_KEY is not set. Pass api_key=... to the tool or export "
                "the TWOCAPTCHA_API_KEY environment variable."
            )

        inp = TwoCaptchaSolverInput(**kwargs)
        payload = self._build_payload(self.api_key, inp)
        task_id = self._submit(payload)
        return self._poll(task_id)
