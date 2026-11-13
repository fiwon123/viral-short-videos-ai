let state = null;
let selected = null;
const $ = (id) => document.getElementById(id);
const shots = () => state ? state.episode.scenes.flatMap((scene) => scene.shots) : [];
const currentShot = () => shots().find((shot) => shot.id === selected);
const escape = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[char]));

function status(text) { $("status").textContent = text; }

async function load() {
  try {
    state = await (await fetch("/api/episode")).json();
    renderShots();
    if (shots()[0]) selectShot(shots()[0].id);
    status(`${shots().length} shots · ${state.channel.name}`);
  } catch (error) {
    status(`Could not load: ${error.message}`);
  }
}

function renderShots() {
  $("shots").innerHTML = shots().map((shot) => `
    <div class="shot ${shot.id === selected ? "active" : ""}" data-id="${escape(shot.id)}">
      <strong>${escape(shot.id)}</strong>
      <small>${Number(shot.duration).toFixed(2)}s · ${(shot.layers || []).length} layers</small>
    </div>`).join("");
  document.querySelectorAll(".shot").forEach((element) => {
    element.onclick = () => selectShot(element.dataset.id);
  });
}

function valueOr(value, fallback) { return value === undefined ? fallback : value; }

function selectShot(id) {
  selected = id;
  const shot = currentShot();
  if (!shot) return;
  renderShots();
  $("shot-title").textContent = shot.id;
  $("duration").value = valueOr(shot.duration, 1);
  const camera = shot.camera || {};
  $("camera-preset").value = camera.preset || "";
  $("cam-x").value = valueOr(camera.x, 0);
  $("cam-y").value = valueOr(camera.y, 0);
  $("cam-zoom").value = valueOr(camera.zoom, 1);
  $("cam-rotate").value = valueOr(camera.rotate, 0);
  renderMarkers();
  refreshStill();
}

function camera() {
  const shot = currentShot();
  shot.camera = shot.camera || {};
  return shot.camera;
}

function bind(id, key, cast = Number, fallback = 0) {
  $(id).oninput = () => {
    const shot = currentShot();
    if (!shot) return;
    const value = $(id).value;
    if (key === "duration") {
      shot.duration = Math.max(0.1, Number(value) || 0.1);
    } else if (key === "camera-preset") {
      if (value) camera().preset = value; else delete camera().preset;
    } else {
      camera()[key] = value === "" ? fallback : cast(value);
    }
    renderShots();
  };
}

function renderMarkers() {
  const markers = state.episode.markers || [];
  $("markers").innerHTML = markers.map((marker, index) => `
    <div class="marker">
      <div class="marker-head">
        <strong>${escape(marker.id)}</strong>
        <button data-remove="${index}">Remove</button>
      </div>
      <small>${escape(marker.shot)} · ${Number(marker.at).toFixed(2)} · ${(marker.events || []).length} events</small>
      <label>At <input type="number" min="0" max="1" step="0.01" value="${Number(marker.at)}" data-at="${index}"></label>
    </div>`).join("") || "<p class='note'>No markers yet.</p>";
  document.querySelectorAll("[data-remove]").forEach((button) => {
    button.onclick = () => {
      state.episode.markers.splice(Number(button.dataset.remove), 1);
      renderMarkers();
    };
  });
  document.querySelectorAll("[data-at]").forEach((input) => {
    input.oninput = () => {
      state.episode.markers[Number(input.dataset.at)].at = Math.max(0, Math.min(1, Number(input.value)));
    };
  });
}

function refreshStill() {
  const shot = currentShot();
  if (!shot) return;
  const image = $("preview");
  image.onerror = () => status("Preview unavailable for this shot; use the renderer preview.");
  image.onload = () => status("Preview ready");
  image.src = `/api/still?shot=${encodeURIComponent(shot.id)}&at=0.5&t=${Date.now()}`;
}

async function save() {
  const response = await fetch("/api/save", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({episode: state.episode}),
  });
  const data = await response.json();
  status(data.error ? `Error: ${data.error}` : `Saved ${data.saved}`);
}

function addMarker() {
  const shot = currentShot();
  if (!shot) return;
  state.episode.markers = state.episode.markers || [];
  state.episode.markers.push({
    id: `impact-${state.episode.markers.length + 1}`,
    shot: shot.id,
    at: 0.5,
    events: [
      {kind: "sfx", cue: "pop", gain: 0.2},
      {kind: "camera_shake", amplitude: 0.015, frequency: 12, duration: 0.3},
      {kind: "effect", template: "dust-burst", x: 0.5, y: 0.7},
    ],
  });
  renderMarkers();
}

bind("duration", "duration");
bind("camera-preset", "camera-preset", String, "");
bind("cam-x", "x");
bind("cam-y", "y");
bind("cam-zoom", "zoom", Number, 1);
bind("cam-rotate", "rotate");
$("save").onclick = save;
$("refresh").onclick = refreshStill;
$("add-marker").onclick = addMarker;
$("guides").onchange = () => $("safearea").classList.toggle("hidden", !$("guides").checked);
$("safearea").classList.add("hidden");
load();
