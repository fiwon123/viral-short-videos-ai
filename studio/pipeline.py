"""The one load-time expansion pipeline every command shares.

Order matters: defs and rigs become plain layers, keyed paint becomes sprite frames, poses, motion recipes/paths/wiggle/follow and ``alive`` idle motion become keys, IK limbs solve on top, the style fills defaults,
markers emit SFX/shakes/effect layers, trails and particles become keyed
layers, and text reveals split last so they see the final layers.
"""

import copy


def prepare_episode(episode, channel, channel_dir, *, style=True):
    from .expand import expand as expand_defs
    from .ik import expand as expand_ik
    from .life import expand as expand_life
    from .moves import expand as expand_moves
    from .poses import expand as expand_poses
    from .markers import expand as expand_markers
    from .morph import expand as expand_morph
    from .paint import expand as expand_paint
    from .particles import expand as expand_particles
    from .presets import apply_style
    from .reveal import expand as expand_reveal
    from .rig3d import expand as expand_rig3d
    from .rigs import load_rig_poses, load_rigs
    from .scenes import load_library
    from .trails import expand as expand_trails

    episode = expand_defs(copy.deepcopy(episode), load_rigs(channel, channel_dir))
    episode = expand_morph(expand_paint(episode, channel))
    episode = expand_poses(episode, load_rig_poses(channel, channel_dir))
    episode = expand_ik(expand_life(expand_moves(episode)))
    episode = expand_rig3d(episode, load_library(channel, channel_dir))
    if style:
        episode = apply_style(episode, channel, channel_dir)
    episode = expand_markers(episode, channel_dir)
    episode = expand_trails(episode)
    episode = expand_particles(episode)
    return expand_reveal(episode, channel, channel_dir)
