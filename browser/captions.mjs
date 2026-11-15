// Per-word kinetic caption motion. Mirrors studio/captions.py word_state.

function easeBack(t) {
  const c1 = 1.70158;
  return 1 + (c1 + 1) * (t - 1) ** 3 + c1 * (t - 1) ** 2;
}

function easeOut(t) {
  return 1 - (1 - t) ** 3;
}

function easeBounce(t) {
  const n = 7.5625, d = 2.75;
  if (t < 1 / d) return n * t * t;
  if (t < 2 / d) { t -= 1.5 / d; return n * t * t + 0.75; }
  if (t < 2.5 / d) { t -= 2.25 / d; return n * t * t + 0.9375; }
  t -= 2.625 / d;
  return n * t * t + 0.984375;
}

export function wordState(word, index, page, frame, fps, size, config) {
  const appear = config.reveal === "page" ? page.start : word.start;
  if (frame < appear) return null;
  const t = Math.min(1, Math.max(0, (frame - appear) / Math.max(1, 0.13 * fps)));
  let scale = 1, dx = 0, dy = 0, rotate = 0, alpha = 1;
  const mode = config.word_in;
  if (mode === "pop") {
    scale = 0.55 + 0.45 * easeBack(t);
    alpha = Math.min(1, t * 3);
  } else if (mode === "bounce") {
    scale = 0.3 + 0.7 * easeBounce(t);
    alpha = Math.min(1, t * 4);
  } else if (mode === "slide") {
    dy = (1 - easeOut(t)) * size * 0.45;
    alpha = t;
  } else if (mode === "fade") {
    alpha = easeOut(t);
  }
  const active = word.start <= frame && frame < word.end;
  const emphasis = Boolean(word.emphasis);
  if (active && config.active.includes("scale")) {
    const rise = Math.min(1, (frame - word.start) / Math.max(1, 0.06 * fps));
    scale *= 1 + (config.active_scale - 1) * easeOut(rise);
  }
  if (emphasis) {
    scale *= config.emphasis_scale;
    const since = (frame - word.start) / fps;
    if (since >= 0 && since < 0.35) {
      const decay = 1 - since / 0.35;
      rotate = Math.sin(since * 55) * 5 * decay;
      dx = Math.sin(since * 70 + 1.3) * size * 0.04 * decay;
    }
  }
  if (config.wave) {
    dy += Math.sin(frame / fps * 2 * Math.PI * 1.1 + index * 0.9) * size * 0.05 * config.wave;
  }
  const tinted = config.active.includes("color") || config.active.includes("pill");
  const state = emphasis ? "emphasis" : (active && tinted ? "active" : "normal");
  return {scale, dx, dy, rotate, alpha, state};
}

export function drawKinetic(ctx, caption, frame, fps, images) {
  const page = caption.pages.find((item) => item.start <= frame && frame < item.end);
  if (!page) return;
  page.words.forEach((word, index) => {
    const state = wordState(word, index, page, frame, fps, page.size, caption.config);
    if (!state || state.alpha <= 0.01) return;
    const sprite = word.sprites[state.state] ?? word.sprites.normal;
    const tile = images.get(sprite.sprite);
    ctx.save();
    ctx.globalAlpha *= state.alpha;
    ctx.translate(word.cx + state.dx, word.cy + state.dy);
    if (state.rotate) ctx.rotate(state.rotate * Math.PI / 180);
    ctx.scale(state.scale, state.scale);
    ctx.drawImage(tile, -tile.naturalWidth / 2, -tile.naturalHeight / 2);
    ctx.restore();
  });
}
