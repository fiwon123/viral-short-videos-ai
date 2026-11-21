const $ = (id) => document.getElementById(id);
const video = $("video");
let fps = 24;
let comments = [];
let pending = null;  // {time, x, y} while the note box is open
let focused = null;  // the comment whose pin is shown

const escape = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[char]));

function status(text) { $("status").textContent = text; }

async function load() {
  try {
    const data = await (await fetch("/api/review")).json();
    fps = data.fps || 24;
    $("title").textContent = `${data.episode} · ${data.render}`;
    comments = data.comments || [];
    renderComments();
  } catch (error) {
    status(`Could not load: ${error.message}`);
  }
}

async function poll() {
  try {
    const data = await (await fetch("/api/comments")).json();
    if (JSON.stringify(data.comments) !== JSON.stringify(comments)) {
      comments = data.comments;
      renderComments();
    }
  } catch (error) { /* the server stopped; keep what is shown */ }
}

function clock() {
  $("clock").textContent = `${video.currentTime.toFixed(2)} s · frame ${Math.floor(video.currentTime * fps + 1e-6)}`;
  if (video.duration) $("scrub").value = Math.round(1000 * video.currentTime / video.duration);
}

function step(frames) {
  video.pause();
  video.currentTime = Math.max(0, Math.min(video.duration || 0, (Math.floor(video.currentTime * fps + 1e-6) + frames + 0.5) / fps));
}

function pins() {
  const shown = [];
  if (pending) shown.push({x: pending.x, y: pending.y, cls: "pin new"});
  if (focused) shown.push({x: focused.x, y: focused.y, cls: `pin ${focused.status}`});
  $("pins").innerHTML = shown.map((pin) =>
    `<span class="${pin.cls}" style="left:${pin.x * 100}%;top:${pin.y * 100}%"></span>`).join("");
}

function placeNote(event) {
  const box = video.getBoundingClientRect();
  const x = (event.clientX - box.left) / box.width;
  const y = (event.clientY - box.top) / box.height;
  if (x < 0 || x > 1 || y < 0 || y > 1) return;
  video.pause();
  pending = {time: video.currentTime, x, y};
  focused = null;
  const note = $("note");
  note.classList.remove("hidden");
  note.style.left = `${Math.min(x, 0.55) * 100}%`;
  note.style.top = `${Math.min(y, 0.7) * 100}%`;
  $("note-text").value = "";
  $("note-text").focus();
  pins();
}

function closeNote() {
  pending = null;
  $("note").classList.add("hidden");
  pins();
}

async function saveNote(event) {
  event.preventDefault();
  const text = $("note-text").value.trim();
  if (!pending || !text) return;
  const response = await fetch("/api/comments", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({...pending, text}),
  });
  const data = await response.json();
  if (!response.ok) {
    status(`Not saved: ${data.error}`);
    return;
  }
  status(`Saved ${data.id} at ${data.time.toFixed(2)} s${data.shot ? ` (shot ${data.shot})` : ""}`);
  closeNote();
  await poll();
}

function renderComments() {
  const open = comments.filter((item) => item.status === "open").length;
  $("comments").innerHTML = `<h2>Comments <small>${open} open · ${comments.length - open} done</small></h2>` +
    (comments.slice().reverse().map((item) => `
      <article class="comment ${item.status}" data-id="${escape(item.id)}">
        <div class="comment-head">
          <strong>${escape(item.id)}</strong>
          <span>${Number(item.time).toFixed(2)} s${item.shot ? ` · ${escape(item.shot)} at ${item.shot_progress}` : ""}</span>
          <em>${item.status === "done" ? "done" : "open"}</em>
        </div>
        <p>${escape(item.text)}</p>
        ${item.reply ? `<p class="reply">${escape(item.reply)}</p>` : ""}
      </article>`).join("") || "<p class='empty'>No comments yet. Pause and click the picture to add one.</p>");
  document.querySelectorAll(".comment").forEach((element) => {
    element.onclick = () => {
      focused = comments.find((item) => item.id === element.dataset.id);
      closeNote();
      video.pause();
      video.currentTime = (focused.frame + 0.5) / fps;
      pins();
    };
  });
}

video.addEventListener("click", placeNote);
video.addEventListener("timeupdate", clock);
video.addEventListener("seeked", clock);
video.addEventListener("play", () => { $("play").textContent = "Pause"; focused = null; pins(); });
video.addEventListener("pause", () => { $("play").textContent = "Play"; });
$("play").onclick = () => (video.paused ? video.play() : video.pause());
$("back").onclick = () => step(-1);
$("forward").onclick = () => step(1);
$("scrub").oninput = () => {
  if (video.duration) video.currentTime = video.duration * $("scrub").value / 1000;
};
$("note").onsubmit = saveNote;
$("note-cancel").onclick = closeNote;
$("note-text").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) saveNote(event);
  if (event.key === "Escape") closeNote();
});
document.addEventListener("keydown", (event) => {
  if (event.target.tagName === "TEXTAREA" || event.target.tagName === "INPUT") return;
  if (event.key === " ") { event.preventDefault(); $("play").click(); }
  if (event.key === "ArrowLeft") step(-1);
  if (event.key === "ArrowRight") step(1);
});
load();
setInterval(poll, 4000);
