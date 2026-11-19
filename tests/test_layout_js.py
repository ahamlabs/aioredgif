"""The cave layout (static/js/layout.js), checked with Node when it is installed."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

LAYOUT = Path(__file__).resolve().parent.parent / "aioredgif" / "static" / "js" / "layout.js"
P, S, W = 9 / 16, 1.0, 16 / 9
CASES = [
    ("laptop, 4 portrait", [P, P, P, P], 1440, 810),
    ("laptop, 9 mixed", [P, P, W, S, P, W, P, S, P], 1440, 810),
    ("tablet, 6 mostly square", [S, S, 0.64, S, S, S], 812, 938),
    ("phone, 6 mixed", [P, W, S, P, W, P], 390, 760),
    ("phone sideways, 4 portrait", [P, P, P, P], 844, 300),
    ("one landscape clip", [W], 1366, 665),
]

SCRIPT = """
const L = require(process.argv[1]);
const cases = JSON.parse(process.argv[2]);
console.log(JSON.stringify(cases.map(([name, aspects, w, h]) => {
  const fit = L.fit(aspects, w, h, 4), grid = L.grid(aspects.length, w, h, 4);
  const crops = (boxes) => boxes.map((b, i) => L.cropShare(b.w / b.h, aspects[i]));
  return { name, w, h, boxes: fit.boxes, fitCrops: crops(fit.boxes), gridCrops: crops(grid.boxes) };
})));
"""


@pytest.fixture(scope="module")
def results():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed")
    out = subprocess.run(
        [node, "-e", SCRIPT, str(LAYOUT), json.dumps(CASES)], capture_output=True, text=True, check=True
    )
    return json.loads(out.stdout)


def test_fills_the_screen_without_overlaps(results):
    for case in results:
        boxes, w, h = case["boxes"], case["w"], case["h"]
        assert max(b["x"] + b["w"] for b in boxes) == pytest.approx(w, abs=1), case["name"]
        assert max(b["y"] + b["h"] for b in boxes) == pytest.approx(h, abs=1), case["name"]
        assert min(b["x"] for b in boxes) >= -0.5 and min(b["y"] for b in boxes) >= -0.5
        for i, a in enumerate(boxes):
            for b in boxes[i + 1 :]:
                overlap_x = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])
                overlap_y = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
                assert overlap_x <= 0.5 or overlap_y <= 0.5, case["name"]


def test_crops_less_than_the_equal_grid(results):
    for case in results:
        assert sum(case["fitCrops"]) <= sum(case["gridCrops"]) + 1e-6, case["name"]
        if len(case["boxes"]) > 1:
            assert max(case["fitCrops"]) < 0.31, case["name"]


def test_one_clip_takes_the_whole_screen(results):
    single = next(case for case in results if case["name"] == "one landscape clip")
    assert single["boxes"][0]["w"] == pytest.approx(1366) and single["boxes"][0]["h"] == pytest.approx(665)


def test_tighter_shapes_when_clips_are_shown_whole():
    """A lower evenness weight ("Show whole") leaves less spare space around the clips."""
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed")
    script = """
const L = require(process.argv[1]);
const a = [1, 1, 1, 1, 1, 1];
const spare = (u) => Math.max(...L.fit(a, 1358, 615, 4, u).boxes.map((b, i) => L.cropShare(b.w / b.h, a[i])));
console.log(JSON.stringify([spare(0.45), spare(0.3)]));
"""
    out = subprocess.run([node, "-e", script, str(LAYOUT)], capture_output=True, text=True, check=True)
    default, whole = json.loads(out.stdout)
    assert whole < default and whole < 0.05
