export function poseTrack(initial, keys = []) {
  let pose = initial;
  const points = [[0, pose, "linear"]];
  for (const {at, ease = "linear", ...changes} of keys) {
    pose = {...pose, ...changes};
    if (at === 0) points.pop();
    points.push([at, pose, ease]);
  }
  return points;
}

export function easing(t, mode) {
  if (mode === "in") return t * t;
  if (mode === "out") return 1 - (1 - t) ** 2;
  if (mode === "smooth") return t * t * (3 - 2 * t);
  return t;
}

export function poseAt(points, progress) {
  for (let i = 1; i < points.length; i++) {
    const [start, from] = points[i - 1];
    const [end, to, mode] = points[i];
    if (progress > end) continue;
    const t = easing((progress - start) / (end - start), mode);
    const mix = (a, b) => a + (b - a) * t;
    return Object.fromEntries(Object.entries(from).map(([key, value]) => [
      key, Array.isArray(value) ? value.map((part, j) => mix(part, to[key][j])) : mix(value, to[key]),
    ]));
  }
  return points.at(-1)[1];
}
