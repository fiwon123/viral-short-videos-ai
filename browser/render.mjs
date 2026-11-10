import {spawnSync} from "node:child_process";
import {existsSync} from "node:fs";
import {readFile, readdir, rename, writeFile} from "node:fs/promises";
import {join} from "node:path";
import {fileURLToPath} from "node:url";

const [backend, work, format, mode] = process.argv.slice(2);
const data = JSON.parse(await readFile(join(work, "visual-plan.json"), "utf8"));
const source = (name) => fileURLToPath(new URL(name, import.meta.url));
const chrome = process.env.STUDIO_CHROME || [
  "/usr/bin/google-chrome", "/usr/bin/chromium", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
].find(existsSync);

async function remotion() {
  const {bundle} = await import("@remotion/bundler");
  const {selectComposition, renderMedia, renderStill} = await import("@remotion/renderer");
  const serveUrl = await bundle({
    entryPoint: source("./remotion.jsx"), publicDir: join(work, "assets"),
    outDir: join(work, "bundle"), enableCaching: false,
  });
  const inputProps = {data};
  const common = {
    serveUrl, inputProps, logLevel: "error", browserExecutable: chrome,
    chromiumOptions: Object.keys(data.scenes).length ? {gl: "swangle"} : {},
  };
  const composition = await selectComposition({...common, id: "ViralVideo"});
  const licenseKey = process.env.REMOTION_LICENSE_KEY;
  const isProduction = mode !== "preview";
  await renderMedia({...common, composition, codec: "h264", muted: true, concurrency: 2,
    imageFormat: "png", colorSpace: "bt601",
    outputLocation: join(work, "picture.mp4"), licenseKey, isProduction});
  const coverProps = {...composition.props, cover: true};
  await renderStill({...common, composition: {...composition, props: coverProps},
    inputProps: {...inputProps, cover: true}, frame: data.cover.frame,
    imageFormat: "png", output: join(work, "cover.png"), licenseKey, isProduction});
}

function html(cover = false) {
  const payload = JSON.stringify(data).replaceAll("<", "\\u003c");
  return `<!doctype html>
<html lang="en">
<meta charset="utf-8">
<title>Viral Video Studio</title>
<style>html,body{margin:0;overflow:hidden}canvas{display:block}</style>
<div id="studio" data-composition-id="studio" data-start="0" data-fps="${data.fps}"
     data-width="${data.width}" data-height="${data.height}" data-duration="${data.frames / data.fps}"
     ${cover ? "data-cover" : ""}>
  <canvas width="${data.width}" height="${data.height}"></canvas>
</div>
<script id="visual-plan" type="application/json">${payload}</script>
<script src="picture.js"></script>
</html>`;
}

function hf(...args) {
  const cli = source("../node_modules/hyperframes/bin/hyperframes.mjs");
  const env = {...process.env, HYPERFRAMES_NO_TELEMETRY: "1"};
  if (chrome && !env.HYPERFRAMES_BROWSER_PATH) env.HYPERFRAMES_BROWSER_PATH = chrome;
  const result = spawnSync(process.execPath, [cli, ...args], {env, encoding: "utf8", maxBuffer: 8 * 1024 * 1024});
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error((result.stdout + "\n" + result.stderr).trim().slice(-3800));
}

async function hyperframes() {
  const {build} = await import("esbuild");
  const index = join(work, "index.html");
  await build({entryPoints: [source("./hyperframes.mjs")], outfile: join(work, "picture.js"),
    bundle: true, format: "iife", minify: true});
  await writeFile(index, html());
  hf("render", work, "--output", join(work, `picture.${format}`), "--format", format,
    "--fps", String(data.fps), "--workers", "2", "--no-browser-gpu");
  await writeFile(index, html(true));
  const stills = join(work, "stills");
  hf("snapshot", work, "--at", String(data.cover.frame / data.fps), "--no-end",
    "--output", stills, "--no-browser-gpu");
  const snapshots = (await readdir(stills)).filter((name) => name.endsWith(".png"));
  if (snapshots.length !== 1) throw new Error("Expected one HyperFrames cover snapshot");
  await rename(join(stills, snapshots[0]), join(work, "cover.png"));
}

try {
  if (backend === "remotion") await remotion();
  else if (backend === "hyperframes") await hyperframes();
  else throw new Error(`Unknown browser renderer: ${backend}`);
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
