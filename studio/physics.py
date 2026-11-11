"""Sampled motion for weight, liquid and debris.

The renderer interpolates 3D keyframes linearly between keys, so believable
physics comes from sampling the curve, not from a smarter easing. Every helper
here returns a track: a list of dicts with `t` in seconds plus whichever of
`position`, `rotation` and `scale` change at that moment.

    track = physics.drop(0.4, [0, 1.6, 0], floor=0.028, bounces=2)
    shot.move("ball", physics.to_pose(track))

Scale keys ride on the same object as position keys, so squash is emitted at the
contact frames themselves rather than on a separate track.
"""

import math

GRAVITY = 9.8
MAX_STEP = 1 / 240


def _rng(seed):
    state = seed or 1
    while True:
        state = (state * 1103515245 + 12345) % (2 ** 31)
        yield state / (2 ** 31)


def flight(t0, start, velocity, *, duration, gravity=GRAVITY, drag=0.0, fps=24):
    """Ballistic arc from `start` with `velocity`, sampled for the renderer."""
    keys, g = [], (0.0, -gravity, 0.0)
    for t in _times(duration, fps):
        position = _integrate(start, velocity, g, drag, t)
        keys.append({"t": round(t0 + t, 5), "position": [round(v, 5) for v in position]})
    return keys


def drop(t0, start, velocity=(0.0, 0.0, 0.0), *, floor=0.0, gravity=GRAVITY, drag=0.06,
         restitution=0.42, bounces=2, friction=0.78, fps=24, limit=4.0, squash=0.22):
    """Fall, bounce with decreasing height, then settle on the floor."""
    g = (0.0, -gravity, 0.0)
    position = [float(v) for v in start]
    velocity = [float(v) for v in velocity]
    keys = [{"t": round(t0, 5), "position": [round(v, 5) for v in position]}]
    contacts, remaining, t, dt = [], bounces, 0.0, MAX_STEP
    next_sample, airborne = 0.0, position[1] > floor
    while t < limit:
        speed_up = math.hypot(*velocity)
        if position[1] <= floor and speed_up < 0.25 and remaining <= 0:
            break
        # Semi-implicit Euler at 240 Hz keeps contacts crisp without special cases.
        velocity = [velocity[i] + (g[i] - drag * velocity[i]) * dt for i in range(3)]
        position = [position[i] + velocity[i] * dt for i in range(3)]
        t += dt
        if position[1] < floor:
            position[1] = floor
            if airborne:  # first frame of contact, before any bounce changes the velocity
                contacts.append((round(t, 5), [round(v, 5) for v in position]))
                airborne = False
            if remaining > 0 and abs(velocity[1]) > 0.28:
                velocity[1] = -velocity[1] * restitution
                velocity[0] *= friction
                velocity[2] *= friction
                remaining -= 1
                airborne = True
            else:
                velocity[1] = 0.0
                velocity[0] *= 0.72
                velocity[2] *= 0.72
        elif position[1] > floor + 1e-6:
            airborne = True
        if t >= next_sample:
            next_sample += 1 / fps
            keys.append({"t": round(t0 + t, 5), "position": [round(v, 5) for v in position]})
    for moment, spot in contacts:
        # The contact frame is sampled between steps, so place it exactly on the floor.
        exact = {"t": round(t0 + moment, 5), "position": [spot[0], round(floor, 5), spot[2]]}
        if not any(key["t"] == exact["t"] and "position" in key for key in keys):
            keys.append(exact)
        _squash(keys, exact["t"], squash, fps)
    return merge(keys)


def burst(t0, origin, *, count=16, speed=(1.2, 3.2), spread=1.0, floor=None, gravity=GRAVITY,
          drag=0.5, fps=24, duration=1.4, seed=7, squash=0.16):
    """Particles leaving one point: debris, kernels, sparks. One track each."""
    random = _rng(seed)
    tracks = []
    for index in range(count):
        angle = 2 * math.pi * next(random)
        elevation = math.acos(1 - 2 * next(random)) if spread >= 1 else next(random) * math.pi * 0.25
        magnitude = speed[0] + (speed[1] - speed[0]) * next(random)
        velocity = [
            magnitude * math.sin(elevation) * math.cos(angle) * (0.65 + 0.7 * next(random)),
            magnitude * math.cos(elevation) + 0.6,
            magnitude * math.sin(elevation) * math.sin(angle) * (0.65 + 0.7 * next(random)),
        ]
        piece = (0.6 + 0.9 * next(random),)
        if floor is None:
            keys = flight(t0 + 0.02 * next(random), origin, velocity, duration=duration,
                          gravity=gravity, drag=drag, fps=fps)
        else:
            keys = drop(t0 + 0.02 * next(random), origin, velocity, floor=floor, gravity=gravity,
                        drag=drag, restitution=0.32, bounces=1, fps=fps,
                        limit=duration, squash=squash)
        for key in keys:
            key["spin"] = round(piece[0] * (key["t"] - t0) * 5.0, 4)
        tracks.append(keys)
    return tracks


def splash(t0, origin, *, count=12, speed=(0.7, 1.8), arc=0.62, floor=None, gravity=GRAVITY,
           drag=0.15, fps=24, duration=0.85, seed=11):
    """Liquid crown: droplets fan upward and outward, slower on the way back."""
    random = _rng(seed)
    tracks = []
    for index in range(count):
        angle = 2 * math.pi * index / count + 0.22 * next(random)
        lift = arc * (0.55 + 0.45 * next(random))
        magnitude = speed[0] + (speed[1] - speed[0]) * next(random)
        velocity = [magnitude * math.cos(angle), lift * 4.2 + magnitude * 0.5,
                    magnitude * math.sin(angle) * 0.8]
        keys = flight(t0 + 0.015 * next(random), origin, velocity, duration=duration,
                      gravity=gravity, drag=drag, fps=fps)
        tracks.append(keys)
    if floor is not None:
        for track in tracks:
            _clamp(track, floor)
    return tracks


def shake(t0, duration, amplitude, *, fps=24, decay=5.0, frequency=17.0, seed=3):
    """Camera jitter that decays: returns offsets to add to position and target."""
    random = _rng(seed)
    axes = [(0.4 + next(random), next(random) * math.tau) for _ in range(3)]
    keys = [{"t": round(t0, 5), "offset": [0.0, 0.0, 0.0]}]
    for t in _times(duration, fps)[1:]:
        envelope = math.exp(-decay * t / max(duration, 1e-6))
        offset = [round(amplitude * envelope * math.sin(frequency * t * (1 + axis[0]) + axis[1]), 5)
                  for axis in axes]
        keys.append({"t": round(t0 + t, 5), "offset": offset})
    keys.append({"t": round(t0 + duration, 5), "offset": [0.0, 0.0, 0.0]})
    return keys


def squash(t0, amount=0.3, *, fps=24, frames=2):
    """Standalone squash and stretch around a contact, in seconds."""
    keys = [{"t": round(t0 - 1 / fps, 5), "scale": [1.0, 1.0, 1.0]},
            {"t": round(t0, 5), "scale": [round(1 + amount, 4), round(1 - amount, 4), round(1 + amount, 4)]},
            {"t": round(t0 + frames / fps, 5), "scale": [round(1 - amount * 0.35, 4),
                                                        round(1 + amount * 0.5, 4),
                                                        round(1 - amount * 0.35, 4)]},
            {"t": round(t0 + (frames + 2) / fps, 5), "scale": [1.0, 1.0, 1.0]}]
    return keys


def merge(*tracks):
    """Combine tracks that animate the same object, newest value per time wins."""
    by_time = {}
    for track in tracks:
        for key in track:
            merged = by_time.setdefault(key["t"], {"t": key["t"]})
            merged.update(key)
    return [by_time[t] for t in sorted(by_time)]


def normalized(track, duration):
    """Convert seconds to the manifest's 0..1 shot time, one frame per instant."""
    frames = {}
    for frame in track:
        if 0 <= frame["t"] <= duration:
            frames.setdefault(round(frame["t"] / duration, 7), {}).update(
                {key: value for key, value in frame.items() if key != "t"})
    return [{"at": at, **frames[at]} for at in sorted(frames)]


def to_pose(track, *, yaw=0.0, roll=0.0, ease="linear"):
    """Episode `pose(t, [x,y,z], yaw, roll, ease)` tuples, ignoring missing axes."""
    poses = []
    for frame in track:
        if "position" not in frame:
            continue
        rotation = frame.get("rotation", [yaw, frame.get("spin", yaw), roll])
        poses.append((round(frame["t"], 5), frame["position"],
                      round(rotation[1], 5), round(rotation[2], 5), ease))
    return poses


def to_scale(track):
    """(t, [sx, sy, sz]) samples for parts that only squash."""
    return [(round(frame["t"], 5), frame["scale"]) for frame in track if "scale" in frame]


def _times(duration, fps):
    count = max(1, math.ceil(duration * fps))
    return [i * duration / count for i in range(count + 1)]


def _integrate(start, velocity, gravity, drag, t):
    if drag <= 0:
        return [start[i] + velocity[i] * t + 0.5 * gravity[i] * t * t for i in range(3)]
    terminal = [gravity[i] / drag for i in range(3)]
    decay = math.exp(-drag * t)
    return [start[i] + (velocity[i] - terminal[i]) * (1 - decay) / drag + terminal[i] * t
            for i in range(3)]


def _squash(keys, at, amount, fps):
    """Insert scale values on the shared track so the contact reads as weight."""
    if amount <= 0:
        return
    shape = [(0, [1 + amount, 1 - amount, 1 + amount]),
             (2 / fps, [1 - amount * 0.3, 1 + amount * 0.45, 1 - amount * 0.3]),
             (4 / fps, [1.0, 1.0, 1.0])]
    shape = [(delay, [round(axis, 4) for axis in scale]) for delay, scale in shape]
    for offset, scale in shape:
        moment = round(at + offset, 5)
        existing = next((key for key in keys if key["t"] == moment), None)
        if existing is None:
            keys.append({"t": moment, "scale": scale})
        else:
            existing["scale"] = scale
    keys.sort(key=lambda key: key["t"])


def _clamp(track, floor):
    for key in track:
        if "position" in key and key["position"][1] < floor:
            key["position"][1] = floor


if __name__ == "__main__":
    track = drop(0, [0, 1.4, 0], floor=0.028, bounces=2)
    print(f"{len(track)} keys over {track[-1]['t']:.2f} s")
    for frame in track:
        y = f"y={frame['position'][1]:6.3f}" if "position" in frame else "         "
        scale = f"scale={frame['scale']}" if "scale" in frame else ""
        print(f"  t={frame['t']:5.2f} {y} {scale}")
