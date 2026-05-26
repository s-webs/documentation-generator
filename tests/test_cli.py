"""Tests for docgen.cli module."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from docgen.analyzer import DocSection, ProjectDocs
from docgen.cli import _is_overview_section, _validate_env


class TestIsOverviewSection:
    def test_exact_match(self):
        assert _is_overview_section("Project Overview") is True

    def test_case_insensitive(self):
        assert _is_overview_section("project overview") is True

    def test_architecture(self):
        assert _is_overview_section("Architecture") is True

    def test_tech_stack_variant(self):
        assert _is_overview_section("Technology Stack") is True

    def test_structure(self):
        assert _is_overview_section("Project Structure") is True

    def test_module_not_overview(self):
        assert _is_overview_section("Module: utils") is False

    def test_api_reference_not_overview(self):
        assert _is_overview_section("API Reference") is False

    def test_getting_started_not_overview(self):
        assert _is_overview_section("Getting Started") is False


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
                DocSection(title="Project Overview", content="A test project.", order=0),
                DocSection(title="Getting Started", content="Run it.", order=20),
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
        assert "Project Overview" in output
        assert "Getting Started" in output
