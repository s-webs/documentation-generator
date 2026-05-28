"""Tests for docgen.cli module."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from docgen.analyzer import DocSection, ProjectDocs
from docgen.cli import _get_chapter_name, _validate_env


class TestGetChapterName:
    def test_about_project(self):
        assert _get_chapter_name("О проекте") == "О проекте"

    def test_passport(self):
        assert _get_chapter_name("Паспорт проекта") == "О проекте"

    def test_architecture(self):
        assert _get_chapter_name("Архитектура") == "О проекте"

    def test_tech_stack(self):
        assert _get_chapter_name("Технологический стек") == "О проекте"

    def test_structure(self):
        assert _get_chapter_name("Структура проекта") == "О проекте"

    def test_getting_started(self):
        assert _get_chapter_name("Начало работы") == "Начало работы"

    def test_modules(self):
        assert _get_chapter_name("Модули и техническая реализация") == "Модули и техническая реализация"

    def test_security(self):
        assert _get_chapter_name("Безопасность") == "Безопасность"

    def test_unknown_falls_through(self):
        assert _get_chapter_name("Something Unknown") == "Something Unknown"


class TestValidateEnv:
    def test_all_present(self):
        env = {
            "OPENAI_API_KEY": "key",
            "OPENAI_BASE_URL": "http://api.test/v1",
            "BOOKSTACK_URL": "http://bs.test",
            "BOOKSTACK_TOKEN_ID": "id",
            "BOOKSTACK_TOKEN_SECRET": "secret",
        }
        with patch.dict(os.environ, env, clear=True):
            _validate_env(dry_run=False)

    def test_dry_run_skips_bookstack(self):
        env = {
            "OPENAI_API_KEY": "key",
            "OPENAI_BASE_URL": "http://api.test/v1",
        }
        with patch.dict(os.environ, env, clear=True):
            _validate_env(dry_run=True)

    def test_missing_api_key(self):
        import pytest

        env = {"OPENAI_BASE_URL": "http://api.test/v1"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValueError, match="OPENAI_API_KEY"):
                _validate_env(dry_run=True)

    def test_missing_base_url(self):
        import pytest

        env = {"OPENAI_API_KEY": "key"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValueError, match="OPENAI_BASE_URL"):
                _validate_env(dry_run=True)

    def test_missing_bookstack_vars(self):
        import pytest

        env = {
            "OPENAI_API_KEY": "key",
            "OPENAI_BASE_URL": "http://api.test/v1",
        }
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValueError, match="BOOKSTACK_URL"):
                _validate_env(dry_run=False)


class TestMainDryRun:
    def test_dry_run_integration(self, tmp_path, capfd):
        (tmp_path / "main.py").write_text("print('hello')")

        mock_docs = ProjectDocs(
            project_name="testproj",
            sections=[
                DocSection(title="О проекте", content="Тестовый проект.", order=0),
                DocSection(title="Начало работы", content="Запуск.", order=10),
            ],
        )

        env = {
            "OPENAI_API_KEY": "test-key",
            "OPENAI_BASE_URL": "http://api.test/v1",
        }

        with (
            patch.dict(os.environ, env, clear=True),
            patch("docgen.cli.analyze_project", return_value=mock_docs),
            patch("sys.argv", ["docgen", str(tmp_path), "--dry-run"]),
        ):
            import logging
            logging.root.handlers.clear()

            from docgen.cli import main
            main()

        captured = capfd.readouterr()
        output = captured.out + captured.err
        assert "DRY RUN" in output
        assert "О проекте" in output
        assert "Начало работы" in output
