# Viral Short Videos — local production shortcuts.
# A template: no channel or episode path is baked in. Values resolve from .env,
# the command line, or discovery under channels/ and episodes/.

SHELL := /bin/sh
.DEFAULT_GOAL := help

-include .env
export YOUTUBE_API_KEY

PYTHON ?= audio-models/venv/bin/python
# In the dev sandbox the image's venv is the studio's Python, whatever .env says.
ifneq ($(SANDBOX_PYTHON),)
PYTHON := $(SANDBOX_PYTHON)
endif

# Docker sandbox, agents, and host setup (make setup-host, make claude, ...).
include sandbox.mk

# An empty value in .env still falls back to discovery; a command-line value always wins.
CHANNEL := $(strip $(CHANNEL))
CHANNEL := $(if $(CHANNEL),$(CHANNEL),$(shell $(PYTHON) -m studio.project channel 2>/dev/null))
EPISODE := $(strip $(EPISODE))
EPISODE := $(if $(EPISODE),$(EPISODE),$(shell $(PYTHON) -m studio.project episode 2>/dev/null))
RENDERER := $(strip $(RENDERER))
RENDERER := $(if $(RENDERER),$(RENDERER),hyperframes)

PREVIEW_FLAG ?= --preview
OUT_ARG = $(if $(OUT),--out "$(OUT)",)
CHANNEL_ARG = $(if $(CHANNEL),--channel $(CHANNEL),)
CHANNEL_DIR = $(patsubst %/,%,$(dir $(CHANNEL)))
LIBRARY ?= audio/cast-v2.json
VOICES ?=
VOICES_ARG = $(if $(VOICES),--voices $(VOICES),)

.PHONY: help status init channel-memory style-lock style-check discover reference viral-check film-qa treatment-lint state deliver narration-check script voice-import review-pack character3d art hardware hero assets sfx sfx-import music-import music-list depth-photo spot character motion-report vfx doctor list channel-doc migrate sound effect motion \
        still presets templates schema batch test support parity safearea editor review comments \
        validate check audio preview render \
        clean clean-cache clean-previews archive published \
        prune-duplicates prune-casting prune-brand prune-legacy

help:
	@echo "Viral Short Videos"
	@echo
	@echo "  Setup (pick one):"
	@echo "  make claude | codex | opencode   run an AI agent in the Docker sandbox (-auto: no prompts)"
	@echo "  make shell                       a shell in the sandbox; make dev-down stops it"
	@echo "  make dev-build | dev-doctor | reset | agents-version | agents-upgrade"
	@echo "  make setup-host                  run on the host instead: venv, node_modules, voice models"
	@echo "  make models                      download the Kokoro voice files (both modes)"
	@echo "  make art-models                  optional depth and cartoon cut-out models for art, hero and depth-photo (~280 MB)"
	@echo
	@echo "  make status                 resolved channel, episode, and .env"
	@echo "  make init                   write .env from what is already on disk"
	@echo "  make assets                 what the channel needs, and what is optional"
	@echo "  make sfx                    regenerate the channel Foley bank"
	@echo "  make vfx                    redraw the channel VFX kit from its palette"
	@echo "  make sound RECIPE=...       synthesize a custom Sound Lab recipe"
	@echo "  make sfx-import DIR=...     import recorded SFX packs into the library [DRY=1]"
	@echo "  make music-import DIR=...   import a royalty-free music folder, tagged by mood [DRY=1]"
	@echo "  make music-list             list the channel music library"
	@echo "  make depth-photo IMAGE=...  split a photo into parallax depth layers [DEPTH= LAYERS= NAME= SHOT=]"
	@echo "  make spot [APPLY=1]         propose SFX cues from the episode's motion"
	@echo "  make character SPEC=...     build a shaded, rig-ready character from a JSON spec"
	@echo "  make art SPEC=...           local AI character art, cut out and rigged [IMAGE= PARTS= BACKEND= SEED= DRY=1]"
	@echo "  make hardware               what this machine can generate art with (GPU, ComfyUI, diffusers)"
	@echo "  make hero EPISODE=... SHOT=...  AI video clip for a hook shot, 2.5D without a GPU [IMAGE= PROMPT= KEEP= WORKFLOW= BACKEND= SEED= DRY=1]"
	@echo "  make discover QUERY=... [RANK=velocity|views|outlier] [SLUG=...]  rank recent Shorts by speed (needs YOUTUBE_API_KEY)"
	@echo "  make reference CHANNEL=... URL=... [TOP=1..3]  study YouTube videos or a channel’s top Shorts"
	@echo "  make character3d OUT=....glb [SPEC=...]  rigged low-poly 3D character (bones for poses and ik)"
	@echo "  make viral-check EPISODE=... [VIDEO=...]  score hook, pacing, loop, packaging and loudness"
	@echo "  make film-qa VIDEO=... [EPISODE=...]  energy curve, dead runs, frozen end, framing of a render (red exits 1)"
	@echo "  make treatment-lint EPISODE=...  check the episode's treatment.md plan before building (red exits 1)"
	@echo "  make state EPISODE=... [WRITE=1]  the stage the evidence supports and the next command"
	@echo "  make review-pack EPISODE=... [VIDEO=...] [LENS=sound]  director, sound and continuity packets for cold reviewers"
	@echo "  make narration-check EPISODE=... [VIDEO=...]  hear each spoken line back and compare it with the script"
	@echo "  make script EPISODE=...     production script (script.md) and voice-app script (voice-script.txt)"
	@echo "  make voice-import EPISODE=... FILE=... [SPEAKER=...] [LANGUAGE=...]  split a recorded script into timed takes"
	@echo "  make deliver EPISODE=... [VIDEO=...]  gate the master and write delivery.md (VERIFY=delivery.md checks it)"
	@echo "  make channel-memory SLUG=... [EPISODE=...]  create missing memory, ledger, idea bank and series bible files"
	@echo "  make motion-report          flag dead holds, linear moves, lockstep starts, snaps, low contrast"
	@echo "  make effect RECIPE=...      generate a custom Effect Lab SVG"
	@echo "  make motion MOTION=pop      emit a manifest-ready motion recipe"
	@echo "  make still EPISODE=... SHOT=A PROGRESS=0.5 [NOAUDIO=1] [ONION=3]  render one review frame"
	@echo "  make presets                list style presets"
	@echo "  make templates              list shot templates"
	@echo "  make schema                 write per-manifest schema wrappers"
	@echo "  make batch SEASON=...       validate or render a season manifest"
	@echo "  make test                   run the local test suite"
	@echo "  make channel-doc            write channel.md from channel.json"
	@echo "  make style-lock [INIT=1] [CHANGE=\"...\"]  refresh the channel AGENTS.md from style-lock.json (CHANGE bumps the version)"
	@echo "  make style-check            audit every episode of the channel against its style lock"
	@echo "  make support                write the renderer support matrix"
	@echo "  make parity                 render the shared renderer parity fixture"
	@echo "  make safearea               write a platform safe-area guide"
	@echo "  make editor                 open the local shot inspector"
	@echo "  make review EPISODE=...     play the newest render and leave notes on a frame"
	@echo "  make comments EPISODE=... [DONE=c1 REPLY=...]  open notes with their frame and close-up, or resolve one"
	@echo "  make doctor                 check ffmpeg, node, Chrome, Kokoro"
	@echo "  make list                   channel folders and episodes"
	@echo
	@echo "  make validate  EPISODE=episodes/<slug>/episode.json"
	@echo "  make check     EPISODE=episodes/<slug>/episode.json"
	@echo "  make audio     EPISODE=episodes/<slug>/episode.json [OUT=<dir>]"
	@echo "  make preview   EPISODE=episodes/<slug>/episode.json [OUT=<dir>] [HOOK=20 opening seconds only]"
	@echo "  make render    EPISODE=episodes/<slug>/episode.json [OUT=<dir>]"
	@echo
	@echo "  CHANNEL and EPISODE are discovered when unambiguous, else set them,"
	@echo "  pass them per call, or put them in .env (see .env.example)."
	@echo "  Overrides: CHANNEL=<manifest> RENDERER=<auto|python|remotion|hyperframes>"
	@echo "             OUT=<dir> PREVIEW_FLAG= PYTHON=<interpreter>"
	@echo
	@echo "  make clean-cache            drop failed render staging, audio takes, __pycache__"
	@echo "  make clean-previews         drop preview packages in output/ and channel folders"
	@echo "  make archive [SLUG=...] [APPLY=1] [NOVIDEO=1] [VERBOSE=1]  clean caches, old versions and published renders in every workspace channel (dry run)"
	@echo "  make published EPISODE=... [URL=...]  mark an uploaded episode so make archive packs its render"
	@echo
	@echo "  make prune-<group>          dry run; add APPLY=1 to delete"
	@echo "    prune-duplicates          duplicate channel manifests"
	@echo "    prune-casting             character sheets from casting"
	@echo "    prune-brand               editable logo and banner artwork"
	@echo "    prune-legacy              manifests and libraries for a retired look"

status:
	@$(PYTHON) -m studio.project status

init:
	@$(PYTHON) -m studio.project init $(if $(FORCE),--force,)
	@echo "Edit .env if the detected values are not the ones you want."

discover:
	@test -n "$(QUERY)" || { echo "Set QUERY='search terms' [REGION=US] [RANK=velocity|views|outlier] [DAYS=7] [SLUG=<channel>]"; exit 1; }
	@$(PYTHON) video.py discover --query "$(QUERY)" --region $(or $(REGION),US) --shorts \
		--rank $(or $(RANK),velocity) --days $(or $(DAYS),7) --limit $(or $(LIMIT),10) \
		$(if $(SLUG),--snapshots workspace/$(SLUG)/research/snapshots,)

reference: export STUDIO_REFERENCE_URLS := $(URL)
reference: export STUDIO_REFERENCE_CHANNEL := $(CHANNEL)
reference: export STUDIO_REFERENCE_TOP := $(TOP)
reference: export STUDIO_REFERENCE_LANGS := $(SUB_LANGS)
reference:
	@$(PYTHON) -m studio.reference_study

character3d:
	@test -n "$(OUT)" || { echo "Set OUT=workspace/<channel>/channel/scene-library/<name>.glb [SPEC=colours.json]"; exit 1; }
	@$(PYTHON) -m studio.glbcharacter $(OUT) $(if $(SPEC),--spec $(SPEC),)

viral-check:
	@test -n "$(EPISODE)" || { echo "Set EPISODE=workspace/<channel>/episodes/<episode>/episode.json [VIDEO=.../video.mp4]"; exit 1; }
	@$(PYTHON) -m studio.viral_check $(EPISODE) $(CHANNEL_ARG) $(if $(VIDEO),--video $(VIDEO),)

film-qa:
	@test -n "$(VIDEO)" || { echo "Set VIDEO=.../video.mp4 [EPISODE=.../episode.json] [ROUTE=continuous|montage|hybrid] [STOP=8.0-8.6]"; exit 1; }
	@$(PYTHON) -m studio.film_qa $(VIDEO) $(if $(EPISODE),--episode $(EPISODE),) $(if $(ROUTE),--route $(ROUTE),) \
		$(if $(STOP),--stop $(STOP),)

state:
	@test -n "$(EPISODE)" || { echo "Set EPISODE=workspace/<channel>/episodes/<episode>/episode.json [WRITE=1]"; exit 1; }
	@$(PYTHON) -m studio.episode_state state $(EPISODE) $(CHANNEL_ARG) $(if $(WRITE),--write,)

deliver:
	@if [ -n "$(VERIFY)" ]; then $(PYTHON) -m studio.episode_state verify $(VERIFY); else \
		test -n "$(EPISODE)" || { echo "Set EPISODE=workspace/<channel>/episodes/<episode>/episode.json [VIDEO=...], or VERIFY=.../delivery.md"; exit 1; }; \
		$(PYTHON) -m studio.episode_state deliver $(EPISODE) $(CHANNEL_ARG) $(if $(VIDEO),--video $(VIDEO),); fi

script:
	@test -n "$(EPISODE)" || { echo "Set EPISODE=workspace/<channel>/episodes/<episode>/episode.json"; exit 1; }
	@$(PYTHON) -m studio.script $(EPISODE)

voice-import:
	@test -n "$(EPISODE)" && test -n "$(FILE)" || { echo "Set EPISODE=... FILE=... [SPEAKER=...] [LANGUAGE=...] [MODEL=...]"; exit 1; }
	@$(PYTHON) -m studio.voice_import "$(EPISODE)" "$(FILE)" $(if $(SPEAKER),--speaker "$(SPEAKER)") \
		$(if $(LANGUAGE),--language "$(LANGUAGE)") $(if $(MODEL),--model "$(MODEL)")

narration-check:
	@test -n "$(EPISODE)" || { echo "Set EPISODE=workspace/<channel>/episodes/<episode>/episode.json [VIDEO=...]"; exit 1; }
	@$(PYTHON) -m studio.narration $(EPISODE) $(if $(VIDEO),--video $(VIDEO),)

review-pack:
	@test -n "$(EPISODE)" || { echo "Set EPISODE=workspace/<channel>/episodes/<episode>/episode.json [VIDEO=...]"; exit 1; }
	@$(PYTHON) -m studio.episode_state review-pack $(EPISODE) $(if $(VIDEO),--video $(VIDEO),) $(if $(LENS),--lens $(LENS),)

treatment-lint:
	@test -n "$(EPISODE)" || { echo "Set EPISODE=workspace/<channel>/episodes/<episode>/episode.json (or its treatment.md)"; exit 1; }
	@$(PYTHON) -m studio.treatment $(EPISODE)

channel-memory:
	@test -n "$(SLUG)" || { echo "Set SLUG=<channel slug> (workspace/<slug>/)"; exit 1; }
	@$(PYTHON) -m studio.memory $(SLUG) $(if $(EPISODE),--episode $(EPISODE),)

assets:
	@test -n "$(CHANNEL)" || { echo "No channel resolved. Run make status, or set CHANNEL=channels/<slug>/channel.json"; exit 1; }
	@$(PYTHON) -m studio.inventory $(CHANNEL)

sfx:
	@test -n "$(CHANNEL)" || { echo "Set CHANNEL=channels/<slug>/channel.json"; exit 1; }
	@$(PYTHON) -m studio.sfx $(CHANNEL_DIR) --library $(LIBRARY) $(VOICES_ARG)

sfx-import:
	@test -n "$(CHANNEL)" || { echo "Set CHANNEL=workspace/<slug>/channel/channel.json"; exit 1; }
	@test -n "$(DIR)" || { echo "Set DIR=path/to/sound-pack"; exit 1; }
	@$(PYTHON) -m studio.samples $(CHANNEL_DIR) --source "$(DIR)" --library $(LIBRARY) $(if $(DRY),--dry-run,)

music-import:
	@test -n "$(CHANNEL)" || { echo "Set CHANNEL=workspace/<slug>/channel/channel.json"; exit 1; }
	@test -n "$(DIR)" || { echo "Set DIR=path/to/music-folder"; exit 1; }
	@$(PYTHON) -m studio.music import $(CHANNEL_DIR) --source "$(DIR)" $(if $(DRY),--dry-run,)

music-list:
	@test -n "$(CHANNEL)" || { echo "Set CHANNEL=workspace/<slug>/channel/channel.json"; exit 1; }
	@$(PYTHON) -m studio.music list $(CHANNEL_DIR)

depth-photo:
	@test -n "$(EPISODE)" || { echo "Set EPISODE=workspace/<slug>/episodes/<episode>/episode.json"; exit 1; }
	@test -n "$(IMAGE)" || { echo "Set IMAGE=path/to/photo.jpg"; exit 1; }
	@$(PYTHON) -m studio.depthphoto $(EPISODE) --image "$(IMAGE)" $(if $(DEPTH),--depth "$(DEPTH)",) \
		$(if $(LAYERS),--layers $(LAYERS),) $(if $(NAME),--name $(NAME),) $(if $(SHOT),--shot $(SHOT),) \
		$(if $(INVERT),--invert,)

character:
	@test -n "$(CHANNEL)" || { echo "Set CHANNEL=workspace/<slug>/channel/channel.json"; exit 1; }
	@test -n "$(SPEC)" || { echo "Set SPEC=art/characters/<id>.json (relative to the channel)"; exit 1; }
	@$(PYTHON) -m studio.character $(CHANNEL_DIR) --spec "$(SPEC)"

art:
	@test -n "$(CHANNEL)" || { echo "Set CHANNEL=workspace/<slug>/channel/channel.json"; exit 1; }
	@test -n "$(SPEC)" || { echo "Set SPEC=art/characters/<id>.json (relative to the channel)"; exit 1; }
	@$(PYTHON) -m studio.aiart $(CHANNEL_DIR) --spec "$(SPEC)" $(if $(IMAGE),--image "$(IMAGE)",) \
		$(if $(PARTS),--parts-dir "$(PARTS)",) $(if $(BACKEND),--backend $(BACKEND),) \
		$(if $(SEED),--seed $(SEED),) $(if $(DRY),--dry-run,)

hero:
	@test -n "$(EPISODE)" || { echo "Set EPISODE=workspace/<slug>/episodes/<episode>/episode.json"; exit 1; }
	@test -n "$(SHOT)" || { echo "Set SHOT=<shot id>"; exit 1; }
	@$(PYTHON) -m studio.heroclip $(EPISODE) --shot $(SHOT) $(CHANNEL_ARG) $(if $(IMAGE),--image "$(IMAGE)",) \
		$(if $(PROMPT),--prompt "$(PROMPT)",) $(if $(KEEP),--keep $(KEEP),) $(if $(WORKFLOW),--workflow "$(WORKFLOW)",) \
		$(if $(BACKEND),--backend $(BACKEND),) $(if $(SEED),--seed $(SEED),) $(if $(DRY),--dry-run,)

hardware:
	@$(PYTHON) -m studio.hardware

spot:
	@test -n "$(EPISODE)" || { echo "Set EPISODE=workspace/<channel>/episodes/<episode>/episode.json"; exit 1; }
	@$(PYTHON) -m studio.spotting $(EPISODE) $(CHANNEL_ARG) $(if $(APPLY),--apply,)

vfx:
	@test -n "$(CHANNEL)" || { echo "Set CHANNEL=channels/<slug>/channel.json"; exit 1; }
	@$(PYTHON) -m studio.vfx $(CHANNEL_DIR)

sound:
	@test -n "$(CHANNEL)" || { echo "Set CHANNEL=workspace/<slug>/channel/channel.json"; exit 1; }
	@test -n "$(RECIPE)" || { echo "Set RECIPE=audio/my-recipe.json"; exit 1; }
	@$(PYTHON) -m studio.soundlab $(CHANNEL_DIR) --recipe $(RECIPE)

effect:
	@test -n "$(CHANNEL)" || { echo "Set CHANNEL=workspace/<slug>/channel/channel.json"; exit 1; }
	@test -n "$(RECIPE)" || { echo "Set RECIPE=vfx/my-effect.json"; exit 1; }
	@$(PYTHON) -m studio.effectlab $(CHANNEL_DIR) --recipe $(RECIPE)

motion:
	@$(PYTHON) video.py motion $(MOTION) \
		$(if $(DURATION),--duration $(DURATION),) \
		$(if $(T0),--t0 $(T0),) \
		$(if $(AMOUNT),--amount $(AMOUNT),)

motion-report:
	@test -n "$(EPISODE)" || { echo "Set EPISODE=workspace/<channel>/episodes/<episode>/episode.json"; exit 1; }
	@$(PYTHON) -m studio.motion_report $(EPISODE) $(CHANNEL_ARG) $(if $(HOLD),--hold $(HOLD),)

still:
	@test -n "$(EPISODE)" || { echo "Set EPISODE=workspace/<channel>/episodes/<episode>/episode.json"; exit 1; }
	@$(PYTHON) video.py still $(EPISODE) $(CHANNEL_ARG) \
		$(if $(SHOT),--shot $(SHOT),) \
		$(if $(PROGRESS),--progress $(PROGRESS),) \
		$(if $(ONION),--onion $(ONION),) \
		$(if $(AT),--at $(AT),) \
		$(if $(SCALE),--scale $(SCALE),) \
		$(if $(SHEET),--sheet $(SHEET),) \
		$(if $(NOAUDIO),--no-audio,) \
		$(if $(NOCAPTIONS),--no-captions,) \
		$(if $(OUT),--out "$(OUT)",)

presets:
	@$(PYTHON) video.py presets $(CHANNEL_ARG)

templates:
	@$(PYTHON) video.py templates $(CHANNEL_ARG)

schema:
	@$(PYTHON) video.py schema

batch:
	@test -n "$(SEASON)" || { echo "Set SEASON=workspace/<slug>/season.json"; exit 1; }
	@$(PYTHON) video.py batch $(SEASON) \
		$(foreach id,$(ONLY),--only $(id),) \
		$(if $(STATUS),--status $(STATUS),) \
		$(if $(RENDERER),--renderer $(RENDERER),) \
		$(if $(PREVIEW),--preview,) \
		$(if $(JOBS),--jobs $(JOBS),) \
		$(if $(VALIDATE_ONLY),--validate-only,) \
		$(if $(DRY_RUN),--dry-run,) \
		$(if $(OUT_ROOT),--out-root "$(OUT_ROOT)",)

test:
	@STUDIO_WORD_TIMING=energy STUDIO_ASR=off $(PYTHON) -m unittest discover -s tests -v  # never load a speech model

style-lock:
	@test -n "$(CHANNEL)" || { echo "Set CHANNEL=workspace/<slug>/channel/channel.json"; exit 1; }
	@$(PYTHON) -m studio.stylelock $(dir $(CHANNEL)) $(if $(INIT),--init,) $(if $(CHANGE),--change "$(CHANGE)",)

style-check:
	@test -n "$(CHANNEL)" || { echo "Set CHANNEL=workspace/<slug>/channel/channel.json"; exit 1; }
	@$(PYTHON) -m studio.stylelock $(dir $(CHANNEL)) --check

channel-doc:
	@test -n "$(CHANNEL)" || { echo "Set CHANNEL=workspace/<slug>/channel/channel.json"; exit 1; }
	@$(PYTHON) video.py channel-doc $(CHANNEL)

migrate:
	@test -n "$(CHANNEL)" || { echo "Set CHANNEL=channels/<slug>/channel.json"; exit 1; }
	@$(PYTHON) -m studio.migrate $(CHANNEL) $(if $(EPISODE),--episode $(EPISODE),) $(if $(APPLY),--apply,)

support:
	@$(PYTHON) video.py support --markdown --out docs/RENDERER-SUPPORT.md

parity:
	@$(PYTHON) video.py parity

safearea:
	@$(PYTHON) video.py safearea --platform $(or $(PLATFORM),youtube-shorts) --out $(or $(OUT),docs/assets/safearea.png)

review:
	@test -n "$(EPISODE)" || { echo "Set EPISODE=workspace/<channel>/episodes/<episode>/episode.json [VIDEO=...]"; exit 1; }
	@$(PYTHON) -m studio.comments serve $(EPISODE) $(if $(VIDEO),--video $(VIDEO),) $(if $(PORT),--port $(PORT),)

comments:
	@test -n "$(EPISODE)" || { echo "Set EPISODE=workspace/<channel>/episodes/<episode>/episode.json [DONE=c1 REPLY=...]"; exit 1; }
	@$(PYTHON) -m studio.comments $(if $(DONE),done $(EPISODE) $(DONE) --reply "$(REPLY)",list $(EPISODE))

editor:
	@test -n "$(EPISODE)" || { echo "Set EPISODE=workspace/<channel>/episodes/<episode>/episode.json"; exit 1; }
	@$(PYTHON) video.py editor $(EPISODE) $(CHANNEL_ARG) $(if $(PORT),--port $(PORT),)

doctor:
	@$(PYTHON) video.py doctor

validate:
	@test -n "$(EPISODE)" || { echo "Set EPISODE=episodes/<slug>/episode.json"; exit 1; }
	@$(PYTHON) video.py validate $(EPISODE) $(CHANNEL_ARG)

check:
	@test -n "$(EPISODE)" || { echo "Set EPISODE=episodes/<slug>/episode.json"; exit 1; }
	@$(PYTHON) video.py check-visual $(EPISODE) $(CHANNEL_ARG)

audio:
	@test -n "$(EPISODE)" || { echo "Set EPISODE=episodes/<slug>/episode.json"; exit 1; }
	@$(PYTHON) video.py audio $(EPISODE) $(CHANNEL_ARG) $(OUT_ARG)

preview:
	@test -n "$(EPISODE)" || { echo "Set EPISODE=episodes/<slug>/episode.json"; exit 1; }
	@$(PYTHON) video.py render $(EPISODE) $(CHANNEL_ARG) --renderer $(RENDERER) \
		$(OUT_ARG) $(if $(PREVIEW_FLAG),$(PREVIEW_FLAG),--full-size-preview) $(if $(HOOK),--seconds $(HOOK),)

render:
	@test -n "$(EPISODE)" || { echo "Set EPISODE=episodes/<slug>/episode.json"; exit 1; }
	@$(PYTHON) video.py render $(EPISODE) $(CHANNEL_ARG) --renderer $(RENDERER) $(OUT_ARG)

list:
	@if [ -d channels ]; then echo "channels:"; ls -1 channels 2>/dev/null | sed 's/^/  /'; fi
	@if [ -d workspace ]; then echo "workspace:"; ls -1 workspace 2>/dev/null | sed 's/^/  /'; fi
	@if [ -d episodes ]; then echo "episodes:"; ls -1 episodes 2>/dev/null | sed 's/^/  /'; fi
	@if [ -d examples ]; then echo "examples:"; find examples -mindepth 1 -maxdepth 1 -type d -printf '  %f\n' 2>/dev/null | sort; fi

clean-cache:
	@find output -mindepth 1 -maxdepth 2 -name '.studio-*' -type d -prune -print -exec rm -rf {} + 2>/dev/null || true
	@find episodes -maxdepth 2 -name '.audio-takes' -type d -print -exec rm -rf {} + 2>/dev/null || true
	@find . -maxdepth 3 -name '__pycache__' -type d -prune -print -exec rm -rf {} + 2>/dev/null || true
	@echo "cache cleaned"

archive:
	@$(PYTHON) -m studio.cleanup archive $(if $(SLUG),--channel $(SLUG),) $(if $(APPLY),--apply,) $(if $(NOVIDEO),--no-video,) $(if $(VERBOSE),--verbose,)

published:
	@test -n "$(EPISODE)" || { echo "Set EPISODE=workspace/<slug>/episodes/<episode>"; exit 1; }
	@$(PYTHON) -m studio.cleanup published $(EPISODE) $(if $(URL),--url $(URL),)

clean-previews:
	@find output -mindepth 1 -maxdepth 2 -name '*-preview' -type d \
		-exec test -f {}/qa.json \; -exec test -f {}/video.mp4 \; -prune -print -exec rm -rf {} + 2>/dev/null || true
	@echo "previews cleaned"

prune-duplicates:
	@test -n "$(CHANNEL)" || { echo "Set CHANNEL=channels/<slug>/channel.json"; exit 1; }
	@$(PYTHON) -m studio.inventory $(CHANNEL) --prune duplicates $(if $(APPLY),--apply,)

prune-casting:
	@test -n "$(CHANNEL)" || { echo "Set CHANNEL=channels/<slug>/channel.json"; exit 1; }
	@$(PYTHON) -m studio.inventory $(CHANNEL) --prune casting $(if $(APPLY),--apply,)

prune-brand:
	@test -n "$(CHANNEL)" || { echo "Set CHANNEL=channels/<slug>/channel.json"; exit 1; }
	@$(PYTHON) -m studio.inventory $(CHANNEL) --prune brand $(if $(APPLY),--apply,)

prune-legacy:
	@test -n "$(CHANNEL)" || { echo "Set CHANNEL=channels/<slug>/channel.json"; exit 1; }
	@$(PYTHON) -m studio.inventory $(CHANNEL) --prune legacy-look $(if $(APPLY),--apply,)
