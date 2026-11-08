"""Content records (announcements / news) for P2."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AnnouncementRecord:
    announcement_id: str
    sec_code: str | None
    sec_name: str | None
    title: str
    published_at: str | None
    url: str | None
    file_url: str | None
    file_type: str | None
    file_size_kb: int | None
    category: str | None
    source_id: str = "cninfo_announcement"
    raw: dict | None = None


@dataclass(frozen=True)
class NewsRecord:
    source_id: str
    title: str
    url: str
    summary: str | None
    published_at: str | None
    license_status: str
    raw: str | None = None
