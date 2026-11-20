/**
 * badges.js — Badge system for aioredgif.
 *
 * Tier system: bronze (1 heart), silver (2 hearts), gold (3 hearts), diamond (4 hearts).
 * Each badge image is CSS-tinted per tier. Earned badges show a shareable card modal
 * with date, time and a custom message.
 */

'use strict';

/* ─── Tier definitions ─────────────────────────────────────────────────────── */

const TIERS = {
  bronze: {
    label: 'Bronze',
    hearts: 1,
    // warm amber tint via hue-rotate + sepia blend
    filter: 'sepia(0.55) saturate(2.2) hue-rotate(5deg) brightness(0.92)',
    glow: '#cd7f32',
    glowRgb: '205,127,50',
    heartFill: '#cd7f32',
    heartGlow: '#ff9f4a',
    rimColor: '#b8860b',
  },
  silver: {
    label: 'Silver',
    hearts: 2,
    filter: 'grayscale(0.6) saturate(1.2) brightness(1.05) contrast(1.1)',
    glow: '#c0c0c0',
    glowRgb: '192,192,192',
    heartFill: '#d8d8e8',
    heartGlow: '#ffffff',
    rimColor: '#a8a8b8',
  },
  gold: {
    label: 'Gold',
    hearts: 3,
    filter: 'sepia(0.45) saturate(3.5) hue-rotate(345deg) brightness(1.08)',
    glow: '#ffd700',
    glowRgb: '255,215,0',
    heartFill: '#ffd700',
    heartGlow: '#fff176',
    rimColor: '#b8860b',
  },
  diamond: {
    label: 'Diamond',
    hearts: 4,
    filter: 'hue-rotate(195deg) saturate(1.8) brightness(1.15) contrast(1.05)',
    glow: '#a8f0ff',
    glowRgb: '168,240,255',
    heartFill: '#a8f0ff',
    heartGlow: '#e0faff',
    rimColor: '#5fc8e8',
  },
};

/* ─── Badge catalogue ───────────────────────────────────────────────────────── */

const BADGE_DEFS = [
  {
    id: 'first_haul',
    name: 'First Haul',
    desc: 'Finish your first pull.',
    file: 'Neon First Haul Unboxing Badge.png',
    tiers: { bronze: 1, silver: 5, gold: 20, diamond: 50 },
    unit: 'pulls',
    icon: '📦',
  },
  {
    id: 'collector',
    name: 'Collector',
    desc: 'Keep faves in your library.',
    file: 'Neon Pink Faves Collector Badge.png',
    tiers: { bronze: 10, silver: 25, gold: 100, diamond: 500 },
    unit: 'faves',
    icon: '⭐',
  },
  {
    id: 'hoarder',
    name: 'Hoarder',
    desc: 'Stash clips in your library.',
    file: 'Neon Clip Hoarder Badge.png',
    tiers: { bronze: 50, silver: 200, gold: 500, diamond: 2000 },
    unit: 'clips',
    icon: '🗂️',
  },
  {
    id: 'held_it',
    name: 'Held It',
    desc: 'Complete edge-timer holds.',
    file: 'Neon Edge-Timer Achievement Badge.png',
    tiers: { bronze: 1, silver: 10, gold: 25, diamond: 100 },
    unit: 'holds',
    icon: '⏳',
  },
  {
    id: 'iron_will',
    name: 'Iron Will',
    desc: 'Survive consecutive holds without breaking.',
    file: 'Neon Iron Will Achievement Badge.png',
    tiers: { bronze: 5, silver: 25, gold: 50, diamond: 200 },
    unit: 'holds total',
    icon: '⛓️',
  },
  {
    id: 'cave_dweller',
    name: 'Cave Dweller',
    desc: 'Time spent in the goon cave.',
    file: 'Neon Cave Dweller Emblem.png',
    tiers: { bronze: 10, silver: 60, gold: 300, diamond: 1200 },
    unit: 'minutes',
    icon: '🕳️',
  },
  {
    id: 'full_wall',
    name: 'Full Wall',
    desc: 'Fill all 9 cave screens.',
    file: 'Neon Full Wall Goon Cave Badge.png',
    tiers: { bronze: 1, silver: 5, gold: 20, diamond: 100 },
    unit: 'sessions',
    icon: '🖥️',
  },
  {
    id: 'goon_god',
    name: 'Goon God',
    desc: 'Total session time — the ascension.',
    file: 'Neon Cosmic Goon God Crest.png',
    tiers: { bronze: 60, silver: 300, gold: 1200, diamond: 6000 },
    unit: 'minutes',
    icon: '👑',
  },
  {
    id: 'deep_diver',
    name: 'Deep Diver',
    desc: 'Explore tags and niches.',
    file: 'Neon Deep Diver Emblem.png',
    tiers: { bronze: 5, silver: 20, gold: 60, diamond: 200 },
    unit: 'unique tags',
    icon: '🔍',
  },
  {
    id: 'tag_hunter',
    name: 'Tag Hunter',
    desc: 'Use include/exclude tag filters on pulls.',
    file: 'Neon Tag Hunter Achievement Badge.png',
    tiers: { bronze: 1, silver: 10, gold: 50, diamond: 200 },
    unit: 'filtered pulls',
    icon: '🏷️',
  },
  {
    id: 'locked_in',
    name: 'Locked In',
    desc: 'Consecutive daily sessions.',
    file: 'Cyber Neon Locked-In Badge.png',
    tiers: { bronze: 3, silver: 7, gold: 30, diamond: 100 },
    unit: 'days',
    icon: '🔒',
  },
  {
    id: 'lurker',
    name: 'Lurker',
    desc: 'Quiet browsing sessions — no sound, no faves.',
    file: 'Neon Lurker Cyberpunk Badge.png',
    tiers: { bronze: 5, silver: 20, gold: 60, diamond: 300 },
    unit: 'silent sessions',
    icon: '👁️',
  },
  {
    id: 'connoisseur',
    name: 'Connoisseur',
    desc: 'Watch full clips without skipping.',
    file: 'Neon Connoisseur Cinematic Badge.png',
    tiers: { bronze: 10, silver: 50, gold: 200, diamond: 1000 },
    unit: 'full watches',
    icon: '🎬',
  },
  {
    id: 'anime_initiate',
    name: 'Anime Initiate',
    desc: 'Fave clips tagged anime.',
    file: 'Neon Magenta Anime Initiate Badge.png',
    tiers: { bronze: 5, silver: 25, gold: 100, diamond: 500 },
    unit: 'anime faves',
    icon: '🌸',
  },
  {
    id: 'anime_gamer',
    name: 'Anime Gamer',
    desc: 'Play clips tagged anime in the cave.',
    file: 'Neon Anime Gamer Fave Clip Badge.png',
    tiers: { bronze: 10, silver: 50, gold: 200, diamond: 1000 },
    unit: 'anime cave clips',
    icon: '🎮',
  },
  {
    id: 'edge_lord',
    name: 'Edge Lord',
    desc: 'Complete long edge-timer sessions.',
    file: 'Neon Edge Lord Emblem.png',
    tiers: { bronze: 1, silver: 5, gold: 20, diamond: 75 },
    unit: 'long sessions',
    icon: '⚡',
  },
  {
    id: 'goon_monk',
    name: 'Goon Monk',
    desc: 'Meditate — keep the cave open silently for a long time.',
    file: 'Neon Goon Monk Meditation Badge.png',
    tiers: { bronze: 10, silver: 30, gold: 90, diamond: 360 },
    unit: 'silent minutes',
    icon: '🧘',
  },
  {
    id: 'into_the_cave',
    name: 'Into the Cave',
    desc: 'Open the goon cave for the first time.',
    file: 'Into the Neon Goon Cave.png',
    tiers: { bronze: 1, silver: 3, gold: 10, diamond: 50 },
    unit: 'cave opens',
    icon: '🌀',
  },
];

/* ─── Storage helpers ───────────────────────────────────────────────────────── */

const STORAGE_KEY = 'aioredgif_badges_v1';

function loadBadgeState() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
  } catch {
    return {};
  }
}

function saveBadgeState(state) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch { /* quota – swallow */ }
}

/**
 * Award a badge tier if not already held and store it.
 * Returns the newly earned tier string, or null.
 *
 * @param {string} badgeId
 * @param {string} tier - 'bronze'|'silver'|'gold'|'diamond'
 * @param {string} [customMessage]
 * @returns {string|null}
 */
function awardBadge(badgeId, tier, customMessage = '') {
  const state = loadBadgeState();
  const tierOrder = ['bronze', 'silver', 'gold', 'diamond'];
  const existing = state[badgeId];
  if (existing && tierOrder.indexOf(existing.tier) >= tierOrder.indexOf(tier)) return null;

  state[badgeId] = {
    tier,
    earnedAt: Date.now(),
    customMessage,
  };
  saveBadgeState(state);
  return tier;
}

/** Check all badge defs against a stats object and auto-award any newly reached tiers. */
function checkAndAward(stats) {
  const tierOrder = ['bronze', 'silver', 'gold', 'diamond'];
  const newlyEarned = [];
  const state = loadBadgeState();

  for (const def of BADGE_DEFS) {
    const statVal = stats[def.id] ?? 0;
    let highestEarned = null;

    for (const t of tierOrder) {
      if (def.tiers[t] !== undefined && statVal >= def.tiers[t]) {
        highestEarned = t;
      }
    }

    if (!highestEarned) continue;

    const existing = state[def.id];
    const existingIdx = existing ? tierOrder.indexOf(existing.tier) : -1;
    const newIdx = tierOrder.indexOf(highestEarned);

    if (newIdx > existingIdx) {
      awardBadge(def.id, highestEarned);
      newlyEarned.push({ def, tier: highestEarned });
    }
  }

  return newlyEarned;
}

/* ─── SVG heart builder ─────────────────────────────────────────────────────── */

/**
 * Build an SVG row of N hearts (filled) + (4-N) hollow, styled for the tier.
 *
 * @param {number} filled
 * @param {object} tierDef
 * @returns {string} SVG markup
 */
function heartsSVG(filled, tierDef, size = 22) {
  const total = 4;
  const gap = size * 1.35;
  const w = gap * total;
  const hearts = Array.from({ length: total }, (_, i) => {
    const x = i * gap + gap / 2;
    const y = size * 0.9;
    const isFilled = i < filled;
    const scale = isFilled ? 1 : 0.85;
    const fill = isFilled ? tierDef.heartFill : 'none';
    const stroke = isFilled ? tierDef.heartGlow : 'rgba(255,255,255,0.35)';
    const sw = isFilled ? 1.5 : 1.2;
    const opacity = isFilled ? 1 : 0.5;
    // Standard heart path, centered at 0,0, then translated
    return `<g transform="translate(${x},${y}) scale(${scale})" opacity="${opacity}">
      <path d="M0,-6 C-3.5,-11 -11,-11 -11,-5 C-11,0 -6,5 0,11 C6,5 11,0 11,-5 C11,-11 3.5,-11 0,-6Z"
        fill="${fill}" stroke="${stroke}" stroke-width="${sw}"
        ${isFilled ? `filter="url(#hglow${filled})"` : ''} />
    </g>`;
  }).join('');

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${size * 1.8}" viewBox="0 0 ${w} ${size * 1.8}" overflow="visible">
    <defs>
      <filter id="hglow${filled}" x="-80%" y="-80%" width="260%" height="260%">
        <feGaussianBlur stdDeviation="2.5" result="blur"/>
        <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
      </filter>
    </defs>
    ${hearts}
  </svg>`;
}

/* ─── Badge card DOM builder ────────────────────────────────────────────────── */

/**
 * Build one .badge-card element for the given def + earned state.
 *
 * @param {object} def - badge definition
 * @param {object|null} earned - { tier, earnedAt, customMessage } or null
 * @returns {HTMLElement}
 */
function buildBadgeCard(def, earned) {
  const tierOrder = ['bronze', 'silver', 'gold', 'diamond'];
  const card = document.createElement('div');
  card.className = `badge-card ${earned ? 'earned tier-' + earned.tier : 'locked'}`;
  card.dataset.badgeId = def.id;

  const tierDef = earned ? TIERS[earned.tier] : null;

  // --- image wrapper ---
  const imgWrap = document.createElement('div');
  imgWrap.className = 'badge-img-wrap';

  const img = document.createElement('img');
  img.src = `img/badges/${encodeURIComponent(def.file)}`;
  img.alt = def.name;
  img.loading = 'lazy';
  if (tierDef) {
    img.style.filter = tierDef.filter;
  }
  imgWrap.appendChild(img);

  // tier ribbon
  if (earned) {
    const ribbon = document.createElement('div');
    ribbon.className = `badge-ribbon tier-${earned.tier}`;
    ribbon.textContent = tierDef.label;
    ribbon.style.setProperty('--tier-glow', tierDef.glow);
    imgWrap.appendChild(ribbon);
  }

  // hearts overlay (positioned over the badge bottom area)
  if (earned) {
    const heartsWrap = document.createElement('div');
    heartsWrap.className = 'badge-hearts';
    heartsWrap.innerHTML = heartsSVG(tierDef.hearts, tierDef, 18);
    imgWrap.appendChild(heartsWrap);
  } else {
    // show locked hearts
    const heartsWrap = document.createElement('div');
    heartsWrap.className = 'badge-hearts locked-hearts';
    heartsWrap.innerHTML = heartsSVG(0, { heartFill: 'none', heartGlow: 'rgba(255,255,255,0.2)' }, 18);
    imgWrap.appendChild(heartsWrap);
  }

  card.appendChild(imgWrap);

  // --- info section ---
  const info = document.createElement('div');
  info.className = 'badge-info';

  const nameEl = document.createElement('div');
  nameEl.className = 'badge-name';
  nameEl.textContent = def.name;
  info.appendChild(nameEl);

  const descEl = document.createElement('div');
  descEl.className = 'badge-desc';
  descEl.textContent = def.desc;
  info.appendChild(descEl);

  // tier progress dots
  const dots = document.createElement('div');
  dots.className = 'badge-tier-dots';
  for (const t of tierOrder) {
    const dot = document.createElement('span');
    dot.className = `tier-dot tier-dot-${t}`;
    dot.title = `${TIERS[t].label}: ${def.tiers[t] ?? '—'} ${def.unit}`;
    if (earned) {
      const earnedIdx = tierOrder.indexOf(earned.tier);
      const thisIdx = tierOrder.indexOf(t);
      if (thisIdx <= earnedIdx) dot.classList.add('reached');
    }
    dot.style.setProperty('--dot-color', TIERS[t].glow);
    dots.appendChild(dot);
  }
  info.appendChild(dots);

  if (earned) {
    const earnedDate = new Date(earned.earnedAt);
    const dateStr = earnedDate.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
    const timeStr = earnedDate.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });

    const meta = document.createElement('div');
    meta.className = 'badge-earned-meta';
    meta.innerHTML = `<span class="badge-earned-label">Earned</span> <span class="badge-earned-date">${dateStr}</span> <span class="badge-earned-sep">·</span> <span class="badge-earned-time">${timeStr}</span>`;
    info.appendChild(meta);

    if (earned.customMessage) {
      const msg = document.createElement('div');
      msg.className = 'badge-custom-msg';
      msg.textContent = `"${earned.customMessage}"`;
      info.appendChild(msg);
    }

    // Share button
    const shareBtn = document.createElement('button');
    shareBtn.className = 'badge-share-btn';
    shareBtn.textContent = 'Share';
    shareBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      openShareModal(def, earned);
    });
    info.appendChild(shareBtn);
  } else {
    // show next tier requirement
    const nextTier = tierOrder.find(t => def.tiers[t] !== undefined);
    if (nextTier) {
      const lock = document.createElement('div');
      lock.className = 'badge-lock-hint';
      lock.textContent = `${def.tiers[nextTier]} ${def.unit} to unlock`;
      info.appendChild(lock);
    }
  }

  card.appendChild(info);
  return card;
}

/* ─── Share modal ───────────────────────────────────────────────────────────── */

function openShareModal(def, earned) {
  const existing = document.getElementById('badge-share-modal');
  if (existing) existing.remove();

  const tierDef = TIERS[earned.tier];
  const earnedDate = new Date(earned.earnedAt);
  const dateStr = earnedDate.toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' });
  const timeStr = earnedDate.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
  const dayStr = earnedDate.toLocaleDateString(undefined, { weekday: 'long' });

  const overlay = document.createElement('div');
  overlay.id = 'badge-share-modal';
  overlay.className = 'badge-modal-overlay';
  overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });

  overlay.innerHTML = `
    <div class="badge-modal" style="--tier-glow:${tierDef.glow};--tier-glow-rgb:${tierDef.glowRgb};--tier-rim:${tierDef.rimColor};--heart-fill:${tierDef.heartFill};">
      <button class="badge-modal-close" title="Close">✕</button>

      <div class="badge-modal-card" id="badge-shareable-card">
        <div class="badge-modal-bg-glow"></div>

        <div class="badge-modal-tier-label">${tierDef.label} Tier</div>

        <div class="badge-modal-img-wrap">
          <img src="img/badges/${encodeURIComponent(def.file)}" alt="${def.name}" style="filter:${tierDef.filter}">
          <div class="badge-modal-hearts">${heartsSVG(tierDef.hearts, tierDef, 24)}</div>
        </div>

        <div class="badge-modal-name">${def.name}</div>
        <div class="badge-modal-desc">${def.desc}</div>

        <div class="badge-modal-divider"></div>

        <div class="badge-modal-meta">
          <div class="badge-modal-meta-row">
            <span class="badge-modal-meta-icon">📅</span>
            <span class="badge-modal-meta-val">${dayStr}, ${dateStr}</span>
          </div>
          <div class="badge-modal-meta-row">
            <span class="badge-modal-meta-icon">🕐</span>
            <span class="badge-modal-meta-val">${timeStr}</span>
          </div>
          <div class="badge-modal-meta-row">
            <span class="badge-modal-meta-icon">🏆</span>
            <span class="badge-modal-meta-val">${tierDef.label} · ${def.icon} ${def.name}</span>
          </div>
        </div>

        <div class="badge-modal-custom-wrap" id="bmc-wrap">
          <textarea class="badge-modal-custom-input" id="bmc-input" placeholder="Add a personal message…" maxlength="140">${earned.customMessage || ''}</textarea>
          <div class="badge-modal-custom-preview" id="bmc-preview">${earned.customMessage ? `"${earned.customMessage}"` : ''}</div>
        </div>

        <div class="badge-modal-watermark">aioredgif · adults only</div>
      </div>

      <div class="badge-modal-actions">
        <button class="badge-modal-btn secondary" id="bmsg-save">Save message</button>
        <button class="badge-modal-btn primary" id="bmsg-copy">Copy card text</button>
        <button class="badge-modal-btn accent" id="bmsg-dl">Download card</button>
      </div>
    </div>
  `;

  document.body.appendChild(overlay);

  overlay.querySelector('.badge-modal-close').addEventListener('click', () => overlay.remove());

  // Save message
  const input = overlay.querySelector('#bmc-input');
  const preview = overlay.querySelector('#bmc-preview');
  input.addEventListener('input', () => {
    const v = input.value.trim();
    preview.textContent = v ? `"${v}"` : '';
  });

  overlay.querySelector('#bmsg-save').addEventListener('click', () => {
    const msg = input.value.trim();
    const state = loadBadgeState();
    if (state[def.id]) {
      state[def.id].customMessage = msg;
      saveBadgeState(state);
    }
    input.style.borderColor = 'var(--tier-glow)';
    setTimeout(() => { input.style.borderColor = ''; }, 800);
    renderBadgesPanel();
  });

  // Copy text
  overlay.querySelector('#bmsg-copy').addEventListener('click', () => {
    const msg = input.value.trim();
    const text = [
      `🏆 ${tierDef.label} ${def.name} — ${def.icon}`,
      `${def.desc}`,
      `Earned: ${dayStr}, ${dateStr} at ${timeStr}`,
      msg ? `"${msg}"` : '',
      `aioredgif · adults only`,
    ].filter(Boolean).join('\n');

    navigator.clipboard?.writeText(text).catch(() => {});
    const btn = overlay.querySelector('#bmsg-copy');
    const orig = btn.textContent;
    btn.textContent = 'Copied!';
    setTimeout(() => { btn.textContent = orig; }, 1500);
  });

  // Download card as PNG via canvas
  overlay.querySelector('#bmsg-dl').addEventListener('click', async () => {
    await downloadBadgeCard(def, earned, tierDef, dateStr, timeStr, dayStr, input.value.trim());
  });

  // Animate in
  requestAnimationFrame(() => overlay.classList.add('visible'));
}

/* ─── Canvas card renderer ──────────────────────────────────────────────────── */

async function downloadBadgeCard(def, earned, tierDef, dateStr, timeStr, dayStr, customMsg) {
  const W = 600, H = 820;
  const canvas = document.createElement('canvas');
  canvas.width = W; canvas.height = H;
  const ctx = canvas.getContext('2d');

  // Background
  const bg = ctx.createRadialGradient(W / 2, H * 0.4, 50, W / 2, H / 2, W * 0.8);
  bg.addColorStop(0, '#1a0a1e');
  bg.addColorStop(0.5, '#0d050f');
  bg.addColorStop(1, '#050305');
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, W, H);

  // Glow haze
  const haze = ctx.createRadialGradient(W / 2, H * 0.38, 20, W / 2, H * 0.38, 240);
  haze.addColorStop(0, `rgba(${tierDef.glowRgb},0.18)`);
  haze.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = haze;
  ctx.fillRect(0, 0, W, H);

  // Tier label pill
  ctx.save();
  ctx.font = 'bold 15px system-ui, sans-serif';
  ctx.letterSpacing = '3px';
  const tierLabel = tierDef.label.toUpperCase();
  const tw = ctx.measureText(tierLabel).width + 32;
  const tx = (W - tw) / 2;
  roundRect(ctx, tx, 28, tw, 30, 15);
  ctx.fillStyle = `rgba(${tierDef.glowRgb},0.18)`;
  ctx.fill();
  ctx.strokeStyle = tierDef.glow;
  ctx.lineWidth = 1;
  ctx.stroke();
  ctx.fillStyle = tierDef.glow;
  ctx.textAlign = 'center';
  ctx.fillText(tierLabel, W / 2, 48);
  ctx.restore();

  // Badge image
  const imgEl = new Image();
  imgEl.crossOrigin = 'anonymous';
  await new Promise((res) => {
    imgEl.onload = res;
    imgEl.onerror = res;
    imgEl.src = `img/badges/${encodeURIComponent(def.file)}`;
  });

  // Composite the image with tier filter via offscreen canvas
  const offW = 420, offH = 420;
  const off = document.createElement('canvas');
  off.width = offW; off.height = offH;
  const octx = off.getContext('2d');
  octx.filter = tierDef.filter;
  octx.drawImage(imgEl, 0, 0, offW, offH);

  // Glow halo behind badge
  const imgX = (W - offW) / 2, imgY = 65;
  ctx.save();
  ctx.shadowColor = tierDef.glow;
  ctx.shadowBlur = 60;
  ctx.drawImage(off, imgX, imgY, offW, offH);
  ctx.shadowBlur = 0;
  ctx.restore();

  // Hearts row
  const heartY = imgY + offH - 32;
  const totalHearts = 4;
  const hSize = 20;
  const hGap = hSize * 2.6;
  const totalW = hGap * totalHearts;
  const startX = (W - totalW) / 2 + hGap / 2;
  for (let i = 0; i < totalHearts; i++) {
    const hx = startX + i * hGap;
    const hy = heartY;
    const filled = i < tierDef.hearts;
    drawHeart(ctx, hx, hy, hSize, filled, tierDef);
  }

  // Badge name
  ctx.save();
  ctx.font = `bold 32px system-ui, sans-serif`;
  ctx.textAlign = 'center';
  ctx.fillStyle = '#fff';
  ctx.shadowColor = tierDef.glow;
  ctx.shadowBlur = 20;
  ctx.fillText(def.name, W / 2, imgY + offH + 50);
  ctx.restore();

  // Description
  ctx.save();
  ctx.font = '16px system-ui, sans-serif';
  ctx.textAlign = 'center';
  ctx.fillStyle = 'rgba(255,255,255,0.65)';
  ctx.fillText(def.desc, W / 2, imgY + offH + 78);
  ctx.restore();

  // Divider
  ctx.save();
  const dg = ctx.createLinearGradient(80, 0, W - 80, 0);
  dg.addColorStop(0, 'transparent');
  dg.addColorStop(0.3, `rgba(${tierDef.glowRgb},0.6)`);
  dg.addColorStop(0.7, `rgba(${tierDef.glowRgb},0.6)`);
  dg.addColorStop(1, 'transparent');
  ctx.strokeStyle = dg;
  ctx.lineWidth = 1;
  const divY = imgY + offH + 100;
  ctx.beginPath(); ctx.moveTo(80, divY); ctx.lineTo(W - 80, divY); ctx.stroke();
  ctx.restore();

  // Meta info
  const metaY = divY + 32;
  const metaItems = [
    [`📅  ${dayStr}, ${dateStr}`, 18],
    [`🕐  ${timeStr}`, 18],
    [`🏆  ${tierDef.label} · ${def.icon} ${def.name}`, 18],
  ];
  ctx.save();
  ctx.textAlign = 'center';
  for (let i = 0; i < metaItems.length; i++) {
    ctx.font = `${metaItems[i][1]}px system-ui, sans-serif`;
    ctx.fillStyle = i === 0 ? tierDef.heartFill : 'rgba(255,255,255,0.75)';
    ctx.fillText(metaItems[i][0], W / 2, metaY + i * 32);
  }
  ctx.restore();

  // Custom message
  if (customMsg) {
    ctx.save();
    ctx.font = 'italic 16px serif';
    ctx.fillStyle = `rgba(${tierDef.glowRgb},0.9)`;
    ctx.textAlign = 'center';
    const msgY = metaY + metaItems.length * 32 + 20;
    wrapText(ctx, `"${customMsg}"`, W / 2, msgY, W - 100, 24);
    ctx.restore();
  }

  // Watermark
  ctx.save();
  ctx.font = '12px system-ui, sans-serif';
  ctx.fillStyle = 'rgba(255,255,255,0.25)';
  ctx.textAlign = 'center';
  ctx.fillText('aioredgif · adults only', W / 2, H - 20);
  ctx.restore();

  // Download
  canvas.toBlob((blob) => {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `aioredgif-${def.id}-${earned.tier}.png`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  }, 'image/png');
}

/* helper: heart path on canvas */
function drawHeart(ctx, cx, cy, r, filled, tierDef) {
  ctx.save();
  ctx.translate(cx, cy);
  ctx.scale(r / 11, r / 11);
  ctx.beginPath();
  ctx.moveTo(0, -6);
  ctx.bezierCurveTo(-3.5, -11, -11, -11, -11, -5);
  ctx.bezierCurveTo(-11, 0, -6, 5, 0, 11);
  ctx.bezierCurveTo(6, 5, 11, 0, 11, -5);
  ctx.bezierCurveTo(11, -11, 3.5, -11, 0, -6);
  ctx.closePath();
  if (filled) {
    ctx.fillStyle = tierDef.heartFill;
    ctx.shadowColor = tierDef.heartGlow;
    ctx.shadowBlur = 12;
    ctx.fill();
  }
  ctx.strokeStyle = filled ? tierDef.heartGlow : 'rgba(255,255,255,0.3)';
  ctx.lineWidth = filled ? 1.5 : 1;
  ctx.stroke();
  ctx.restore();
}

/* helper: rounded rect */
function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.arcTo(x + w, y, x + w, y + r, r);
  ctx.lineTo(x + w, y + h - r);
  ctx.arcTo(x + w, y + h, x + w - r, y + h, r);
  ctx.lineTo(x + r, y + h);
  ctx.arcTo(x, y + h, x, y + h - r, r);
  ctx.lineTo(x, y + r);
  ctx.arcTo(x, y, x + r, y, r);
  ctx.closePath();
}

/* helper: word-wrapped text */
function wrapText(ctx, text, x, y, maxWidth, lineH) {
  const words = text.split(' ');
  let line = '';
  let cy = y;
  for (const w of words) {
    const test = line + (line ? ' ' : '') + w;
    if (ctx.measureText(test).width > maxWidth && line) {
      ctx.fillText(line, x, cy);
      line = w;
      cy += lineH;
    } else {
      line = test;
    }
  }
  if (line) ctx.fillText(line, x, cy);
}

/* ─── Panel renderer ────────────────────────────────────────────────────────── */

function renderBadgesPanel() {
  const container = document.getElementById('badges-grid');
  if (!container) return;

  container.innerHTML = '';
  const state = loadBadgeState();

  // Filter controls
  const activeFilter = container.dataset.filter || 'all';

  for (const def of BADGE_DEFS) {
    const earned = state[def.id] || null;
    if (activeFilter === 'earned' && !earned) continue;
    if (activeFilter === 'locked' && earned) continue;

    const card = buildBadgeCard(def, earned);
    card.addEventListener('click', () => {
      if (earned) openShareModal(def, earned);
    });
    container.appendChild(card);
  }
}

/* ─── Filter bar ────────────────────────────────────────────────────────────── */

function initBadgeFilters() {
  const bar = document.getElementById('badge-filter-bar');
  if (!bar) return;

  const grid = document.getElementById('badges-grid');

  bar.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-filter]');
    if (!btn) return;
    bar.querySelectorAll('[data-filter]').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    grid.dataset.filter = btn.dataset.filter;
    renderBadgesPanel();
  });
}

/* ─── Earned toast notification ────────────────────────────────────────────── */

function showEarnedToast(def, tier) {
  const tierDef = TIERS[tier];
  const toast = document.createElement('div');
  toast.className = `badge-toast tier-${tier}`;
  toast.style.setProperty('--tier-glow', tierDef.glow);
  toast.style.setProperty('--tier-glow-rgb', tierDef.glowRgb);
  toast.innerHTML = `
    <div class="badge-toast-img">
      <img src="img/badges/${encodeURIComponent(def.file)}" alt="${def.name}" style="filter:${tierDef.filter}">
    </div>
    <div class="badge-toast-body">
      <div class="badge-toast-label">${tierDef.label} Unlocked</div>
      <div class="badge-toast-name">${def.icon} ${def.name}</div>
      <div class="badge-toast-desc">${def.desc}</div>
    </div>
  `;

  document.body.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add('visible'));
  setTimeout(() => {
    toast.classList.remove('visible');
    setTimeout(() => toast.remove(), 600);
  }, 4000);

  toast.addEventListener('click', () => {
    const state = loadBadgeState();
    openShareModal(def, state[def.id]);
  });
}

/* ─── Public API ─────────────────────────────────────────────────────────────── */

window.BadgeSystem = {
  TIERS,
  BADGE_DEFS,
  awardBadge,
  checkAndAward,
  showEarnedToast,
  renderBadgesPanel,
  initBadgeFilters,
  openShareModal,
  loadBadgeState,

  /** Call this once on page load. */
  init() {
    renderBadgesPanel();
    initBadgeFilters();
  },

  /** Convenience: award then show toast if newly earned. */
  grantAndNotify(badgeId, tier, customMessage = '') {
    const newly = awardBadge(badgeId, tier, customMessage);
    if (newly) {
      const def = BADGE_DEFS.find(d => d.id === badgeId);
      if (def) showEarnedToast(def, tier);
      renderBadgesPanel();
    }
    return !!newly;
  },
};
