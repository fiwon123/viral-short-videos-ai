import {gsap} from "gsap";
import {easing, poseAt} from "./pose.mjs";
import {createThreeStage} from "./three.mjs";

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

export async function createPainter(canvas, data, urlFor) {
  const {width, height, captions, shots, scenes, cover} = data;
  const names = new Set([
    ...shots.flatMap(({layers}) => layers.map((layer) => layer.sprite)),
    ...captions.map((cue) => cue.sprite),
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
  const stage = Object.keys(scenes).length ? await createThreeStage(scenes, width, height, urlFor) : null;
  const three = shots.map((shot) => shot.three ? stage.compile(shot.three) : null);
  const ctx = canvas.getContext("2d");
  const incoming = document.createElement("canvas");
  incoming.width = width;
  incoming.height = height;
  const overlay = incoming.getContext("2d");
  const hiddenOnCover = new Set(cover.hide);

  function paintLayers(target, layers, progress, offset, speech, isCover) {
    for (const layer of layers) {
      if (isCover && hiddenOnCover.has(layer.id)) continue;
      const pose = layer.getPose(progress);
      if (!pose.opacity) continue;
      const w = Math.max(1, layer.width * pose.scale);
      let h = layer.height * pose.scale;
      if (layer.mouth) {
        const level = speech?.[2] === layer.mouth ? speech[3][offset - speech[0]] : 0;
        h *= 0.18 + 0.82 * level;
      }
      h = Math.max(1, h);
      target.save();
      target.translate(pose.x * width, pose.y * height);
      target.rotate(-pose.rotate * Math.PI / 180);
      target.globalAlpha = pose.opacity;
      target.drawImage(layer.tile, -w / 2, -h / 2, w, h);
      target.restore();
    }
  }

  function paintShot(target, index, frame, isCover) {
    const shot = shots[index];
    const offset = frame - shot.start;
    const progress = offset / Math.max(1, shot.end - shot.start - 1);
    const speech = isCover ? null : shot.speech.find(([start, end]) => start <= offset && offset < end);
    target.fillStyle = shot.background;
    target.fillRect(0, 0, width, height);
    paintLayers(target, planes[index].background, progress, offset, speech, isCover);
    if (three[index]) target.drawImage(three[index](progress), 0, 0);
    paintLayers(target, planes[index].foreground, progress, offset, speech, isCover);
  }

  return {
    draw(frame, isCover = false) {
      const index = findFrame(shots, frame);
      const transition = shots[index].transition;
      if (!isCover && transition && frame < transition.end) {
        paintShot(ctx, index - 1, shots[index - 1].end - 1, false);
        paintShot(overlay, index, frame, false);
        const t = (frame - transition.start + 1) / (transition.end - transition.start);
        ctx.save();
        if (transition.type === "dissolve") ctx.globalAlpha = easing(t, "smooth");
        else {
          ctx.beginPath();
          ctx.rect(0, 0, Math.floor(width * t), height);
          ctx.clip();
        }
        ctx.drawImage(incoming, 0, 0);
        ctx.restore();
      } else {
        paintShot(ctx, index, frame, isCover);
      }
      const caption = captions[findFrame(captions, frame)];
      if (!isCover && caption && caption.start <= frame) {
        ctx.drawImage(images.get(caption.sprite), caption.x, caption.y);
      }
    },
    dispose() {
      for (const timeline of vectorTimelines) timeline.kill();
      stage?.dispose();
    },
  };
}
