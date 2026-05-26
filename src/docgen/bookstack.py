"""BookStack REST API client for creating and updating documentation structure."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

import requests

logger = logging.getLogger("docgen")


@dataclass
class BookStackConfig:
    """BookStack connection configuration."""

    url: str
    token_id: str
    token_secret: str

    @classmethod
    def from_env(cls) -> BookStackConfig:
        """Load config from environment variables."""
        url = os.environ.get("BOOKSTACK_URL", "").rstrip("/")
        token_id = os.environ.get("BOOKSTACK_TOKEN_ID", "")
        token_secret = os.environ.get("BOOKSTACK_TOKEN_SECRET", "")

        if not url:
            raise ValueError("BOOKSTACK_URL environment variable is required")
        if not token_id or not token_secret:
            raise ValueError(
                "BOOKSTACK_TOKEN_ID and BOOKSTACK_TOKEN_SECRET are required. "
                "Create an API token in BookStack: Settings → API Tokens"
            )

        return cls(url=url, token_id=token_id, token_secret=token_secret)


class BookStackClient:
    """Client for BookStack REST API with idempotent create-or-update semantics."""

    def __init__(self, config: BookStackConfig) -> None:
        self.config = config
        self.base_url = f"{config.url}/api"
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Token {config.token_id}:{config.token_secret}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

    def _request(self, method: str, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        """Make an API request."""
        url = f"{self.base_url}{endpoint}"
        response = self.session.request(method, url, **kwargs)

        if not response.ok:
            error_detail = ""
            try:
                error_detail = response.json().get("message", response.text)
            except Exception:
                error_detail = response.text
            raise RuntimeError(
                f"BookStack API error {response.status_code}: {error_detail}"
            )

        if response.status_code == 204:
            return {}
        return response.json()

    # ---- Find methods ----

    def find_shelf(self, name: str) -> dict[str, Any] | None:
        """Find a shelf by exact name. Returns first match or None."""
        result = self._request("GET", "/shelves", params={"filter[name]": name, "count": 1})
        data = result.get("data", [])
        return data[0] if data else None

    def find_book(self, name: str) -> dict[str, Any] | None:
        """Find a book by exact name. Returns first match or None."""
        result = self._request("GET", "/books", params={"filter[name]": name, "count": 1})
        data = result.get("data", [])
        return data[0] if data else None

    def find_chapter(self, name: str, book_id: int) -> dict[str, Any] | None:
        """Find a chapter by name within a specific book."""
        result = self._request(
            "GET", "/chapters",
            params={"filter[name]": name, "filter[book_id]": book_id, "count": 1},
        )
        data = result.get("data", [])
        return data[0] if data else None

    def find_page(
        self,
        name: str,
        book_id: int | None = None,
        chapter_id: int | None = None,
    ) -> dict[str, Any] | None:
        """Find a page by name, optionally scoped to a book or chapter."""
        params: dict[str, Any] = {"filter[name]": name, "count": 1}
        if chapter_id is not None:
            params["filter[chapter_id]"] = chapter_id
        elif book_id is not None:
            params["filter[book_id]"] = book_id
        result = self._request("GET", "/pages", params=params)
        data = result.get("data", [])
        return data[0] if data else None

    # ---- Create methods ----

    def create_shelf(self, name: str, description: str = "") -> dict[str, Any]:
        """Create a new shelf."""
        return self._request("POST", "/shelves", json={
            "name": name,
            "description": description,
        })

    def create_book(
        self, name: str, description: str = "", shelf_id: int | None = None,
    ) -> dict[str, Any]:
        """Create a new book, optionally on a shelf."""
        payload: dict[str, Any] = {"name": name, "description": description}
        if shelf_id is not None:
            payload["shelf_id"] = shelf_id
        return self._request("POST", "/books", json=payload)

    def create_chapter(
        self, name: str, book_id: int, description: str = "",
    ) -> dict[str, Any]:
        """Create a new chapter in a book."""
        return self._request("POST", "/chapters", json={
            "name": name,
            "book_id": book_id,
            "description": description,
        })

    def create_page(
        self,
        name: str,
        content: str,
        book_id: int | None = None,
        chapter_id: int | None = None,
    ) -> dict[str, Any]:
        """Create a new page in a book or chapter."""
        if book_id is None and chapter_id is None:
            raise ValueError("Either book_id or chapter_id must be provided")

        payload: dict[str, Any] = {
            "name": name,
            "content": content,
            "markdown": content,
        }
        if chapter_id is not None:
            payload["chapter_id"] = chapter_id
        else:
            payload["book_id"] = book_id

        return self._request("POST", "/pages", json=payload)

    # ---- Update methods ----

    def update_shelf(self, shelf_id: int, **fields: Any) -> dict[str, Any]:
        """Update an existing shelf."""
        return self._request("PUT", f"/shelves/{shelf_id}", json=fields)

    def update_book(self, book_id: int, **fields: Any) -> dict[str, Any]:
        """Update an existing book."""
        return self._request("PUT", f"/books/{book_id}", json=fields)

    def update_chapter(self, chapter_id: int, **fields: Any) -> dict[str, Any]:
        """Update an existing chapter."""
        return self._request("PUT", f"/chapters/{chapter_id}", json=fields)

    def update_page(self, page_id: int, **fields: Any) -> dict[str, Any]:
        """Update an existing page."""
        return self._request("PUT", f"/pages/{page_id}", json=fields)

    # ---- Idempotent find-or-create / create-or-update ----

    def find_or_create_shelf(self, name: str, description: str = "") -> dict[str, Any]:
        """Return existing shelf or create a new one."""
        existing = self.find_shelf(name)
        if existing:
            logger.debug("Found existing shelf '%s' (id=%s)", name, existing["id"])
            return existing
        logger.debug("Creating new shelf '%s'", name)
        return self.create_shelf(name, description)

    def find_or_create_book(
        self, name: str, description: str = "", shelf_id: int | None = None,
    ) -> dict[str, Any]:
        """Return existing book or create a new one."""
        existing = self.find_book(name)
        if existing:
            logger.debug("Found existing book '%s' (id=%s)", name, existing["id"])
            return existing
        logger.debug("Creating new book '%s'", name)
        return self.create_book(name, description, shelf_id)

    def find_or_create_chapter(
        self, name: str, book_id: int, description: str = "",
    ) -> dict[str, Any]:
        """Return existing chapter or create a new one."""
        existing = self.find_chapter(name, book_id)
        if existing:
            logger.debug("Found existing chapter '%s' (id=%s)", name, existing["id"])
            return existing
        logger.debug("Creating new chapter '%s'", name)
        return self.create_chapter(name, book_id, description)

    def create_or_update_page(
        self,
        name: str,
        content: str,
        book_id: int | None = None,
        chapter_id: int | None = None,
    ) -> dict[str, Any]:
        """Create a page or update it if one with the same name already exists."""
        existing = self.find_page(name, book_id=book_id, chapter_id=chapter_id)
        if existing:
            logger.debug("Updating existing page '%s' (id=%s)", name, existing["id"])
            return self.update_page(existing["id"], markdown=content, content=content)
        return self.create_page(name, content, book_id=book_id, chapter_id=chapter_id)

    # ---- Utility ----

    def test_connection(self) -> bool:
        """Test if the API connection works."""
        try:
            self._request("GET", "/shelves", params={"count": 1})
            return True
        except RuntimeError:
            return False
