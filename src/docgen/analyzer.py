"""AI analyzer — generates technical documentation from project code via OpenAI-compatible API."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

import requests

from .scanner import ProjectFile, ProjectScan

logger = logging.getLogger("docgen")

DEFAULT_MODEL = "mimo-v2.5-pro"
MAX_CONTEXT_CHARS = 150_000


@dataclass
class DocSection:
    """A documentation section with title, content, and optional subsections."""

    title: str
    content: str
    order: int = 0


@dataclass
class ProjectDocs:
    """Complete documentation for a project."""

    project_name: str
    sections: list[DocSection] = field(default_factory=list)


SYSTEM_PROMPT = """\
You are a technical documentation writer. Your job is to analyze source code \
and produce clear, well-structured documentation in Markdown format.

IMPORTANT: Write ALL documentation content in Russian language. \
Use Russian for all section titles, descriptions, and text. \
Technical terms (class names, function names, file paths, CLI commands) \
may remain in English where appropriate.

You always respond with valid JSON matching the requested schema. \
Do not include any text outside the JSON.

IMPORTANT: All newlines inside JSON string values must be escaped as \\n. \
Do NOT use literal newlines inside JSON strings. \
Ensure every string is properly closed with a quote before the next JSON key."""


def _build_overview_prompt(scan: ProjectScan) -> str:
    """Build prompt for project overview generation."""
    key_names = {
        "readme.md", "readme.txt", "readme",
        "package.json", "pyproject.toml", "cargo.toml", "go.mod",
        "dockerfile", "docker-compose.yml", "docker-compose.yaml",
        ".env.example", "settings.py", "config.py", "config.yaml",
        "app.py", "main.py", "index.ts", "index.js", "main.go",
        "requirements.txt", "gemfile", "makefile",
    }

    key_files = [f for f in scan.files if os.path.basename(f.path).lower() in key_names]
    key_files_content = ""
    for f in key_files[:10]:
        key_files_content += f"\n\n--- {f.path} ---\n{f.content[:5000]}"

    return f"""Проанализируй проект и сгенерируй документацию на русском языке.

## Информация о проекте
{scan.summary()}

## Дерево файлов
```
{scan.tree}
```

## Ключевые файлы
{key_files_content}

Ответь JSON-объектом с массивом "sections". Каждая секция имеет "title" (string) и "content" (Markdown string).

Сгенерируй секции строго в указанном порядке:

1. **О проекте** — что делает проект, его назначение, целевая аудитория.

2. **Паспорт проекта** — content должен содержать ТОЛЬКО Markdown-таблицу с двумя колонками: \
"Параметр" и "Значение". Строки таблицы (заполни на основе анализа кода):
   - Наименование проекта
   - Команда проекта (если указана в README/конфигах, иначе напиши "Не указана")
   - Краткое описание проекта
   - Практическая применимость
   - Используемые технологии
   - Стадия готовности проекта (определи по состоянию кода: прототип / MVP / продакшен)
   - Ожидаемый результат

3. **Архитектура** — высокоуровневая архитектура, паттерны проектирования, основные компоненты.

4. **Технологический стек** — языки, фреймворки, библиотеки, инструменты.

5. **Структура проекта** — описание структуры каталогов и файлов.

Пиши на русском языке. Документация должна быть профессиональной и подробной."""


def _build_modules_prompt(scan: ProjectScan) -> str:
    """Build prompt for combined modules and technical implementation docs."""
    files_content = ""
    for f in scan.files[:30]:
        files_content += f"\n\n--- {f.path} ---\n{f.content[:6000]}"

    return f"""Проанализируй все исходные файлы проекта и сгенерируй единый раздел \
"Модули и техническая реализация".

## Проект: {scan.name}

## Дерево файлов
```
{scan.tree}
```

## Исходные файлы:
{files_content}

Ответь JSON-объектом: {{"title": "Модули и техническая реализация", "content": "..."}}
Содержание (content) должно быть подробной Markdown-документацией на русском языке. \
Для каждого модуля/каталога проекта опиши:
- Назначение модуля
- Ключевые классы и функции, их сигнатуры и назначение
- Взаимодействие между модулями
- API-эндпоинты, если применимо (метод, путь, описание)
- Используемые переменные окружения и конфигурация

Структурируй документ по модулям/каталогам с заголовками. \
Пиши подробно, но лаконично."""


def _build_setup_prompt(scan: ProjectScan) -> str:
    """Build prompt for setup/installation documentation."""
    setup_names = {
        "readme.md", "readme.txt", "package.json", "pyproject.toml",
        "requirements.txt", "dockerfile", "docker-compose.yml",
        "docker-compose.yaml", "makefile", ".env.example",
        "gemfile", "cargo.toml", "go.mod",
    }
    setup_files = [f for f in scan.files if os.path.basename(f.path).lower() in setup_names]

    files_content = ""
    for f in setup_files[:10]:
        files_content += f"\n\n--- {f.path} ---\n{f.content[:5000]}"

    return f"""Сгенерируй документацию по установке и запуску проекта.

## Проект: {scan.name}
## Языки: {', '.join(f'{k}: {v}' for k, v in scan.languages.items())}

## Конфигурационные файлы:
{files_content}

Ответь JSON-объектом: {{"title": "Начало работы", "content": "..."}}
Документируй на русском языке:
- Предварительные требования и системные требования
- Шаги установки
- Настройка окружения
- Как запустить проект
- Частые проблемы и их решение"""


def _build_security_prompt(scan: ProjectScan) -> str:
    """Build prompt for security audit documentation."""
    files_content = ""
    for f in scan.files[:30]:
        files_content += f"\n\n--- {f.path} ---\n{f.content[:6000]}"

    return f"""Проведи аудит безопасности проекта на основе исходного кода и сгенерируй \
раздел документации "Безопасность".

## Проект: {scan.name}

## Исходные файлы:
{files_content}

Ответь JSON-объектом: {{"title": "Безопасность", "content": "..."}}
Содержание (content) должно быть подробной Markdown-документацией на русском языке. \
Проанализируй и документируй:
- **Управление секретами и переменными окружения** — как хранятся и используются \
API-ключи, токены, пароли; есть ли риск утечки
- **Аутентификация и авторизация** — механизмы аутентификации в проекте, \
управление доступом, токены
- **Валидация входных данных** — проверяются ли пользовательские данные, \
защита от инъекций, sanitization
- **Безопасность зависимостей** — используемые сторонние библиотеки, \
известные уязвимости, актуальность версий
- **Рекомендации по улучшению** — конкретные шаги для повышения безопасности проекта

Будь объективен и конкретен. Указывай файлы и строки, где обнаружены проблемы."""


def _call_ai(
    api_key: str,
    base_url: str,
    model: str,
    prompt: str,
    retries: int = 3,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    """Call OpenAI-compatible API via requests and parse JSON response."""
    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept-Encoding": "identity",
    }
    payload = {
        "model": model,
        "max_tokens": 32000,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    }

    http = session or requests.Session()
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            resp = http.post(url, headers=headers, json=payload, timeout=(30, 600))

            logger.debug(
                "HTTP %d | Content-Length: %s | Encoding: %s | Body[:200]: %s",
                resp.status_code,
                resp.headers.get("Content-Length", "?"),
                resp.headers.get("Content-Encoding", "none"),
                resp.text[:200] if resp.text else "(empty)",
            )

            if resp.status_code != 200:
                raise RuntimeError(f"API returned {resp.status_code}: {resp.text[:500]}")

            if not resp.text or not resp.text.strip():
                raise ValueError("API returned empty response body")

            data = resp.json()

            msg = data["choices"][0]["message"]
            text: str = msg.get("content", "") or ""
            finish = data["choices"][0].get("finish_reason", "unknown")

            logger.debug(
                "AI response: finish_reason=%s, msg_keys=%s, content_len=%d, "
                "content_repr[:100]=%r",
                finish, list(msg.keys()), len(text), text[:100],
            )

            if not text.strip():
                raise ValueError(f"Empty response from model (finish_reason={finish})")

            return _extract_json(text)

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            last_error = e
            if attempt < retries - 1:
                delay = 3 * (attempt + 1)
                logger.warning(
                    "Attempt %d/%d failed: %s — retrying in %ds...",
                    attempt + 1, retries, e, delay,
                )
                time.sleep(delay)
        except Exception as e:
            last_error = e
            if attempt < retries - 1:
                delay = 5 * (attempt + 1)
                logger.warning(
                    "Attempt %d/%d failed: %s — retrying in %ds...",
                    attempt + 1, retries, e, delay,
                )
                time.sleep(delay)

    raise last_error  # type: ignore[misc]


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences wrapping JSON.

    Only strips fences when the text *starts* with ```, to avoid
    corrupting JSON that contains code fences inside string values.
    """
    stripped = text.strip()
    if not stripped.startswith("```"):
        return text

    if stripped.startswith("```json"):
        start = 7
    else:
        start = 3
        if stripped[start:start + 1] == "\n":
            start += 1
        else:
            nl = stripped.find("\n", start)
            start = (nl + 1) if nl != -1 else start

    end = stripped.rfind("```")
    if end > start:
        return stripped[start:end].strip()
    return stripped[start:].strip()


def _find_json_object(text: str) -> str:
    """Locate the outermost {...} JSON object in the text."""
    first_brace = text.find("{")
    if first_brace < 0:
        return text
    depth = 0
    in_string = False
    escape = False
    for i in range(first_brace, len(text)):
        c = text[i]
        if escape:
            escape = False
            continue
        if c == "\\" and in_string:
            escape = True
            continue
        if c == '"' and not escape:
            in_string = not in_string
        elif not in_string:
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return text[first_brace : i + 1]
    return text[first_brace:]


_VALID_JSON_ESCAPES = frozenset(r'"\\/bfnrtu')


def _fix_json_strings(text: str) -> str:
    """Escape control characters and invalid escape sequences inside JSON string values."""
    result: list[str] = []
    in_string = False
    escape_next = False
    for ch in text:
        if escape_next:
            escape_next = False
            if ch not in _VALID_JSON_ESCAPES:
                result.append("\\")
            result.append(ch)
            continue
        if ch == "\\" and in_string:
            result.append(ch)
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            result.append(ch)
            continue
        if in_string:
            if ch == "\n":
                result.append("\\n")
                continue
            if ch == "\r":
                result.append("\\r")
                continue
            if ch == "\t":
                result.append("\\t")
                continue
            if ord(ch) < 0x20:
                result.append(f"\\u{ord(ch):04x}")
                continue
        result.append(ch)
    return "".join(result)


def _clean_text(text: str) -> str:
    """Strip BOM, zero-width chars, and other invisible Unicode garbage."""
    text = text.lstrip("\ufeff\u200b\u200c\u200d\u2060\u00a0")
    return text.strip()


def _extract_json(text: str) -> dict[str, Any]:
    """Extract JSON from model response, handling code blocks, control chars, etc."""
    text = _clean_text(text)
    text = _strip_code_fences(text)

    # Stage 1: try direct parse (works when text is already valid JSON,
    # e.g. content field already unescaped by resp.json())
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.debug("JSON parse stage 1 (direct) failed: %s", e)

    # Stage 2: extract JSON object boundaries (for text with extra
    # preamble/postamble around the JSON)
    extracted = _find_json_object(text)
    try:
        return json.loads(extracted)
    except json.JSONDecodeError as e:
        logger.debug("JSON parse stage 2 (extract) failed: %s", e)

    # Stage 3: fix control chars and invalid escapes
    repaired = _fix_json_strings(extracted)
    try:
        return json.loads(repaired)
    except json.JSONDecodeError as e:
        logger.debug("JSON parse stage 3 (fix strings) failed: %s", e)

    # Stage 4: strip trailing commas
    repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
    try:
        return json.loads(repaired)
    except json.JSONDecodeError as e:
        logger.debug("JSON parse stage 4 (trailing commas) failed: %s", e)
        raise


def _truncate_scan(scan: ProjectScan, max_chars: int = MAX_CONTEXT_CHARS) -> ProjectScan:
    """Create a truncated copy of scan if total content is too large."""
    if scan.total_size <= max_chars:
        return scan

    priority_names = {
        "readme.md", "package.json", "pyproject.toml", "dockerfile",
        "docker-compose.yml", "app.py", "main.py", "index.ts",
    }

    def priority_key(f: ProjectFile) -> int:
        return 0 if os.path.basename(f.path).lower() in priority_names else 1

    sorted_files = sorted(scan.files, key=priority_key)
    selected: list[ProjectFile] = []
    total = 0

    for f in sorted_files:
        if total + len(f.content) > max_chars:
            remaining = max_chars - total
            if remaining > 500:
                truncated = ProjectFile(
                    path=f.path,
                    content=f.content[:remaining] + "\n... [truncated]",
                    language=f.language,
                )
                selected.append(truncated)
            break
        selected.append(f)
        total += len(f.content)

    return ProjectScan(root=scan.root, files=selected, tree=scan.tree)


def _generate_section(
    api_key: str,
    base_url: str,
    model: str,
    prompt: str,
    fallback_title: str,
    order: int,
    session: requests.Session | None = None,
) -> DocSection | None:
    """Generate a single documentation section, returning None on failure."""
    try:
        result = _call_ai(api_key, base_url, model, prompt, session=session)
        return DocSection(
            title=result.get("title", fallback_title),
            content=result.get("content", ""),
            order=order,
        )
    except Exception as e:
        logger.warning("Failed to generate '%s': %s", fallback_title, e)
        return None


def analyze_project(scan: ProjectScan, model: str | None = None) -> ProjectDocs:
    """Analyze a project and generate documentation in 4 chapters.

    Chapters: О проекте (overview), Начало работы, Модули и техническая
    реализация, Безопасность. Each is generated sequentially via a shared
    HTTP session.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is required")

    base_url = os.environ.get("OPENAI_BASE_URL")
    if not base_url:
        raise ValueError("OPENAI_BASE_URL environment variable is required")
    base_url = base_url.rstrip("/")

    model = model or os.environ.get("OPENAI_MODEL", DEFAULT_MODEL)
    scan = _truncate_scan(scan)
    docs = ProjectDocs(project_name=scan.name)

    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(
        pool_connections=2, pool_maxsize=2, max_retries=0,
    )
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    # 1. Overview (sequential)
    logger.info("  Generating project overview...")
    overview_prompt = _build_overview_prompt(scan)
    try:
        result = _call_ai(api_key, base_url, model, overview_prompt, session=session)
        for i, section in enumerate(result.get("sections", [])):
            docs.sections.append(DocSection(
                title=section["title"],
                content=section["content"],
                order=i,
            ))
    except Exception as e:
        logger.warning("  Failed to parse overview: %s", e)

    # 2. Fixed documentation sections
    tasks: list[tuple[str, str, int]] = [
        (_build_setup_prompt(scan), "Начало работы", 10),
        (_build_modules_prompt(scan), "Модули и техническая реализация", 20),
        (_build_security_prompt(scan), "Безопасность", 30),
    ]

    for prompt, title, ord_ in tasks:
        logger.info("  [AI] %s ...", title)
        section = _generate_section(
            api_key, base_url, model, prompt, title, ord_, session=session,
        )
        if section is not None:
            docs.sections.append(section)

    session.close()
    docs.sections.sort(key=lambda s: s.order)
    return docs
