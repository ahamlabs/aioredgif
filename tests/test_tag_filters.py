"""Include / exclude tag filters: the rule itself, pulls, and the library."""

import pytest
from conftest import wait_for_job

from aioredgif.tagfilter import TagFilter, split_tags

NICHE = "https://www.redgifs.com/niches/lost-bet-captions"
# The fake niche has four posts tagged:
#   nicheaclip [Captions, Blonde]   nichebclip [Captions]
#   nichecclip [Captions, Solo]     nichedclip [Blonde, Solo]


def test_rule():
    assert TagFilter().matches(["anything"])
    assert TagFilter(include=["Blonde", "Solo"]).matches(["solo"])
    assert not TagFilter(include=["Blonde", "Solo"], match="all").matches(["solo"])
    assert TagFilter(include=["#blonde", " SOLO "], match="all").matches(["Blonde", "Solo", "POV"])
    assert not TagFilter(exclude=["pov"]).matches(["Blonde", "POV"])
    assert not TagFilter(include=["blonde"], exclude=["blonde"]).matches(["Blonde"])  # exclusion wins
    assert split_tags(" #Blonde, solo,,blonde ") == ["Blonde", "solo"]
    assert TagFilter(["b", "a"]).key() == TagFilter(["A", "B"]).key()
    assert TagFilter(["Blonde", "Solo"], ["POV"], "all").describe() == "only Blonde and Solo, not POV"
    with pytest.raises(ValueError):
        TagFilter(match="some")


def _ids(status):
    return sorted(item["id"] for item in status["items"])


def test_pull_with_exclude(api):
    tc, calls, _ = api
    status = wait_for_job(tc, tc.post("/v1/jobs", json={"urls": [NICHE], "exclude_tags": ["solo"]}).json()["id"])
    assert _ids(status) == ["nicheaclip", "nichebclip"]
    assert status["filtered_out"] == 2 and status["downloaded"] == 2
    assert not any("N2" in c or "N3" in c for c in calls)  # skipped posts are never downloaded


def test_pull_with_include_any_and_all(api):
    tc, _, _ = api
    any_ = wait_for_job(tc, tc.post("/v1/jobs", json={"urls": [NICHE], "include_tags": "Blonde, Solo"}).json()["id"])
    assert _ids(any_) == ["nicheaclip", "nichecclip", "nichedclip"]
    body = {"urls": [NICHE], "include_tags": ["blonde", "solo"], "tag_match": "all"}
    all_ = wait_for_job(tc, tc.post("/v1/jobs", json=body).json()["id"])
    assert _ids(all_) == ["nichedclip"]
    assert any_["id"] != all_["id"]  # different filters are different history entries
    labels = {item["id"]: item["tag_filter"] for item in tc.get("/v1/history").json()["items"]}
    assert labels[all_["id"]] == "only blonde and solo"


def test_same_link_same_filter_is_one_entry(api):
    tc, _, _ = api
    body = {"urls": [NICHE], "exclude_tags": ["Solo"]}
    first = wait_for_job(tc, tc.post("/v1/jobs", json=body).json()["id"])
    again = tc.post("/v1/jobs", json={"urls": [NICHE], "exclude_tags": ["#solo"]}).json()
    assert again["id"] == first["id"] and again["reused"] is True


def test_library_include_exclude(api):
    tc, _, _ = api
    wait_for_job(tc, tc.post("/v1/jobs", json={"urls": [NICHE]}).json()["id"])

    def ids(**params):
        return sorted(item["id"] for item in tc.get("/v1/library", params=params).json()["items"])

    assert ids(include="blonde,solo") == ["nicheaclip", "nichecclip", "nichedclip"]
    assert ids(include="blonde,solo", match="all") == ["nichedclip"]
    assert ids(exclude="captions") == ["nichedclip"]
    assert ids(include="captions", exclude="blonde,solo") == ["nichebclip"]
    listing = tc.get("/v1/library", params={"exclude": "solo"}).json()
    assert {t["tag"] for t in listing["tags"]} == {"Captions", "Blonde"}  # facets follow the filter
    assert tc.get("/v1/library", params={"match": "most"}).status_code == 422
    archive = tc.get("/v1/library/archive", params={"include": "solo", "match": "all"})
    assert archive.status_code == 200
