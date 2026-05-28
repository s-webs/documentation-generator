"""CLI entry point — orchestrates scanning, analysis, and BookStack publishing."""

from __future__ import annotations

import argparse
import logging
import os
import sys

from dotenv import load_dotenv

from .analyzer import analyze_project
from .bookstack import BookStackClient, BookStackConfig
from .scanner import scan_project

logger = logging.getLogger("docgen")

CHAPTER_MAP: dict[str, str] = {
    "о проекте": "О проекте",
    "паспорт проекта": "О проекте",
    "архитектура": "О проекте",
    "технологический стек": "О проекте",
    "структура проекта": "О проекте",
    "начало работы": "Начало работы",
    "модули и техническая реализация": "Модули и техническая реализация",
    "безопасность": "Безопасность",
}

CHAPTER_ORDER = ["О проекте", "Начало работы", "Модули и техническая реализация", "Безопасность"]


def _get_chapter_name(section_title: str) -> str:
    """Map a section title to its parent chapter name."""
    lower = section_title.lower()
    for keyword, chapter in CHAPTER_MAP.items():
        if keyword in lower:
            return chapter
    return section_title


def _validate_env(dry_run: bool) -> None:
    """Check that all required environment variables are set before doing any work."""
    missing: list[str] = []
    if not os.environ.get("OPENAI_API_KEY"):
        missing.append("OPENAI_API_KEY")
    if not os.environ.get("OPENAI_BASE_URL"):
        missing.append("OPENAI_BASE_URL")
    if not dry_run:
        for var in ("BOOKSTACK_URL", "BOOKSTACK_TOKEN_ID", "BOOKSTACK_TOKEN_SECRET"):
            if not os.environ.get(var):
                missing.append(var)
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="docgen",
        description="AI agent that generates technical documentation and publishes it to BookStack",
    )
    parser.add_argument(
        "project_path",
        help="Path to the project directory to document",
    )
    parser.add_argument(
        "--name",
        help="Custom project name (default: directory name)",
    )
    parser.add_argument(
        "--model",
        help="AI model to use (default: mimo-v2.5-pro)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Analyze project but don't publish to BookStack",
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to .env file (default: .env)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()
    load_dotenv(args.env_file)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(message)s",
    )

    # Validate env vars early, before any scanning work
    try:
        _validate_env(args.dry_run)
    except ValueError as e:
        logger.error("Error: %s", e)
        sys.exit(1)

    # Step 1: Scan project
    logger.info("\n%s", "=" * 60)
    logger.info("  docgen — AI Documentation Generator")
    logger.info("%s\n", "=" * 60)

    logger.info("[1/3] Scanning project: %s", args.project_path)
    try:
        scan = scan_project(args.project_path)
    except ValueError as e:
        logger.error("Error: %s", e)
        sys.exit(1)

    logger.info("  Found %d files", len(scan.files))
    lang_summary = ", ".join(f"{k}({v})" for k, v in list(scan.languages.items())[:5])
    logger.info("  Languages: %s\n", lang_summary)

    if args.name:
        scan.name = args.name

    # Step 2: Analyze with AI
    logger.info("[2/3] Analyzing with AI...")
    try:
        docs = analyze_project(scan, model=args.model)
    except ValueError as e:
        logger.error("Error: %s", e)
        sys.exit(1)
    except Exception as e:
        logger.error("Error calling AI API: %s", e)
        sys.exit(1)

    logger.info("  Generated %d documentation sections\n", len(docs.sections))

    if args.dry_run:
        logger.info("[DRY RUN] Skipping BookStack publishing")
        logger.info("\nGenerated sections:")
        for section in docs.sections:
            content_preview = section.content[:100].replace("\n", " ")
            logger.info("  - %s (%d chars)", section.title, len(section.content))
            logger.info("    %s...", content_preview)
        return

    # Step 3: Publish to BookStack
    logger.info("[3/3] Publishing to BookStack...")
    try:
        config = BookStackConfig.from_env()
    except ValueError as e:
        logger.error("Error: %s", e)
        sys.exit(1)

    client = BookStackClient(config)

    if not client.test_connection():
        logger.error("Error: Cannot connect to BookStack API. Check URL and credentials.")
        sys.exit(1)

    try:
        logger.info("  Creating/updating book: %s", docs.project_name)
        book = client.find_or_create_book(
            name=docs.project_name,
            description=f"Technical documentation for {docs.project_name}",
        )
        book_id: int = book["id"]

        chapters_by_name: dict[str, dict] = {}
        sections_by_chapter: dict[str, list] = {}

        for section in docs.sections:
            ch_name = _get_chapter_name(section.title)
            if ch_name not in sections_by_chapter:
                sections_by_chapter[ch_name] = []
            sections_by_chapter[ch_name].append(section)

        for ch_name in CHAPTER_ORDER:
            sections = sections_by_chapter.get(ch_name)
            if not sections:
                continue

            if ch_name not in chapters_by_name:
                logger.info("  Creating/updating chapter: %s", ch_name)
                chapters_by_name[ch_name] = client.find_or_create_chapter(
                    name=ch_name,
                    book_id=book_id,
                )

            chapter = chapters_by_name[ch_name]
            for section in sections:
                logger.info("    Creating/updating page: %s", section.title)
                client.create_or_update_page(
                    name=section.title,
                    content=section.content,
                    chapter_id=chapter["id"],
                )

        for ch_name, sections in sections_by_chapter.items():
            if ch_name in CHAPTER_ORDER:
                continue
            logger.info("  Creating/updating chapter: %s", ch_name)
            chapter = client.find_or_create_chapter(name=ch_name, book_id=book_id)
            for section in sections:
                logger.info("    Creating/updating page: %s", section.title)
                client.create_or_update_page(
                    name=section.title,
                    content=section.content,
                    chapter_id=chapter["id"],
                )

        logger.info("\n%s", "=" * 60)
        logger.info("  Done! Documentation published to BookStack")
        logger.info("  Book: %s/books/%s", config.url, book_id)
        logger.info("%s\n", "=" * 60)

    except RuntimeError as e:
        logger.error("Error publishing to BookStack: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
