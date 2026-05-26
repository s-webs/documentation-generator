"""Tests for docgen.scanner module."""

from __future__ import annotations

import os
import tempfile

from docgen.scanner import (
    ProjectFile,
    ProjectScan,
    _build_tree,
    _detect_language,
    _is_binary,
    scan_project,
)


class TestDetectLanguage:
    def test_python(self):
        assert _detect_language("app.py") == "Python"

    def test_javascript(self):
        assert _detect_language("index.js") == "JavaScript"

    def test_typescript(self):
        assert _detect_language("main.ts") == "TypeScript"

    def test_dockerfile(self):
        assert _detect_language("Dockerfile") == "Dockerfile"

    def test_makefile(self):
        assert _detect_language("Makefile") == "Makefile"

    def test_unknown(self):
        assert _detect_language("data.xyz") == "Unknown"

    def test_case_insensitive(self):
        assert _detect_language("App.PY") == "Python"

    def test_nested_path(self):
        assert _detect_language("src/utils/helper.go") == "Go"


class TestIsBinary:
    def test_png(self):
        assert _is_binary("image.png") is True

    def test_python(self):
        assert _is_binary("script.py") is False

    def test_lock(self):
        assert _is_binary("yarn.lock") is True

    def test_exe(self):
        assert _is_binary("prog.exe") is True


class TestProjectFile:
    def test_dataclass_fields(self):
        pf = ProjectFile(path="a.py", content="print(1)", language="Python")
        assert pf.path == "a.py"
        assert pf.content == "print(1)"
        assert pf.language == "Python"


class TestProjectScan:
    def test_name_from_root(self):
        scan = ProjectScan(root="/tmp/myproject", files=[], tree="")
        assert scan.name == "myproject"

    def test_custom_name(self):
        scan = ProjectScan(root="/tmp/myproject", files=[], tree="", name="Custom")
        assert scan.name == "Custom"

    def test_languages(self):
        files = [
            ProjectFile("a.py", "x", "Python"),
            ProjectFile("b.py", "y", "Python"),
            ProjectFile("c.js", "z", "JavaScript"),
        ]
        scan = ProjectScan(root="/tmp/p", files=files, tree="")
        langs = scan.languages
        assert langs["Python"] == 2
        assert langs["JavaScript"] == 1

    def test_total_size(self):
        files = [
            ProjectFile("a.py", "hello", "Python"),
            ProjectFile("b.py", "world!", "Python"),
        ]
        scan = ProjectScan(root="/tmp/p", files=files, tree="")
        assert scan.total_size == 11

    def test_summary(self):
        files = [ProjectFile("a.py", "x", "Python")]
        scan = ProjectScan(root="/tmp/p", files=files, tree="")
        s = scan.summary()
        assert "Python" in s
        assert "1" in s


class TestScanProject:
    def test_scan_basic(self, tmp_path):
        (tmp_path / "main.py").write_text("print('hello')")
        (tmp_path / "readme.md").write_text("# Project")

        result = scan_project(str(tmp_path))

        assert len(result.files) == 2
        paths = {f.path for f in result.files}
        assert "main.py" in paths
        assert "readme.md" in paths

    def test_scan_skips_hidden_files(self, tmp_path):
        (tmp_path / ".hidden").write_text("secret")
        (tmp_path / "visible.py").write_text("x = 1")

        result = scan_project(str(tmp_path))

        paths = {f.path for f in result.files}
        assert ".hidden" not in paths
        assert "visible.py" in paths

    def test_scan_skips_binary(self, tmp_path):
        (tmp_path / "image.png").write_bytes(b"\x89PNG")
        (tmp_path / "code.py").write_text("pass")

        result = scan_project(str(tmp_path))

        paths = {f.path for f in result.files}
        assert "image.png" not in paths
        assert "code.py" in paths

    def test_scan_skips_skip_dirs(self, tmp_path):
        node_modules = tmp_path / "node_modules"
        node_modules.mkdir()
        (node_modules / "pkg.js").write_text("module.exports = {}")
        (tmp_path / "app.js").write_text("console.log('hi')")

        result = scan_project(str(tmp_path))

        paths = {f.path for f in result.files}
        assert "app.js" in paths
        assert not any("node_modules" in p for p in paths)

    def test_scan_skips_empty_files(self, tmp_path):
        (tmp_path / "empty.py").write_text("")
        (tmp_path / "notempty.py").write_text("x = 1")

        result = scan_project(str(tmp_path))

        paths = {f.path for f in result.files}
        assert "empty.py" not in paths
        assert "notempty.py" in paths

    def test_scan_respects_gitignore(self, tmp_path):
        (tmp_path / ".gitignore").write_text("ignored.py\n")
        (tmp_path / "ignored.py").write_text("x = 1")
        (tmp_path / "kept.py").write_text("y = 2")

        result = scan_project(str(tmp_path))

        paths = {f.path for f in result.files}
        assert "ignored.py" not in paths
        assert "kept.py" in paths

    def test_scan_not_a_directory(self):
        import pytest

        with pytest.raises(ValueError, match="Not a directory"):
            scan_project("/nonexistent/path")

    def test_tree_output(self, tmp_path):
        sub = tmp_path / "src"
        sub.mkdir()
        (sub / "main.py").write_text("pass")
        (tmp_path / "readme.md").write_text("# Hi")

        result = scan_project(str(tmp_path))

        assert "src/" in result.tree
        assert "main.py" in result.tree
        assert "readme.md" in result.tree
