# Viral Short Videos — local production shortcuts.
# A template: no channel or episode path is baked in. Values resolve from .env,
# the command line, or discovery under channels/ and episodes/.

SHELL := /bin/sh
.DEFAULT_GOAL := help

-include .env

PYTHON ?= audio-models/venv/bin/python

# An empty value in .env still falls back to discovery; a command-line value always wins.
CHANNEL := $(strip $(CHANNEL))
CHANNEL := $(if $(CHANNEL),$(CHANNEL),$(shell $(PYTHON) -m studio.project channel 2>/dev/null))
EPISODE := $(strip $(EPISODE))
EPISODE := $(if $(EPISODE),$(EPISODE),$(shell $(PYTHON) -m studio.project episode 2>/dev/null))
RENDERER := $(strip $(RENDERER))
RENDERER := $(if $(RENDERER),$(RENDERER),hyperframes)

PREVIEW_FLAG ?= --preview
SLUG := $(notdir $(patsubst %/,%,$(dir $(EPISODE))))
PREVIEW_OUT = output/$(SLUG)-preview
RENDER_OUT = output/$(SLUG)-v1
CHANNEL_ARG = $(if $(CHANNEL),--channel $(CHANNEL),)

.PHONY: help status init assets doctor list \
        validate check audio preview render \
        clean clean-cache clean-previews \
        prune-duplicates prune-casting prune-brand prune-legacy

help:
	@echo "Viral Short Videos"
	@echo
	@echo "  make status                 resolved channel, episode, and .env"
	@echo "  make init                   write .env from what is already on disk"
	@echo "  make assets                 what the channel needs, and what is optional"
	@echo "  make doctor                 check ffmpeg, node, Chrome, Kokoro"
	@echo "  make list                   channel folders and episodes"
	@echo
	@echo "  make validate  EPISODE=episodes/<slug>/episode.json"
	@echo "  make check     EPISODE=episodes/<slug>/episode.json"
	@echo "  make audio     EPISODE=episodes/<slug>/episode.json [OUT=<dir>]"
	@echo "  make preview   EPISODE=episodes/<slug>/episode.json [OUT=<dir>]"
	@echo "  make render    EPISODE=episodes/<slug>/episode.json [OUT=<dir>]"
	@echo
	@echo "  CHANNEL and EPISODE are discovered when unambiguous, else set them,"
	@echo "  pass them per call, or put them in .env (see .env.example)."
	@echo "  Overrides: CHANNEL=<manifest> RENDERER=<python|remotion|hyperframes>"
	@echo "             OUT=<dir> PREVIEW_FLAG= PYTHON=<interpreter>"
	@echo
	@echo "  make clean-cache            drop failed render staging, audio takes, __pycache__"
	@echo "  make clean-previews         drop output/*-preview packages"
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

assets:
	@test -n "$(CHANNEL)" || { echo "No channel resolved. Run make status, or set CHANNEL=channels/<slug>/channel.json"; exit 1; }
	@$(PYTHON) -m studio.inventory $(CHANNEL)

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
	@$(PYTHON) video.py audio $(EPISODE) $(CHANNEL_ARG) --out $(if $(OUT),$(OUT),output/$(SLUG)-audio)

preview:
	@test -n "$(EPISODE)" || { echo "Set EPISODE=episodes/<slug>/episode.json"; exit 1; }
	@$(PYTHON) video.py render $(EPISODE) $(CHANNEL_ARG) --renderer $(RENDERER) \
		--out $(if $(OUT),$(OUT),$(PREVIEW_OUT)) $(PREVIEW_FLAG)

render:
	@test -n "$(EPISODE)" || { echo "Set EPISODE=episodes/<slug>/episode.json"; exit 1; }
	@$(PYTHON) video.py render $(EPISODE) $(CHANNEL_ARG) --renderer $(RENDERER) \
		--out $(if $(OUT),$(OUT),$(RENDER_OUT))

list:
	@echo "channels:"; ls -1 channels 2>/dev/null | sed 's/^/  /' || true
	@echo "episodes:"; ls -1 episodes 2>/dev/null | sed 's/^/  /' || true

clean-cache:
	@find output -maxdepth 1 -name '.studio-*' -type d -print -exec rm -rf {} + 2>/dev/null || true
	@find episodes -maxdepth 2 -name '.audio-takes' -type d -print -exec rm -rf {} + 2>/dev/null || true
	@find . -maxdepth 3 -name '__pycache__' -type d -prune -print -exec rm -rf {} + 2>/dev/null || true
	@echo "cache cleaned"

clean-previews:
	@find output -maxdepth 1 -name '*-preview' -type d -print -exec rm -rf {} + 2>/dev/null || true
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
