// aioredgif cave layout: fit N clips of different shapes into a screen, filling it completely.
//
// The screen is cut recursively, side by side or stacked, in any nesting (a "guillotine" layout):
// for example a 2x2 block of square clips next to a column of tall ones. When every cut follows the
// shapes of what is inside it, each clip gets a box of exactly its own shape and the whole
// arrangement has one combined shape. Scaling that to the screen crops every clip by the same small
// amount, so we look for the arrangement whose combined shape is closest to the screen's.
//
// Search: for every subset of the clips (n <= 9, so at most 512), keep a handful of arrangements
// with different combined shapes, built by joining two smaller subsets side by side or stacked.
// Cost = share of each clip cut off + how uneven the screen sizes are (so no screen ends up tiny).
//
// Works in the browser (window.AioLayout) and in Node (module.exports) for tests.
(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.AioLayout = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const CROP_WEIGHT = 1.0;
  const UNEVEN_WEIGHT = 0.45;
  const BUCKET = 0.14;     // arrangements whose shapes differ by less than ~14% compete; the most even one stays
  const KEEP = 16;         // most arrangements kept per subset of clips
  const STEP = 0.05;       // shapes are rounded to ~5% steps so similar sets of clips share cached results
  const cache = new Map(); // clip shapes -> arrangements; the screen size only matters for the final pick

  // Share of the media hidden when an item of aspect `media` fills a box of aspect `box`.
  function cropShare(box, media) {
    const r = box / media;
    return 1 - Math.min(r, 1 / r);
  }

  // How unequal the screen sizes are: coefficient of variation of their area shares.
  // Shares always add up to 1, so only their sum of squares (`sq`) and count are needed.
  function unevenness(sq, count) {
    const mean = 1 / count;
    return Math.sqrt(Math.max(0, sq / count - mean * mean)) / mean;
  }

  // Join two arrangements side by side ("H", same height) or stacked ("V", same width).
  function join(x, y, dir) {
    let aspect, wx;
    if (dir === "H") { aspect = x.aspect + y.aspect; wx = x.aspect / aspect; }
    else { aspect = 1 / (1 / x.aspect + 1 / y.aspect); wx = (1 / x.aspect) / (1 / x.aspect + 1 / y.aspect); }
    // x gets share wx of the area, y the rest; each clip's share scales with its part.
    const sq = wx * wx * x.sq + (1 - wx) * (1 - wx) * y.sq;
    const count = x.count + y.count;
    return { aspect, sq, count, x, y, dir, spread: unevenness(sq, count) };
  }

  // Keep a spread of shapes: per ~12% band of aspect, the most even arrangement; at most KEEP bands.
  function prune(list) {
    const bands = new Map();
    for (const c of list) {
      const key = Math.round(Math.log(c.aspect) / BUCKET);
      const cur = bands.get(key);
      if (!cur || c.spread < cur.spread) bands.set(key, c);
    }
    return [...bands.values()].sort((p, q) => p.spread - q.spread).slice(0, KEEP);
  }

  // `aspects` must be sorted and rounded (see fit): then any set of clips with the same shapes,
  // in any order, shares one cached search.
  function search(aspects) {
    const key = aspects.map((a) => a.toFixed(4)).join(",");
    if (cache.has(key)) return cache.get(key);
    const n = aspects.length;
    const best = new Array(1 << n);
    for (let i = 0; i < n; i++) best[1 << i] = [{ aspect: aspects[i], sq: 1, count: 1, leaf: i, spread: 0 }];
    const subsets = [];
    for (let s = 1; s < 1 << n; s++) if (s & (s - 1)) subsets.push(s);
    subsets.sort((p, q) => popcount(p) - popcount(q));
    for (const s of subsets) {
      const found = [];
      for (let t = (s - 1) & s; t > 0; t = (t - 1) & s) {
        const u = s ^ t;
        if (t < u) continue; // each pair once
        for (const x of best[t]) for (const y of best[u]) { found.push(join(x, y, "H")); found.push(join(x, y, "V")); }
      }
      best[s] = prune(found);
    }
    const result = best[(1 << n) - 1];
    if (cache.size > 200) cache.clear();
    cache.set(key, result);
    return result;
  }

  function popcount(v) { let c = 0; while (v) { v &= v - 1; c++; } return c; }

  // Turn an arrangement into boxes inside (x, y, w, h).
  function place(node, x, y, w, h, gap, boxes) {
    if (node.leaf !== undefined) { boxes[node.leaf] = { x, y, w, h }; return; }
    const a = node.x.aspect, b = node.y.aspect;
    if (node.dir === "H") {
      const free = Math.max(0, w - gap), wa = (free * a) / (a + b);
      place(node.x, x, y, wa, h, gap, boxes);
      place(node.y, x + wa + gap, y, free - wa, h, gap, boxes);
    } else {
      const free = Math.max(0, h - gap), ia = 1 / a, ib = 1 / b, ha = (free * ia) / (ia + ib);
      place(node.x, x, y, w, ha, gap, boxes);
      place(node.y, x, y + ha + gap, w, free - ha, gap, boxes);
    }
  }

  /**
   * Fit items into a width x height area.
   * @param {number[]} aspects  width / height of each item (unknown: pass the expected shape).
   * @param {number} width      area width in px.
   * @param {number} height     area height in px.
   * @param {number} [gap=4]    space between boxes in px.
   * @param {number} [uneven]   how much to favour equal screen sizes over screens shaped exactly like
   *                            their clips (default 0.45; lower fills the screen more tightly).
   * @returns {{boxes: {x:number,y:number,w:number,h:number}[], mode: "fit", cost: number}}
   *          boxes[i] belongs to aspects[i]; together they tile the whole area.
   */
  function fit(aspects, width, height, gap = 4, uneven = UNEVEN_WEIGHT) {
    const n = aspects.length;
    if (!n || width <= 0 || height <= 0) return { boxes: [], mode: "fit", cost: 0 };
    const screen = width / height;
    const rounded = aspects.map((a) => Math.exp(Math.round(Math.log(a > 0 && isFinite(a) ? a : 9 / 16) / STEP) * STEP));
    const order = rounded.map((_, i) => i).sort((i, j) => rounded[i] - rounded[j]);
    let pick = null, pickCost = Infinity;
    for (const c of search(order.map((i) => rounded[i]))) {
      const cost = CROP_WEIGHT * cropShare(screen, c.aspect) + uneven * c.spread;
      if (cost < pickCost) { pick = c; pickCost = cost; }
    }
    const sorted = new Array(n);
    place(pick, 0, 0, width, height, gap, sorted);
    const boxes = new Array(n);
    order.forEach((original, k) => { boxes[original] = sorted[k]; });
    return { boxes, mode: "fit", cost: pickCost };
  }

  /** Equal grid, the classic layout: boxes in reading order. */
  function grid(n, width, height, gap = 4) {
    const cols = n === 1 ? 1 : n <= 4 ? 2 : 3;
    const rows = Math.ceil(n / cols);
    const w = (width - gap * (cols - 1)) / cols;
    const h = (height - gap * (rows - 1)) / rows;
    return {
      boxes: Array.from({ length: n }, (_, i) => ({ x: (i % cols) * (w + gap), y: Math.floor(i / cols) * (h + gap), w, h })),
      mode: "grid",
      cost: 0,
    };
  }

  return { fit, grid, cropShare };
});
