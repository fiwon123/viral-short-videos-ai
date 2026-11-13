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
  t = Math.max(0, Math.min(1, t));
  if (mode === "in") return t * t;
  if (mode === "out") return 1 - (1 - t) ** 2;
  if (mode === "smooth") return t * t * (3 - 2 * t);
  if (mode === "sine") return 0.5 - 0.5 * Math.cos(Math.PI * t);
  if (mode === "expo") return t >= 1 ? 1 : 1 - 2 ** (-10 * t);
  if (mode === "circ") return Math.sqrt(Math.max(0, 1 - (1 - t) ** 2));
  if (mode === "quint") return 1 - (1 - t) ** 5;
  if (mode === "back") {
    const c1 = 1.70158, c3 = c1 + 1;
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2;
  }
  if (mode === "elastic") {
    if (t === 0 || t === 1) return t;
    return 2 ** (-10 * t) * Math.sin((t * 10 - 0.75) * (2 * Math.PI / 3)) + 1;
  }
  if (mode === "bounce") {
    const n1 = 7.5625, d1 = 2.75;
    if (t < 1 / d1) return n1 * t * t;
    if (t < 2 / d1) return n1 * (t -= 1.5 / d1) * t + 0.75;
    if (t < 2.5 / d1) return n1 * (t -= 2.25 / d1) * t + 0.9375;
    return n1 * (t -= 2.625 / d1) * t + 0.984375;
  }
  if (mode === "spring") return 1 - Math.exp(-6 * t) * Math.cos(9 * t);
  if (mode === "hold") return t < 1 ? 0 : 1;
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
      key, typeof value === "boolean" ? (progress >= end ? to[key] : value)
        : Array.isArray(value) ? value.map((part, j) => mix(part, to[key][j])) : mix(value, to[key]),
    ]));
  }
  return points.at(-1)[1];
}

export function objectTrack(object, keys) {
  return poseTrack({
    position: object.position,
    rotation: object.rotation ?? [0, 0, 0],
    scale: object.scale ?? [1, 1, 1],
    visible: object.visible ?? true,
  }, keys);
}
