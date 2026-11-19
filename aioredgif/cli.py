"""The ``aioredgif`` command line.

Everything works without the web server, straight on the same download folder::

    aioredgif                                   start the web app (same as "aioredgif serve")
    aioredgif pull <link|@user|#tag|niche:slug>  download, with a progress bar; Ctrl+C pauses
    aioredgif resume <pull-id>                  carry on with a paused or interrupted pull
    aioredgif info <@user|link>                 creator profile and analysis (add --json for data)
    aioredgif export --format jsonl             library as JSON, JSON Lines or CSV
    aioredgif library                           what is in the library
    aioredgif history                           every pull

Human-friendly output goes to stderr and data (``--json``, exports) to stdout,
so ``aioredgif info @someone --json > someone.json`` gives clean JSON.
Colours are off when output is not a terminal, or when NO_COLOR is set.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import os
import shutil
import signal
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TextIO

from aioredgif import __version__
from aioredgif.config import Settings
from aioredgif.models import JobRequest, JobState, JobStatus
from aioredgif.tagfilter import TagFilter, split_tags

COMMANDS = ("serve", "pull", "resume", "info", "export", "library", "history", "version")

LOGO = r"""
    ____  ______
   / __ \/ ____/
  / /_/ / / __
 / _, _/ /_/ /
/_/ |_|\____/
  '    '    '
"""
LOGO_SIDE = {2: "aioredgif {version}", 3: "pull. keep. play.", 4: "adults only"}
LOGO_COLOURS = [213, 207, 199, 198, 197, 160]  # pink to red, top to bottom


# --------------------------------------------------------------------------- terminal


class Terminal:
    """Writes human-friendly output to stderr, with colour when it is a terminal.

    Args:
        colour: Force colour on or off; by default it follows the terminal and NO_COLOR.
        ascii_only: Draw bars with ``#`` and ``-`` instead of block characters.
        quiet: Print only errors and final data.
    """

    def __init__(self, colour: bool | None = None, ascii_only: bool = False, quiet: bool = False) -> None:
        self.out: TextIO = sys.stderr
        is_tty = hasattr(self.out, "isatty") and self.out.isatty()
        self.colour = colour if colour is not None else (is_tty and "NO_COLOR" not in os.environ)
        self.live = is_tty
        encoding = (getattr(self.out, "encoding", "") or "").lower()
        self.blocks = not ascii_only and "utf" in encoding
        self.quiet = quiet

    def paint(self, text: str, colour: int | None = None, bold: bool = False, dim: bool = False) -> str:
        """Wrap text in ANSI colour codes (256-colour palette) when colour is on."""
        if not self.colour:
            return text
        codes = []
        if bold:
            codes.append("1")
        if dim:
            codes.append("2")
        if colour is not None:
            codes.append(f"38;5;{colour}")
        return f"\033[{';'.join(codes)}m{text}\033[0m" if codes else text

    def say(self, text: str = "") -> None:
        """Print a line (unless quiet)."""
        if not self.quiet:
            print(text, file=self.out, flush=True)

    def error(self, text: str) -> None:
        """Print an error, always."""
        print(self.paint("error: ", 196, bold=True) + text, file=self.out, flush=True)

    def banner(self) -> None:
        """The RG logo in ASCII, pink to red, with the name and version beside it."""
        if self.quiet:
            return
        lines = LOGO.strip("\n").splitlines()
        width = max(len(line) for line in lines) + 4
        for index, line in enumerate(lines):
            side = LOGO_SIDE.get(index, "").format(version=__version__)
            colour = LOGO_COLOURS[min(index, len(LOGO_COLOURS) - 1)]
            text = self.paint(line.ljust(width), colour, bold=index < 5)
            if side:
                text += self.paint(side, 123 if index == 2 else 245, bold=index == 2)
            self.say(text)
        self.say()

    def bar(self, fraction: float, width: int = 30) -> str:
        """A progress bar like ``[########------]``."""
        fraction = max(0.0, min(1.0, fraction))
        filled = round(fraction * width)
        full, empty = ("█", "░") if self.blocks else ("#", "-")
        return "[" + self.paint(full * filled, 198) + self.paint(empty * (width - filled), 240) + "]"

    def heading(self, text: str) -> None:
        """A section heading."""
        self.say(self.paint(text, 213, bold=True))

    def field(self, label: str, value: object) -> None:
        """A ``label  value`` line, skipped when the value is empty."""
        if value in (None, "", [], {}):
            return
        if isinstance(value, int) and not isinstance(value, bool):
            value = f"{value:,}"
        self.say(f"  {self.paint(label.ljust(18), 245)}{value}")


class Progress:
    """A single self-updating progress line (or periodic lines when not a terminal)."""

    def __init__(self, term: Terminal, label: str) -> None:
        self.term = term
        self.label = label
        self.started = time.monotonic()
        self.last_draw = 0.0
        self.last_plain = -1

    def update(self, done: int, total: int | None, detail: str = "", rate: str = "") -> None:
        """Redraw the line (at most ten times a second)."""
        if self.term.quiet:
            return
        now = time.monotonic()
        if self.term.live and now - self.last_draw < 0.1 and done != total:
            return
        self.last_draw = now
        fraction = done / total if total else 0.0
        elapsed = now - self.started
        eta = ""
        if total and done and done < total:
            eta = f"eta {_clock(elapsed / done * (total - done))}"
        counts = f"{done}/{total}" if total else f"{done}"
        parts = [self.term.paint(self.label, 213, bold=True), self.term.bar(fraction), counts]
        if total:
            parts.append(f"{fraction:4.0%}")
        parts += [p for p in (rate, eta, self.term.paint(detail, 245)) if p]
        line = "  ".join(parts)
        if self.term.live:
            columns = shutil.get_terminal_size((100, 20)).columns
            print("\r\033[2K" + _fit(line, columns), end="", file=self.term.out, flush=True)
        else:
            step = int(fraction * 10)
            if step != self.last_plain:
                self.last_plain = step
                print(line, file=self.term.out, flush=True)

    def finish(self) -> None:
        """End the progress line."""
        if self.term.live and not self.term.quiet:
            print(file=self.term.out, flush=True)


def _fit(line: str, columns: int) -> str:
    """Cut a line to the terminal width, counting only visible characters."""
    visible, out, i = 0, [], 0
    while i < len(line):
        if line[i] == "\033":
            end = line.find("m", i)
            out.append(line[i : end + 1])
            i = end + 1
            continue
        if visible >= columns - 1:
            break
        out.append(line[i])
        visible += 1
        i += 1
    return "".join(out) + ("\033[0m" if "\033" in line else "")


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}" + ("" if number == 1 else "s")


def _clock(seconds: float) -> str:
    seconds = int(seconds)
    hours, rest = divmod(seconds, 3600)
    return f"{hours}:{rest // 60:02d}:{rest % 60:02d}" if hours else f"{rest // 60}:{rest % 60:02d}"


def _size(num: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024 or unit == "GB":
            return f"{num:.0f} {unit}" if unit in ("B", "KB") else f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} TB"


def _print_json(data: object) -> None:
    sys.stdout.write(json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n")


# --------------------------------------------------------------------------- arguments


def source_request(sources: Sequence[str], args: argparse.Namespace) -> JobRequest:
    """Turn command-line sources into a pull request.

    Accepts RedGIFs links, ``@creator``, ``#tag``, ``niche:slug`` and bare creator handles.
    """
    urls, users, tags, niches = [], [], [], []
    for source in sources:
        if "redgifs.com" in source:
            urls.append(source)
        elif source.startswith("#"):
            tags.append(source[1:])
        elif source.startswith("niche:"):
            niches.append(source.split(":", 1)[1])
        else:
            users.append(source.lstrip("@"))
    return JobRequest(
        urls=urls,
        users=users,
        tags=tags,
        niches=niches,
        limit_per_source=args.limit,
        quality=args.quality,
        include_images=not args.no_images,
        include_tags=split_tags(args.include),
        exclude_tags=split_tags(args.exclude),
        tag_match=args.match,
    )


def build_parser() -> argparse.ArgumentParser:
    """The argument parser for every command."""
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--download-dir", type=Path, help="where the library lives (default: AIOREDGIF_DOWNLOAD_DIR)")
    common.add_argument("--no-color", action="store_true", help="plain output")
    common.add_argument("--ascii", action="store_true", help="draw bars with # and - only")
    common.add_argument("-q", "--quiet", action="store_true", help="no banner or progress")
    common.add_argument("-v", "--verbose", action="store_true", help="log every request to RedGIFs")

    tags = argparse.ArgumentParser(add_help=False)
    tags.add_argument("--include", default="", help="keep only items with these tags (comma separated)")
    tags.add_argument("--exclude", default="", help="skip items with any of these tags")
    tags.add_argument(
        "--match", choices=("any", "all"), default="any", help="keep items with any or all --include tags"
    )

    parser = argparse.ArgumentParser(
        prog="aioredgif",
        description="Pull, keep, browse and play RedGIFs creators, niches and tags. Adults only.",
        epilog="Run 'aioredgif <command> --help' for a command's options. With no command, the web app starts.",
    )
    parser.add_argument("--version", action="version", version=f"aioredgif {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="command")

    serve = sub.add_parser("serve", parents=[common], help="start the web app and API (the default)")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true", help="restart on code changes (development)")

    pull = sub.add_parser("pull", parents=[common, tags], help="download creators, niches, tags or posts")
    pull.add_argument("sources", nargs="+", help="links, @creator, #tag, niche:slug or creator handles")
    pull.add_argument("--limit", type=int, default=100, help="most posts per source (default 100)")
    pull.add_argument("--quality", choices=("hd", "sd"), default="hd")
    pull.add_argument("--no-images", action="store_true", help="skip image posts")
    pull.add_argument("--zip", type=Path, help="also write everything to this .zip")
    pull.add_argument("--json", action="store_true", help="print the finished pull as JSON on stdout")

    resume = sub.add_parser("resume", parents=[common], help="carry on with a paused or interrupted pull")
    resume.add_argument("pull_id", help="the id shown by 'aioredgif history'")
    resume.add_argument("--zip", type=Path, help="also write everything to this .zip")
    resume.add_argument("--json", action="store_true")

    info = sub.add_parser("info", parents=[common], help="a creator's profile, posts and analysis")
    info.add_argument("creator", help="@handle, handle, or profile link")
    info.add_argument("--limit", type=int, default=1000, help="most posts to read (default 1000)")
    info.add_argument("--json", action="store_true", help="print the full report as JSON on stdout")
    info.add_argument("--out", type=Path, help="write the full report to this JSON file")
    info.add_argument("--no-posts", action="store_true", help="leave the per-post list out of the JSON")

    export = sub.add_parser("export", parents=[common, tags], help="library data as JSON, JSON Lines or CSV")
    export.add_argument("--format", choices=("json", "jsonl", "csv"), default="jsonl")
    export.add_argument("--creator", default="", help="only this creator")
    export.add_argument("--kind", choices=("all", "video", "image"), default="all")
    export.add_argument("--creators", action="store_true", help="one report per creator instead of posts")
    export.add_argument("--out", type=Path, help="write to this file instead of stdout")

    library = sub.add_parser("library", parents=[common, tags], help="what is in the library")
    library.add_argument("--creator", default="")
    library.add_argument("--json", action="store_true")

    history = sub.add_parser("history", parents=[common], help="every pull")
    history.add_argument("--json", action="store_true")

    sub.add_parser("version", help="print the version")
    return parser


def _settings(args: argparse.Namespace) -> Settings:
    overrides = {"browser_enabled": False}
    if getattr(args, "download_dir", None):
        overrides["download_dir"] = args.download_dir
    return Settings(**overrides)


# --------------------------------------------------------------------------- commands


async def _watch(services: object, job: JobStatus, term: Terminal) -> JobStatus:
    """Show a pull's progress until it finishes. Ctrl+C pauses it."""
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    # Windows has no loop signal handlers; KeyboardInterrupt is caught in main() there.
    with contextlib.suppress(NotImplementedError, RuntimeError):
        loop.add_signal_handler(signal.SIGINT, stop.set)
    progress = Progress(term, "pulling")
    started = time.monotonic()
    try:
        while job.state in (JobState.queued, JobState.running):
            if stop.is_set():
                progress.finish()
                term.say(term.paint("Pausing... finished clips are kept.", 213))
                services.jobs.pause(job)
                while job.id in services.jobs._tasks:  # noqa: SLF001 - wait for the task to settle
                    await asyncio.sleep(0.05)
                break
            saved = sum(result.bytes or 0 for result in job.files if not result.skipped)
            elapsed = max(0.001, time.monotonic() - started)
            rate = f"{_size(saved / elapsed)}/s" if saved else ""
            last = job.files[-1].id if job.files else ("finding posts" if not job.discovered else "")
            progress.update(job.downloaded + job.failed, job.discovered or None, last, rate)
            await asyncio.sleep(0.1)
    finally:
        with contextlib.suppress(NotImplementedError, RuntimeError):
            loop.remove_signal_handler(signal.SIGINT)
    if job.state != JobState.paused:
        progress.update(job.downloaded + job.failed, job.discovered or job.downloaded + job.failed, "", "")
        progress.finish()
    return job


def _report_pull(job: JobStatus, term: Terminal, services: object, zip_path: Path | None) -> None:
    from aioredgif.archive import with_sidecars, write_zip
    from aioredgif.metadata import live_stats

    state_colour = {"done": 120, "paused": 123, "failed": 196, "interrupted": 214}.get(job.state.value, 245)
    term.say()
    term.say(f"  {term.paint(job.state.value.upper(), state_colour, bold=True)}  pull {term.paint(job.id, 213)}")
    term.field("stashed", f"{job.downloaded} of {job.discovered}")
    term.field("already had", job.already_had or None)
    term.field("skipped by tags", job.filtered_out or None)
    term.field("missed", job.failed or None)
    new_bytes = sum(result.bytes or 0 for result in job.files if not result.skipped and result.path)
    term.field("downloaded", _size(new_bytes) if new_bytes else None)
    term.field("library", str(services.library.dir.resolve()))
    tags = live_stats(job)["tags"][:8]
    if tags:
        term.field("top tags", ", ".join(f"{tag['tag']} ({tag['count']})" for tag in tags))
    if job.error:
        term.field("error", job.error)
    if job.state == JobState.paused:
        term.say(f"\n  Resume with: {term.paint(f'aioredgif resume {job.id}', 123)}")
    if zip_path:
        paths = [Path(r.path) for r in job.files if r.path and Path(r.path).exists()]
        if paths:
            job_dir = services.jobs.root / job.id
            extras = [(p, p.name) for p in (job_dir / "metadata.json", job_dir / "tags.json") if p.exists()]
            write_zip(with_sidecars(paths) + extras, zip_path)
            term.field("zip", f"{zip_path} ({_size(zip_path.stat().st_size)})")


async def cmd_pull(args: argparse.Namespace, term: Terminal) -> int:
    """``aioredgif pull``."""
    from aioredgif.services import open_services

    try:
        request = source_request(args.sources, args)
    except ValueError as exc:
        term.error(str(exc))
        return 2
    async with open_services(_settings(args)) as services:
        job = services.jobs.submit(request)
        if job.reused:
            term.say(term.paint("Pulled before: clips already in the library are reused, only new ones download.", 245))
        term.say(f"  {term.paint('pull', 245)} {term.paint(job.id, 213)}  {job.label}")
        job = await _watch(services, job, term)
        _report_pull(job, term, services, args.zip)
        if args.json:
            _print_json(json.loads(job.model_dump_json()))
    return 0 if job.state in (JobState.done, JobState.paused) else 1


async def cmd_resume(args: argparse.Namespace, term: Terminal) -> int:
    """``aioredgif resume``."""
    from aioredgif.services import open_services

    async with open_services(_settings(args)) as services:
        job = services.jobs.jobs.get(args.pull_id)
        if not job:
            term.error(f"no pull {args.pull_id!r}; see 'aioredgif history'")
            return 2
        services.jobs.rerun(job)
        term.say(f"  {term.paint('resuming', 245)} {term.paint(job.id, 213)}  {job.label}")
        job = await _watch(services, job, term)
        _report_pull(job, term, services, args.zip)
        if args.json:
            _print_json(json.loads(job.model_dump_json()))
    return 0 if job.state in (JobState.done, JobState.paused) else 1


def _handle_from(text: str) -> str:
    from aioredgif.parsing import classify_url

    if "redgifs.com" in text:
        kind, value = classify_url(text)
        if kind == "creator" and value:
            return value
    return text.strip().lstrip("@")


async def cmd_info(args: argparse.Namespace, term: Terminal) -> int:
    """``aioredgif info``: creator profile, posts and analysis."""
    from aioredgif.client import RedGifsError
    from aioredgif.creators import creator_report
    from aioredgif.services import open_services

    handle = _handle_from(args.creator)
    progress = Progress(term, "reading")
    async with open_services(_settings(args)) as services:
        try:
            report = await creator_report(
                services.client,
                handle,
                args.limit,
                services.library,
                on_progress=lambda done, total: progress.update(
                    done, min(total, args.limit) if total else None, f"@{handle}"
                ),
            )
        except RedGifsError as exc:
            progress.finish()
            term.error(f"could not read @{handle}: {exc}")
            return 1
    progress.finish()
    if args.no_posts:
        report.pop("posts", None)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    if args.json:
        _print_json(report)
    if not args.json or args.out:
        show_report(report, term)
        if args.out:
            term.say(f"\n  Full report written to {term.paint(str(args.out), 123)}")
    return 0


def show_report(report: dict, term: Terminal) -> None:
    """Print a creator report for people: profile, numbers, tags and timeline."""
    creator, summary = report["creator"], report["summary"]
    term.say()
    name = f"@{creator['username']}" + (f"  ({creator['display_name']})" if creator.get("display_name") else "")
    term.say(
        "  "
        + term.paint(name, 213, bold=True)
        + ("  " + term.paint("verified", 120) if creator.get("verified") else "")
    )
    term.field("profile", creator.get("profile_url"))
    term.field("profile image", creator.get("profile_image"))
    term.field("about", (creator.get("description") or "")[:100] or None)
    term.field("followers", creator.get("followers"))
    term.field("total views", creator.get("views"))
    term.field("posts on profile", creator.get("total_posts"))
    term.field("joined", (creator.get("joined") or "")[:10] or None)
    term.say()
    term.heading("  posts read")
    term.field(
        "total", f"{summary['posts']}  ({_count(summary['videos'], 'clip')}, {_count(summary['images'], 'image')})"
    )
    if summary.get("duration_s"):
        duration = summary["duration_s"]
        term.field("footage", f"{_clock(duration['total'])} total, {duration['mean']:.1f}s average clip")
    if summary.get("views"):
        term.field("views", f"{summary['views']['total']:,} total, {summary['views']['median']:,.0f} median per post")
    if summary.get("likes"):
        rate = f", like rate {summary['like_rate']:.2%}" if summary.get("like_rate") else ""
        term.field("likes", f"{summary['likes']['total']:,} total{rate}")
    timeline = summary["timeline"]
    if timeline["first_upload"]:
        span = f"{timeline['first_upload'][:10]} to {timeline['last_upload'][:10]}"
        gap = timeline.get("mean_days_between_uploads")
        term.field("uploads", span + (f", one every {gap:.1f} days on average" if gap else ""))
    shapes = ", ".join(f"{count} {shape}" for shape, count in summary["orientation"].items())
    term.field("shapes", shapes)
    term.field("in your library", f"{summary['in_library']} of {summary['posts']}")
    if summary["tags"]:
        term.say()
        term.heading(f"  top tags  ({summary['unique_tags']} different, {summary['tags_per_post']} per post)")
        top = summary["tags"][:12]
        most = top[0]["count"]
        for entry in top:
            bar = term.bar(entry["count"] / most, 24)
            term.say(f"  {entry['tag'][:18].ljust(18)} {bar} {entry['count']:>4}  {entry['share']:.0%}")
    if timeline["by_month"]:
        term.say()
        term.heading("  uploads by month")
        months = list(timeline["by_month"].items())[-12:]
        most = max(count for _, count in months)
        for month, count in months:
            term.say(f"  {month}  {term.bar(count / most, 24)} {count:>4}")
    if summary["most_viewed"]:
        term.say()
        term.heading("  most viewed")
        for post in summary["most_viewed"][:5]:
            term.say(f"  {post['views']:>10,}  {post['page_url']}")
    term.say()
    term.say(term.paint(f"  Download them all: aioredgif pull @{creator['username']}", 245))
    term.say(term.paint(f"  Every field as JSON: aioredgif info @{creator['username']} --json", 245))


async def cmd_export(args: argparse.Namespace, term: Terminal) -> int:
    """``aioredgif export``: library data as JSON / JSONL / CSV, or per-creator reports."""
    from aioredgif.creators import library_reports
    from aioredgif.exports import library_posts, render
    from aioredgif.library import Library

    settings = _settings(args)
    library = Library(settings.download_dir, settings.library_rescan_seconds)
    tags = TagFilter(split_tags(args.include), split_tags(args.exclude), args.match)
    target = args.out.open("w", encoding="utf-8", newline="") if args.out else sys.stdout
    try:
        if args.creators:
            reports = library_reports(library)
            if args.creator:
                reports = {k: v for k, v in reports.items() if k.lower() == args.creator.lower()}
            target.write(json.dumps({"creators": reports}, ensure_ascii=False, indent=2, default=str) + "\n")
            count = len(reports)
            what = "creators"
        else:
            posts = library_posts(library, args.creator, tags, args.kind)
            for chunk in render(posts, args.format):
                target.write(chunk)
            count = len(posts)
            what = "posts"
    finally:
        if args.out:
            target.close()
    if args.out:
        term.say(f"  {count} {what} written to {term.paint(str(args.out), 123)}")
    return 0


def cmd_library(args: argparse.Namespace, term: Terminal) -> int:
    """``aioredgif library``: a summary of what is stored."""
    from aioredgif.creators import analyse, library_record
    from aioredgif.library import Library

    settings = _settings(args)
    library = Library(settings.download_dir, settings.library_rescan_seconds)
    tags = TagFilter(split_tags(args.include), split_tags(args.exclude), args.match)
    entries = library.search(creator=args.creator, tags=tags)
    posts = [library_record(library, entry) for entry in entries]
    summary = analyse(posts)
    creators: dict[str, int] = {}
    for entry in entries:
        creators[entry["creator"]] = creators.get(entry["creator"], 0) + 1
    if args.json:
        _print_json({"folder": str(library.dir.resolve()), "creators": creators, "summary": summary})
        return 0
    term.field("folder", str(library.dir.resolve()))
    term.field(
        "items", f"{summary['posts']}  ({_count(summary['videos'], 'clip')}, {_count(summary['images'], 'image')})"
    )
    term.field("size", _size(sum(entry["bytes"] for entry in entries)))
    if summary.get("duration_s"):
        term.field("footage", _clock(summary["duration_s"]["total"]))
    if creators:
        term.say()
        term.heading("  creators")
        most = max(creators.values())
        for name, count in sorted(creators.items(), key=lambda pair: -pair[1])[:15]:
            term.say(f"  {name[:22].ljust(22)} {term.bar(count / most, 20)} {count:>5}")
    if summary["tags"]:
        term.say()
        term.heading("  tags")
        most = summary["tags"][0]["count"]
        for entry in summary["tags"][:12]:
            term.say(f"  {entry['tag'][:22].ljust(22)} {term.bar(entry['count'] / most, 20)} {entry['count']:>5}")
    return 0


def cmd_history(args: argparse.Namespace, term: Terminal) -> int:
    """``aioredgif history``: every pull, newest first."""
    from aioredgif.downloader import JobManager
    from aioredgif.library import Library

    settings = _settings(args)
    library = Library(settings.download_dir, settings.library_rescan_seconds)
    manager = JobManager(None, settings, library)  # read-only: nothing is started
    jobs = sorted(manager.jobs.values(), key=lambda job: job.last_run or job.created, reverse=True)
    if args.json:
        _print_json([json.loads(job.model_dump_json(exclude={"files", "items"})) for job in jobs])
        return 0
    if not jobs:
        term.say("  No pulls yet. Try: aioredgif pull @someone")
        return 0
    colours = {"done": 120, "paused": 123, "failed": 196, "interrupted": 214}
    for job in jobs:
        when = (job.last_run or job.created).strftime("%Y-%m-%d %H:%M")
        state = term.paint(job.state.value.ljust(11), colours.get(job.state.value, 245))
        counts = f"{job.downloaded}/{job.discovered}"
        term.say(f"  {term.paint(job.id, 213)}  {state} {counts.rjust(9)}  {when}  {job.label}")
    resumable = [job for job in jobs if job.state in (JobState.paused, JobState.interrupted, JobState.failed)]
    if resumable:
        term.say(term.paint(f"\n  Resume one with: aioredgif resume {resumable[0].id}", 245))
    return 0


def cmd_serve(args: argparse.Namespace, term: Terminal) -> int:
    """``aioredgif serve``: the web app and API."""
    import uvicorn

    if args.download_dir:
        os.environ["AIOREDGIF_DOWNLOAD_DIR"] = str(args.download_dir)
    term.say(f"  Web app: {term.paint(f'http://{args.host}:{args.port}/', 123)}")
    term.say(f"  API docs: {term.paint(f'http://{args.host}:{args.port}/docs', 123)}")
    term.say(term.paint("  Ctrl+C stops the server; running pulls resume on the next start.\n", 245))
    uvicorn.run("aioredgif.app:app", host=args.host, port=args.port, reload=args.reload)
    return 0


HANDLERS: dict[str, Callable] = {
    "pull": cmd_pull,
    "resume": cmd_resume,
    "info": cmd_info,
    "export": cmd_export,
    "library": cmd_library,
    "history": cmd_history,
    "serve": cmd_serve,
}
BANNER_FOR = {"serve", "pull", "resume", "info"}


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line.

    Args:
        argv: Arguments without the program name; defaults to ``sys.argv[1:]``.

    Returns:
        The exit status: 0 on success, 1 when a pull or lookup failed, 2 for bad input.
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or (argv[0].startswith("-") and argv[0] not in ("-h", "--help", "--version")):
        argv.insert(0, "serve")  # "aioredgif" and "aioredgif --port 9000" start the web app
    args = build_parser().parse_args(argv)
    if args.command == "version":
        print(f"aioredgif {__version__}")
        return 0
    if args.command != "serve":
        level = logging.INFO if args.verbose else logging.WARNING
        logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s", force=True)
    term = Terminal(colour=False if args.no_color else None, ascii_only=args.ascii, quiet=args.quiet)
    if args.command in BANNER_FOR and not getattr(args, "json", False):
        term.banner()
    handler = HANDLERS[args.command]
    try:
        result = handler(args, term)
        return asyncio.run(result) if asyncio.iscoroutine(result) else result
    except KeyboardInterrupt:  # only reached where no signal handler could be installed
        term.error("stopped")
        return 130
