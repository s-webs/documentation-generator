# docgen

CLI tool that automatically generates technical documentation from source code using AI and publishes it to [BookStack](https://www.bookstackapp.com/).

## How it works

1. **Scan** — recursively reads the project directory, filters out binary/hidden files, respects `.gitignore`, and builds a structured representation of the codebase.
2. **Analyze** — sends the codebase context to an OpenAI-compatible API to generate documentation sections (overview, architecture, tech stack, API reference, setup guide, per-module docs). Independent sections are generated in parallel for speed.
3. **Publish** — creates (or updates) a shelf, book, chapters, and pages in BookStack via its REST API. Re-running on the same project updates existing documentation instead of creating duplicates.

## Installation

```bash
# Clone and install in editable mode
git clone <repo-url>
cd documentation-gen
python -m venv .venv
source .venv/bin/activate
pip install -e .

# For development (includes pytest)
pip install -e ".[dev]"
```

## Configuration

Copy `.env.example` to `.env` and fill in the values:

```bash
cp .env.example .env
```

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | Yes | API key for the OpenAI-compatible provider |
| `OPENAI_BASE_URL` | Yes | Base URL of the API (e.g. `https://api.openai.com/v1`) |
| `OPENAI_MODEL` | No | Model name (default: `mimo-v2.5-pro`) |
| `BOOKSTACK_URL` | Yes* | BookStack instance URL (e.g. `http://localhost:8080`) |
| `BOOKSTACK_TOKEN_ID` | Yes* | BookStack API token ID |
| `BOOKSTACK_TOKEN_SECRET` | Yes* | BookStack API token secret |

\* Not required when using `--dry-run`.

## Usage

```bash
# Generate and publish documentation
docgen /path/to/project

# Preview without publishing (no BookStack credentials needed)
docgen /path/to/project --dry-run

# Custom project name and shelf
docgen /path/to/project --name "My Project" --shelf "Engineering Docs"

# Use a different model
docgen /path/to/project --model gpt-4o

# Debug output
docgen /path/to/project --verbose

# Specify a different .env file
docgen /path/to/project --env-file /path/to/.env
```

## Project structure

```
src/docgen/
├── cli.py        — CLI entry point, orchestrates the pipeline
├── scanner.py    — Project directory scanner and file reader
├── analyzer.py   — AI-powered documentation generator (async)
└── bookstack.py  — BookStack REST API client with idempotent operations
```

## Running tests

```bash
pytest
```
