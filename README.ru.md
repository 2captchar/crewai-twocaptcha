# crewai-twocaptcha

[![PyPI](https://img.shields.io/pypi/v/crewai-twocaptcha.svg)](https://pypi.org/project/crewai-twocaptcha/)
[![Python](https://img.shields.io/pypi/pyversions/crewai-twocaptcha.svg)](https://pypi.org/project/crewai-twocaptcha/)
[![CI](https://github.com/2captchar/crewai-twocaptcha/actions/workflows/ci.yml/badge.svg)](https://github.com/2captchar/crewai-twocaptcha/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

> **Язык:** [English](./README.md) · **Русский**

`TwoCaptchaSolverTool` — инструмент для [CrewAI](https://github.com/crewAIInc/crewAI),
который решает капчи через сервис [2Captcha](https://2captcha.com/) и возвращает
агенту готовый токен-решение (например, `g-recaptcha-response`).

## Поддерживаемые типы капч

| `captcha_type` | Метод 2Captcha | Обязательные поля | Проверка end-to-end |
| -------------- | -------------- | ----------------- | ------------------- |
| `recaptcha_v2` | `userrecaptcha`                | `website_url`, `sitekey` | ✔ |
| `recaptcha_v3` | `userrecaptcha` + `version=v3` | `website_url`, `sitekey`, `action` (опц. `min_score`) | ✔ |
| `turnstile`    | `turnstile`                    | `website_url`, `sitekey` (опц. `action`) | ✔ |
| `image`        | `base64`                       | `body` (картинка в base64) | ✔ |
| `geetest`      | `geetest`                      | `website_url`, `gt`, `challenge` | покрыт юнит-тестами; для live нужен свежий `challenge` |

End-to-end проверка выполняется по официальным демо-страницам 2Captcha;
повторить её у себя можно через `scripts/live_check.py` (см. ниже).

## Установка

```bash
pip install crewai-twocaptcha
```

Или через `uv`:

```bash
uv add crewai-twocaptcha
```

## Быстрый старт

Задайте API-ключ 2Captcha:

```bash
export TWOCAPTCHA_API_KEY="ваш-2captcha-api-key"
```

```powershell
# PowerShell (Windows)
$env:TWOCAPTCHA_API_KEY = "ваш-2captcha-api-key"
```

Пример использования:

```python
from crewai_twocaptcha import TwoCaptchaSolverTool

tool = TwoCaptchaSolverTool()

token = tool.run(
    captcha_type="recaptcha_v2",
    website_url="https://example.com/login",
    sitekey="6Lc_aCMTAAAAABx7u2N0D1XVhC2VB3b7C3oFqOAx",
)

print(token)  # -> значение g-recaptcha-response
```

## Параметры

### Конструктор

- `api_key` (`str`, опц.): API-ключ 2Captcha. Если не задан, берётся из
  переменной окружения `TWOCAPTCHA_API_KEY`.
- `config` (`TwoCaptchaConfig | dict`, опц.): настройки опроса/таймаутов.

Поля `TwoCaptchaConfig` и их значения по умолчанию:

| Поле | По умолчанию | Описание |
| ---- | ------------ | -------- |
| `poll_interval` | `10` | Интервал между опросами результата (секунды) |
| `max_attempts`  | `30` | Максимум опросов (при дефолте ≈ 5 минут на задачу) |
| `timeout`       | `20` | HTTP-таймаут на запрос (секунды) |
| `api_base`      | `https://2captcha.com` | Базовый URL API |

### Переменные окружения

- `TWOCAPTCHA_API_KEY` — ваш ключ [2Captcha](https://2captcha.com/enterpage).

## Примеры по каждому типу капчи

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
    action="login",  # опционально
)
```

### Image (текстовая капча)

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

## Использование внутри CrewAI-агента

```python
from crewai import Agent, Crew, Task
from crewai_twocaptcha import TwoCaptchaSolverTool

solver = TwoCaptchaSolverTool()

scraper = Agent(
    role="Web Scraper",
    goal="Логиниться на страницах, требующих решения капчи.",
    backstory="Эксперт по автоматизации сценариев с капчами.",
    tools=[solver],
)

task = Task(
    description=(
        "Реши reCAPTCHA на https://example.com/login с sitekey "
        "6Lc_aCMTAAAAABx7u2N0D1XVhC2VB3b7C3oFqOAx и верни токен."
    ),
    expected_output="Токен g-recaptcha-response как строка.",
    agent=scraper,
)

Crew(agents=[scraper], tasks=[task]).kickoff()
```

## Обработка ошибок

Инструмент бросает исключения, а не возвращает строки с ошибкой — иначе агент
не отличил бы «ошибку» от настоящего токена:

- `ValueError` — не задан `TWOCAPTCHA_API_KEY`.
- `pydantic.ValidationError` — входные данные не соответствуют выбранному
  `captcha_type` (например, `recaptcha_v3` без `action`).
- `crewai_twocaptcha.TwoCaptchaError` — ошибка API 2Captcha
  (`ERROR_WRONG_USER_KEY`, `ERROR_CAPTCHA_UNSOLVABLE`, …) или превышен лимит
  `config.max_attempts * config.poll_interval` секунд.
- `requests.HTTPError` — не-2xx HTTP-ответ от API.

## Повторить end-to-end проверку у себя

В репозитории лежит `scripts/live_check.py` — он прогоняет все типы капч через
официальные демо-страницы 2Captcha:

```bash
export TWOCAPTCHA_API_KEY="ваш-ключ"
python scripts/live_check.py
```

Полный прогон обходится примерно в $0.01–0.02. Флаг `--no-image` пропускает
картинку, флаг `--geetest GT CHALLENGE` подключает GeeTest (значения `gt` и
свежего `challenge` нужно взять из DevTools браузера).

## Ссылки

- Справочник API 2Captcha: <https://2captcha.com/2captcha-api>
- Получить API-ключ: <https://2captcha.com/enterpage>
- CrewAI: <https://github.com/crewAIInc/crewAI>
- Как публиковать свой инструмент для CrewAI: <https://docs.crewai.com/en/guides/tools/publish-custom-tools>

## Лицензия

MIT — см. [LICENSE](./LICENSE).
