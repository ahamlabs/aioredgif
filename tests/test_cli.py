"""The command line, run in-process against the fake RedGIFs."""

import json

import httpx
import pytest

from aioredgif import cli, services
from aioredgif.config import Settings
from tests.conftest import make_handler


@pytest.fixture
def run(tmp_path, monkeypatch, capsys):
    """Run ``aioredgif <args>`` and return ``(exit_code, stdout, stderr)``."""
    monkeypatch.setattr("aioredgif.client.backoff", lambda attempt: 0)
    monkeypatch.setattr("aioredgif.downloader.backoff", lambda attempt: 0)
    calls = []
    real_open = services.open_services

    def fake_open(settings, transport=None):
        return real_open(settings, transport=httpx.MockTransport(make_handler(calls)))

    monkeypatch.setattr(services, "open_services", fake_open)
    monkeypatch.setattr(
        cli,
        "_settings",
        lambda args: Settings(
            download_dir=tmp_path, upstream_min_interval=0, browser_enabled=False, library_rescan_seconds=0
        ),
    )

    def invoke(*args):
        code = cli.main(list(args))
        out, err = capsys.readouterr()
        return code, out, err

    invoke.dir = tmp_path
    return invoke


def test_version(run):
    code, out, _ = run("version")
    assert code == 0 and out.startswith("aioredgif ")


def test_source_parsing():
    args = cli.build_parser().parse_args(["pull", "@a", "b", "#Blonde", "niche:lost-bet-captions", "--exclude", "solo"])
    request = cli.source_request(args.sources, args)
    assert request.users == ["a", "b"]
    assert request.tags == ["Blonde"]
    assert request.niches == ["lost-bet-captions"]
    assert request.exclude_tags == ["solo"]


def test_info_json_is_clean_and_complete(run):
    code, out, err = run("info", "https://www.redgifs.com/users/paul57ak57", "--json")
    assert code == 0
    report = json.loads(out)  # nothing but JSON on stdout
    assert report["schema"] == "aioredgif.creator/1"
    assert report["creator"]["username"] == "paul57ak57"
    assert report["creator"]["profile_image"]
    assert report["summary"]["posts"] == len(report["posts"])
    assert report["summary"]["tags"][0]["tag"]
    assert "____" not in err  # no banner around --json


def test_info_pretty(run):
    code, _, err = run("info", "@paul57ak57", "--no-color")
    assert code == 0
    assert "@paul57ak57" in err and "top tags" in err and "\033[" not in err


def test_info_unknown_creator(run):
    code, _, err = run("info", "@nobody", "--no-color")
    assert code == 1 and "could not read" in err


def test_pull_then_library_export_history(run):
    code, out, err = run("pull", "@paul57ak57", "--limit", "3", "--no-color", "--json", "--zip", str(run.dir / "p.zip"))
    assert code == 0, err
    job = json.loads(out)
    assert job["state"] == "done" and job["downloaded"] == 3
    assert (run.dir / "p.zip").stat().st_size > 0
    assert "DONE" in err

    code, out, _ = run("library", "--json")
    assert json.loads(out)["summary"]["posts"] == 3

    code, out, _ = run("export", "--format", "csv")
    lines = out.strip().splitlines()
    assert lines[0].startswith("id,creator") and len(lines) == 4

    code, out, _ = run("export", "--format", "jsonl", "--exclude", "solo")
    assert all("Solo" not in json.loads(line)["tags"] for line in out.strip().splitlines())

    code, out, _ = run("export", "--creators")
    assert "paul57ak57" in json.loads(out)["creators"]

    code, out, _ = run("history", "--json")
    assert json.loads(out)[0]["id"] == job["id"]

    # The same pull again downloads nothing new.
    code, out, _ = run("pull", "@paul57ak57", "--limit", "3", "--json", "-q")
    assert json.loads(out)["already_had"] == 3
