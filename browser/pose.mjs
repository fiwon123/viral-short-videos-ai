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

function cubicBezier(t, x1, y1, x2, y2) {
  t = Math.max(0, Math.min(1, t));
  if (t <= 0) return 0;
  if (t >= 1) return 1;
  const curve = (u, a, b) => 3 * a * u * (1 - u) ** 2 + 3 * b * u * u * (1 - u) + u ** 3;
  let low = 0, high = 1;
  for (let index = 0; index < 24; index += 1) {
    const middle = (low + high) / 2;
    if (curve(middle, x1, x2) < t) low = middle;
    else high = middle;
  }
  return curve((low + high) / 2, y1, y2);
}

function spring(t, stiffness = 140, damping = 12, mass = 1) {
  t = Math.max(0, Math.min(1, t));
  if (t <= 0) return 0;
  if (t >= 1) return 1;
  stiffness = Math.max(0.01, stiffness);
  damping = Math.max(0, damping);
  mass = Math.max(0.0001, mass);
  const omega = Math.sqrt(stiffness / mass);
  const zeta = damping / (2 * Math.sqrt(stiffness * mass));
  if (zeta < 1) {
    const wd = omega * Math.sqrt(1 - zeta * zeta);
    return 1 - Math.exp(-zeta * omega * t)
      * (Math.cos(wd * t) + (zeta * omega / Math.max(wd, 1e-6)) * Math.sin(wd * t));
  }
  return 1 - Math.exp(-omega * t) * (1 + omega * t);
}

export function easing(t, mode) {
  t = Math.max(0, Math.min(1, t));
  if (mode && typeof mode === "object") {
    if (mode.type === "cubic-bezier") return cubicBezier(t, ...(mode.points ?? [0.4, 0, 0.2, 1]));
    if (mode.type === "spring") return spring(t, mode.stiffness, mode.damping, mode.mass);
    return t;
  }
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
  if (mode === "auto") return t * t * (3 - 2 * t);
  return t;
}

function catmullRom(p0, p1, p2, p3, t) {
  const t2 = t * t;
  const t3 = t2 * t;
  return 0.5 * (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
    + (-p0 + 3 * p1 - 3 * p2 + p3) * t3);
}

function mixValue(a, b, t) {
  if (Array.isArray(a)) return a.map((part, index) => part + (b[index] - part) * t);
  return a + (b - a) * t;
}

export function poseAt(points, progress) {
  for (let i = 1; i < points.length; i += 1) {
    const [start, from] = points[i - 1];
    const [end, to, mode, easeProps = {}] = points[i];
    if (progress > end) continue;
    const t = end > start ? (progress - start) / (end - start) : 1;
    const result = {};
    for (const [key, value] of Object.entries(from)) {
      if (typeof value === "boolean" || key === "frame") {
        result[key] = progress >= end ? to[key] : value;
        continue;
      }
      const propertyMode = easeProps[key] ?? mode;
      if (propertyMode === "auto") {
        const p0 = i >= 2 ? points[i - 2][1][key] ?? value : value;
        const p3 = i + 1 < points.length ? points[i + 1][1][key] ?? to[key] : to[key];
        if (Array.isArray(value)) {
          result[key] = value.map((part, index) => catmullRom(p0[index] ?? part, part,
            to[key][index], p3[index] ?? to[key][index], t));
        } else {
          result[key] = catmullRom(p0, value, to[key], p3, t);
        }
      } else {
        result[key] = mixValue(value, to[key], easing(t, propertyMode));
      }
    }
    return result;
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
