"""The museums an art collection is curated from, by name (art backgrounds plan, D7).

Each provider admits a work only on its own rights signal and returns its largest allowed image.
None is generalised to another: a provider is added with its own fixture and rights test, and a
work's rights evidence records the field the provider answered, its value and when.
"""

from __future__ import annotations

import csv
import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from art_fetch import IMAGE_BYTES, USER_AGENT, Fetcher, FetchError, Response, fetch_https
from art_works import Provider, ProviderWork, Refused

CC0_URI = "https://creativecommons.org/publicdomain/zero/1.0/"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _get(fetch: Fetcher, url: str, hosts: frozenset[str], **options: Any) -> Response:
    """One request; a fetch the policy refuses or that fails refuses the work, not the run."""
    try:
        return fetch(url, allowed_hosts=hosts, **options)
    except FetchError as exc:
        raise Refused(str(exc)) from exc


def _json(response: Response, what: str) -> dict[str, Any]:
    if response.status in (404, 410):
        raise Refused(f"{what} is gone (HTTP {response.status})")
    if response.status != 200:
        raise Refused(f"{what} answered HTTP {response.status}")
    try:
        payload = json.loads(response.body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Refused(f"{what} is not JSON") from exc
    if not isinstance(payload, dict):
        raise Refused(f"{what} is not an object")
    return payload


def _text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _image(fetch: Fetcher, url: str, hosts: frozenset[str], headers: dict[str, str]) -> bytes:
    response = _get(fetch, url, hosts, max_bytes=IMAGE_BYTES, headers=headers)
    if response.status != 200 or not response.body:
        raise Refused(f"the image answered HTTP {response.status}")
    return response.body


def _rights(field: str, value: object, image_url: str, **extra: object) -> dict[str, Any]:
    return {
        "license": "CC0-1.0",
        "uri": CC0_URI,
        "evidence": {
            "provider_field": field,
            "provider_value": value,
            "image_url": image_url,
            "observed_at": _now(),
            **extra,
        },
    }


class Met:
    """The Metropolitan Museum of Art's Open Access API: `isPublicDomain` and its full image."""

    name = "met"
    API = "https://collectionapi.metmuseum.org/public/collection/v1/objects/{object_id}"
    API_HOSTS = frozenset({"collectionapi.metmuseum.org"})
    IMAGE_HOSTS = frozenset({"images.metmuseum.org"})

    def __init__(self, fetch: Fetcher = fetch_https) -> None:
        self._fetch = fetch

    def fetch(self, object_id: str) -> ProviderWork:
        record = _json(
            _get(self._fetch, self.API.format(object_id=object_id), self.API_HOSTS),
            f"The Met object {object_id}",
        )
        if str(record.get("objectID")) != object_id:
            raise Refused("the record names another object")
        if record.get("isPublicDomain") is not True:
            raise Refused("isPublicDomain is not true")
        image_url = record.get("primaryImage") or record.get("primaryImageSmall")
        if not isinstance(image_url, str) or not image_url:
            raise Refused("no Open Access image")
        image = _image(self._fetch, image_url, self.IMAGE_HOSTS, {})
        creator = _text(record.get("artistDisplayName"))
        bio = _text(record.get("artistDisplayBio"))
        return ProviderWork(
            provider=self.name,
            object_id=object_id,
            image=image,
            placard={
                "title": _text(record.get("title")),
                "creator": f"{creator}\n{bio}" if creator and bio else creator,
                "date": _text(record.get("objectDate")),
                "medium": _text(record.get("medium")),
                "dimensions": _text(record.get("dimensions")),
                "institution": "The Metropolitan Museum of Art",
                "canonical_url": _text(record.get("objectURL"))
                or f"https://www.metmuseum.org/art/collection/search/{object_id}",
            },
            rights=_rights(
                "isPublicDomain",
                True,
                image_url,
                image_field="primaryImage" if record.get("primaryImage") else "primaryImageSmall",
            ),
        )


class ArtInstitute:
    """The Art Institute of Chicago's API: `is_public_domain` and IIIF at 1686 px wide.

    The museum asks for 843 px unless there is a clear need for 1686; a wall screen is one, and
    the selection rules refuse a work whose 1686 px image would be upscaled (D6.2, D7).
    """

    name = "aic"
    API = (
        "https://api.artic.edu/api/v1/artworks/{object_id}"
        "?fields=id,title,artist_display,date_display,medium_display,dimensions,"
        "is_public_domain,image_id"
    )
    IMAGE = "https://www.artic.edu/iiif/2/{image_id}/full/1686,/0/default.jpg"
    API_HOSTS = frozenset({"api.artic.edu"})
    IMAGE_HOSTS = frozenset({"www.artic.edu"})

    def __init__(self, fetch: Fetcher = fetch_https) -> None:
        self._fetch = fetch

    def fetch(self, object_id: str) -> ProviderWork:
        payload = _json(
            _get(
                self._fetch,
                self.API.format(object_id=object_id),
                self.API_HOSTS,
                headers={"AIC-User-Agent": USER_AGENT},
            ),
            f"Art Institute artwork {object_id}",
        )
        record = payload.get("data")
        if not isinstance(record, dict) or str(record.get("id")) != object_id:
            raise Refused("the record names another object")
        if record.get("is_public_domain") is not True:
            raise Refused("is_public_domain is not true")
        image_id = record.get("image_id")
        if not isinstance(image_id, str) or not image_id:
            raise Refused("no image")
        image_url = self.IMAGE.format(image_id=image_id)
        image = _image(self._fetch, image_url, self.IMAGE_HOSTS, {"AIC-User-Agent": USER_AGENT})
        return ProviderWork(
            provider=self.name,
            object_id=object_id,
            image=image,
            placard={
                "title": _text(record.get("title")),
                "creator": _text(record.get("artist_display")),
                "date": _text(record.get("date_display")),
                "medium": _text(record.get("medium_display")),
                "dimensions": _text(record.get("dimensions")),
                "institution": "Art Institute of Chicago",
                "canonical_url": f"https://www.artic.edu/artworks/{object_id}",
            },
            rights=_rights("is_public_domain", True, image_url),
        )


class Cleveland:
    """The Cleveland Museum of Art's Open Access API: `share_license_status` and its print image."""

    name = "cleveland"
    API = "https://openaccess-api.clevelandart.org/api/artworks/{object_id}"
    API_HOSTS = frozenset({"openaccess-api.clevelandart.org"})
    IMAGE_HOSTS = frozenset({"openaccess-cdn.clevelandart.org"})

    def __init__(self, fetch: Fetcher = fetch_https) -> None:
        self._fetch = fetch

    def fetch(self, object_id: str) -> ProviderWork:
        payload = _json(
            _get(self._fetch, self.API.format(object_id=object_id), self.API_HOSTS),
            f"Cleveland artwork {object_id}",
        )
        record = payload.get("data")
        if not isinstance(record, dict) or str(record.get("id")) != object_id:
            raise Refused("the record names another object")
        if record.get("share_license_status") != "CC0":
            raise Refused("share_license_status is not CC0")
        images = record.get("images")
        images = images if isinstance(images, dict) else {}
        image_url = None
        for size in ("print", "web"):
            candidate = images.get(size)
            if isinstance(candidate, dict) and isinstance(candidate.get("url"), str):
                image_url = candidate["url"]
                break
        if not image_url:
            raise Refused("no image")
        image = _image(self._fetch, image_url, self.IMAGE_HOSTS, {})
        creators = record.get("creators")
        creator = (
            _text(creators[0].get("description"))
            if isinstance(creators, list) and creators and isinstance(creators[0], dict)
            else None
        )
        return ProviderWork(
            provider=self.name,
            object_id=object_id,
            image=image,
            placard={
                "title": _text(record.get("title")),
                "creator": creator,
                "date": _text(record.get("creation_date")),
                "medium": _text(record.get("technique")),
                "dimensions": _text(record.get("measurements")),
                "institution": "The Cleveland Museum of Art",
                "canonical_url": _text(record.get("url"))
                or f"https://www.clevelandart.org/art/{object_id}",
            },
            rights=_rights("share_license_status", "CC0", image_url),
        )


class NationalGallery:
    """The National Gallery of Art's open data: `openaccess` on its primary published image.

    The NGA publishes its collection as CSV files rather than an API. Point `NGA_OPENDATA` at a
    checkout of https://github.com/NationalGalleryOfArt/opendata; images come from its IIIF
    service, at most 2400 px on the long side.
    """

    name = "nga"
    IMAGE_HOSTS = frozenset({"api.nga.gov"})
    IMAGE_SIZE = "!2400,2400"

    def __init__(self, opendata: Path | None = None, fetch: Fetcher = fetch_https) -> None:
        self._opendata = opendata
        self._fetch = fetch
        self._objects: dict[str, dict[str, str]] | None = None
        self._images: dict[str, dict[str, str]] | None = None

    def _tables(self) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
        if self._objects is None or self._images is None:
            root = self._opendata or Path(os.environ.get("NGA_OPENDATA", ""))
            tables = root / "data"
            if not all(
                (tables / name).is_file() for name in ("objects.csv", "published_images.csv")
            ):
                raise Refused("NGA_OPENDATA does not point at the NGA open data")
            with (tables / "objects.csv").open(encoding="utf-8", newline="") as handle:
                self._objects = {row["objectid"]: row for row in csv.DictReader(handle)}
            with (tables / "published_images.csv").open(encoding="utf-8", newline="") as handle:
                self._images = {
                    row["depictstmsobjectid"]: row
                    for row in csv.DictReader(handle)
                    if row.get("viewtype") == "primary"
                }
        return self._objects, self._images

    def fetch(self, object_id: str) -> ProviderWork:
        objects, images = self._tables()
        record = objects.get(object_id)
        published = images.get(object_id)
        if record is None:
            raise Refused("no such object")
        if published is None or published.get("openaccess") != "1":
            raise Refused("openaccess is not 1")
        base = (published.get("iiifurl") or "").rstrip("/")
        if not base:
            raise Refused("no image")
        image_url = f"{base}/full/{self.IMAGE_SIZE}/0/default.jpg"
        image = _image(self._fetch, image_url, self.IMAGE_HOSTS, {})
        return ProviderWork(
            provider=self.name,
            object_id=object_id,
            image=image,
            placard={
                "title": _text(record.get("title")),
                "creator": _text(record.get("attribution")),
                "date": _text(record.get("displaydate")),
                "medium": _text(record.get("medium")),
                "dimensions": _text(record.get("dimensions")),
                "institution": "National Gallery of Art, Washington",
                "canonical_url": f"https://www.nga.gov/collection/art-object-page.{object_id}.html",
            },
            rights=_rights("openaccess", "1", image_url, uuid=published.get("uuid")),
        )


def providers(fetch: Fetcher = fetch_https) -> Mapping[str, Provider]:
    return {
        Met.name: Met(fetch),
        ArtInstitute.name: ArtInstitute(fetch),
        Cleveland.name: Cleveland(fetch),
        NationalGallery.name: NationalGallery(fetch=fetch),
    }


PROVIDERS: Mapping[str, Provider] = providers()
