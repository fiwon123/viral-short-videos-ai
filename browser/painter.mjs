import {gsap} from "gsap";
import {easing, poseAt, poseTrack} from "./pose.mjs";
import {createThreeStage} from "./three.mjs";

const IDENTITY = [1, 0, 0, 1, 0, 0];

function multiply(first, second) {
  const [a, b, c, d, e, f] = first;
  const [g, h, i, j, k, l] = second;
  return [
    a * g + c * h, b * g + d * h,
    a * i + c * j, b * i + d * j,
    a * k + c * l + e, b * k + d * l + f,
  ];
}

const translate = (x, y) => [1, 0, 0, 1, x, y];
const scale = (x, y = x) => [x, 0, 0, y, 0, 0];
const rotate = (radians) => [Math.cos(radians), Math.sin(radians), -Math.sin(radians), Math.cos(radians), 0, 0];

function layerMatrix(pose, width, height, pivot, {parent = null, parentOrigin = null, camera = null, parallax = 1, mouth = 1, box = null} = {}) {
  const boxWidth = box?.[0] ?? width;
  const boxHeight = box?.[1] ?? height;
  const px = (pivot?.[0] ?? 0.5) * boxWidth;
  const py = (pivot?.[1] ?? 0.5) * boxHeight;
  const translation = parentOrigin
    ? translate(parentOrigin[0] + pose.x * width, parentOrigin[1] + pose.y * height)
    : translate(pose.x * width, pose.y * height);
  let local = multiply(
    translation,
    multiply(
      rotate(-(pose.rotate ?? 0) * Math.PI / 180),
      multiply(scale(pose.scale ?? 1, (pose.scale ?? 1) * mouth), translate(-px, -py)),
    ),
  );
  if (parent) local = multiply(parent, local);
  if (camera && parallax) {
    const amount = Math.max(0, Math.min(2, parallax));
    const tuned = {
      x: (camera.x ?? 0) * amount,
      y: (camera.y ?? 0) * amount,
      zoom: 1 + ((camera.zoom ?? 1) - 1) * amount,
      rotate: (camera.rotate ?? 0) * amount,
    };
    local = multiply(cameraMatrix(tuned, width, height), local);
  }
  return local;
}

function cameraMatrix(camera, width, height) {
  return multiply(translate((camera.x ?? 0) * width, (camera.y ?? 0) * height),
    multiply(translate(width / 2, height / 2),
      multiply(rotate(-(camera.rotate ?? 0) * Math.PI / 180),
        multiply(scale(camera.zoom ?? 1), translate(-width / 2, -height / 2)))));
}

function findFrame(items, frame) {
  let left = 0;
  let right = items.length;
  while (left < right) {
    const mid = (left + right) >>> 1;
    if (items[mid].end <= frame) left = mid + 1;
    else right = mid;
  }
  return left;
}

async function image(url) {
  const element = new Image();
  element.src = url;
  try {
    await element.decode();
  } catch (error) {
    throw new Error(`Could not decode visual asset ${url}`, {cause: error});
  }
  return element;
}

const BLEND = {
  normal: "source-over", add: "lighter", screen: "screen",
  multiply: "multiply", overlay: "overlay", "soft-light": "soft-light",
};

function roundRect(ctx, x, y, width, height, radius) {
  if (ctx.roundRect) {
    ctx.beginPath();
    ctx.roundRect(x, y, width, height, radius);
  } else {
    ctx.beginPath();
    ctx.rect(x, y, width, height);
  }
}

function noiseTile(size = 192, seed = 17) {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext("2d");
  const pixels = ctx.createImageData(size, size);
  let state = seed || 1;
  for (let i = 0; i < pixels.data.length; i += 4) {
    state = (state * 1664525 + 1013904223) >>> 0;
    const value = (state >>> 24) & 0xff;
    pixels.data[i] = pixels.data[i + 1] = pixels.data[i + 2] = value;
    pixels.data[i + 3] = 255;
  }
  ctx.putImageData(pixels, 0, 0);
  return canvas;
}

export async function createPainter(canvas, data, urlFor) {
  const {width, height, captions, shots, scenes, cover} = data;
  const names = new Set([
    ...shots.flatMap(({layers}) => layers.map((layer) => layer.sprite)),
    ...captions.flatMap((cue) => cue.karaoke
      ? [cue.background.sprite, ...cue.words.flatMap((word) => [word.normal.sprite, word.active.sprite])]
      : [cue.sprite]),
  ]);
  const images = new Map(await Promise.all([...names].map(async (name) => [name, await image(urlFor(name))])));
  const vectorTimelines = [];
  const planes = shots.map(({layers}) => {
    const background = [];
    const foreground = [];
    for (const layer of layers) {
      const tile = images.get(layer.sprite);
      const fit = layer.box ? Math.min(layer.box[0] / tile.naturalWidth, layer.box[1] / tile.naturalHeight) : 1;
      const prepared = {
        ...layer, tile, width: tile.naturalWidth * fit, height: tile.naturalHeight * fit,
        getPose: (progress) => poseAt(layer.poses, progress),
      };
      if (layer.box && layer.poses.length > 1) {
        const state = {...layer.poses[0][1]};
        const timeline = gsap.timeline({paused: true});
        for (let i = 1; i < layer.poses.length; i++) {
          const [start] = layer.poses[i - 1];
          const [end, pose, mode] = layer.poses[i];
          timeline.to(state, {...pose, duration: end - start, ease: (t) => easing(t, mode), lazy: false}, start);
        }
        prepared.getPose = (progress) => {
          timeline.seek(progress, true);
          return state;
        };
        vectorTimelines.push(timeline);
      }
      (layer.plane === "background" ? background : foreground).push(prepared);
    }
    return {background, foreground};
  });
  const stages = shots.map((shot) => {
    if (!shot.three) return null;
    const scene = scenes[shot.three.scene];
    const camera = shot.camera ? poseTrack({x: 0, y: 0, zoom: 1, rotate: 0}, shot.camera.keyframes) : null;
    return {camera};
  });
  const stage = Object.keys(scenes).length ? await createThreeStage(scenes, width, height, urlFor) : null;
  const three = shots.map((shot) => shot.three ? stage.compile({...shot.three, duration: shot.duration}) : null);
  const ctx = canvas.getContext("2d");
  const incoming = document.createElement("canvas");
  incoming.width = width;
  incoming.height = height;
  const overlay = incoming.getContext("2d");
  const motion = document.createElement("canvas");
  motion.width = width;
  motion.height = height;
  const motionCtx = motion.getContext("2d");
  const fx = document.createElement("canvas");
  fx.width = width;
  fx.height = height;
  const fxCtx = fx.getContext("2d");
  const grain = noiseTile(192, 29);
  const hiddenOnCover = new Set(cover.hide);
  for (const {layers} of shots) {
    for (const layer of layers) {
      if (layer.parent && hiddenOnCover.has(layer.parent)) hiddenOnCover.add(layer.id);
    }
  }
  const palette = data.palette ?? {};

  function paintLayers(target, layers, progress, offset, speech, isCover, camera) {
    const matrices = new Map();
    const alphas = new Map();
    const origins = new Map();
    for (const layer of layers) {
      if (isCover && hiddenOnCover.has(layer.id)) continue;
      const pose = layer.getPose(progress);
      const parentMatrix = layer.parent ? matrices.get(layer.parent) : null;
      const parentAlpha = layer.parent ? (alphas.get(layer.parent) ?? 1) : 1;
      const alpha = (pose.opacity ?? 1) * parentAlpha;
      let mouth = 1;
      if (layer.mouth) {
        const level = speech?.[2] === layer.mouth ? speech[3][offset - speech[0]] : 0;
        mouth = 0.18 + 0.82 * level;
      }
      const matrix = layerMatrix(pose, width, height, layer.pivot,
        {parent: parentMatrix, parentOrigin: layer.parent ? origins.get(layer.parent) : null,
         camera, parallax: layer.parallax, mouth, box: [layer.width, layer.height]});
      matrices.set(layer.id, matrix);
      alphas.set(layer.id, alpha);
      origins.set(layer.id, [(layer.pivot?.[0] ?? 0.5) * layer.width,
        (layer.pivot?.[1] ?? 0.5) * layer.height * mouth]);
      if (alpha <= 0) continue;
      target.save();
      target.setTransform(...matrix);
      target.globalAlpha = alpha;
      target.globalCompositeOperation = BLEND[layer.blend] ?? "source-over";
      target.filter = layer.blur ? `blur(${Math.max(0.4, Math.min(width, height) * layer.blur * 0.02)}px)` : "none";
      target.drawImage(layer.tile, 0, 0, layer.width, layer.height);
      target.restore();
    }
  }

  function applyPost(target, post, frame) {
    if (!post || !Object.keys(post).length) return;
    const ctx2 = target.getContext("2d");
    const filters = [];
    if (post.brightness !== undefined) filters.push(`brightness(${post.brightness})`);
    if (post.contrast !== undefined) filters.push(`contrast(${post.contrast})`);
    if (post.saturation !== undefined) filters.push(`saturate(${post.saturation})`);
    if (post.hue) filters.push(`hue-rotate(${post.hue}deg)`);
    if (filters.length) {
      fxCtx.setTransform(1, 0, 0, 1, 0, 0);
      fxCtx.clearRect(0, 0, width, height);
      fxCtx.filter = filters.join(" ");
      fxCtx.drawImage(target, 0, 0);
      fxCtx.filter = "none";
      ctx2.setTransform(1, 0, 0, 1, 0, 0);
      ctx2.clearRect(0, 0, width, height);
      ctx2.drawImage(fx, 0, 0);
    }
    if (post.bloom) {
      fxCtx.setTransform(1, 0, 0, 1, 0, 0);
      fxCtx.clearRect(0, 0, width, height);
      fxCtx.filter = `blur(${Math.max(2, Math.round(Math.min(width, height) * 0.035 * post.bloom))}px)`;
      fxCtx.drawImage(target, 0, 0);
      fxCtx.filter = "none";
      ctx2.save();
      ctx2.globalCompositeOperation = "screen";
      ctx2.globalAlpha = Math.min(0.85, post.bloom);
      ctx2.drawImage(fx, 0, 0);
      ctx2.restore();
    }
    if (post.chromatic) {
      fxCtx.setTransform(1, 0, 0, 1, 0, 0);
      fxCtx.clearRect(0, 0, width, height);
      fxCtx.drawImage(target, 0, 0);
      const shift = Math.max(1, Math.round(Math.min(width, height) * 0.006 * post.chromatic));
      ctx2.save();
      ctx2.globalCompositeOperation = "screen";
      ctx2.globalAlpha = 0.18;
      ctx2.drawImage(fx, shift, 0);
      ctx2.drawImage(fx, -shift, 0);
      ctx2.restore();
    }
    if (post.blur) {
      fxCtx.setTransform(1, 0, 0, 1, 0, 0);
      fxCtx.clearRect(0, 0, width, height);
      fxCtx.filter = `blur(${Math.max(0.5, Math.min(width, height) * 0.012 * post.blur)}px)`;
      fxCtx.drawImage(target, 0, 0);
      fxCtx.filter = "none";
      ctx2.setTransform(1, 0, 0, 1, 0, 0);
      ctx2.clearRect(0, 0, width, height);
      ctx2.drawImage(fx, 0, 0);
    }
    if (post.grain) {
      const pattern = ctx2.createPattern(grain, "repeat");
      ctx2.save();
      ctx2.globalCompositeOperation = "overlay";
      ctx2.globalAlpha = Math.min(0.5, post.grain * 0.45);
      ctx2.fillStyle = pattern;
      ctx2.fillRect(0, 0, width, height);
      ctx2.restore();
    }
    if (post.vignette) {
      const gradient = ctx2.createRadialGradient(width / 2, height / 2, Math.min(width, height) * 0.2,
        width / 2, height / 2, Math.hypot(width, height) / 2);
      gradient.addColorStop(0, "rgba(0,0,0,0)");
      gradient.addColorStop(1, `rgba(0,0,0,${Math.min(0.9, post.vignette)})`);
      ctx2.fillStyle = gradient;
      ctx2.fillRect(0, 0, width, height);
    }
    if (post.letterbox) {
      const bar = Math.round(height * post.letterbox / 2);
      ctx2.fillStyle = "#000";
      ctx2.fillRect(0, 0, width, bar);
      ctx2.fillRect(0, height - bar, width, bar);
    }
  }

  function paintShot(target, index, frame, isCover) {
    const shot = shots[index];
    const offset = frame - shot.start;
    const progress = offset / Math.max(1, shot.end - shot.start - 1);
    const speech = isCover ? null : shot.speech.find(([start, end]) => start <= offset && offset < end);
    const camera = shot.camera ? poseAt(poseTrack({
      x: shot.camera.x ?? 0, y: shot.camera.y ?? 0,
      zoom: shot.camera.zoom ?? 1, rotate: shot.camera.rotate ?? 0,
    }, shot.camera.keyframes ?? []), progress) : null;
    target.fillStyle = shot.background;
    target.fillRect(0, 0, width, height);
    paintLayers(target, planes[index].background, progress, offset, speech, isCover, camera);
    if (three[index]) target.drawImage(three[index](progress), 0, 0);
    paintLayers(target, planes[index].foreground, progress, offset, speech, isCover, camera);
    applyPost(target.canvas, shot.post, frame);
  }

  function drawCaption(frame) {
    const caption = captions[findFrame(captions, frame)];
    if (!caption || caption.start > frame) return;
    if (caption.karaoke) {
      const background = images.get(caption.background.sprite);
      ctx.drawImage(background, caption.background.x, caption.background.y);
      for (const word of caption.words) {
        if (frame >= word.start && frame < word.end) {
          ctx.save();
          ctx.fillStyle = palette.accent ?? "#FFBD54";
          const [x0, y0, x1, y1] = word.box;
          roundRect(ctx, x0 - 3, y0 - 2, (x1 - x0) + 6, (y1 - y0) + 6, 5);
          ctx.fill();
          ctx.restore();
          const active = images.get(word.active.sprite);
          ctx.drawImage(active, word.active.x, word.active.y);
        } else {
          const normal = images.get(word.normal.sprite);
          ctx.drawImage(normal, word.normal.x, word.normal.y);
        }
      }
    } else {
      const sprite = images.get(caption.sprite);
      ctx.drawImage(sprite, caption.x, caption.y);
    }
  }

  function transition(t, type) {
    if (type === "dissolve") {
      ctx.globalAlpha = easing(t, "smooth");
      ctx.drawImage(incoming, 0, 0);
      return;
    }
    if (type === "flash" || type === "dip-to-black") {
      if (t < 0.5) {
        ctx.fillStyle = type === "flash" ? "#fff" : "#000";
        ctx.globalAlpha = t * 2;
        ctx.fillRect(0, 0, width, height);
      } else {
        ctx.drawImage(incoming, 0, 0);
        ctx.fillStyle = type === "flash" ? "#fff" : "#000";
        ctx.globalAlpha = (1 - t) * 2;
        ctx.fillRect(0, 0, width, height);
      }
      return;
    }
    ctx.save();
    if (type === "wipe-left" || type === "luma-wipe") {
      ctx.beginPath();
      ctx.rect(0, 0, Math.floor(width * t), height);
      ctx.clip();
    } else if (type === "wipe-right") {
      ctx.beginPath();
      ctx.rect(width - Math.floor(width * t), 0, Math.floor(width * t), height);
      ctx.clip();
    } else if (type === "wipe-up") {
      ctx.beginPath();
      ctx.rect(0, 0, width, Math.floor(height * t));
      ctx.clip();
    } else if (type === "wipe-down") {
      ctx.beginPath();
      ctx.rect(0, height - Math.floor(height * t), width, Math.floor(height * t));
      ctx.clip();
    } else if (type.startsWith("slide") || type.startsWith("whip")) {
      const direction = type.endsWith("left") ? -1 : type.endsWith("right") ? 1 : 0;
      if (direction) ctx.translate((1 - t) * width * direction, 0);
      else ctx.translate(0, (1 - t) * height * (type.endsWith("up") ? 1 : -1));
    } else if (type === "zoom-in") {
      ctx.translate(width / 2, height / 2);
      ctx.scale(0.84 + 0.16 * t, 0.84 + 0.16 * t);
      ctx.translate(-width / 2, -height / 2);
    } else if (type === "zoom-out") {
      ctx.translate(width / 2, height / 2);
      ctx.scale(1 + 0.2 * (1 - t), 1 + 0.2 * (1 - t));
      ctx.translate(-width / 2, -height / 2);
    } else if (type === "iris") {
      ctx.beginPath();
      ctx.arc(width / 2, height / 2, Math.hypot(width, height) / 2 * t, 0, Math.PI * 2);
      ctx.clip();
    }
    if (type.startsWith("whip")) ctx.filter = `blur(${Math.round(10 * (1 - t))}px)`;
    ctx.drawImage(incoming, 0, 0);
    ctx.restore();
  }

  return {
    draw(frame, isCover = false) {
      const index = findFrame(shots, frame);
      const shot = shots[index];
      const edge = shot.transition;
      if (!isCover && edge && frame < edge.end) {
        paintShot(ctx, index - 1, shots[index - 1].end - 1, false);
        paintShot(overlay, index, frame, false);
        const t = (frame - edge.start + 1) / (edge.end - edge.start);
        ctx.save();
        ctx.globalAlpha = 1;
        transition(t, edge.type);
        ctx.restore();
      } else {
        paintShot(ctx, index, frame, isCover);
      }
      if (!isCover && shot.motion_blur > 0 && frame > shot.start) {
        paintShot(motionCtx, index, frame - 1, false);
        ctx.save();
        ctx.globalAlpha = Math.min(0.38, shot.motion_blur * 0.38);
        ctx.drawImage(motion, 0, 0);
        ctx.restore();
      }
      ctx.globalAlpha = 1;
      ctx.globalCompositeOperation = "source-over";
      ctx.filter = "none";
      if (!isCover) drawCaption(frame);
    },
    dispose() {
      for (const timeline of vectorTimelines) timeline.kill();
      stage?.dispose();
    },
  };
}
