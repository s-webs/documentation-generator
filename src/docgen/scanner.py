"""Project scanner — reads project files and builds a structured representation."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import pathspec

MAX_FILE_SIZE = 100_000  # 100KB per file
BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg", ".webp",
    ".mp3", ".mp4", ".wav", ".avi", ".mov", ".mkv", ".flac",
    ".zip", ".tar", ".gz", ".rar", ".7z", ".bz2",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".exe", ".dll", ".so", ".dylib", ".bin", ".o", ".a",
    ".woff", ".woff2", ".ttf", ".eot",
    ".sqlite", ".db", ".lock",
}

SKIP_DIRS = {
    "node_modules", "__pycache__", ".git", ".svn", ".hg",
    ".venv", "venv", "env", ".env", ".tox", ".mypy_cache",
    ".pytest_cache", "dist", "build", ".eggs", ".idea", ".vscode",
    "vendor", "target", "bin", "obj",
}


@dataclass
class ProjectFile:
    """Represents a single file in the project."""

    path: str
    content: str
    language: str


@dataclass
class ProjectScan:
    """Result of scanning a project directory."""

    root: str
    files: list[ProjectFile]
    tree: str
    name: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            self.name = os.path.basename(os.path.abspath(self.root))

    @property
    def languages(self) -> dict[str, int]:
        """Count files per language."""
        counts: dict[str, int] = {}
        for f in self.files:
            counts[f.language] = counts.get(f.language, 0) + 1
        return dict(sorted(counts.items(), key=lambda x: -x[1]))

    @property
    def total_size(self) -> int:
        return sum(len(f.content) for f in self.files)

    def summary(self) -> str:
        """Human-readable summary of the project."""
        lang_parts = [f"{lang}: {count}" for lang, count in self.languages.items()]
        return (
            f"Project: {self.name}\n"
            f"Files: {len(self.files)}\n"
            f"Languages: {', '.join(lang_parts)}\n"
            f"Total content size: {self.total_size:,} chars"
        )


EXT_MAP: dict[str, str] = {
    ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
    ".jsx": "React JSX", ".tsx": "React TSX", ".vue": "Vue",
    ".rb": "Ruby", ".php": "PHP", ".java": "Java",
    ".go": "Go", ".rs": "Rust", ".c": "C", ".cpp": "C++",
    ".h": "C/C++ Header", ".cs": "C#", ".swift": "Swift",
    ".kt": "Kotlin", ".scala": "Scala", ".r": "R",
    ".sh": "Shell", ".bash": "Bash", ".zsh": "Zsh",
    ".sql": "SQL", ".html": "HTML", ".css": "CSS",
    ".scss": "SCSS", ".sass": "Sass", ".less": "Less",
    ".json": "JSON", ".yaml": "YAML", ".yml": "YAML",
    ".toml": "TOML", ".xml": "XML", ".md": "Markdown",
    ".rst": "reStructuredText", ".txt": "Text",
    ".dockerfile": "Dockerfile", ".tf": "Terraform",
    ".graphql": "GraphQL", ".proto": "Protobuf",
    ".lua": "Lua", ".dart": "Dart", ".ex": "Elixir",
    ".erl": "Erlang", ".hs": "Haskell", ".ml": "OCaml",
    ".clj": "Clojure", ".groovy": "Groovy",
}

SPECIAL_FILENAMES: dict[str, str] = {
    "dockerfile": "Dockerfile",
    "makefile": "Makefile",
    "cmakelists.txt": "Cmakelists.txt",
    "rakefile": "Rakefile",
    "gemfile": "Gemfile",
    "cargo.toml": "TOML",
}


def _detect_language(filepath: str) -> str:
    """Detect language from file extension."""
    basename = os.path.basename(filepath).lower()
    if basename in SPECIAL_FILENAMES:
        return SPECIAL_FILENAMES[basename]
    _, ext = os.path.splitext(filepath)
    return EXT_MAP.get(ext.lower(), "Unknown")


def _is_binary(filepath: str) -> bool:
    """Check if file is likely binary."""
    _, ext = os.path.splitext(filepath)
    return ext.lower() in BINARY_EXTENSIONS


def _load_gitignore(root: str) -> pathspec.PathSpec | None:
    """Load .gitignore patterns if the file exists."""
    gitignore_path = os.path.join(root, ".gitignore")
    if os.path.exists(gitignore_path):
        with open(gitignore_path) as f:
            return pathspec.PathSpec.from_lines("gitignore", f)
    return None


def _build_tree(root: str, files: list[str]) -> str:
    """Build a tree-like string representation of the project."""
    tree_lines: list[str] = []
    prefix_map: dict[str, list[str]] = {}

    for filepath in sorted(files):
        rel = os.path.relpath(filepath, root)
        parts = rel.split(os.sep)
        for i, part in enumerate(parts):
            dir_path = os.sep.join(parts[:i])
            if dir_path not in prefix_map:
                prefix_map[dir_path] = []
            if part not in prefix_map[dir_path]:
                prefix_map[dir_path].append(part)

    def _add_tree(dir_path: str, prefix: str = "") -> None:
        items = sorted(prefix_map.get(dir_path, []))
        dirs: list[str] = []
        file_items: list[str] = []
        for item in items:
            child_path = f"{dir_path}{os.sep}{item}" if dir_path else item
            if child_path in prefix_map:
                dirs.append(item)
            else:
                file_items.append(item)

        all_items = dirs + file_items
        for i, item in enumerate(all_items):
            is_last = i == len(all_items) - 1
            connector = "└── " if is_last else "├── "
            child_path = f"{dir_path}{os.sep}{item}" if dir_path else item

            if child_path in prefix_map:
                tree_lines.append(f"{prefix}{connector}{item}/")
                extension = "    " if is_last else "│   "
                _add_tree(child_path, prefix + extension)
            else:
                tree_lines.append(f"{prefix}{connector}{item}")

    tree_lines.append(f"{os.path.basename(root)}/")
    _add_tree("")
    return "\n".join(tree_lines)


def scan_project(project_path: str) -> ProjectScan:
    """Scan a project directory and return structured representation.

    Args:
        project_path: Path to the project root directory.

    Returns:
        ProjectScan with all readable files, tree structure, and metadata.
    """
    project_path = os.path.abspath(project_path)
    if not os.path.isdir(project_path):
        raise ValueError(f"Not a directory: {project_path}")

    gitignore = _load_gitignore(project_path)
    files: list[ProjectFile] = []
    all_paths: list[str] = []

    for dirpath, dirnames, filenames in os.walk(project_path):
        dirnames[:] = [
            d for d in dirnames
            if d not in SKIP_DIRS and not d.startswith(".")
        ]

        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(filepath, project_path)

            if filename.startswith("."):
                continue

            if gitignore and gitignore.match_file(rel_path):
                continue

            if _is_binary(filepath):
                continue

            try:
                size = os.path.getsize(filepath)
                if size > MAX_FILE_SIZE or size == 0:
                    continue
            except OSError:
                continue

            try:
                with open(filepath, encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except (OSError, PermissionError):
                continue

            language = _detect_language(filepath)
            files.append(ProjectFile(path=rel_path, content=content, language=language))
            all_paths.append(filepath)

    tree = _build_tree(project_path, all_paths)
    return ProjectScan(root=project_path, files=files, tree=tree)
