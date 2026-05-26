"""Tests for docgen.analyzer module."""

from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest

from docgen.analyzer import (
    DocSection,
    ProjectDocs,
    _build_overview_prompt,
    _build_setup_prompt,
    _extract_json,
    _truncate_scan,
    analyze_project,
)
from docgen.scanner import ProjectFile, ProjectScan


class TestExtractJson:
    def test_clean_json(self):
        text = '{"title": "Hello", "content": "World"}'
        result = _extract_json(text)
        assert result["title"] == "Hello"
        assert result["content"] == "World"

    def test_json_in_code_block(self):
        text = '```json\n{"title": "Hi", "content": "There"}\n```'
        result = _extract_json(text)
        assert result["title"] == "Hi"

    def test_json_in_generic_code_block(self):
        text = '```\n{"title": "A", "content": "B"}\n```'
        result = _extract_json(text)
        assert result["title"] == "A"

    def test_json_with_leading_text(self):
        text = 'Here is the result:\n{"title": "X", "content": "Y"}'
        result = _extract_json(text)
        assert result["title"] == "X"

    def test_json_with_unescaped_newlines(self):
        text = '{"title": "A", "content": "line1\nline2\nline3"}'
        result = _extract_json(text)
        assert result["content"] == "line1\nline2\nline3"

    def test_json_with_sections_array(self):
        text = '{"sections": [{"title": "A", "content": "B"}, {"title": "C", "content": "D"}]}'
        result = _extract_json(text)
        assert len(result["sections"]) == 2
        assert result["sections"][0]["title"] == "A"

    def test_json_with_escaped_newlines(self):
        text = '{"title": "A", "content": "line1\\nline2"}'
        result = _extract_json(text)
        assert result["content"] == "line1\nline2"

    def test_json_with_reasoning_prefix(self):
        text = 'Let me think about this...\n\nOkay, here:\n```json\n{"title": "Result", "content": "Done"}\n```'
        result = _extract_json(text)
        assert result["title"] == "Result"

    def test_nested_json(self):
        text = '{"title": "A", "content": "has {braces} inside"}'
        result = _extract_json(text)
        assert "braces" in result["content"]

    def test_invalid_backslash_escapes(self):
        text = '{"title": "A", "content": "path C:\\Users\\special"}'
        result = _extract_json(text)
        assert "Users" in result["content"]

    def test_trailing_comma(self):
        text = '{"sections": [{"title": "A", "content": "B"},]}'
        result = _extract_json(text)
        assert result["sections"][0]["title"] == "A"

    def test_invalid_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            _extract_json("not json at all")


class TestTruncateScan:
    def test_no_truncation_needed(self):
        files = [ProjectFile("a.py", "x" * 100, "Python")]
        scan = ProjectScan(root="/tmp/p", files=files, tree="tree")
        result = _truncate_scan(scan, max_chars=1000)
        assert len(result.files) == 1
        assert result.files[0].content == "x" * 100

    def test_truncation_applied(self):
        files = [
            ProjectFile("a.py", "x" * 600, "Python"),
            ProjectFile("b.py", "y" * 600, "Python"),
        ]
        scan = ProjectScan(root="/tmp/p", files=files, tree="tree")
        result = _truncate_scan(scan, max_chars=1000)
        total = sum(len(f.content) for f in result.files)
        assert total <= 1100

    def test_priority_files_kept(self):
        files = [
            ProjectFile("random.py", "x" * 500, "Python"),
            ProjectFile("pyproject.toml", "y" * 200, "TOML"),
        ]
        scan = ProjectScan(root="/tmp/p", files=files, tree="tree")
        result = _truncate_scan(scan, max_chars=300)
        paths = [f.path for f in result.files]
        assert "pyproject.toml" in paths

    def test_tree_preserved(self):
        files = [ProjectFile("a.py", "x" * 2000, "Python")]
        scan = ProjectScan(root="/tmp/p", files=files, tree="my-tree")
        result = _truncate_scan(scan, max_chars=100)
        assert result.tree == "my-tree"


class TestBuildPrompts:
    def _make_scan(self) -> ProjectScan:
        files = [
            ProjectFile("pyproject.toml", "[project]\nname='test'", "TOML"),
            ProjectFile("src/main.py", "print('hi')", "Python"),
        ]
        return ProjectScan(root="/tmp/testproj", files=files, tree="testproj/\n├── pyproject.toml\n└── src/")

    def test_overview_prompt_contains_project_info(self):
        scan = self._make_scan()
        prompt = _build_overview_prompt(scan)
        assert "testproj" in prompt
        assert "pyproject.toml" in prompt
        assert "JSON" in prompt

    def test_setup_prompt_contains_config(self):
        scan = self._make_scan()
        prompt = _build_setup_prompt(scan)
        assert "pyproject.toml" in prompt
        assert "Getting Started" in prompt


class TestAnalyzeProject:
    def test_missing_api_key(self):
        scan = ProjectScan(root="/tmp/p", files=[], tree="")
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="OPENAI_API_KEY"):
                analyze_project(scan)

    def test_missing_base_url(self):
        scan = ProjectScan(root="/tmp/p", files=[], tree="")
        env = {"OPENAI_API_KEY": "test-key"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValueError, match="OPENAI_BASE_URL"):
                analyze_project(scan)
