"""Validate a channel's cast identities and Foley library."""

from .core import asset, load


def load_audio_library(channel, base):
    if "audio_library" not in channel:
        return None
    path = asset(base, channel["audio_library"])
    library = load(path, "audio_library")
    for profile in library.get("voices", {}).values():
        if design := profile.get("character_design"):
            asset(path.parent, design["reference"])
            if "approved_take" in design:
                asset(path.parent, design["approved_take"])
    for key, variants in library.get("sounds", {}).items():
        files = {asset(path.parent, file) for file in variants}
        if len(files) != len(variants):
            raise ValueError(f"{key} lists the same audio file more than once")
    return library, path


def validate_audio(episode, audio_library):
    library = audio_library[0] if audio_library else {}
    voices, sounds = library.get("voices", {}), library.get("sounds", {})
    for scene in episode["scenes"]:
        for shot in scene["shots"]:
            for line in shot.get("speech", []):
                speaker = line["speaker"]
                if voices and speaker not in voices:
                    raise ValueError(f"{shot['id']} has no cast profile for {speaker}")
                if speaker in voices:
                    if "voice" in line:
                        raise ValueError(f"{shot['id']}/{speaker} must use the channel voice profile. Remove the legacy voice override.")
                    if voices[speaker]["engine"] == "recorded" and "file" not in line:
                        raise ValueError(f"{shot['id']}/{speaker} requires an approved voice take in speech.file")
            for cue in shot.get("sfx", []):
                stack = [cue]
                while stack:
                    item = stack.pop()
                    if "sound" in item:
                        variants = sounds.get(item["sound"])
                        if not variants or item.get("variant", 1) > len(variants):
                            raise ValueError(f"{shot['id']} references an unknown sound or variant: {item['sound']}")
                    stack.extend(item.get("layers", []))
