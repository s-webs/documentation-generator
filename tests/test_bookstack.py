"""Tests for docgen.bookstack module."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
import responses

from docgen.bookstack import BookStackClient, BookStackConfig

BASE_URL = "http://bookstack.test"


@pytest.fixture
def config() -> BookStackConfig:
    return BookStackConfig(url=BASE_URL, token_id="tid", token_secret="tsecret")


@pytest.fixture
def client(config: BookStackConfig) -> BookStackClient:
    return BookStackClient(config)


class TestBookStackConfig:
    def test_from_env_success(self):
        env = {
            "BOOKSTACK_URL": "http://localhost:8080",
            "BOOKSTACK_TOKEN_ID": "id123",
            "BOOKSTACK_TOKEN_SECRET": "secret456",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = BookStackConfig.from_env()
            assert cfg.url == "http://localhost:8080"
            assert cfg.token_id == "id123"
            assert cfg.token_secret == "secret456"

    def test_from_env_strips_trailing_slash(self):
        env = {
            "BOOKSTACK_URL": "http://localhost:8080/",
            "BOOKSTACK_TOKEN_ID": "id",
            "BOOKSTACK_TOKEN_SECRET": "secret",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = BookStackConfig.from_env()
            assert cfg.url == "http://localhost:8080"

    def test_from_env_missing_url(self):
        env = {"BOOKSTACK_TOKEN_ID": "id", "BOOKSTACK_TOKEN_SECRET": "s"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValueError, match="BOOKSTACK_URL"):
                BookStackConfig.from_env()

    def test_from_env_missing_token(self):
        env = {"BOOKSTACK_URL": "http://localhost"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValueError, match="BOOKSTACK_TOKEN_ID"):
                BookStackConfig.from_env()


class TestBookStackClientCreate:
    @responses.activate
    def test_create_shelf(self, client: BookStackClient):
        responses.add(
            responses.POST,
            f"{BASE_URL}/api/shelves",
            json={"id": 1, "name": "Test Shelf"},
            status=200,
        )
        result = client.create_shelf("Test Shelf", "A description")
        assert result["id"] == 1
        assert result["name"] == "Test Shelf"

    @responses.activate
    def test_create_book(self, client: BookStackClient):
        responses.add(
            responses.POST,
            f"{BASE_URL}/api/books",
            json={"id": 2, "name": "Test Book"},
            status=200,
        )
        result = client.create_book("Test Book", shelf_id=1)
        assert result["id"] == 2

    @responses.activate
    def test_create_chapter(self, client: BookStackClient):
        responses.add(
            responses.POST,
            f"{BASE_URL}/api/chapters",
            json={"id": 3, "name": "Ch1"},
            status=200,
        )
        result = client.create_chapter("Ch1", book_id=2)
        assert result["id"] == 3

    @responses.activate
    def test_create_page(self, client: BookStackClient):
        responses.add(
            responses.POST,
            f"{BASE_URL}/api/pages",
            json={"id": 4, "name": "Page1"},
            status=200,
        )
        result = client.create_page("Page1", "# Content", chapter_id=3)
        assert result["id"] == 4

    def test_create_page_requires_parent(self, client: BookStackClient):
        with pytest.raises(ValueError, match="Either book_id or chapter_id"):
            client.create_page("Page1", "content")


class TestBookStackClientFind:
    @responses.activate
    def test_find_shelf_found(self, client: BookStackClient):
        responses.add(
            responses.GET,
            f"{BASE_URL}/api/shelves",
            json={"data": [{"id": 1, "name": "Docs"}]},
            status=200,
        )
        result = client.find_shelf("Docs")
        assert result is not None
        assert result["id"] == 1

    @responses.activate
    def test_find_shelf_not_found(self, client: BookStackClient):
        responses.add(
            responses.GET,
            f"{BASE_URL}/api/shelves",
            json={"data": []},
            status=200,
        )
        result = client.find_shelf("Nonexistent")
        assert result is None

    @responses.activate
    def test_find_chapter(self, client: BookStackClient):
        responses.add(
            responses.GET,
            f"{BASE_URL}/api/chapters",
            json={"data": [{"id": 5, "name": "Overview"}]},
            status=200,
        )
        result = client.find_chapter("Overview", book_id=2)
        assert result is not None
        assert result["id"] == 5


class TestBookStackClientIdempotent:
    @responses.activate
    def test_find_or_create_shelf_existing(self, client: BookStackClient):
        responses.add(
            responses.GET,
            f"{BASE_URL}/api/shelves",
            json={"data": [{"id": 10, "name": "Existing"}]},
            status=200,
        )
        result = client.find_or_create_shelf("Existing")
        assert result["id"] == 10
        assert len(responses.calls) == 1  # Only GET, no POST

    @responses.activate
    def test_find_or_create_shelf_new(self, client: BookStackClient):
        responses.add(
            responses.GET,
            f"{BASE_URL}/api/shelves",
            json={"data": []},
            status=200,
        )
        responses.add(
            responses.POST,
            f"{BASE_URL}/api/shelves",
            json={"id": 11, "name": "New"},
            status=200,
        )
        result = client.find_or_create_shelf("New")
        assert result["id"] == 11
        assert len(responses.calls) == 2  # GET then POST

    @responses.activate
    def test_create_or_update_page_existing(self, client: BookStackClient):
        responses.add(
            responses.GET,
            f"{BASE_URL}/api/pages",
            json={"data": [{"id": 20, "name": "Overview"}]},
            status=200,
        )
        responses.add(
            responses.PUT,
            f"{BASE_URL}/api/pages/20",
            json={"id": 20, "name": "Overview"},
            status=200,
        )
        result = client.create_or_update_page("Overview", "# Updated", chapter_id=3)
        assert result["id"] == 20
        assert len(responses.calls) == 2  # GET then PUT

    @responses.activate
    def test_create_or_update_page_new(self, client: BookStackClient):
        responses.add(
            responses.GET,
            f"{BASE_URL}/api/pages",
            json={"data": []},
            status=200,
        )
        responses.add(
            responses.POST,
            f"{BASE_URL}/api/pages",
            json={"id": 21, "name": "New Page"},
            status=200,
        )
        result = client.create_or_update_page("New Page", "content", chapter_id=3)
        assert result["id"] == 21


class TestBookStackClientConnection:
    @responses.activate
    def test_test_connection_success(self, client: BookStackClient):
        responses.add(
            responses.GET,
            f"{BASE_URL}/api/shelves",
            json={"data": []},
            status=200,
        )
        assert client.test_connection() is True

    @responses.activate
    def test_test_connection_failure(self, client: BookStackClient):
        responses.add(
            responses.GET,
            f"{BASE_URL}/api/shelves",
            json={"message": "Unauthorized"},
            status=401,
        )
        assert client.test_connection() is False

    @responses.activate
    def test_api_error_raises_runtime_error(self, client: BookStackClient):
        responses.add(
            responses.POST,
            f"{BASE_URL}/api/shelves",
            json={"message": "Validation failed"},
            status=422,
        )
        with pytest.raises(RuntimeError, match="422"):
            client.create_shelf("Bad")
