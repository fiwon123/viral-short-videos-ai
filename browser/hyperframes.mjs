import {gsap} from "gsap";
import {createPainter} from "./painter.mjs";

const data = JSON.parse(document.getElementById("visual-plan").textContent);
const canvas = document.querySelector("canvas");
const cover = document.getElementById("studio").hasAttribute("data-cover");
let frame = 0;
let painter;
const clock = {
  get seconds() {
    return frame / data.fps;
  },
  set seconds(time) {
    frame = Math.min(data.frames - 1, Math.max(0, Math.round(time * data.fps)));
    painter?.draw(frame, cover);
  },
};
window.__timelines ??= {};
window.__timelines.studio = gsap.timeline({paused: true}).fromTo(
  clock, {seconds: 0}, {seconds: data.frames / data.fps, duration: data.frames / data.fps, ease: "none"},
);
window.__hf ??= {};
window.__hf.buildReady ??= {};
window.__hf.buildReady.studio = createPainter(canvas, data, (name) => `assets/${name}`).then((instance) => {
  painter = instance;
  painter.draw(frame, cover);
}).catch((error) => {
  window.__hfStartupError = String(error);
  throw error;
});
