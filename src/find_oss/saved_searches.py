from __future__ import annotations

import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import yaml
from pydantic import BaseModel


class SavedSearchError(ValueError):
    pass


class DuplicateSavedSearchError(SavedSearchError):
    pass


class SavedSearchNotFoundError(SavedSearchError):
    pass


class InvalidSavedSearchStoreError(SavedSearchError):
    pass


class SavedSearch(BaseModel):
    name: str
    slug: str
    query: str
    created_at: datetime
    updated_at: datetime


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not slug:
        raise SavedSearchError("Saved search name must contain a letter or number.")
    return slug


class SavedSearchStore:
    schema_version = 1

    def __init__(self, path: Path) -> None:
        self.path = path

    def _load(self) -> list[SavedSearch]:
        if not self.path.exists():
            return []
        try:
            raw = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as error:
            raise InvalidSavedSearchStoreError(
                f"Could not parse saved search file {self.path}: {error}"
            ) from error
        if not isinstance(raw, dict) or raw.get("schema_version") != self.schema_version:
            raise InvalidSavedSearchStoreError(
                f"Unsupported or missing schema_version in {self.path}."
            )
        try:
            return [SavedSearch.model_validate(item) for item in raw.get("searches", [])]
        except (TypeError, ValueError) as error:
            raise InvalidSavedSearchStoreError(
                f"Invalid saved search data in {self.path}: {error}"
            ) from error

    def _write(self, searches: list[SavedSearch]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": self.schema_version,
            "searches": [
                item.model_dump(mode="json") for item in sorted(
                    searches, key=lambda search: search.slug
                )
            ],
        }
        handle, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", dir=self.path.parent, text=True
        )
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as temporary:
                yaml.safe_dump(payload, temporary, sort_keys=False)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_name, self.path)
        except BaseException:
            Path(temporary_name).unlink(missing_ok=True)
            raise

    def list(self) -> list[SavedSearch]:
        return sorted(self._load(), key=lambda item: item.slug)

    def get(self, name_or_slug: str) -> SavedSearch:
        slug = slugify(name_or_slug)
        for item in self._load():
            if item.slug == slug:
                return item
        raise SavedSearchNotFoundError(f"Saved search '{name_or_slug}' was not found.")

    def create(self, name: str, query: str) -> SavedSearch:
        searches = self._load()
        slug = slugify(name)
        if any(item.slug == slug for item in searches):
            raise DuplicateSavedSearchError(
                f"Saved search '{name}' already exists; use saved update."
            )
        now = datetime.now(timezone.utc)
        item = SavedSearch(
            name=name.strip(),
            slug=slug,
            query=query.strip(),
            created_at=now,
            updated_at=now,
        )
        searches.append(item)
        self._write(searches)
        return item

    def update(self, name_or_slug: str, query: str) -> SavedSearch:
        searches = self._load()
        existing = self.get(name_or_slug)
        updated = existing.model_copy(
            update={"query": query.strip(), "updated_at": datetime.now(timezone.utc)}
        )
        self._write([updated if item.slug == existing.slug else item for item in searches])
        return updated

    def delete(self, name_or_slug: str) -> None:
        searches = self._load()
        existing = self.get(name_or_slug)
        self._write([item for item in searches if item.slug != existing.slug])

