"""Single registry for renderer names, capabilities and selection."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Renderer:
    name: str
    browser: bool
    svg: bool
    three: bool
    package: str | None = None


RENDERERS = {
    "python": Renderer("python", browser=False, svg=False, three=False),
    "hyperframes": Renderer("hyperframes", browser=True, svg=True, three=True,
                            package="hyperframes"),
    "remotion": Renderer("remotion", browser=True, svg=True, three=True,
                         package="@remotion/renderer"),
}
RENDERER_NAMES = tuple(RENDERERS)


def get(name):
    try:
        return RENDERERS[name]
    except KeyError:
        raise ValueError(f"Unknown renderer: {name}. Available: {', '.join(RENDERER_NAMES)}") from None


def choose(episode, requested="auto", shots=None):
    """Resolve ``auto`` from the visuals the requested shots actually use."""
    if requested and requested != "auto":
        return get(requested).name
    if shots is None:
        shots = [shot for scene in episode.get("scenes", []) for shot in scene.get("shots", [])]
    for shot in shots:
        if "three" in shot:
            return "hyperframes"
        if any(layer.get("kind") == "svg" for layer in shot.get("layers", [])):
            return "hyperframes"
    return "python"
