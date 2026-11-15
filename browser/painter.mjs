import {easing, poseAt, poseTrack} from "./pose.mjs";
import {createThreeStage} from "./three.mjs";
import {drawKinetic} from "./captions.mjs";

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
const skew = (xDegrees, yDegrees) => [1, Math.tan(yDegrees * Math.PI / 180),
  Math.tan(xDegrees * Math.PI / 180), 1, 0, 0];

function apply(m, x, y) {
  return [m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]];
}

function inverse(m) {
  const [a, b, c, d, e, f] = m;
  const determinant = a * d - b * c;
  return [d / determinant, -b / determinant, -c / determinant, a / determinant,
    (c * f - d * e) / determinant, (b * e - a * f) / determinant];
}

function layerMatrix(pose, width, height, pivot, {parent = null, parentOrigin = null, camera = null, parallax = 1, mouth = 1, box = null} = {}) {
  const boxWidth = box?.[0] ?? width;
  const boxHeight = box?.[1] ?? height;
  const px = (pivot?.[0] ?? 0.5) * boxWidth;
  const py = (pivot?.[1] ?? 0.5) * boxHeight;
  const translation = parentOrigin
    ? translate(parentOrigin[0] + pose.x * width, parentOrigin[1] + pose.y * height)
    : translate(pose.x * width, pose.y * height);
  const uniform = pose.scale ?? 1;
  let local = multiply(
    translation,
    multiply(
      rotate(-(pose.rotate ?? 0) * Math.PI / 180),
      multiply(
        skew(pose.skew_x ?? 0, pose.skew_y ?? 0),
        multiply(scale(pose.scale_x ?? uniform, (pose.scale_y ?? uniform) * mouth),
          translate(-px, -py)),
      ),
    ),
  );
  // Children inherit depth and camera through the parent's world matrix.
  if (parent) return multiply(parent, local);
  const depth = depthScale(pose.z ?? 0, camera);
  if (depth !== 1) {
    local = multiply(translate(width / 2, height / 2),
      multiply(scale(depth), multiply(translate(-width / 2, -height / 2), local)));
  }
  if (camera && parallax) {
    const amount = Math.max(0, Math.min(2, parallax));
    const tuned = {
      x: (camera.x ?? 0) * amount * depthPan(pose.z ?? 0, camera),
      y: (camera.y ?? 0) * amount * depthPan(pose.z ?? 0, camera),
      zoom: 1 + ((camera.zoom ?? 1) - 1) * amount,
      rotate: (camera.rotate ?? 0) * amount,
    };
    local = multiply(cameraMatrix(tuned, width, height), local);
  }
  return local;
}

// Draw-on reveal in the layer's local box. Mirrors studio/design.py wipe_region.
function wipeClip(target, layer, pose) {
  const amount = Math.max(0, Math.min(1, pose.wipe ?? 1));
  if (amount >= 1) return;
  const w = layer.width, h = layer.height;
  const from = layer.wipe_from ?? "left";
  let box = [0, 0, w * amount, h];
  if (from === "right") box = [w * (1 - amount), 0, w * amount, h];
  else if (from === "top") box = [0, 0, w, h * amount];
  else if (from === "bottom") box = [0, h * (1 - amount), w, h * amount];
  else if (from === "center") box = [w * (1 - amount) / 2, 0, w * amount, h];
  target.beginPath();
  target.rect(...box);
  target.clip();
}

// Mirrors studio/transform.py focal/depth_scale/depth_fade and design.depth_blur.
function focal(camera) {
  const fov = Math.max(10, Math.min(110, camera?.fov ?? 50));
  return 1 / (2 * Math.tan((fov * Math.PI / 180) / 2));
}

function depthScale(z, camera) {
  const cz = camera?.z ?? 0;
  if (!cz) return 1;
  const f = focal(camera);
  return Math.max(0.05, f + z) / Math.max(0.05, f + z - cz);
}

function depthPan(z, camera) {
  if (!z) return 1;
  const f = focal(camera);
  return f / Math.max(0.05, f + z);
}

function depthFade(z, camera) {
  const distance = focal(camera) + (z ?? 0) - (camera?.z ?? 0);
  return Math.max(0, Math.min(1, (distance - 0.08) / 0.25));
}

function depthBlur(z, camera, focus) {
  if (!focus) return 0;
  const distance = Math.abs((z ?? 0) - (focus.z ?? 0));
  return (focus.amount ?? 0.5) * Math.max(0, Math.min(1, (distance - (focus.range ?? 0.2)) / 1));
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
    ...shots.flatMap(({layers, transition}) => [
      ...layers.flatMap((layer) => [layer.sprite, ...(layer.frames ?? []),
        layer.mask?.sprite].filter(Boolean)),
      ...(transition?.mask_sprite ? [transition.mask_sprite] : []),
    ]),
    ...captions.flatMap((cue) => cue.kinetic
      ? cue.pages.flatMap((page) => page.words.flatMap((word) => Object.values(word.sprites).map((item) => item.sprite)))
      : cue.karaoke
        ? [cue.background.sprite, ...cue.words.flatMap((word) => [word.normal.sprite, word.active.sprite])]
        : [cue.sprite]),
  ]);
  const images = new Map(await Promise.all([...names].map(async (name) => [name, await image(urlFor(name))])));
  const planes = shots.map(({layers}) => {
    const background = [];
    const foreground = [];
    for (const layer of layers) {
      const tile = images.get(layer.sprite);
      const fit = layer.box ? Math.min(layer.box[0] / tile.naturalWidth, layer.box[1] / tile.naturalHeight) : 1;
      const prepared = {
        ...layer, tile, frames: layer.frames?.map((name) => images.get(name)),
        width: tile.naturalWidth * fit, height: tile.naturalHeight * fit,
        getPose: (progress) => poseAt(layer.poses, progress),
      };
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
  const maskCanvas = document.createElement("canvas");
  const maskCtx = maskCanvas.getContext("2d");
  const layerMaskCanvas = document.createElement("canvas");
  layerMaskCanvas.width = width;
  layerMaskCanvas.height = height;
  const layerMaskCtx = layerMaskCanvas.getContext("2d");
  const grain = noiseTile(192, 29);
  const paperBlotch = noiseTile(48, 11);
  const paperFibre = noiseTile(256, 5);
  const tintCanvases = new Map();

  function tintTile(layer, tile, color, opacity) {
    let canvas = tintCanvases.get(layer.id);
    if (!canvas) {
      canvas = document.createElement("canvas");
      tintCanvases.set(layer.id, canvas);
    }
    if (canvas.width !== tile.width || canvas.height !== tile.height) {
      canvas.width = tile.width;
      canvas.height = tile.height;
    }
    const tint = canvas.getContext("2d");
    tint.setTransform(1, 0, 0, 1, 0, 0);
    tint.globalAlpha = 1;
    tint.globalCompositeOperation = "source-over";
    tint.clearRect(0, 0, canvas.width, canvas.height);
    tint.drawImage(tile, 0, 0);
    tint.globalCompositeOperation = "multiply";
    tint.globalAlpha = opacity;
    tint.fillStyle = color;
    tint.fillRect(0, 0, canvas.width, canvas.height);
    tint.globalAlpha = 1;
    tint.globalCompositeOperation = "destination-in";
    tint.drawImage(tile, 0, 0);
    tint.globalCompositeOperation = "source-over";
    return canvas;
  }

  function lumaMask(progress, softness, invert, seed) {
    const scale = 4;
    const mw = Math.max(4, Math.ceil(width / scale));
    const mh = Math.max(4, Math.ceil(height / scale));
    if (maskCanvas.width !== mw || maskCanvas.height !== mh) {
      maskCanvas.width = mw;
      maskCanvas.height = mh;
    }
    const image = maskCtx.createImageData(mw, mh);
    const threshold = -0.8 + progress * 2.2;
    const feather = Math.max(0.015, softness);
    for (let y = 0; y < mh; y++) {
      const ny = y / Math.max(1, mh - 1);
      for (let x = 0; x < mw; x++) {
        const nx = x / Math.max(1, mw - 1);
        const noise = 0.5 + 0.5 * Math.sin(nx * 17.3 + ny * 9.7 + seed)
          * Math.sin(nx * 5.1 - ny * 13.9 + seed * 0.7);
        const ramp = nx * 0.55 + (1 - ny) * 0.25 + noise * 0.20;
        let alpha = Math.max(0, Math.min(1, (ramp - threshold) / feather + 0.5));
        if (invert) alpha = 1 - alpha;
        const offset = (y * mw + x) * 4;
        image.data[offset] = image.data[offset + 1] = image.data[offset + 2] = 255;
        image.data[offset + 3] = Math.round(alpha * 255);
      }
    }
    maskCtx.putImageData(image, 0, 0);
    return maskCanvas;
  }
  const hiddenOnCover = new Set(cover.hide);
  for (const {layers} of shots) {
    for (const layer of layers) {
      if (layer.parent && hiddenOnCover.has(layer.parent)) hiddenOnCover.add(layer.id);
    }
  }
  const palette = data.palette ?? {};
  const paintColor = (value, fallback) => {
    if (!value) return palette[fallback] ?? fallback;
    return palette[value] ?? value;
  };

  function maskSpecsFor(layer, byId) {
    const specs = [];
    const seen = new Set();
    let current = layer;
    while (current) {
      if (seen.has(current.id)) throw new Error(`Mask cycle at ${current.id}`);
      seen.add(current.id);
      if (current.mask) specs.push(current.mask);
      current = current.parent ? byId.get(current.parent) : null;
    }
    return specs;
  }

  function preLayerMatrix(layer, progress, camera, byId, origins) {
    const state = layer.getPose(progress);
    const parent = layer.parent ? byId.get(layer.parent) : null;
    const parentMatrix = parent ? preLayerMatrix(parent, progress, camera, byId, origins) : null;
    const matrix = layerMatrix(state, width, height, layer.pivot, {
      parent: parentMatrix, parentOrigin: layer.parent ? origins.get(layer.parent) : null,
      camera, box: [layer.width, layer.height],
    });
    origins.set(layer.id, [(layer.pivot?.[0] ?? 0.5) * layer.width,
      (layer.pivot?.[1] ?? 0.5) * layer.height]);
    return matrix;
  }

  function maskBuffer(spec, progress, camera, byId, origins) {
    maskCanvas.width = width;
    maskCanvas.height = height;
    maskCtx.setTransform(1, 0, 0, 1, 0, 0);
    maskCtx.clearRect(0, 0, width, height);
    maskCtx.globalCompositeOperation = "source-over";
    const feather = Number(spec.feather ?? 0);
    maskCtx.filter = feather ? `blur(${Math.max(0.5, Math.min(width, height) * feather * 0.08)}px)` : "none";
    const source = String(spec.source ?? "");
    if (source.startsWith("layer:")) {
      const layer = byId.get(source.split(":", 2)[1]);
      if (!layer) throw new Error(`Mask references unknown layer: ${source}`);
      const matrix = preLayerMatrix(layer, progress, camera, byId, origins);
      maskCtx.setTransform(...matrix);
      maskCtx.drawImage(layer.tile, 0, 0, layer.width, layer.height);
    } else {
      const sprite = images.get(spec.sprite);
      if (!sprite) throw new Error(`Mask image was not prepared: ${spec.sprite}`);
      maskCtx.drawImage(sprite, 0, 0, width, height);
    }
    maskCtx.setTransform(1, 0, 0, 1, 0, 0);
    maskCtx.filter = "none";
    if (spec.mode === "luma" || spec.invert) {
      const pixels = maskCtx.getImageData(0, 0, width, height);
      for (let i = 0; i < pixels.data.length; i += 4) {
        let alpha = pixels.data[i + 3];
        if (spec.mode === "luma") {
          alpha = (pixels.data[i] * 0.299 + pixels.data[i + 1] * 0.587
            + pixels.data[i + 2] * 0.114) * (alpha / 255);
        }
        if (spec.invert) alpha = 255 - alpha;
        pixels.data[i + 3] = alpha;
      }
      maskCtx.putImageData(pixels, 0, 0);
    }
    return maskCanvas;
  }

  let projector = null;

  function paintLayers(target, layers, progress, offset, speech, isCover, camera, visemes = {}, shotDuration = 1) {
    const matrices = new Map();
    const alphas = new Map();
    const origins = new Map();
    const byId = new Map(layers.map((layer) => [layer.id, layer]));
    const states = new Map(layers.map((layer) => {
      const pose = layer.getPose(progress);
      if (layer.anchor3d && projector) {
        // Pin to a 3D object's screen position; authored x/y become an extra offset.
        const point = projector(layer.anchor3d.object, layer.anchor3d.offset3d ?? [0, 0, 0]);
        if (point) {
          const [dx, dy] = layer.anchor3d.offset ?? [0, 0];
          return [layer.id, {...pose, x: point[0] + dx, y: point[1] + dy, visible: (pose.visible ?? true) && point[2]}];
        }
      }
      return [layer.id, pose];
    }));
    const chosen = new Map();
    for (const layer of layers) {
      const state = states.get(layer.id);
      if (layer.variant_group && (state.visible ?? true)) chosen.set(layer.variant_group, layer.id);
    }
    const depths = new Map();
    for (const layer of layers) {
      if (isCover && (hiddenOnCover.has(layer.id) || (layer.parent && hiddenOnCover.has(layer.parent)))) continue;
      const pose = states.get(layer.id);
      if (!(pose.visible ?? true)) continue;
      const tile = layer.frames?.length
        ? layer.frames[Math.max(0, Math.min(layer.frames.length - 1, Math.round(pose.frame ?? 0)))]
        : layer.tile;
      const rootZ = layer.parent && depths.has(layer.parent) ? depths.get(layer.parent) : (pose.z ?? 0);
      depths.set(layer.id, rootZ);
      const blur = (pose.blur ?? layer.blur ?? 0) + depthBlur(rootZ, camera, camera?.focus);
      const tintOpacity = pose.tint_opacity ?? 0;
      const tintColor = pose.tint_color
        ? `rgb(${pose.tint_color.map((value) => Math.round(value)).join(",")})`
        : (layer.tint ? paintColor(layer.tint, "accent") : null);
      const drawTile = tintColor && tintOpacity > 0 ? tintTile(layer, tile, tintColor, tintOpacity) : tile;
      if (layer.viseme_for) {
        const shape = visemes[layer.viseme_for];
        if (shape && layer.viseme && layer.viseme !== shape) continue;
      }
      if (layer.variant_group && chosen.get(layer.variant_group) !== layer.id) continue;
      if (layer.parent && !(states.get(layer.parent)?.visible ?? true)) continue;
      const parentMatrix = layer.parent ? matrices.get(layer.parent) : null;
      const parentAlpha = layer.parent ? (alphas.get(layer.parent) ?? 1) : 1;
      let alpha = (pose.opacity ?? 1) * parentAlpha;
      if (!layer.parent && camera && (rootZ || camera.z)) alpha *= depthFade(rootZ, camera);
      const levelFor = (speaker) => (speech?.[2] === speaker ? (speech[3][offset - speech[0]] ?? 0) : 0);
      if (layer.quiet && levelFor(layer.quiet) > 0.08) continue;
      if (layer.mouth && layer.talk_only && levelFor(layer.mouth) <= 0.08) continue;
      let mouth = 1;
      if (layer.mouth) {
        const level = speech?.[2] === layer.mouth ? speech[3][offset - speech[0]] : 0;
        const floor = layer.talk_only ? 0.4 : 0.18;
        mouth = floor + (1 - floor) * level;
      }
      const matrix = layerMatrix(pose, width, height, layer.pivot,
        {parent: parentMatrix, parentOrigin: layer.parent ? origins.get(layer.parent) : null,
         camera, parallax: layer.parallax, mouth, box: [layer.width, layer.height]});
      matrices.set(layer.id, matrix);
      alphas.set(layer.id, alpha);
      origins.set(layer.id, [(layer.pivot?.[0] ?? 0.5) * layer.width,
        (layer.pivot?.[1] ?? 0.5) * layer.height * mouth]);
      if (layer.kind === "group" || alpha <= 0) continue;
      const masks = maskSpecsFor(layer, byId);
      if (!masks.length) {
        const motion = Number(layer.motion_blur ?? 0);
        if (motion > 0) {
          // Full-pose shutter, mirrored from studio/design.py (MOTION_SHUTTER seconds at motion 1).
          const window = motion * 0.08 / Math.max(0.1, shotDuration);
          const samples = motion >= 0.5 ? 5 : 3;
          for (let index = 0; index < samples; index += 1) {
            const factor = (index - (samples - 1) / 2) / Math.max(1, samples - 1);
            const moved = poseAt(layer.poses, Math.max(0, Math.min(1, progress + window * factor)));
            const samplePose = {...pose};
            for (const key of ["x", "y", "scale", "scale_x", "scale_y", "rotate", "skew_x", "skew_y"]) {
              if (moved[key] !== undefined) samplePose[key] = moved[key];
            }
            const sampleMatrix = layerMatrix(samplePose, width, height, layer.pivot,
              {parent: parentMatrix, parentOrigin: layer.parent ? origins.get(layer.parent) : null,
               camera, parallax: layer.parallax, mouth, box: [layer.width, layer.height]});
            target.save();
            target.setTransform(...sampleMatrix);
            wipeClip(target, layer, samplePose);
            target.globalAlpha = alpha / samples;
            target.globalCompositeOperation = BLEND[layer.blend] ?? "source-over";
            target.filter = blur
              ? `blur(${Math.max(0.4, Math.min(width, height) * blur * 0.02)}px)` : "none";
            target.drawImage(drawTile, 0, 0, layer.width, layer.height);
            target.restore();
          }
          continue;
        }
        target.save();
        target.setTransform(...matrix);
        wipeClip(target, layer, pose);
        target.globalAlpha = alpha;
        target.globalCompositeOperation = BLEND[layer.blend] ?? "source-over";
        target.filter = blur ? `blur(${Math.max(0.4, Math.min(width, height) * blur * 0.02)}px)` : "none";
        const shadow = layer.shadow;
        const glow = layer.glow;
        if (shadow) {
          target.shadowColor = paintColor(shadow.color, "background");
          target.shadowBlur = Math.max(1, Math.min(width, height) * (shadow.blur ?? 0.18) * 0.16);
          target.shadowOffsetX = (shadow.offset_x ?? 0) * width;
          target.shadowOffsetY = (shadow.offset_y ?? 0) * height;
          target.globalAlpha = (shadow.opacity ?? 0.55);
          target.drawImage(drawTile, 0, 0, layer.width, layer.height);
          target.shadowColor = "transparent";
          target.shadowBlur = 0;
          target.shadowOffsetX = 0;
          target.shadowOffsetY = 0;
        }
        target.globalAlpha = alpha;
        target.drawImage(drawTile, 0, 0, layer.width, layer.height);
        if (glow) {
          target.globalCompositeOperation = "screen";
          target.globalAlpha = alpha * (glow.opacity ?? 0.6);
          target.filter = `blur(${Math.max(1, Math.min(width, height) * (glow.size ?? 0.18) * 0.16)}px)`;
          target.drawImage(drawTile, 0, 0, layer.width, layer.height);
        }
        target.restore();
        continue;
      }
      layerMaskCtx.setTransform(1, 0, 0, 1, 0, 0);
      layerMaskCtx.globalCompositeOperation = "source-over";
      layerMaskCtx.globalAlpha = 1;
      layerMaskCtx.clearRect(0, 0, width, height);
      layerMaskCtx.save();
      layerMaskCtx.setTransform(...matrix);
      wipeClip(layerMaskCtx, layer, pose);
      layerMaskCtx.globalAlpha = alpha;
      layerMaskCtx.filter = blur
        ? `blur(${Math.max(0.4, Math.min(width, height) * blur * 0.02)}px)` : "none";
      layerMaskCtx.drawImage(drawTile, 0, 0, layer.width, layer.height);
      layerMaskCtx.restore();
      layerMaskCtx.filter = "none";
      for (const spec of masks) {
        const mask = maskBuffer(spec, progress, camera, byId, origins);
        layerMaskCtx.globalCompositeOperation = "destination-in";
        layerMaskCtx.drawImage(mask, 0, 0);
      }
      layerMaskCtx.globalCompositeOperation = "source-over";
      target.save();
      target.globalAlpha = 1;
      target.globalCompositeOperation = BLEND[layer.blend] ?? "source-over";
      target.drawImage(layerMaskCanvas, 0, 0);
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
    if (post.tint) {
      ctx2.save();
      ctx2.globalCompositeOperation = "overlay";
      ctx2.globalAlpha = 0.12;
      ctx2.fillStyle = paintColor(post.tint, "accent");
      ctx2.fillRect(0, 0, width, height);
      ctx2.restore();
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
    if (post.paper) {
      ctx2.save();
      ctx2.globalCompositeOperation = "multiply";
      ctx2.imageSmoothingEnabled = true;
      fxCtx.setTransform(1, 0, 0, 1, 0, 0);
      fxCtx.clearRect(0, 0, width, height);
      fxCtx.fillStyle = "#fff";
      fxCtx.fillRect(0, 0, width, height);
      fxCtx.globalAlpha = Math.min(1, post.paper * 0.35);
      fxCtx.drawImage(paperBlotch, 0, 0, width, height);
      fxCtx.globalAlpha = Math.min(1, post.paper * 0.15);
      fxCtx.fillStyle = ctx2.createPattern(paperFibre, "repeat");
      fxCtx.fillRect(0, 0, width, height);
      fxCtx.globalAlpha = 1;
      ctx2.drawImage(fx, 0, 0);
      ctx2.restore();
    }
    if (post.leak) {
      const reach = Math.hypot(width, height) * 0.75;
      const pulse = 0.75 + 0.25 * Math.sin(frame * 0.05);
      const gradient = ctx2.createRadialGradient(width, -height * 0.05, 0, width, -height * 0.05, reach);
      const strength = Math.min(1, post.leak * 0.55 * pulse);
      for (const stop of [0, 0.25, 0.5, 0.75, 1]) {
        gradient.addColorStop(stop, `rgba(255,176,112,${(strength * (1 - stop) ** 1.6).toFixed(4)})`);
      }
      ctx2.save();
      ctx2.globalCompositeOperation = "screen";
      ctx2.fillStyle = gradient;
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

  function trackedCamera(index, progress) {
    const shot = shots[index];
    if (!shot.camera) return null;
    const base = poseAt(poseTrack({
      x: shot.camera.x ?? 0, y: shot.camera.y ?? 0,
      zoom: shot.camera.zoom ?? 1, rotate: shot.camera.rotate ?? 0,
      z: shot.camera.z ?? 0, fov: shot.camera.fov ?? 50,
    }, shot.camera.keyframes ?? []), progress);
    base.focus = shot.camera.focus;
    const track = shot.camera.track;
    if (!track) return base;
    const all = [...planes[index].background, ...planes[index].foreground];
    const byId = new Map(all.map((layer) => [layer.id, layer]));
    const subject = byId.get(track.layer);
    if (!subject) return base;
    const origins = new Map();
    const pre = (layer) => {
      const state = layer.getPose(progress);
      const parent = layer.parent ? byId.get(layer.parent) : null;
      const parentMatrix = parent ? pre(parent)[0] : null;
      const matrix = layerMatrix(state, width, height, layer.pivot, {
        parent: parentMatrix, parentOrigin: layer.parent ? origins.get(layer.parent) : null,
        camera: null, box: [layer.width, layer.height],
      });
      origins.set(layer.id, [(layer.pivot?.[0] ?? 0.5) * layer.width,
        (layer.pivot?.[1] ?? 0.5) * layer.height]);
      return [matrix, layer];
    };
    const [matrix, layer] = pre(subject);
    const [subjectX, subjectY] = apply(matrix, layer.width / 2, layer.height / 2);
    const desired = [Number(track.x ?? 0.5) * width, Number(track.y ?? 0.5) * height];
    const inv = inverse(cameraMatrix({...base, x: 0, y: 0}, width, height));
    const [targetX, targetY] = apply(inv, desired[0], desired[1]);
    return {...base, x: (base.x ?? 0) + (targetX - subjectX) / width,
      y: (base.y ?? 0) + (targetY - subjectY) / height};
  }

  function paintShot(target, index, frame, isCover, shift = 0) {
    const shot = shots[index];
    const offset = frame - shot.start;
    // shift is a sub-frame offset for motion blur; audio-driven state stays on the whole frame.
    const progress = Math.max(0, Math.min(1, (offset + shift) / Math.max(1, shot.end - shot.start - 1)));
    const speech = isCover ? null : shot.speech.find(([start, end]) => start <= offset && offset < end);
    const visemes = {};
    if (!isCover) {
      for (const item of shot.visemes ?? []) {
        if (item.start <= frame && frame < item.end && item.at <= frame) {
          visemes[item.speaker] = item.shape;
        }
      }
    }
    const camera = trackedCamera(index, progress);
    target.fillStyle = shot.background;
    target.fillRect(0, 0, width, height);
    // Render 3D first so anchor3d layers project through the current camera.
    const threeCanvas = three[index] ? three[index](progress) : null;
    projector = three[index]?.project ?? null;
    paintLayers(target, planes[index].background, progress, offset, speech, isCover, camera, visemes, shot.duration ?? 1);
    if (threeCanvas) target.drawImage(threeCanvas, 0, 0);
    paintLayers(target, planes[index].foreground, progress, offset, speech, isCover, camera, visemes, shot.duration ?? 1);
    applyPost(target.canvas, shot.post, frame);
  }

  function drawCaption(frame) {
    const caption = captions[findFrame(captions, frame)];
    if (!caption || caption.start > frame) return;
    if (caption.kinetic) {
      drawKinetic(ctx, caption, frame, data.fps, images);
      return;
    }
    const animation = caption.animation ?? "none";
    ctx.save();
    if (animation !== "none") {
      const span = Math.max(1, (caption.end - caption.start) * 0.22);
      const t = Math.max(0, Math.min(1, (frame - caption.start) / span));
      if (animation === "pop") {
        const scaleValue = 0.9 + 0.1 * t;
        ctx.translate(width / 2, height / 2);
        ctx.scale(scaleValue, scaleValue);
        ctx.translate(-width / 2, -height / 2);
      } else if (animation === "slide") {
        ctx.translate(0, (1 - t) * height * 0.035);
      } else if (animation === "rise") {
        ctx.translate(0, (1 - t) * height * 0.06);
      } else if (animation === "fade") {
        ctx.globalAlpha = t;
      }
    }
    if (caption.karaoke) {
      const background = images.get(caption.background.sprite);
      ctx.drawImage(background, caption.background.x, caption.background.y);
      for (const word of caption.words) {
        if (frame >= word.start && frame < word.end) {
          ctx.save();
          ctx.fillStyle = caption.highlight ?? palette.accent ?? "#FFBD54";
          const [x0, y0, x1, y1] = word.box;
          const pad = caption.highlight_pad ?? 3;
          roundRect(ctx, x0 - pad, y0 - pad, (x1 - x0) + pad * 2, (y1 - y0) + pad * 2,
            caption.highlight_radius ?? 5);
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
    ctx.restore();
  }

  function transitionMask(maskSprite, progress, softness, invert, mode) {
    const sprite = images.get(maskSprite);
    if (!sprite) throw new Error(`Transition mask was not prepared: ${maskSprite}`);
    maskCanvas.width = width;
    maskCanvas.height = height;
    maskCtx.setTransform(1, 0, 0, 1, 0, 0);
    maskCtx.clearRect(0, 0, width, height);
    maskCtx.drawImage(sprite, 0, 0, width, height);
    const pixels = maskCtx.getImageData(0, 0, width, height);
    const feather = Math.max(0.015, softness);
    for (let i = 0; i < pixels.data.length; i += 4) {
      let alpha = pixels.data[i + 3];
      if (mode === "alpha") {
        alpha = alpha * progress;
      } else {
        const luma = pixels.data[i] * 0.299 + pixels.data[i + 1] * 0.587
          + pixels.data[i + 2] * 0.114;
        alpha = Math.max(0, Math.min(1, (luma / 255 - (1 - progress)) / feather + 0.5)) * 255;
      }
      if (invert) alpha = 255 - alpha;
      pixels.data[i + 3] = alpha;
    }
    maskCtx.putImageData(pixels, 0, 0);
    return maskCanvas;
  }

  function transition(t, type, easeMode = "smooth", edge = {}) {
    t = easing(t, easeMode);
    if (type === "dissolve") {
      ctx.globalAlpha = t;
      ctx.drawImage(incoming, 0, 0);
      return;
    }
    if (type === "luma-wipe") {
      const mask = lumaMask(t, edge.softness ?? 0.08, edge.invert ?? false, edge.seed ?? 17);
      fxCtx.setTransform(1, 0, 0, 1, 0, 0);
      fxCtx.clearRect(0, 0, width, height);
      fxCtx.globalCompositeOperation = "source-over";
      fxCtx.drawImage(incoming, 0, 0);
      fxCtx.globalCompositeOperation = "destination-in";
      fxCtx.drawImage(mask, 0, 0, width, height);
      fxCtx.globalCompositeOperation = "source-over";
      ctx.save();
      ctx.globalAlpha = 1;
      ctx.drawImage(fx, 0, 0);
      ctx.restore();
      return;
    }
    if (type === "mask" && edge.mask_sprite) {
      const mask = transitionMask(edge.mask_sprite, t, edge.softness ?? 0.08,
        edge.invert ?? false, edge.mask_mode ?? "luma");
      fxCtx.setTransform(1, 0, 0, 1, 0, 0);
      fxCtx.clearRect(0, 0, width, height);
      fxCtx.globalCompositeOperation = "source-over";
      fxCtx.drawImage(incoming, 0, 0);
      fxCtx.globalCompositeOperation = "destination-in";
      fxCtx.drawImage(mask, 0, 0);
      fxCtx.globalCompositeOperation = "source-over";
      ctx.save();
      ctx.globalAlpha = 1;
      ctx.drawImage(fx, 0, 0);
      ctx.restore();
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
        transition(t, edge.type, edge.ease ?? "smooth", edge);
        ctx.restore();
      } else {
        // Same shutter as studio/render.py: average 3 or 5 sub-frames spread over motion_blur frames.
        const blur = isCover ? 0 : Number(shot.motion_blur ?? 0);
        const subframes = blur >= 0.55 ? 5 : blur >= 0.18 ? 3 : 1;
        if (subframes > 1) {
          for (let i = 0; i < subframes; i += 1) {
            paintShot(motionCtx, index, frame, false, (i - (subframes - 1) / 2) * blur);
            ctx.save();
            ctx.globalAlpha = 1 / (i + 1);
            ctx.drawImage(motion, 0, 0);
            ctx.restore();
          }
        } else {
          paintShot(ctx, index, frame, isCover);
        }
      }
      ctx.globalAlpha = 1;
      ctx.globalCompositeOperation = "source-over";
      ctx.filter = "none";
      if (!isCover) drawCaption(frame);
    },
    dispose() {
      stage?.dispose();
    },
  };
}
