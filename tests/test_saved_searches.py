from pathlib import Path

import pytest

from find_oss.saved_searches import (
    DuplicateSavedSearchError,
    InvalidSavedSearchStoreError,
    SavedSearchNotFoundError,
    SavedSearchStore,
    slugify,
)


def test_slugify_creates_stable_machine_name() -> None:
    assert slugify(" AI Agents / Weekend Wins ") == "ai-agents-weekend-wins"


def test_saved_search_crud_round_trip(tmp_path: Path) -> None:
    store = SavedSearchStore(tmp_path / "saved-searches.yaml")

    created = store.create("AI Agent Wins", "Find Python agent issues")
    assert created.slug == "ai-agent-wins"
    assert store.get("ai-agent-wins").query == "Find Python agent issues"

    updated = store.update("ai-agent-wins", "Find TypeScript agent issues")
    assert updated.query == "Find TypeScript agent issues"
    assert updated.created_at == created.created_at
    assert store.list() == [updated]

    store.delete("ai-agent-wins")
    with pytest.raises(SavedSearchNotFoundError):
        store.get("ai-agent-wins")


def test_create_rejects_duplicate_slug(tmp_path: Path) -> None:
    store = SavedSearchStore(tmp_path / "saved-searches.yaml")
    store.create("AI Agent Wins", "first")

    with pytest.raises(DuplicateSavedSearchError):
        store.create("ai-agent-wins", "second")


def test_malformed_yaml_has_actionable_error(tmp_path: Path) -> None:
    path = tmp_path / "saved-searches.yaml"
    path.write_text("searches: [", encoding="utf-8")

    with pytest.raises(InvalidSavedSearchStoreError, match="Could not parse"):
        SavedSearchStore(path).list()

