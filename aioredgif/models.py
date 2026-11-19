"""Pydantic models shared by the API, the downloader and the storage layers."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from aioredgif.tagfilter import TagFilter, split_tags

Order = Literal["new", "top", "trending", "best", "latest", "oldest", "hot"]
Quality = Literal["hd", "sd"]


class GifUrls(BaseModel):
    """Media addresses RedGIFs returns for one post."""

    hd: str | None = None
    sd: str | None = None
    poster: str | None = None
    thumbnail: str | None = None
    vthumbnail: str | None = None


class Gif(BaseModel):
    """One RedGIFs post (a clip or an image), normalised from the API.

    Attributes:
        id: Lowercase post id, e.g. ``"mysteriousspottedzethusspinipes"``.
        user_name: Creator handle (not the display name).
        tags: Tags as RedGIFs lists them.
        urls: Media addresses.
        is_image: True for image posts.
        niches: Niche slugs the post belongs to.
        sources: Where a job found this post, e.g. ``"niche:lost-bet-captions"``.
        raw: The full upstream object, kept for the JSON dump and not sent in
            API responses.
    """

    id: str
    user_name: str | None = None
    tags: list[str] = []
    urls: GifUrls
    duration: float | None = None
    width: int | None = None
    height: int | None = None
    has_audio: bool | None = None
    views: int | None = None
    likes: int | None = None
    created: datetime | None = None
    is_image: bool = False
    niches: list[str] = []
    description: str | None = None
    verified: bool | None = None
    sources: list[str] = []
    raw: dict = Field(default_factory=dict, exclude=True)

    @classmethod
    def from_api(cls, data: dict) -> Gif:
        """Build a Gif from one entry of a RedGIFs API response.

        Args:
            data: A ``gif`` object as returned by ``/v2/gifs/...``.

        Returns:
            The normalised post.
        """
        created = data.get("createDate")
        urls = {key: value for key, value in (data.get("urls") or {}).items() if key in GifUrls.model_fields}
        return cls(
            id=data["id"],
            user_name=data.get("userName"),
            tags=data.get("tags") or [],
            urls=GifUrls(**urls),
            duration=data.get("duration"),
            width=data.get("width"),
            height=data.get("height"),
            has_audio=data.get("hasAudio"),
            views=data.get("views"),
            likes=data.get("likes"),
            created=datetime.fromtimestamp(created) if isinstance(created, (int, float)) else None,
            is_image=data.get("type") == 2,
            niches=data.get("niches") or [],
            description=data.get("description") or None,
            verified=data.get("verified"),
            raw=data,
        )


class Page(BaseModel):
    """One page of a creator, niche or search feed."""

    items: list[Gif]
    page: int
    pages: int
    total: int
    users: list[dict] = Field(default_factory=list, description="Creator profiles RedGIFs sent along")


class JobRequest(BaseModel):
    """What to pull. At least one source is required; they can be mixed.

    Attributes:
        users: Creator handles (a leading ``@`` is ignored).
        tags: Tags to search for together (a leading ``#`` is ignored).
        niches: Niche slugs, e.g. ``"lost-bet-captions"``.
        ids: Specific post ids.
        urls: Any RedGIFs links: creator, niche, tag or watch pages.
        limit_per_source: Most posts taken from each source.
        order: Sort order asked of RedGIFs (it falls back if refused).
        quality: ``"hd"`` or ``"sd"``.
        include_images: Also download image posts.
        include_tags: Keep only posts with these tags (see ``tag_match``).
        exclude_tags: Skip posts with any of these tags. Exclusion wins.
        tag_match: ``"any"`` keeps posts with at least one included tag,
            ``"all"`` only posts with every included tag.
    """

    users: list[str] = Field(default_factory=list, description="Creator usernames")
    tags: list[str] = Field(default_factory=list, description="Tags, searched together")
    niches: list[str] = Field(default_factory=list, description="Niche slugs, e.g. lost-bet-captions")
    ids: list[str] = Field(default_factory=list, description="Specific post ids")
    urls: list[str] = Field(default_factory=list, description="Any RedGIFs links (creator, niche, tag, watch)")
    limit_per_source: int = Field(50, ge=1, le=1000)
    order: Order = "new"
    quality: Quality = "hd"
    include_images: bool = True
    include_tags: list[str] = Field(default_factory=list, description="Keep only posts with these tags")
    exclude_tags: list[str] = Field(default_factory=list, description="Skip posts with any of these tags")
    tag_match: Literal["any", "all"] = "any"

    @field_validator("include_tags", "exclude_tags", mode="before")
    @classmethod
    def _accept_comma_text(cls, value: object) -> object:
        """Allow ``"blonde, solo"`` as well as ``["blonde", "solo"]``."""
        return split_tags(value) if isinstance(value, str) else value

    @property
    def tag_filter(self) -> TagFilter:
        """The include/exclude rule this request asks for."""
        return TagFilter(self.include_tags, self.exclude_tags, self.tag_match)

    @model_validator(mode="after")
    def _normalise(self) -> JobRequest:
        if not (self.users or self.tags or self.niches or self.ids or self.urls):
            raise ValueError("Provide at least one of users, tags, niches, ids or urls")
        self.users = [user.strip().lstrip("@").lower() for user in self.users if user.strip()]
        self.tags = [tag.strip().lstrip("#") for tag in self.tags if tag.strip()]
        self.niches = [niche.strip().strip("/").lower() for niche in self.niches if niche.strip()]
        self.include_tags = split_tags(self.include_tags)
        self.exclude_tags = split_tags(self.exclude_tags)
        return self


class JobState(StrEnum):
    """Life cycle of a pull."""

    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"
    paused = "paused"  # stopped on request; resumes only when asked
    interrupted = "interrupted"  # the server stopped mid-pull; resumes on the next start


class FileResult(BaseModel):
    """Outcome for one post in a job."""

    id: str
    path: str | None = None
    bytes: int | None = None
    skipped: bool = False  # already in the library, nothing downloaded
    error: str | None = None


class JobItem(BaseModel):
    """A post a job found, with what the page needs to show it.

    ``width`` and ``height`` (when RedGIFs reports them) let the goon cave lay
    screens out by each clip's shape before the clip has loaded.
    """

    id: str
    user_name: str | None = None
    thumbnail: str | None = None
    tags: list[str] = []
    niches: list[str] = []
    sources: list[str] = []
    width: int | None = None
    height: int | None = None


class JobStatus(BaseModel):
    """A pull: its request, progress, results and history fields.

    Attributes:
        discovered: Posts found across all sources.
        downloaded: Posts now available (downloaded or reused).
        filtered_out: Posts found but skipped by the request's tag filter.
        already_had: Posts reused from the library instead of downloaded again.
        source_key: Stable key for "the same link(s)"; repeat pulls share it.
        label: Short human description of the sources.
        runs: How many times this pull has run.
        reused: True when a submit returned this existing history entry.
        imported: True for pulls rebuilt from an older version's folders.
    """

    id: str
    state: JobState
    request: JobRequest
    discovered: int = 0
    filtered_out: int = 0
    items: list[JobItem] = []
    downloaded: int = 0
    failed: int = 0
    files: list[FileResult] = []
    error: str | None = None
    created: datetime
    finished: datetime | None = None
    source_key: str = ""
    label: str = ""
    runs: int = 1
    last_run: datetime | None = None
    already_had: int = 0
    reused: bool = False
    imported: bool = False


class ResolveRequest(BaseModel):
    """Body of ``POST /v1/resolve``."""

    url: str
    use_browser: bool = False


class ResolveResult(BaseModel):
    """What a RedGIFs link points at."""

    kind: Literal["watch", "creator", "tag", "niche", "unknown"]
    ids: list[str] = []
    user_name: str | None = None
    tag: str | None = None
    niche: str | None = None
    media_urls: list[str] = []
    method: Literal["parse", "browser"] = "parse"
