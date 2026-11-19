// aioredgif page logic. Plain browser JavaScript, no build step.
// Sections: setup, pulling, results grid, player, faves, session/edge timer, cave,
// views (library, history, rewards).

// Settings used to live under "reel." keys; carry them over once so faves and ranks survive.
try {
  for (let i = 0; i < localStorage.length; i++) {
    const k = localStorage.key(i);
    if (k && k.startsWith("reel.")) {
      const nk = "aioredgif." + k.slice(5);
      if (localStorage.getItem(nk) === null) localStorage.setItem(nk, localStorage.getItem(k));
    }
  }
} catch {}

const $ = (id) => document.getElementById(id);
const f = $("f"), go = $("go"), err = $("err"), sheet = $("sheet");
let timer = null;
const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;

// Glitch burst on load and on hover
for (const id of ["h1a", "h1b"]) {
  const el = $(id);
  const burst = () => { el.classList.remove("go"); void el.offsetWidth; el.classList.add("go"); };
  if (!reduced) { setTimeout(burst, 250); el.addEventListener("mouseenter", burst); }
}

// Ticker
function setTicker(parts) {
  const html = parts.map((p) => `<span>${p}<i>✦</i></span>`).join("");
  $("ticker").innerHTML = html + html; // doubled for a seamless loop
}
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const IDLE = ["Lock in", "Goon cave", "Up to 9 screens", "Edge timer", "Faves that stick", "Creators", "Niches", "Tags", "Edge loop", "Keep going", "Whole stash in one .zip"];
setTicker(IDLE);

// Backdrop + hero art: your brand images first, the current job's thumbnails once a job runs
function setBackdrop(srcs) {
  const bd = $("backdrop");
  bd.innerHTML = "";
  if (!srcs.length) return;
  for (let i = 0; i < 24; i++) {
    const img = new Image(); img.alt = ""; img.src = srcs[i % srcs.length]; img.onerror = () => img.remove();
    bd.append(img);
  }
}
function setCards(srcs) {
  if (!srcs.length) return;
  const art = $("art");
  art.innerHTML = "";
  for (const s of srcs.slice(0, 3)) {
    const c = document.createElement("div"); c.className = "card";
    const img = new Image(); img.alt = ""; img.src = s; c.append(img); art.append(c);
  }
}
fetch("/v1/brand").then((r) => r.json()).then(({ images }) => { setBackdrop(images); setCards(images); }).catch(() => {});

// Preview blur (remembered per browser when storage is available)
const blurp = $("blurp");
try { blurp.checked = localStorage.getItem("aioredgif.blur") === "1"; } catch {}
const applyBlur = () => document.body.classList.toggle("blur", blurp.checked);
blurp.addEventListener("change", () => { applyBlur(); try { localStorage.setItem("aioredgif.blur", blurp.checked ? "1" : "0"); } catch {} });
applyBlur();

const nicheName = (slug) => decodeURIComponent(slug).replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

function who(url) {
  try {
    const p = new URL(url.includes("://") ? url : "https://" + url).pathname.split("/").filter(Boolean);
    if (p[0] === "users" && p[1]) return { kind: "creator", name: decodeURIComponent(p[1]) };
    if (p[0] === "gifs" && p[1]) return { kind: "tag", name: "#" + decodeURIComponent(p[1]) };
    if (p[0] === "niches" && p[1]) return { kind: "niche", name: nicheName(p[1]) };
    if (p[0] === "watch" && p[1]) return { kind: "video", name: p[1] };
  } catch {}
  return null;
}

// Pull-time tag filter (remembered by the browser)
for (const id of ["incTags", "excTags", "tagMatch"]) {
  try { const saved = localStorage.getItem("aioredgif.pull." + id); if (saved !== null) $(id).value = saved; } catch {}
  $(id).addEventListener("input", () => { try { localStorage.setItem("aioredgif.pull." + id, $(id).value); } catch {} summarisePullFilter(); });
}
function summarisePullFilter() {
  const inc = $("incTags").value.trim(), exc = $("excTags").value.trim();
  const parts = [];
  if (inc) parts.push("only " + inc.split(",").map((t) => t.trim()).filter(Boolean).join($("tagMatch").value === "all" ? " and " : " or "));
  if (exc) parts.push("not " + exc.split(",").map((t) => t.trim()).filter(Boolean).join(", "));
  $("pullFilterSummary").textContent = parts.length ? "(" + parts.join(", ") + ")" : "";
  if (parts.length) $("pullFilters").open = true;
}
summarisePullFilter();

let autoZip = new Set();   // job ids whose .zip should download as soon as they finish
f.addEventListener("submit", (e) => { e.preventDefault(); pull(false); });
$("goZip").onclick = () => pull(true);
async function pull(zip) {
  err.textContent = "";
  let url = $("url").value.trim();
  if (url && !url.includes("://")) url = "https://" + url;
  const target = who(url);
  if (!target || !/redgifs\.com/i.test(url)) {
    err.textContent = "That’s not a RedGIFs creator, niche or tag link. Try redgifs.com/users/name or redgifs.com/niches/name.";
    return;
  }
  const previous = currentJob && ["running", "queued"].includes(currentJob.state) ? currentJob : null;
  clearInterval(timer);
  go.disabled = true; $("goZip").disabled = true; go.textContent = "Warming up…";
  try {
    const r = await fetch("/v1/jobs", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({
        urls: [url], limit_per_source: +$("limit").value, quality: f.q.value,
        include_tags: $("incTags").value, exclude_tags: $("excTags").value, tag_match: $("tagMatch").value,
      }),
    });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(detail(body, r));
    if (zip) autoZip.add(body.id);
    if (body.reused) toast("You’ve pulled this link before. Clips already in your library are reused, so only new ones get downloaded.", 6000);
    if (previous && previous.id !== body.id) toast("The other pull keeps going in the background. Pause or open it from History.", 5000);
    go.disabled = false; $("goZip").disabled = false; go.textContent = "Load it all";
    start(body, target);
  } catch (ex) {
    err.textContent = ex.message;
    go.disabled = false; $("goZip").disabled = false; go.textContent = "Load it all";
  }
}

function detail(body, r) {
  if (r.status === 429) return "Easy, you’re going too fast. Wait a minute and try again.";
  const d = body.detail;
  if (Array.isArray(d)) return d.map((x) => x.msg).join(", ");
  return d || `The server answered ${r.status}.`;
}

let jobBackdropSet = false;
function start(job, target) {
  clearInterval(timer);   // only one pull drives the results area at a time
  $("run").hidden = false;
  $("zip").hidden = true; $("meta").hidden = true; $("tagsjson").hidden = true;
  $("tags").hidden = true; pick.clear(); tagsKey = ""; jobBackdropSet = false;
  $("pauseBtn").hidden = true; $("retry").hidden = true;
  sheet.innerHTML = "";
  $("bar").style.width = "0";
  $("title").textContent = `Looking up ${target.name}`;
  $("sub").textContent = "Scouting the page.";
  setTicker([`Pulling <em>${esc(target.name)}</em>`, "Scouting the page", "Lock in"]);
  const tick = async () => {
    try {
      const r = await fetch(`/v1/jobs/${job.id}`);
      if (!r.ok) throw new Error(detail(await r.json().catch(() => ({})), r));
      render(await r.json(), target);
    } catch (ex) { err.textContent = ex.message; }
  };
  tick();
  timer = setInterval(tick, 1200);
  $("run").scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" });
}

const built = new Set();
const stashed = new Map();   // id -> {image}
let currentJob = null;
let tickerKey = "";
function render(job, target) {
  currentJob = job;
  const total = job.discovered, done = job.downloaded, failed = job.failed;
  const files = new Map(job.files.map((x) => [x.id, x]));

  if (job.items.length && sheet.children.length !== job.items.length) {
    sheet.innerHTML = ""; built.clear(); stashed.clear();
    job.items.forEach((it, i) => {
      const el = document.createElement("div");
      el.className = "frame"; el.id = "fr-" + it.id;
      el.innerHTML = `<img alt="" loading="lazy"><span class="no">${i + 1}</span><span class="st"></span>`;
      if (it.thumbnail) {
        const img = el.querySelector("img");
        img.onerror = () => { img.onerror = () => img.remove(); img.src = it.thumbnail; };
        img.src = `/v1/jobs/${job.id}/thumbs/${it.id}`;
      }
      sheet.appendChild(el);
    });
  }
  if (job.items.length && !jobBackdropSet) {
    jobBackdropSet = true;
    setBackdrop(job.items.filter((it) => it.thumbnail).slice(0, 24).map((it) => `/v1/jobs/${job.id}/thumbs/${it.id}`));
  }
  for (const it of job.items) {
    const res = files.get(it.id);
    if (!res || built.has(it.id)) continue;
    built.add(it.id);
    const old = $("fr-" + it.id);
    if (res.error) { old.classList.add("fail"); old.title = "Failed: " + res.error; continue; }
    const a = document.createElement("a");
    a.className = "frame done"; a.id = old.id; a.innerHTML = old.innerHTML;
    a.href = `/v1/jobs/${job.id}/files/${it.id}?inline=true`;
    a.setAttribute("aria-label", `Play clip ${it.id}`);
    a.dataset.id = it.id;
    a.dataset.image = /\.(jpe?g|png|gif|webp)$/i.test(res.path || "") ? "1" : "";
    a.addEventListener("click", (e) => {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return; // let "open in new tab" work
      e.preventDefault(); openPlayer(it.id);
    });
    a.addEventListener("pointerenter", (e) => { if (e.pointerType === "mouse") hoverPreview(a, true); });
    a.addEventListener("pointerleave", () => hoverPreview(a, false));
    a.append(faveButton({ id: it.id, jobId: job.id }));
    old.replaceWith(a);
    stashed.set(it.id, { image: !!a.dataset.image });
  }

  const owner = job.items[0]?.user_name || target.name;
  const pct = total ? Math.round(((done + failed) / total) * 100) : 0;
  $("bar").style.width = pct + "%";

  const live = job.state === "running" || job.state === "queued";
  const pb = $("pauseBtn");
  pb.hidden = !live;
  pb.onclick = async () => {
    pb.disabled = true;
    const r = await fetch(`/v1/jobs/${job.id}/pause`, { method: "POST" });
    pb.disabled = false;
    if (r.ok) toast("Pausing. Everything stashed so far stays in your library; resume any time.", 4500);
  };

  if (job.state === "paused") {
    stop();
    $("title").textContent = "Pull paused";
    $("sub").textContent = `${done} of ${total || "?"} stashed. Resume whenever you like; nothing gets downloaded twice.`;
    const rb = $("retry"); rb.textContent = "Resume"; rb.hidden = false;
    rb.onclick = () => { rb.hidden = true; resumePull(job.id); };
    $("startS").hidden = done === 0;
    setTicker(["Paused", `${done} stashed`, "Resume any time"]);
    return;
  }
  if (job.state === "failed") {
    stop();
    $("title").textContent = "Session interrupted";
    $("sub").textContent = (job.error ? "RedGIFs said: " + job.error.replace(/^\d+:\s*/, "") : "The pull stopped.")
      + (done ? ` ${done} clips made it into your library first.` : "") + " Try again picks up where it stopped.";
    const rb = $("retry"); rb.textContent = "Try again"; rb.hidden = false; rb.onclick = () => { rb.hidden = true; resumePull(job.id); };
    setTicker(["Session interrupted", esc(job.error || "Check the link and try again")]);
    return;
  }
  if (job.state === "done" && total === 0) {
    stop();
    $("title").textContent = "Nothing to stash";
    $("sub").textContent = "This page has no public clips.";
    sheet.innerHTML = `<p class="empty">No clips found for ${esc(target.name)}. Try another creator or niche.</p>`;
    setTicker(IDLE);
    return;
  }
  const n = total || "…";
  $("title").textContent = target.kind === "creator" ? `${n} clips from ${owner}`
    : target.kind === "niche" ? `${n} clips deep in ${target.name}` : `${n} clips tagged ${target.name}`;
  renderTags(job);
  applyFilter();
  $("sub").textContent = total
    ? `${done} stashed${job.already_had ? ` (${job.already_had} already in your library)` : ""}${job.filtered_out ? `, ${job.filtered_out} skipped by your tag filter` : ""}${failed ? `, ${failed} missed` : ""}${job.state === "done" ? ". Tap a clip to start a session." : ` of ${total}. Tap a stashed clip to play it now.`}`
    : "Scouting the page.";

  // Ticker: live progress + top tags
  const top = topTags(job.items, 6);
  const tk = `${done}/${total}/${job.state}/${top.join()}`;
  if (total && tk !== tickerKey) {
    tickerKey = tk;
    setTicker([
      target.kind === "creator" ? `<em>${esc(owner)}</em>` : `<em>${esc(target.name)}</em>`,
      job.state === "done" ? `${done} stashed` : `${done} of ${total} stashed`, "Lock in",
      ...top.map(([t, c]) => `#${esc(t)} ${c}`),
    ]);
  }

  $("startS").hidden = done === 0;
  $("retry").hidden = true;
  const z = $("zip");
  z.hidden = done === 0;
  z.href = `/v1/jobs/${job.id}/archive`;
  z.textContent = job.state === "done" ? `Download .zip (${done})` : `Download .zip (${done} so far)`;
  if (job.state === "done" && autoZip.has(job.id)) {
    autoZip.delete(job.id);
    if (done > 0) { z.click(); toast("All stashed. Your .zip is downloading.", 5000); }
  }
  if (job.state === "done") onPullDone(job);
  if (done > 0 && job.state === "done") {
    $("meta").href = `/v1/jobs/${job.id}/metadata?kind=all`; $("meta").hidden = false;
    $("tagsjson").href = `/v1/jobs/${job.id}/metadata?kind=tags`; $("tagsjson").hidden = false;
  }
  if (job.state === "done") stop();
}

function tagCounts(items) {
  const counts = new Map();
  for (const it of items) for (const t of new Set(it.tags)) counts.set(t, (counts.get(t) || 0) + 1);
  return [...counts].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}
const topTags = (items, k) => tagCounts(items).slice(0, k);

// ---------- Tag filters: tap a chip to keep only that tag, again to hide it, again to clear ----------
class TagPick {
  constructor() { this.inc = new Map(); this.exc = new Map(); this.match = "any"; }   // lowercase -> shown name
  state(tag) { const k = tag.toLowerCase(); return this.inc.has(k) ? "include" : this.exc.has(k) ? "exclude" : "off"; }
  cycle(tag) {
    const k = tag.toLowerCase();
    if (this.inc.has(k)) { this.inc.delete(k); this.exc.set(k, tag); }
    else if (this.exc.has(k)) this.exc.delete(k);
    else this.inc.set(k, tag);
  }
  clear() { this.inc.clear(); this.exc.clear(); }
  get active() { return this.inc.size + this.exc.size > 0; }
  key() { return [...this.inc.keys()].sort() + "/" + [...this.exc.keys()].sort() + "/" + this.match; }
  passes(tags) {
    const have = new Set((tags || []).map((t) => t.toLowerCase()));
    for (const k of this.exc.keys()) if (have.has(k)) return false;
    if (!this.inc.size) return true;
    const hits = [...this.inc.keys()].map((k) => have.has(k));
    return this.match === "all" ? hits.every(Boolean) : hits.some(Boolean);
  }
  describe() {
    const parts = [];
    if (this.inc.size) parts.push("only " + [...this.inc.values()].join(this.match === "all" ? " and " : " or "));
    if (this.exc.size) parts.push("not " + [...this.exc.values()].join(", "));
    return parts.join(", ");
  }
  params() { return { include: [...this.inc.values()].join(","), exclude: [...this.exc.values()].join(","), match: this.match }; }
}
// A chip for one tag. Tags in the filter stay visible even when the filtered set no longer contains them.
function tagChip(tag, count, pick, onChange) {
  const b = document.createElement("button");
  const st = pick.state(tag);
  b.type = "button"; b.className = "chip"; b.dataset.state = st;
  b.setAttribute("aria-label", `${tag}: ${st === "include" ? "keeping only these" : st === "exclude" ? "hidden" : "not filtered"}. Tap to change.`);
  b.title = st === "off" ? "Tap to keep only this tag" : st === "include" ? "Tap to hide this tag instead" : "Tap to clear";
  const mark = document.createElement("i"); mark.className = "mark"; mark.textContent = st === "include" ? "✓" : st === "exclude" ? "✕" : "";
  if (st !== "off") b.append(mark);
  b.append(tag);
  const n = document.createElement("b"); n.textContent = count ?? ""; b.append(n);
  b.onclick = () => { pick.cycle(tag); pending.tag_filter = true; onChange(); };
  return b;
}
// The "any / all" switch and a "clear" link, shown only when they matter.
function tagControls(box, pick, onChange) {
  box.innerHTML = "";
  if (!pick.active) return;
  if (pick.inc.size >= 2) {
    const seg = document.createElement("span"); seg.className = "seg"; seg.setAttribute("role", "radiogroup"); seg.setAttribute("aria-label", "Match");
    for (const [val, label] of [["any", "Any of these"], ["all", "All of these"]]) {
      const l = document.createElement("label");
      const r = document.createElement("input"); r.type = "radio"; r.name = box.id + "-m"; r.value = val; r.checked = pick.match === val;
      r.onchange = () => { pick.match = val; onChange(); };
      const sp = document.createElement("span"); sp.textContent = label;
      l.append(r, sp); seg.append(l);
    }
    box.append("Keep clips with", seg);
  }
  const clear = document.createElement("button"); clear.type = "button"; clear.className = "link"; clear.textContent = "Clear tag filter";
  clear.onclick = () => { pick.clear(); onChange(); };
  box.append(clear);
}
function chipList(counts, pick) {
  // counts: [[tag, n], ...]. Add filter tags that are missing (e.g. hidden ones) so they can be un-hidden.
  const seen = new Set(counts.map(([t]) => t.toLowerCase()));
  const extra = [...pick.inc.values(), ...pick.exc.values()].filter((t) => !seen.has(t.toLowerCase())).map((t) => [t, null]);
  return [...extra, ...counts];
}

// Tag panel: click a tag to filter the sheet
const pick = new TagPick();
let tagsKey = "", showAll = false, lastItems = [];
function renderTags(job) {
  lastItems = job.items;
  if (!job.items.length) return;
  const sorted = tagCounts(job.items);
  const key = job.items.length + ":" + sorted.length + ":" + showAll + ":" + pick.key();
  if (key === tagsKey) return;
  tagsKey = key;
  const rerender = () => { tagsKey = ""; renderTags({ items: lastItems }); applyFilter(); };
  $("tags").hidden = sorted.length === 0;
  const kept = job.items.filter((it) => pick.passes(it.tags)).length;
  $("tagsub").textContent = pick.active
    ? `${kept} of ${job.items.length} clips: ${pick.describe()}. The player and cave stick to these.`
    : `${sorted.length} tags across ${job.items.length} clips. Tap a tag to keep only it, again to hide it, again to clear.`;
  tagControls($("tagCtl"), pick, rerender);
  const list = chipList(showAll ? sorted : sorted.slice(0, 18), pick);
  const chips = $("chips");
  chips.innerHTML = "";
  for (const [t, c] of list) chips.append(tagChip(t, c, pick, rerender));
  if (sorted.length > 18) {
    const m = document.createElement("button");
    m.type = "button"; m.className = "chip more";
    m.textContent = showAll ? "Show fewer" : `Show all ${sorted.length}`;
    m.onclick = () => { showAll = !showAll; tagsKey = ""; renderTags({ items: lastItems }); };
    chips.append(m);
  }
  applyFilter();
}
function applyFilter() {
  for (const it of lastItems) {
    const el = $("fr-" + it.id);
    if (el) el.classList.toggle("out", pick.active && !pick.passes(it.tags));
  }
}


// ---------- Session player ----------
const ICON = {"play": "<svg viewBox=\"0 0 24 24\" fill=\"currentColor\"><path d=\"M7 4.5v15l13-7.5z\"/></svg>", "pause": "<svg viewBox=\"0 0 24 24\" fill=\"currentColor\"><path d=\"M6 4h4.5v16H6zM13.5 4H18v16h-4.5z\"/></svg>", "vol": "<svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M4 9v6h4l5 4V5L8 9z\" fill=\"currentColor\"/><path d=\"M16.5 8.5a5 5 0 0 1 0 7M19 6a8.5 8.5 0 0 1 0 12\"/></svg>", "mute": "<svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\" stroke-linecap=\"round\"><path d=\"M4 9v6h4l5 4V5L8 9z\" fill=\"currentColor\"/><path d=\"M17 9l5 6M22 9l-5 6\"/></svg>"};
const vid = $("vid"), still = $("still"), player = $("player"), stage = $("stage"), seek = $("seek");
const pl = { id: null, opener: null, sessionSec: 0, imgTimer: null, dragging: false };
const store = { get(k, d) { try { const v = localStorage.getItem("aioredgif." + k); return v === null ? d : JSON.parse(v); } catch { return d; } },
                set(k, v) { try { localStorage.setItem("aioredgif." + k, JSON.stringify(v)); } catch {} } };
const fmt = (t) => { t = Math.max(0, Math.floor(t || 0)); const h = Math.floor(t / 3600), m = Math.floor(t / 60) % 60, s = t % 60;
                     return (h ? h + ":" + String(m).padStart(2, "0") : m) + ":" + String(s).padStart(2, "0"); };

// Saved preferences
vid.volume = store.get("vol", 0.8); vid.muted = store.get("muted", false);
vid.loop = store.get("loop", true); vid.playbackRate = 1;
let keepGoing = store.get("auto", false);
$("volr").value = Math.round(vid.volume * 100);
$("plSpeed").value = String(store.get("speed", 1));
const syncPills = () => { $("plLoop").setAttribute("aria-pressed", String(vid.loop)); $("plAuto").setAttribute("aria-pressed", String(keepGoing)); };
const syncVol = () => { $("plMute").innerHTML = vid.muted || vid.volume === 0 ? ICON.mute : ICON.vol;
                        $("volr").value = vid.muted ? 0 : Math.round(vid.volume * 100);
                        $("volr").style.setProperty("--track", `linear-gradient(90deg, var(--pink) ${$("volr").value}%, var(--char-2) 0)`); };
syncPills(); syncVol();

function playable() {
  return lastItems.filter((it) => stashed.has(it.id) && pick.passes(it.tags)).map((it) => it.id);
}
let deck = [], deckSource = "stash";
function stashDeck() {
  if (!currentJob) return [];
  return playable().map((id) => {
    const it = lastItems.find((x) => x.id === id);
    return { id, user_name: it.user_name, tags: it.tags, image: stashed.get(id)?.image, jobId: currentJob.id,
             width: it.width, height: it.height,
             play: `/v1/jobs/${currentJob.id}/files/${id}?inline=true`, dl: `/v1/jobs/${currentJob.id}/files/${id}`,
             thumb: `/v1/jobs/${currentJob.id}/thumbs/${id}` };
  });
}
const refreshDeck = () => { deck = deckSource === "stash" ? stashDeck() : deckSource === "library" ? lib.deck.slice() : faves.slice(); };
function openPlayer(id, source = "stash") {
  deckSource = source; refreshDeck();
  if (!deck.length) return;
  pl.opener = document.activeElement;
  player.hidden = false; document.body.classList.add("locked");
  sessionStart();
  load(id || deck[0].id);
  $("plPlay").focus();
}
function closePlayer() {
  vid.pause(); vid.removeAttribute("src"); vid.load(); clearTimeout(pl.imgTimer);
  if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
  player.hidden = true; if (cave.hidden) document.body.classList.remove("locked");
  const back = pl.id && $("fr-" + pl.id); (back || pl.opener)?.focus?.();
  sessionEnd();
}
function load(id) {
  refreshDeck();
  const idx = deck.findIndex((x) => x.id === id), it = deck[idx];
  if (!it) return;
  pl.id = id; clearTimeout(pl.imgTimer);
  session.clips.add(id); pending.clips.add(id);
  $("plWho").textContent = it.user_name ? "@" + it.user_name : id;
  $("plIdx").textContent = `${idx + 1} of ${deck.length}${deckSource === "faves" ? " faves" : deckSource === "library" && libPick.active ? ", " + libPick.describe() : deckSource === "stash" && pick.active ? ", " + pick.describe() : ""}`;
  $("plDl").href = it.dl;
  $("plFav").setAttribute("aria-pressed", String(faveIds.has(id)));
  $("plFav").hidden = deckSource === "stash" && !it.jobId;
  $("plTags").innerHTML = (it.tags || []).slice(0, 8).map((t) => `<span>#${esc(t)}</span>`).join("");
  still.hidden = !it.image; vid.hidden = !!it.image;
  if (it.image) {
    vid.pause(); still.src = it.play;
    seek.value = 0; $("plTime").textContent = "Image";
    if (keepGoing) pl.imgTimer = setTimeout(next, 6000);
  } else {
    vid.src = it.play;
    vid.playbackRate = +$("plSpeed").value;
    if (!edge.holding) vid.play().catch(() => {});
  }
  // Warm the next clip so skipping feels instant
  const nxt = deck[(idx + 1) % deck.length];
  if (nxt && nxt.id !== id && !nxt.image) fetch(nxt.play, { headers: { Range: "bytes=0-1048575" } }).catch(() => {});
}
let shuffle = store.get("shuffle", false);
function step(d) {
  refreshDeck(); if (!deck.length) return;
  if (shuffle && deck.length > 1) { let n; do { n = deck[Math.floor(Math.random() * deck.length)].id; } while (n === pl.id); return load(n); }
  const i = deck.findIndex((x) => x.id === pl.id);
  load(deck[(i + d + deck.length) % deck.length].id);
}
const next = () => step(1), prev = () => step(-1);
function flash(icon) { $("plFlashIcon").innerHTML = icon; const f = $("plFlash"); f.classList.add("show"); requestAnimationFrame(() => setTimeout(() => f.classList.remove("show"), 60)); }
function toggle() { if (vid.hidden || edge.holding) return; if (vid.paused) { vid.play().catch(() => {}); flash(ICON.play); } else { vid.pause(); flash(ICON.pause); } }

vid.addEventListener("play", () => { $("plPlay").innerHTML = ICON.pause; });
vid.addEventListener("pause", () => { $("plPlay").innerHTML = ICON.play; });
vid.addEventListener("timeupdate", () => {
  const d = vid.duration || 0;
  if (!pl.dragging) seek.value = d ? Math.round((vid.currentTime / d) * 1000) : 0;
  $("plTime").textContent = `${fmt(vid.currentTime)} / ${fmt(d)}`;
  paintSeek();
});
vid.addEventListener("progress", paintSeek);
function paintSeek() {
  const d = vid.duration || 0, played = seek.value / 10;
  let buf = 0; try { if (d && vid.buffered.length) buf = (vid.buffered.end(vid.buffered.length - 1) / d) * 100; } catch {}
  seek.style.setProperty("--track", `linear-gradient(90deg, var(--violet), var(--pink) ${played}%, rgba(255,255,255,.22) ${played}%, rgba(255,255,255,.22) ${Math.max(buf, played)}%, var(--char-2) ${Math.max(buf, played)}%)`);
}
vid.addEventListener("ended", () => { if (!vid.loop && keepGoing) next(); });
seek.addEventListener("input", () => { pl.dragging = true; if (vid.duration) vid.currentTime = (seek.value / 1000) * vid.duration; paintSeek(); });
seek.addEventListener("change", () => { pl.dragging = false; });

$("plPlay").onclick = toggle;
$("plMedia").addEventListener("click", toggle);
$("plMedia").addEventListener("dblclick", () => fullscreen());
$("plNext").onclick = next; $("plPrev").onclick = prev;
$("plClose").onclick = closePlayer;
$("plLoop").onclick = () => { vid.loop = !vid.loop; store.set("loop", vid.loop); syncPills(); };
$("plAuto").onclick = () => { keepGoing = !keepGoing; store.set("auto", keepGoing); syncPills(); };
$("plSpeed").onchange = () => { vid.playbackRate = +$("plSpeed").value; store.set("speed", +$("plSpeed").value); };
$("volr").oninput = () => { vid.volume = $("volr").value / 100; vid.muted = vid.volume === 0; store.set("vol", vid.volume); store.set("muted", vid.muted); syncVol(); };
$("plMute").onclick = () => { vid.muted = !vid.muted; if (!vid.muted && vid.volume === 0) vid.volume = 0.6; store.set("muted", vid.muted); store.set("vol", vid.volume); syncVol(); };
function fullscreen() { if (document.fullscreenElement) document.exitFullscreen().catch(() => {}); else stage.requestFullscreen?.().catch(() => {}); }
$("plFs").onclick = fullscreen;
$("startS").onclick = () => openPlayer(null, "stash");
$("plShuf").setAttribute("aria-pressed", String(shuffle));
$("plShuf").onclick = () => { shuffle = !shuffle; store.set("shuffle", shuffle); $("plShuf").setAttribute("aria-pressed", String(shuffle)); };
$("plFav").onclick = () => { const it = deck.find((x) => x.id === pl.id); if (it) toggleFave(it).then(() => $("plFav").setAttribute("aria-pressed", String(faveIds.has(it.id)))); };
player.addEventListener("click", (e) => { if (e.target === player) closePlayer(); });

document.addEventListener("keydown", (e) => {
  if (player.hidden || e.target.matches("input[type=url], select")) return;
  const k = e.key.toLowerCase();
  const map = {
    " ": toggle, k: () => $("plAuto").click(), arrowright: () => (vid.currentTime += 5), arrowleft: () => (vid.currentTime -= 5),
    arrowup: () => { vid.muted = false; vid.volume = Math.min(1, vid.volume + 0.1); store.set("vol", vid.volume); syncVol(); },
    arrowdown: () => { vid.volume = Math.max(0, vid.volume - 0.1); store.set("vol", vid.volume); syncVol(); },
    m: () => $("plMute").click(), l: () => $("plLoop").click(), n: next, p: prev, f: fullscreen, escape: () => { if (!document.fullscreenElement) closePlayer(); },
    h: () => $("plFav").click(), s: () => $("plShuf").click(), e: cycleEdge,
  };
  if (map[k] && !(k === " " && e.target.tagName === "BUTTON")) { e.preventDefault(); map[k](); }
});



// Hover preview on stashed frames (muted, desktop only)
function hoverPreview(a, on) {
  const existing = a.querySelector(".hover-vid");
  if (!on) { if (existing) { existing.pause(); existing.remove(); } return; }
  if (existing || a.dataset.image || reduced) return;
  const v = document.createElement("video");
  Object.assign(v, { muted: true, loop: true, autoplay: true, playsInline: true, src: a.href });
  v.className = "hover-vid"; v.setAttribute("aria-hidden", "true");
  a.insertBefore(v, a.querySelector(".no"));
}

// ---------- Faves (kept on the server per browser) ----------
let cid = store.get("cid", null);
if (!cid) { cid = (crypto.randomUUID?.() || Math.random().toString(36).slice(2) + Date.now().toString(36)).replace(/[^A-Za-z0-9_-]/g, ""); store.set("cid", cid); }
const CH = { "X-Client-Id": cid };
let faves = [], faveIds = new Set();
async function loadFaves() {
  try {
    const r = await fetch("/v1/faves", { headers: CH }); if (!r.ok) return;
    faves = (await r.json()).items.map((f) => ({ ...f, dl: f.play.replace("?c=", "?download=true&c=") }));
    faveIds = new Set(faves.map((f) => f.id));
  } catch {}
  $("favesN").textContent = faves.length;
  document.querySelectorAll(".fav-btn").forEach((b) => b.setAttribute("aria-pressed", String(faveIds.has(b.dataset.id))));
  if (!$("favesView").hidden) renderFaves();
}
async function toggleFave(it) {
  const on = faveIds.has(it.id);
  const r = await fetch(`/v1/faves/${it.id}`, on
    ? { method: "DELETE", headers: CH }
    : { method: "PUT", headers: { ...CH, "content-type": "application/json" }, body: JSON.stringify({ job_id: it.jobId || null }) });
  if (!r.ok && r.status !== 404) { toast("Couldn’t update faves. That clip’s job may have expired."); return; }
  if (!on) session.faves++;
  await loadFaves();
}
function renderFaves() {
  const sh = $("favesSheet"); sh.innerHTML = "";
  $("favesSub").textContent = faves.length
    ? `${faves.length} clips you couldn’t let go of. They survive restarts.`
    : "Nothing here yet. Heart a clip in the stash, the player or the cave and it lands here.";
  faves.forEach((f, i) => {
    const a = document.createElement("a");
    a.className = "frame done"; a.href = f.play; a.id = "fv-" + f.id;
    a.innerHTML = `<img alt="" loading="lazy"><span class="no">${i + 1}</span><span class="st"></span>`;
    const img = a.querySelector("img"); posterFallback(img, f.play, f.image); img.src = f.thumb;
    a.append(faveButton(f));
    a.onclick = (e) => { if (e.metaKey || e.ctrlKey || e.button !== 0) return; e.preventDefault(); openPlayer(f.id, "faves"); };
    sh.append(a);
  });
}
function faveButton(it) {
  const b = document.createElement("button");
  b.type = "button"; b.className = "fav-btn"; b.dataset.id = it.id; b.textContent = "♥";
  b.setAttribute("aria-label", "Fave"); b.setAttribute("aria-pressed", String(faveIds.has(it.id)));
  b.onclick = (e) => { e.preventDefault(); e.stopPropagation(); toggleFave(it); };
  return b;
}
$("favesBtn").onclick = () => { const v = $("favesView"); v.hidden = !v.hidden; if (!v.hidden) { renderFaves(); v.scrollIntoView({ behavior: reduced ? "auto" : "smooth" }); } };
$("favesPlay").onclick = () => faves.length ? openPlayer(null, "faves") : toast("No faves yet. Heart a clip first.");
$("favesCave").onclick = () => faves.length ? openCave("faves") : toast("No faves yet. Heart a clip first.");
$("caveBtn").onclick = () => openCave();
loadFaves();

// ---------- Session tracking + report ----------
const session = { active: false, sec: 0, clips: new Set(), faves: 0 };
function sessionStart() { if (session.active) return; Object.assign(session, { active: true, sec: 0, clips: new Set(), faves: 0 }); }
function sessionEnd() {
  if (!player.hidden || !cave.hidden || !session.active) return;
  session.active = false; edgeStop(); flushRewards();
  if (session.sec >= 10) toast(`Session report: <b>${fmt(session.sec)}</b> locked in, <b>${session.clips.size}</b> clips, <b>${session.faves}</b> new faves.`, 7000);
}
function playingNow() {
  if (edge.holding) return false;
  if (!player.hidden) return !vid.hidden && !vid.paused;
  if (!cave.hidden) return [...wall.querySelectorAll("video")].some((v) => !v.paused) || !!wall.querySelector(".slot img");
  return false;
}
setInterval(() => {
  if (session.active && playingNow()) { session.sec++; pending.seconds++; }
  $("plTimer").textContent = fmt(session.sec); $("cvTimer").textContent = fmt(session.sec);
}, 1000);
let toastT;
function toast(html, ms = 4000) { if (rewardShowing) { rewardQ.push(html); return; } const t = $("toast"); t.classList.remove("reward"); t.innerHTML = html; t.hidden = false; clearTimeout(toastT); toastT = setTimeout(() => (t.hidden = true), ms); }

// ---------- Edge timer: play for N seconds, hold for M, repeat ----------
const edge = { mode: store.get("edge", "off"), holding: false, phaseEnd: 0, t: null };
const edgeSels = [...document.querySelectorAll(".edgeSel")];
edgeSels.forEach((sel) => { sel.value = edge.mode; sel.onchange = () => setEdge(sel.value); });
function setEdge(m) { edge.mode = m; store.set("edge", m); edgeSels.forEach((s) => (s.value = m)); edgeStop(); if (m !== "off" && session.active) edgeGo(); }
function cycleEdge() { const o = ["off", "30/10", "60/15", "90/20", "rand"]; setEdge(o[(o.indexOf(edge.mode) + 1) % o.length]);
                       toast(edge.mode === "off" ? "Edge timer off." : `Edge timer: ${edgeSels[0].selectedOptions[0].text}.`, 2000); }
function edgeDur() {
  if (edge.mode === "rand") return [20 + Math.floor(Math.random() * 70), 6 + Math.floor(Math.random() * 20)];
  return edge.mode.split("/").map(Number);
}
function edgeGo() {
  clearTimeout(edge.t); if (edge.mode === "off") return;
  edge.holding = false; $("edgeHud").hidden = true;
  const [on] = edgeDur(); edge.phaseEnd = Date.now() + on * 1000; edge.next = "hold";
  setMedia(true); edgeTick();
}
function edgeHold() {
  const [, off] = edgeDur(); edge.holding = true; edge.phaseEnd = Date.now() + off * 1000; edge.next = "go";
  setMedia(false);
  const h = $("edgeHud"); h.classList.remove("go"); h.hidden = false;
  $("edgeWord").textContent = "Hold"; $("edgeSub").textContent = "Hands off. Back in when it hits zero.";
  edgeTick();
}
function edgeTick() {
  clearTimeout(edge.t);
  if (edge.mode === "off" || (player.hidden && cave.hidden)) return edgeStop();
  const left = Math.max(0, Math.ceil((edge.phaseEnd - Date.now()) / 1000));
  $("edgeCount").textContent = left;
  const chip = $("edgeChip"); chip.hidden = edge.holding; chip.textContent = `Edge timer: hold in ${left}s`;
  if (left <= 0) {
    if (edge.next === "hold") return edgeHold();
    pending.edge_holds++;
    const h = $("edgeHud"); h.classList.add("go"); $("edgeWord").textContent = "Go"; $("edgeCount").textContent = ""; $("edgeSub").textContent = "Back in.";
    setTimeout(() => { if (!edge.holding) h.hidden = true; }, 900);
    return edgeGo();
  }
  edge.t = setTimeout(edgeTick, 250);
}
function edgeStop() { clearTimeout(edge.t); edge.t = null; edge.holding = false; $("edgeHud").hidden = true; $("edgeChip").hidden = true; }
function setMedia(play) {
  const vs = !player.hidden ? (vid.hidden ? [] : [vid]) : [...wall.querySelectorAll("video")];
  vs.forEach((v) => play ? v.play().catch(() => {}) : v.pause());
}
$("edgeHud").addEventListener("click", () => {}); // holds can't be skipped by tapping
vid.addEventListener("play", () => { if (edge.mode !== "off" && !edge.t && !edge.holding) edgeGo(); });

// ---------- Goon cave: a wall of rotating screens ----------
const cave = $("cave"), wall = $("wall");
const cv = { src: "stash", deck: [], tiles: [], loud: 0, timer: null };
$("cvN").value = String(store.get("cvN", 4)); $("cvRot").value = String(store.get("cvRot", 20));
$("cvKind").value = store.get("cvKind", "video");
// What goes on the wall: clips, images (e.g. a creator's photo sets) or both.
function caveDeck() {
  const d = cv.src === "faves" ? faves : cv.src === "library" ? lib.deck : stashDeck();
  const kind = $("cvKind").value;
  return d.filter((x) => kind === "all" || (kind === "image" ? x.image : !x.image));
}
async function openCave(src) {
  cv.src = src || (currentJob && stashed.size ? "stash" : "library");
  if (cv.src === "library" && !lib.deck.length) await loadLibDeck();
  $("cvSrc").value = cv.src;
  cave.hidden = false; document.body.classList.add("locked");
  pending.cave_opened = true;
  sessionStart(); buildWall();
  if (edge.mode !== "off") edgeGo();
  $("cvExit").focus();
}
function closeCave() {
  clearInterval(cv.timer); wall.querySelectorAll("video").forEach((v) => { v.pause(); v.removeAttribute("src"); v.load(); });
  wall.innerHTML = ""; cave.hidden = true; if (player.hidden) document.body.classList.remove("locked"); sessionEnd();
}
function pickClip(exclude) {
  const pool = cv.deck.filter((x) => !exclude.has(x.id));
  const from = pool.length ? pool : cv.deck;
  return from[Math.floor(Math.random() * from.length)];
}
// ---- Wall layout: "fit" packs screens by each clip's shape (see layout.js); "grid" is the equal grid.
const shapes = new Map();          // id -> measured width/height
const PORTRAIT = 9 / 16;           // RedGIFs is mostly vertical: a sensible guess until a clip reports its size
const FILL_CROP_LIMIT = 0.25;      // in "Fill screen" mode, never hide more than this share of a clip
// When clips are shown whole, a screen that doesn't match its clip shows a blurred band instead of
// cropping, so shape screens more tightly to their clips (at some cost to equal sizes).
const UNEVEN = { whole: 0.3, fill: 0.45 };
const aspectOf = (c) => shapes.get(c.id) || (c.width && c.height ? c.width / c.height : PORTRAIT);
$("cvLayout").value = store.get("cvLayout", "fit");
$("cvFrame").value = store.get("cvFrame", "whole");

function buildWall() {
  clearInterval(cv.timer);
  cv.deck = caveDeck();
  const n = +$("cvN").value;
  pending.cave_screens = Math.max(pending.cave_screens, n);
  wall.innerHTML = ""; cv.tiles = [];
  if (!cv.deck.length) {
    const kind = $("cvKind").value, what = kind === "image" ? "images" : kind === "video" ? "clips" : "clips or images";
    const hint = cv.src === "faves" ? "Heart some first, or switch the source."
      : cv.src === "library" ? "Pull a creator or niche, or copy files into the downloads folder and press Rescan in the Library."
      : "Let a few stash first, or switch the source to Library.";
    wall.innerHTML = `<div class="cave-empty"><p>No ${what} in ${cv.src === "stash" ? "this pull" : "your " + cv.src} yet.<br>${hint}</p></div>`;
    return;
  }
  const shown = new Set();
  for (let i = 0; i < n; i++) {
    const tile = document.createElement("div"); tile.className = "tile"; tile.tabIndex = 0;
    tile.innerHTML = `<div class="screen"><img class="backdrop" alt="" hidden><div class="slot"></div></div><div class="rot"></div><div class="tl"><i></i><span class="snd"></span></div>`;
    const t = { el: tile, slot: tile.querySelector(".slot"), bg: tile.querySelector(".backdrop"), v: null, clip: null, swapAt: 0, box: null };
    // Tap: hear this screen. Double tap (or double click): open it full size. Works the same on touch screens.
    let lastTap = 0;
    tile.addEventListener("click", () => {
      const now = Date.now();
      if (now - lastTap < 320) { const id = t.clip?.id; const src = cv.src; closeCave(); openPlayer(id, src); return; }
      lastTap = now; setLoud(i);
    });
    wall.append(tile); cv.tiles.push(t);
    const c = pickClip(shown, null); shown.add(c.id); loadTile(t, c, i, n);
  }
  layoutWall();
  setLoud(Math.min(cv.loud, n - 1));
  cv.timer = setInterval(rotateTick, 250);
}

function layoutWall() {
  if (!cv.tiles.length) return;
  const W = wall.clientWidth, H = wall.clientHeight;
  if (!W || !H) return;
  const mode = $("cvLayout").value;
  const result = mode === "grid"
    ? AioLayout.grid(cv.tiles.length, W, H, 4)
    : AioLayout.fit(cv.tiles.map((t) => aspectOf(t.clip)), W, H, 4, UNEVEN[$("cvFrame").value]);
  cv.tiles.forEach((t, i) => {
    const b = result.boxes[i];
    t.box = b;
    Object.assign(t.el.style, { left: b.x + "px", top: b.y + "px", width: b.w + "px", height: b.h + "px" });
    fitMedia(t);
  });
}
// "Show whole" (the default) never cuts anything off: the clip is fitted inside its screen and any
// spare strip is filled with a blurred copy of its poster. "Fill screen" covers the screen instead,
// unless that would hide more than FILL_CROP_LIMIT of the clip.
function fitMedia(t) {
  if (!t.box || !t.clip) return;
  const hidden = AioLayout.cropShare(t.box.w / t.box.h, aspectOf(t.clip));
  const contain = $("cvFrame").value === "whole" || hidden > FILL_CROP_LIMIT;
  t.el.classList.toggle("contain", contain);
  const poster = t.clip.thumb || (t.clip.image ? t.clip.play : "");
  const needsBg = contain && hidden > 0.005 && poster;
  t.bg.hidden = !needsBg;
  if (needsBg && t.bg.dataset.src !== poster) { t.bg.src = poster; t.bg.dataset.src = poster; }
}
// A clip's real shape arrives with its metadata; re-fit if the guess was off.
let refitT;
function learnShape(c, w, h) {
  if (!w || !h) return;
  const was = aspectOf(c), now = w / h;
  shapes.set(c.id, now);
  if (Math.abs(Math.log(now / was)) > 0.12 && $("cvLayout").value === "fit") {
    clearTimeout(refitT); refitT = setTimeout(layoutWall, 250);
  } else {
    cv.tiles.filter((t) => t.clip === c).forEach(fitMedia);
  }
}
new ResizeObserver(() => { if (!cave.hidden) { clearTimeout(refitT); refitT = setTimeout(layoutWall, 120); } }).observe(wall);

// Pick a clip not on the wall. When replacing one, prefer a similar shape so the wall stays put.
function pickClip(exclude, wantAspect) {
  const pool = cv.deck.filter((x) => !exclude.has(x.id));
  const from = pool.length ? pool : cv.deck;
  if (!wantAspect || $("cvLayout").value !== "fit") return from[Math.floor(Math.random() * from.length)];
  const sample = [];
  for (let k = 0; k < Math.min(8, from.length); k++) sample.push(from[Math.floor(Math.random() * from.length)]);
  sample.sort((a, b) => Math.abs(Math.log(aspectOf(a) / wantAspect)) - Math.abs(Math.log(aspectOf(b) / wantAspect)));
  return sample[0];
}

function loadTile(t, c, i = 0, n = 1) {
  t.clip = c; session.clips.add(c.id); pending.clips.add(c.id);
  if (t.v) { t.v.pause(); t.v.removeAttribute("src"); t.v.load(); }
  t.slot.innerHTML = "";
  if (c.image) {
    const img = new Image(); img.alt = "";
    img.onload = () => learnShape(c, img.naturalWidth, img.naturalHeight);
    img.src = c.play;
    t.slot.append(img); t.v = null;
  } else {
    const v = document.createElement("video");
    Object.assign(v, { muted: true, loop: true, playsInline: true, preload: "auto", src: c.play });
    v.addEventListener("loadedmetadata", () => learnShape(c, v.videoWidth, v.videoHeight), { once: true });
    t.slot.append(v); t.v = v;
    if (!edge.holding) v.play().catch(() => {});
  }
  t.el.querySelector(".tl i").textContent = c.user_name ? "@" + c.user_name : "";
  t.el.classList.add("fresh"); clearTimeout(t.freshT); t.freshT = setTimeout(() => t.el.classList.remove("fresh"), 2500);
  fitMedia(t);
  const rot = +$("cvRot").value;
  t.swapAt = rot ? Date.now() + rot * 1000 * (1 + i / Math.max(1, n)) : 0; // staggered so screens don't all flip at once
  t.span = rot ? t.swapAt - Date.now() : 0;
}
function rotateTick() {
  if (edge.holding) { cv.tiles.forEach((t) => t.swapAt && (t.swapAt += 250)); return; }
  const now = Date.now();
  cv.tiles.forEach((t, i) => {
    const bar = t.el.querySelector(".rot");
    if (!t.swapAt) { bar.style.width = 0; return; }
    bar.style.width = Math.min(100, 100 * (1 - (t.swapAt - now) / t.span)) + "%";
    if (now >= t.swapAt) rotateTile(i);
  });
}
function rotateTile(i) {
  const t = cv.tiles[i]; if (!t) return;
  const shown = new Set(cv.tiles.map((x) => x.clip?.id));
  const rot = +$("cvRot").value;
  loadTile(t, pickClip(shown, t.box ? t.box.w / t.box.h : null), 0, 1);
  if (rot) { t.swapAt = Date.now() + rot * 1000; t.span = rot * 1000; }
  if (i === cv.loud) setLoud(i);
}
function setLoud(i) {
  cv.loud = i;
  cv.tiles.forEach((t, j) => {
    const loud = j === i; t.el.classList.toggle("loud", loud);
    if (t.v) { t.v.muted = !loud || vid.muted; t.v.volume = vid.volume; }
    t.el.querySelector(".snd").textContent = loud ? (t.v ? "♪ sound" : "selected") : "";
  });
}
$("cvKind").onchange = () => { store.set("cvKind", $("cvKind").value); buildWall(); };
$("cvLayout").onchange = () => { store.set("cvLayout", $("cvLayout").value); layoutWall(); };
$("cvFrame").onchange = () => { store.set("cvFrame", $("cvFrame").value); layoutWall(); };
$("cvMore").onclick = () => {
  const open = $("cvOpts").classList.toggle("open");
  $("cvMore").setAttribute("aria-expanded", String(open));
  setTimeout(layoutWall, 50);   // the bar changed height
};
$("cvExit").onclick = closeCave;
$("cvN").onchange = () => { store.set("cvN", +$("cvN").value); buildWall(); };
$("cvRot").onchange = () => { store.set("cvRot", +$("cvRot").value); buildWall(); };
$("cvSrc").onchange = async () => { cv.src = $("cvSrc").value; if (cv.src === "library") await loadLibDeck(); buildWall(); };
document.addEventListener("keydown", (e) => {
  if (cave.hidden || !player.hidden || e.target.matches("select")) return;
  const k = e.key.toLowerCase();
  if (k === "escape") { e.preventDefault(); closeCave(); }
  else if (k === "r") rotateTile(cv.loud);
  else if (k === "l") layoutWall();
  else if (k === "e") cycleEdge();
  else if (k === "m") { vid.muted = !vid.muted; store.set("muted", vid.muted); syncVol(); setLoud(cv.loud); }
  else if (k === "h") { const c = cv.tiles[cv.loud]?.clip; if (c) toggleFave(c).then(() => toast(faveIds.has(c.id) ? "Faved." : "Removed from faves.", 1500)); }
  else if (/^[1-9]$/.test(k) && +k <= cv.tiles.length) setLoud(+k - 1);
});

// ---------- Views (library / history / rewards / faves): one open at a time ----------
const VIEWS = { libBtn: "libraryView", histBtn: "historyView", rankBtn: "rewardsView", favesBtn: "favesView" };
const ON_OPEN = { libraryView: () => loadLibrary(), historyView: () => loadHistory(), rewardsView: () => renderRewards(), favesView: () => renderFaves() };
for (const [btn, view] of Object.entries(VIEWS)) {
  $(btn).onclick = () => {
    const opening = $(view).hidden;
    Object.values(VIEWS).forEach((v) => ($(v).hidden = true));
    if (opening) { $(view).hidden = false; ON_OPEN[view](); $(view).scrollIntoView({ behavior: reduced ? "auto" : "smooth" }); }
  };
}
const showView = (view) => { Object.values(VIEWS).forEach((v) => ($(v).hidden = v !== view)); ON_OPEN[view]?.(); $(view).scrollIntoView({ behavior: reduced ? "auto" : "smooth" }); };

const fmtBytes = (b) => b >= 1e9 ? (b / 1e9).toFixed(1) + " GB" : b >= 1e6 ? Math.round(b / 1e6) + " MB" : Math.round(b / 1e3) + " KB";
const hrs = (sec) => sec < 3600 ? Math.round(sec / 60) + " min" : (sec / 3600).toFixed(sec < 36000 ? 1 : 0).replace(/\.0$/, "") + " h";

// ---------- Library ----------
const lib = { items: [], total: 0, deck: [] };
const libPick = new TagPick();
const libEntry = (e) => ({ id: e.id, user_name: e.creator, tags: e.tags, play: e.play, dl: e.dl, thumb: e.thumb, image: e.image,
                           width: e.width, height: e.height, jobId: null });
const libParams = (extra = {}) => new URLSearchParams({ q: $("libQ").value.trim(), creator: $("libCreator").value, ...libPick.params(),
                                                        kind: $("libKind").value, sort: $("libSort").value, ...extra });
async function refreshLibCount() {
  try { const d = await (await fetch("/v1/library?limit=1")).json(); $("libN").textContent = d.total; } catch {}
}
async function loadLibrary(append = false) {
  let d;
  try { d = await (await fetch("/v1/library?" + libParams({ offset: append ? lib.items.length : 0, limit: 120 }))).json(); }
  catch { $("libSub").textContent = "Couldn’t reach the library. Is the server running?"; return; }
  lib.total = d.total;
  lib.items = append ? lib.items.concat(d.items) : d.items;
  lib.deck = [];                                    // filters changed: rebuild the play deck on demand
  const filtered = $("libQ").value.trim() || $("libCreator").value || libPick.active || $("libKind").value !== "all";
  if (!append) {
    const sel = $("libCreator"), keep = sel.value;
    sel.innerHTML = `<option value="">All creators</option>` +
      d.creators.map((c) => `<option value="${esc(c.creator)}">${esc(c.creator)} (${c.count})</option>`).join("");
    if (keep && !d.creators.some((c) => c.creator === keep)) sel.insertAdjacentHTML("beforeend", `<option value="${esc(keep)}">${esc(keep)}</option>`);
    sel.value = keep;
    const chips = $("libTags"); chips.innerHTML = "";
    const relist = () => loadLibrary();
    tagControls($("libTagCtl"), libPick, relist);
    for (const [t, c] of chipList(d.tags.slice(0, 24).map((x) => [x.tag, x.count]), libPick)) chips.append(tagChip(t, c, libPick, relist));
    $("libSub").textContent = d.total
      ? `${libPick.active ? libPick.describe().replace(/^./, (c) => c.toUpperCase()) + ": " : ""}${[d.clips && `${d.clips} clip${d.clips === 1 ? "" : "s"}`, d.images && `${d.images} image${d.images === 1 ? "" : "s"}`].filter(Boolean).join(" and ")}${filtered ? " match" : ""}, ${fmtBytes(d.total_bytes)}${d.total_duration_s >= 60 ? `, ${hrs(d.total_duration_s)} of footage` : ""}, from ${d.creators.length} creator${d.creators.length === 1 ? "" : "s"}. Yours for good, every session.`
      : filtered ? "Nothing matches. Loosen the filters." : "Your library is empty. Pull a creator or niche and everything lands here for good.";
    $("libZip").href = "/v1/library/archive?" + libParams();
    $("libZip").hidden = !d.total;
    if (!filtered) $("libN").textContent = d.total;
  }
  const sh = $("libSheet");
  if (!append) sh.innerHTML = "";
  d.items.forEach((e, k) => sh.append(libFrame(e, (append ? lib.items.length - d.items.length : 0) + k)));
  $("libMore").hidden = lib.items.length >= d.total;
}
// Clips copied in by hand have no poster: show a frame of the video instead.
function posterFallback(img, playUrl, isImage) {
  img.onerror = () => {
    if (isImage) { img.remove(); return; }
    const v = document.createElement("video");
    Object.assign(v, { muted: true, preload: "metadata", playsInline: true, src: playUrl + (playUrl.includes("?") ? "&" : "?") + "t#t=1" });
    v.className = "poster-vid"; v.setAttribute("aria-hidden", "true");
    img.replaceWith(v);
  };
}
function libFrame(e, i) {
  const a = document.createElement("a");
  a.className = "frame done"; a.href = e.play; a.dataset.id = e.id; a.dataset.image = e.image ? "1" : "";
  a.innerHTML = `<img alt="" loading="lazy"><span class="no">${i + 1}</span><span class="st"></span>`;
  const img = a.querySelector("img"); posterFallback(img, e.play, e.image); img.src = e.thumb;
  a.title = `@${e.creator}${e.tags.length ? "  #" + e.tags.slice(0, 5).join(" #") : ""}`;
  a.append(faveButton(libEntry(e)));
  a.onclick = async (ev) => {
    if (ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.button !== 0) return;
    ev.preventDefault();
    await loadLibDeck();
    if (!lib.deck.some((x) => x.id === e.id)) lib.deck.unshift(libEntry(e));
    openPlayer(e.id, "library");
  };
  a.addEventListener("pointerenter", (ev) => { if (ev.pointerType === "mouse") hoverPreview(a, true); });
  a.addEventListener("pointerleave", () => hoverPreview(a, false));
  return a;
}
async function loadLibDeck() {
  if (lib.deck.length) return lib.deck;
  try {
    const d = await (await fetch("/v1/library?" + ($("libraryView").hidden ? new URLSearchParams({ limit: 1000, sort: "random" }) : libParams({ limit: 1000 })))).json();
    lib.deck = d.items.map(libEntry);
  } catch { lib.deck = []; }
  return lib.deck;
}
let libT;
$("libQ").addEventListener("input", () => { clearTimeout(libT); libT = setTimeout(() => loadLibrary(), 250); });
["libCreator", "libKind", "libSort"].forEach((id) => ($(id).onchange = () => loadLibrary()));
$("libMore").onclick = () => loadLibrary(true);
$("libRescan").onclick = async () => {
  const b = $("libRescan"); b.disabled = true; b.textContent = "Scanning…";
  try {
    const d = await (await fetch("/v1/library/rescan", { method: "POST" })).json();
    toast(`Library rescanned: <b>${d.indexed}</b> files found, including anything you copied into the downloads folder.`, 5000);
    lib.deck = []; await loadLibrary(); refreshLibCount();
  } finally { b.disabled = false; b.textContent = "Rescan folder"; }
};
$("libPlay").onclick = async () => { await loadLibDeck(); lib.deck.length ? openPlayer(null, "library") : toast("Nothing in the library to play yet."); };
$("libCave").onclick = async () => { await loadLibDeck(); openCave("library"); };
refreshLibCount();

// ---------- History ----------
function targetFromJob(j) {
  const r = j.request;
  return (r.urls[0] && who(r.urls[0])) || (r.users[0] && { kind: "creator", name: r.users[0] })
      || (r.niches[0] && { kind: "niche", name: nicheName(r.niches[0]) }) || { kind: "tag", name: j.label };
}
async function loadHistory() {
  let d; try { d = await (await fetch("/v1/history")).json(); } catch { return; }
  const list = $("histList"); list.innerHTML = "";
  $("histSub").textContent = d.items.length
    ? `${d.items.length} pull${d.items.length === 1 ? "" : "s"}. Paste the same link again and only new clips get downloaded. Interrupted pulls pick up where they stopped.`
    : "No pulls yet. Drop a creator, niche or tag link up top.";
  for (const h of d.items) {
    const row = document.createElement("div");
    row.className = "hrow " + h.state;
    const when = new Date(h.last_run || h.created).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
    const stateWord = { done: "done", interrupted: "interrupted", running: "pulling", queued: "queued", failed: "failed", paused: "paused" }[h.state] || h.state;
    row.innerHTML = `
      <div class="hthumbs">${h.thumbs.map((t) => `<img src="${t}" alt="" loading="lazy" onerror="this.remove()">`).join("")}</div>
      <div class="hmain"><b>${esc(h.urls[0] || h.label)}</b><span class="state ${h.state}">${stateWord}</span>
        <p>${h.tag_filter ? `Tag filter: ${esc(h.tag_filter)}${h.filtered_out ? ` (${h.filtered_out} skipped)` : ""}. ` : ""}${h.imported ? "From an older version. " : ""}${h.downloaded} of ${h.discovered || "?"} clips stashed${h.already_had ? `, ${h.already_had} reused from the library` : ""}${h.failed ? `, ${h.failed} missed` : ""}. ${h.quality.toUpperCase()}. Pulled ${h.runs} time${h.runs === 1 ? "" : "s"}, last ${when}.</p></div>
      <div class="hact"></div>`;
    const act = row.querySelector(".hact");
    const btn = (label, cls, fn) => { const b = document.createElement("button"); b.type = "button"; b.className = "btn " + cls; b.textContent = label; b.onclick = fn; act.append(b); return b; };
    if (["interrupted", "failed", "paused"].includes(h.state)) btn("Resume", "hot", () => resumePull(h.id));
    else if (h.state === "done") btn("Pull new clips", "ghost", () => resumePull(h.id));
    if (h.state === "running" || h.state === "queued")
      btn("Pause", "ghost", async () => { await fetch(`/v1/jobs/${h.id}/pause`, { method: "POST" }); setTimeout(loadHistory, 600); });
    btn("Open", "ghost", () => openPull(h.id));
    if (h.downloaded) { const z = document.createElement("a"); z.className = "btn ghost"; z.textContent = "Download .zip"; z.href = `/v1/jobs/${h.id}/archive`; act.append(z); }
    if (h.state !== "running" && h.state !== "queued")
      btn("Forget", "ghost", async () => { await fetch(`/v1/history/${h.id}`, { method: "DELETE" }); loadHistory(); });
    list.append(row);
  }
  clearTimeout(histT);
  if (!$("historyView").hidden && d.items.some((h) => h.state === "running" || h.state === "queued")) histT = setTimeout(loadHistory, 2000);
  return d.items;
}
let histT;
async function openPull(id) {
  const r = await fetch(`/v1/jobs/${id}`); if (!r.ok) return toast("That pull is gone.");
  const job = await r.json(); clearInterval(timer);
  if (job.request.urls[0]) $("url").value = job.request.urls[0];
  start(job, targetFromJob(job));
}
async function resumePull(id) {
  const r = await fetch(`/v1/jobs/${id}/resume`, { method: "POST" });
  if (!r.ok) return toast(detail(await r.json().catch(() => ({})), r));
  const job = await r.json(); if (job.request.urls[0]) $("url").value = job.request.urls[0];
  start(job, targetFromJob(job));
  toast("Picking up where it left off. Clips already stashed are skipped.", 4000);
}
// After a restart the server resumes interrupted pulls by itself: tell the user
loadHistory().then((items) => {
  const live = (items || []).filter((h) => h.state === "running" || h.state === "queued");
  if (live.length) toast(`Picking up <b>${live.length}</b> pull${live.length === 1 ? "" : "s"} that got interrupted last time. See History.`, 7000);
});
const pullsCounted = new Set();
function onPullDone(job) {
  const key = job.id + ":" + job.runs;
  if (pullsCounted.has(key)) return;
  pullsCounted.add(key);
  pending.stashed += Math.max(0, job.downloaded - job.already_had);
  lib.deck = []; refreshLibCount(); flushRewards();
  if (!$("historyView").hidden) loadHistory();
}

// ---------- Rewards ----------
const pending = { seconds: 0, clips: new Set(), edge_holds: 0, stashed: 0, cave_opened: false, cave_screens: 0, tag_filter: false };
let me = null, flushing = false;
const rewardQ = [];
function applyMe(d, announce) {
  me = d;
  $("rankTitle").textContent = d.rank.title;
  $("rankBar").style.width = Math.round(d.rank.progress * 100) + "%";
  $("rankBtn").title = `${d.rank.title}: ${hrs(d.rank.seconds)} locked in` + (d.rank.next_title ? `. ${hrs(d.rank.next_at - d.rank.seconds)} to ${d.rank.next_title}.` : ". Top rank.");
  if (announce) {
    if (d.rank_up) rewardQ.push(`<small>Rank up</small><big>${esc(d.rank_up.title)}</big><small>${hrs(d.rank_up.seconds)} locked in.${d.rank_up.next_title ? ` Next up: ${esc(d.rank_up.next_title)}.` : ""}</small>`);
    for (const b of d.new_badges || []) rewardQ.push(`<small>Badge unlocked</small><big>${esc(b.title)}</big><small>${esc(b.how)}.</small>`);
    showRewards();
  }
  if (!$("rewardsView").hidden) renderRewards();
}
let rewardShowing = false;
function showRewards() {
  if (rewardShowing || !rewardQ.length) return;
  rewardShowing = true;
  const t = $("toast"); t.classList.add("reward"); t.innerHTML = rewardQ.shift(); t.hidden = false; clearTimeout(toastT);
  toastT = setTimeout(() => { t.hidden = true; t.classList.remove("reward"); rewardShowing = false; showRewards(); }, 4200);
}
async function flushRewards() {
  const any = pending.seconds || pending.clips.size || pending.edge_holds || pending.stashed || pending.cave_opened || pending.cave_screens || pending.tag_filter;
  if (flushing || (!any && me)) return;
  const body = { seconds: pending.seconds, clips: [...pending.clips], edge_holds: pending.edge_holds, stashed: pending.stashed,
                 cave_opened: pending.cave_opened, cave_screens: pending.cave_screens, tag_filter: pending.tag_filter, faves: faves.length };
  Object.assign(pending, { seconds: 0, clips: new Set(), edge_holds: 0, stashed: 0, cave_opened: false, cave_screens: 0, tag_filter: false });
  flushing = true;
  try {
    const r = await fetch("/v1/me/events", { method: "POST", keepalive: true, headers: { ...CH, "content-type": "application/json" }, body: JSON.stringify(body) });
    if (r.ok) applyMe(await r.json(), true);
  } catch {} finally { flushing = false; }
}
setInterval(flushRewards, 15000);
document.addEventListener("visibilitychange", () => { if (document.hidden) flushRewards(); });
window.addEventListener("pagehide", flushRewards);
fetch("/v1/me", { headers: CH }).then((r) => r.json()).then((d) => applyMe(d, false)).catch(() => {});
function renderRewards() {
  if (!me) return;
  const r = me.rank, st = me.stats;
  $("rwTitle").textContent = r.title;
  $("rwSub").textContent = `${hrs(st.seconds)} locked in. ` + (r.next_title ? `${hrs(r.next_at - st.seconds)} more to ${r.next_title}. ` : "You’re at the top. ")
    + `${st.clips_seen} different clip${st.clips_seen === 1 ? "" : "s"} watched, ${st.edge_holds} hold${st.edge_holds === 1 ? "" : "s"} survived, ${st.faves} fave${st.faves === 1 ? "" : "s"}. Ranks count total time and never drop.`;
  $("rwLadder").innerHTML = me.ranks.map((x, i) => `<div class="rung ${i + 1 < r.level ? "got" : i + 1 === r.level ? "now" : ""}">${esc(x.title)}<small>${x.at ? hrs(x.at) : "start"}</small></div>`).join("");
  $("rwBadges").innerHTML = me.badges.map((b) => `<div class="badge ${b.earned ? "got" : ""}"><b>${esc(b.title)}</b><p>${esc(b.how)}${b.earned ? ". Earned " + new Date(b.earned).toLocaleDateString() : ""}</p><i><span style="width:${Math.round(b.progress * 100)}%"></span></i></div>`).join("");
}

function stop() {
  clearInterval(timer);
  go.disabled = false; $("goZip").disabled = false; go.textContent = "Load it all";
}
