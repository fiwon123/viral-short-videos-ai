"""The one load-time expansion pipeline every command shares.

Order matters: word and beat anchors resolve first (every later step sees plain
numbers), defs and rigs become plain layers, keyed paint becomes sprite frames, poses, motion recipes/paths/wiggle/follow and ``alive`` idle motion become keys, IK limbs solve on top, the style fills defaults,
markers emit SFX/shakes/effect layers, trails and particles become keyed
layers, and text reveals split last so they see the final layers.
"""

import copy
from pathlib import Path


def prepare_episode(episode, channel, channel_dir, *, style=True, episode_dir=None, clock=None):
    from .anchors import present, resolve
    from .expand import expand as expand_defs
    from .ik import expand as expand_ik
    from .life import expand as expand_life
    from .moves import expand as expand_moves
    from .poses import expand as expand_poses
    from .light2d import expand as expand_light
    from .markers import expand as expand_markers
    from .morph import expand as expand_morph
    from .music import expand as expand_music
    from .paint import expand as expand_paint
    from .particles import expand as expand_particles
    from .presets import apply_style
    from .reveal import expand as expand_reveal
    from .physics3d import expand as expand_physics3d
    from .rig3d import expand as expand_rig3d
    from .rigs import load_rig_poses, load_rigs
    from .scenes import load_library
    from .trails import expand as expand_trails

    if present(episode):
        episode = resolve(episode, clock, lambda: beat_grid(episode, channel, channel_dir, style, episode_dir))
    episode = expand_defs(copy.deepcopy(episode), load_rigs(channel, channel_dir))
    episode = expand_morph(expand_paint(episode, channel))
    episode = expand_poses(episode, load_rig_poses(channel, channel_dir))
    episode = expand_ik(expand_life(expand_moves(episode)))
    library = load_library(channel, channel_dir)
    episode = expand_rig3d(expand_physics3d(episode, library), library)
    if style:
        episode = apply_style(episode, channel, channel_dir)
    episode = expand_light(expand_music(episode, channel, channel_dir, episode_dir), channel)
    episode = expand_markers(episode, channel_dir)
    episode = expand_trails(episode)
    episode = expand_particles(episode)
    episode = expand_reveal(episode, channel, channel_dir)
    if episode_dir is not None:
        from .videolayer import expand as expand_video

        episode = expand_video(episode, Path(episode_dir), channel_dir)
    return episode


def beat_grid(episode, channel, channel_dir, style=True, episode_dir=None):
    """The beat grid of the music the episode will actually play (after the style and the library pick)."""
    from .anchors import music_grid
    from .music import expand as expand_music
    from .presets import apply_style

    probe = {key: copy.deepcopy(value) for key, value in episode.items() if key != "defs"}
    if style:
        probe = apply_style(probe, channel, channel_dir)
    probe = expand_music(probe, channel, channel_dir, episode_dir)
    return music_grid(probe.get("music"), episode_dir)


def resolve_source(episode, channel, channel_dir, episode_dir=None):
    """The authored episode with anchors turned into numbers (estimated from the text), nothing else
    expanded: for tools that read authored keys and cues (motion-report, viral-check, spot)."""
    from .anchors import present, resolve

    if not present(episode):
        return episode
    return resolve(episode, None, lambda: beat_grid(episode, channel, channel_dir, True, episode_dir))


def prepare_measured(episode, channel, channel_dir, episode_dir, audio_library=None):
    """``prepare_episode`` with word anchors on the measured takes instead of a text estimate.

    Only episodes that use anchors pay for it: one extra audio pass (takes are cached), then the
    visuals are expanded again against the real word and shot times.
    """
    from tempfile import TemporaryDirectory

    from .anchors import clock_from_timeline, present
    from .audio import prepare_audio

    prepared = prepare_episode(episode, channel, channel_dir, episode_dir=episode_dir)
    if not present(episode):
        return prepared
    with TemporaryDirectory(prefix=".anchors-") as temp:
        work = Path(temp)
        timeline, _ = prepare_audio(prepared, Path(episode_dir), work / "mix.wav", work, audio_library,
                                    channel=channel)
    return prepare_episode(episode, channel, channel_dir, episode_dir=episode_dir,
                           clock=clock_from_timeline(prepared, timeline))
