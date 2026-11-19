"""Creator reports and structured exports."""

import csv
import io
import json

from conftest import wait_for_job

USER = "https://www.redgifs.com/users/paul57ak57"


def test_creator_report(api):
    tc, _, _ = api
    report = tc.get("/v1/users/paul57ak57/report").json()
    assert report["schema"] == "aioredgif.creator/1" and report["source"] == "redgifs"
    creator = report["creator"]
    assert creator["username"] == "paul57ak57" and creator["display_name"] == "JuliaBNWO"
    assert creator["profile_image"].startswith("https://userpic.redgifs.com/")
    assert creator["followers"] == 81 and creator["total_posts"] == 6 and creator["joined"].startswith("2026-02")

    summary = report["summary"]
    assert summary["posts"] == 6 and summary["videos"] == 5 and summary["images"] == 1
    assert summary["tags"][0]["tag"] == "Blonde" and summary["tags"][0]["count"] == 6
    assert summary["tags"][1]["tag"] == "Solo" and summary["tags"][1]["first_used"]
    assert summary["tag_pairs"] == [{"tags": ["Blonde", "Solo"], "count": 2}]
    assert summary["views"]["total"] == sum(100 * n for n in range(3, 9))
    assert summary["most_viewed"][0]["id"] == "gif2c"
    timeline = summary["timeline"]
    assert timeline["first_upload"] < timeline["last_upload"] and timeline["mean_days_between_uploads"] == 3
    assert sum(timeline["by_month"].values()) == 6 and sum(timeline["by_weekday"].values()) == 6
    assert summary["in_library"] == 0

    post = report["posts"][0]
    assert post["page_url"].startswith("https://www.redgifs.com/watch/")
    assert post["download"]["hd"].endswith(".mp4") and post["download"]["cli"].startswith("aioredgif pull ")
    assert post["orientation"] == "portrait" and post["created"]

    summary_only = tc.get("/v1/users/paul57ak57/report", params={"posts": "false", "limit": 2}).json()
    assert "posts" not in summary_only and summary_only["summary"]["posts"] == 2 and summary_only["complete"] is False


def test_report_marks_downloaded_posts(api):
    tc, _, _ = api
    wait_for_job(tc, tc.post("/v1/jobs", json={"urls": [USER], "limit_per_source": 3}).json()["id"])
    report = tc.get("/v1/users/paul57ak57/report").json()
    assert report["summary"]["in_library"] == 3
    assert sum(1 for post in report["posts"] if post["file"]) == 3


def test_unknown_creator_is_404(api):
    tc, _, _ = api
    assert tc.get("/v1/users/nobodyhere/report").status_code in (404, 502)


def test_library_exports(api):
    tc, _, _ = api
    wait_for_job(tc, tc.post("/v1/jobs", json={"urls": [USER]}).json()["id"])

    lines = tc.get("/v1/library/export", params={"format": "jsonl"}).text.strip().splitlines()
    records = [json.loads(line) for line in lines]
    assert len(records) == 6 and all(r["creator"] == "paul57ak57" and r["file"].startswith("library/") for r in records)
    assert "raw" not in records[0] and records[0]["created"] >= records[-1]["created"]  # newest first

    document = tc.get("/v1/library/export", params={"format": "json", "include": "solo"}).json()
    assert document["schema"] == "aioredgif.posts/1" and len(document["posts"]) == 2

    table = list(csv.DictReader(io.StringIO(tc.get("/v1/library/export", params={"format": "csv"}).text)))
    assert len(table) == 6 and table[0]["tags"] in ("Blonde;Solo", "Blonde") and table[0]["hd_url"]

    creators = tc.get("/v1/library/creators").json()["creators"]
    assert creators["paul57ak57"]["summary"]["posts"] == 6 and creators["paul57ak57"]["source"] == "library"
    assert tc.get("/v1/library/export", params={"format": "xml"}).status_code == 422
