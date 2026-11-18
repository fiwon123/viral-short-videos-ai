# Dev sandbox and setup targets, included by the Makefile.
#
# Two ways to run the studio:
#
#   Docker sandbox (recommended for AI agents)
#     make claude | codex | opencode    start the sandbox and run the agent in it
#     make shell                        a shell in the sandbox
#     The agent sees this checkout and nothing else of the host.
#
#   Host
#     make setup-host                   venv in audio-models/venv + node_modules
#     make models                       Kokoro voice files (shared by both modes)
#
# POSIX hosts (Linux, macOS, WSL2). Native Windows: `python scripts/dev-up.py`.

.PHONY: setup-host models dev-up dev-down dev-restart dev-shell shell dev-log dev-build reset \
        dev-agent opencode opencode-auto claude claude-auto codex codex-auto \
        agents-version agents-upgrade opencode-upgrade claude-upgrade codex-upgrade \
        dev-doctor check-image image-inputs-hash preflight check-host check-identity check-secrets check-port \
        prepare-mounts

# --- Host identity -----------------------------------------------------------
# The workspace OWNER, not the current process: GNU stat, then BSD stat, then id.
HOST_UID ?= $(shell stat -c '%u' . 2>/dev/null || stat -f '%u' . 2>/dev/null || id -u)
HOST_GID ?= $(shell stat -c '%g' . 2>/dev/null || stat -f '%g' . 2>/dev/null || id -g)
HOST_HOME ?= $(HOME)
export HOST_UID HOST_GID HOST_HOME

# A system Python for the host-side helpers (setup-host, agents-upgrade). PYTHON
# itself is the studio's venv, which may not exist yet.
HOST_PYTHON ?= $(shell command -v python3 2>/dev/null || command -v python 2>/dev/null)

# --- Agents --------------------------------------------------------------------
# Plain targets ask before acting. The -auto targets do not: the container is the
# boundary. .env is an empty read-only file inside it (docker-compose.yml), so
# no agent can read the keys in any mode — Codex included, which has no file
# deny list of its own — and check-secrets refuses to start while any other
# secret file is in the checkout. Extra flags for one run:
# make claude AGENT_ARGS="--model sonnet".
OPENCODE_CMD      ?= opencode
OPENCODE_AUTO_CMD ?= opencode --auto
CLAUDE_CMD        ?= claude
CLAUDE_AUTO_CMD   ?= claude --dangerously-skip-permissions
CODEX_CMD         ?= codex --sandbox danger-full-access
CODEX_AUTO_CMD    ?= codex --dangerously-bypass-approvals-and-sandbox
AGENT_ARGS        ?=

COMPOSE_UP := docker compose -f docker-compose.yml -f docker-compose.agent.yml

# --- Is the dev image current? -------------------------------------------------
# The Dockerfile and every file it COPYs, in this order. scripts/dev-up.py hashes
# the same list. dev-up never rebuilds; a stale image is refused by name.
IMAGE_INPUTS ?= Dockerfile requirements.txt requirements-voice.txt package.json package-lock.json scripts/dev-sandbox-rc.sh
IMAGE_INPUTS_HASH = $(shell cat $(IMAGE_INPUTS) 2>/dev/null | { sha256sum 2>/dev/null || shasum -a 256; } | cut -c1-16)
DEV_IMAGE ?= $(shell sed -n 's/^name:[[:space:]]*//p' docker-compose.yml | head -n 1)-dev

# --- Host setup ----------------------------------------------------------------
# The venv lives where the Makefile looks for it (PYTHON). uv is used when it is
# installed (it can fetch a Python 3.13 if the host has none); otherwise the
# host's python3, which must be 3.10–3.13 for the voice engine.
VENV ?= audio-models/venv

setup-host:
	@if [ -x "$(VENV)/bin/python" ]; then echo "[setup] $(VENV) exists — updating its packages."; \
	elif command -v uv >/dev/null 2>&1; then \
	  UV_PYTHON_INSTALL_DIR=audio-models/python uv venv --python 3.13 "$(VENV)"; \
	else \
	  test -n "$(HOST_PYTHON)" || { echo "ERROR: install Python 3.10-3.13 (or uv) first." >&2; exit 1; }; \
	  "$(HOST_PYTHON)" -m venv "$(VENV)"; \
	fi
	@if command -v uv >/dev/null 2>&1; then \
	  uv pip install --python "$(VENV)/bin/python" -r requirements.txt -r requirements-voice.txt; \
	else \
	  "$(VENV)/bin/python" -m pip install -r requirements.txt -r requirements-voice.txt; \
	fi
	@command -v npm >/dev/null 2>&1 || { echo "ERROR: install Node.js 22+ for the SVG and 3D renderers, then rerun." >&2; exit 1; }
	@npm ci --ignore-scripts --no-audit --no-fund
	@$(MAKE) --no-print-directory models
	@echo; echo "[setup] done. Still needed on the host: ffmpeg/ffprobe, espeak-ng, Chrome or Chromium."
	@$(MAKE) --no-print-directory doctor PYTHON="$(VENV)/bin/python" || true

# Kokoro voice files. audio-models/ is ignored and shared with the sandbox
# through the bind mount, so one download serves both modes.
KOKORO_URL ?= https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0
KOKORO_FILES ?= kokoro-v1.0.int8.onnx voices-v1.0.bin

models:
	@mkdir -p audio-models
	@for f in $(KOKORO_FILES); do \
	  if [ -s "audio-models/$$f" ]; then echo "[models] $$f present"; continue; fi; \
	  echo "[models] downloading $$f"; \
	  curl -fL --retry 3 -o "audio-models/$$f.part" "$(KOKORO_URL)/$$f" && mv "audio-models/$$f.part" "audio-models/$$f" \
	    || { rm -f "audio-models/$$f.part"; echo "ERROR: could not download $$f" >&2; exit 1; }; \
	done

# --- Preflight -----------------------------------------------------------------
preflight: check-host check-identity check-secrets check-port prepare-mounts

# The sandbox masks .env (docker-compose.yml). Any other secret file in the
# checkout would be readable by every agent in it, Codex included, so the
# sandbox refuses to start until it is moved out of the repository.
check-secrets:
	@found="$$(find . \( -path ./node_modules -o -path ./.git -o -path ./audio-models \) -prune -o \
	  \( -name '.env.*' -o -name '.envrc' -o -name '.env' \) -print 2>/dev/null \
	  | grep -v -e '^\./\.env$$' -e '\.env\.example$$' || true)"; \
	if [ -n "$$found" ]; then \
	  echo "ERROR: these files can hold secrets and would be readable inside the sandbox:" >&2; \
	  echo "$$found" | sed 's/^/         /' >&2; \
	  echo "       Only ./.env is hidden from the agents. Move the others out of the repository." >&2; \
	  exit 1; \
	fi

# The sandbox targets drive Docker from the host. Inside the sandbox there is no
# Docker (on purpose), so say where you are instead of failing on `docker`.
check-host:
	@if [ -f /.dockerenv ]; then \
	  echo "ERROR: you are already inside the sandbox. Run the studio targets directly (make test, make render ...)." >&2; exit 1; \
	fi

check-identity:
	@test "$(HOST_UID)" != "0" || { echo "ERROR: refusing to run the sandbox as UID 0; fix the checkout's ownership or set HOST_UID." >&2; exit 1; }

HOST_PORT ?= 8765

check-port:
	@if [ -n "$(HOST_PORT)" ] && [ -z "$$($(COMPOSE_UP) ps -q dev 2>/dev/null)" ] \
	   && bash -c 'exec 3<>/dev/tcp/127.0.0.1/$(HOST_PORT)' 2>/dev/null; then \
	  echo "ERROR: host port $(HOST_PORT) (make editor) is already in use." >&2; \
	  echo "       Free it, or use another: HOST_PORT=<free-port> make dev-up" >&2; \
	  exit 1; \
	fi

# Mount sources and targets the host must provide. node_modules and .env are
# mount targets inside the checkout: Docker would create a missing one on the
# host as root. An empty .env is what `make init` fills in.
prepare-mounts:
	@mkdir -p "$(HOST_HOME)/.config/gh" node_modules audio-models && touch "$(HOST_HOME)/.gitconfig"
	@[ -e .env ] || touch .env

check-image:
	@have="$$(docker image inspect --format '{{ index .Config.Labels "dev.image-inputs" }}' '$(DEV_IMAGE)' 2>/dev/null || true)"; \
	if [ -z "$$have" ]; then \
	  echo "[sandbox] no dev image yet — building it (once; several minutes)."; \
	  $(MAKE) --no-print-directory dev-build; \
	elif [ "$$have" != "$(IMAGE_INPUTS_HASH)" ]; then \
	  echo "ERROR: the dev image is out of date: it was not built from the current $(IMAGE_INPUTS)." >&2; \
	  echo "       Rebuild it: make dev-build   (agent logins are kept, they live in volumes)" >&2; \
	  exit 1; \
	fi

image-inputs-hash:
	@echo "$(IMAGE_INPUTS_HASH)"

# --- Sandbox lifecycle ---------------------------------------------------------
# The GitHub token is resolved once per command and forwarded, never stored.
dev-up: preflight check-image
	@set -e; token="$$(scripts/resolve-gh-token.sh 2>/dev/null || true)"; \
	  GH_TOKEN="$$token" GITHUB_TOKEN="$$token" $(COMPOSE_UP) up -d --force-recreate dev
	@echo "[sandbox] up. Ctrl-C stops the log stream, not the sandbox (make dev-down)."
	@$(COMPOSE_UP) logs -f dev

dev-down: check-host
	@$(COMPOSE_UP) down

dev-restart:
	@$(MAKE) --no-print-directory dev-down
	@$(MAKE) --no-print-directory dev-up

dev-log: check-host
	@$(COMPOSE_UP) logs -f dev

# The only target that rebuilds. Run it after editing anything in IMAGE_INPUTS.
dev-build: check-host check-identity
	@$(COMPOSE_UP) build --build-arg DEV_IMAGE_INPUTS=$(IMAGE_INPUTS_HASH) dev

reset: check-host
	@echo "Removing the sandbox volumes: agent logins and the container's node_modules." >&2
	@$(COMPOSE_UP) down --volumes

shell: dev-shell
opencode: dev-opencode
opencode-auto: dev-opencode-auto
claude: dev-claude
claude-auto: dev-claude-auto
codex: dev-codex
codex-auto: dev-codex-auto

# Starts the sandbox when it is not running (a running one is left alone, so an
# agent already working in it keeps its session).
define ensure_sandbox
	@if [ -z "$$($(COMPOSE_UP) ps -q dev 2>/dev/null)" ]; then \
	  echo "[sandbox] starting..."; \
	  token="$$(scripts/resolve-gh-token.sh 2>/dev/null || true)"; \
	  GH_TOKEN="$$token" GITHUB_TOKEN="$$token" $(COMPOSE_UP) up -d dev; fi
endef

dev-shell: preflight check-image
	$(ensure_sandbox)
	@$(COMPOSE_UP) exec dev zsh -l

dev-agent: preflight check-image
	@test -n "$(AGENT_CMD)" || { echo "ERROR: run an agent target (make claude, make codex-auto, ...), not dev-agent." >&2; exit 1; }
	$(ensure_sandbox)
	@bin="$(firstword $(AGENT_CMD))"; \
	 tty="-T"; if [ -t 0 ]; then tty="-it"; fi; \
	 $(COMPOSE_UP) exec $$tty dev zsh -lc "cd /workspace && if ! command -v $$bin >/dev/null; then echo \"ERROR: $$bin is not installed in this image — add it to SANDBOX_AGENTS in the Dockerfile, then make dev-build.\" >&2; exit 127; fi; exec $(AGENT_CMD) $(AGENT_ARGS)"

dev-opencode: AGENT_CMD = $(OPENCODE_CMD)
dev-opencode: dev-agent
dev-opencode-auto: AGENT_CMD = $(OPENCODE_AUTO_CMD)
dev-opencode-auto: dev-agent
dev-claude: AGENT_CMD = $(CLAUDE_CMD)
dev-claude: dev-agent
dev-claude-auto: AGENT_CMD = $(CLAUDE_AUTO_CMD)
dev-claude-auto: dev-agent
dev-codex: AGENT_CMD = $(CODEX_CMD)
dev-codex: dev-agent
dev-codex-auto: AGENT_CMD = $(CODEX_AUTO_CMD)
dev-codex-auto: dev-agent

# --- Agent versions -------------------------------------------------------------
agents-version: check-host
	@test -n "$$($(COMPOSE_UP) ps -q dev 2>/dev/null)" || { echo "ERROR: the sandbox is not running — make dev-up." >&2; exit 1; }
	@$(COMPOSE_UP) exec -T dev bash /workspace/scripts/agents-status.sh
	@if [ -n "$(HOST_PYTHON)" ]; then echo; $(HOST_PYTHON) scripts/agents-pin.py show; fi

AGENTS_TO_UPGRADE ?=
AGENT_VERSION ?=

# Rewrites the pins in the Dockerfile, rebuilds, and re-creates a running
# sandbox. Commit the Dockerfile change so everyone moves together.
agents-upgrade: preflight
	@test -n "$(HOST_PYTHON)" || { echo "ERROR: agents-upgrade needs python3 on the host." >&2; exit 1; }
	@$(HOST_PYTHON) scripts/agents-pin.py bump $(AGENTS_TO_UPGRADE) $(if $(AGENT_VERSION),--version $(AGENT_VERSION))
	@$(MAKE) --no-print-directory dev-build
	@if [ -n "$$($(COMPOSE_UP) ps -q dev 2>/dev/null)" ]; then \
	  token="$$(scripts/resolve-gh-token.sh 2>/dev/null || true)"; \
	  GH_TOKEN="$$token" GITHUB_TOKEN="$$token" $(COMPOSE_UP) up -d --force-recreate dev; \
	  $(MAKE) --no-print-directory agents-version; \
	fi

opencode-upgrade: AGENTS_TO_UPGRADE = opencode
opencode-upgrade: agents-upgrade
claude-upgrade: AGENTS_TO_UPGRADE = claude
claude-upgrade: agents-upgrade
codex-upgrade: AGENTS_TO_UPGRADE = codex
codex-upgrade: agents-upgrade

# Docker, the image, the token, the studio inside the sandbox, and each agent's
# login (by exit code only; no credential is printed).
dev-doctor: check-host
	@status=0; \
	ok()   { printf '  ok    %s\n' "$$1"; }; \
	bad()  { printf '  FAIL  %s\n' "$$1"; status=1; }; \
	note() { printf '  --    %s\n' "$$1"; }; \
	if docker info >/dev/null 2>&1; then ok "Docker is running"; else bad "Docker is not reachable — start Docker Desktop or the docker service"; fi; \
	have="$$(docker image inspect --format '{{ index .Config.Labels "dev.image-inputs" }}' '$(DEV_IMAGE)' 2>/dev/null || true)"; \
	if [ -z "$$have" ]; then note "no dev image yet — make dev-up builds it"; \
	elif [ "$$have" = "$(IMAGE_INPUTS_HASH)" ]; then ok "dev image is current"; \
	else bad "dev image is out of date — make dev-build"; fi; \
	if [ -n "$$(scripts/resolve-gh-token.sh 2>/dev/null)" ]; then ok "GitHub token available (gh works in the sandbox)"; \
	else note "no GitHub token — gh auth login on the host"; fi; \
	for f in $(KOKORO_FILES); do [ -s "audio-models/$$f" ] || note "audio-models/$$f missing — make models (needed for Kokoro voices)"; done; \
	if [ -n "$$($(COMPOSE_UP) ps -q dev 2>/dev/null)" ]; then \
	  ok "sandbox is running"; \
	  $(COMPOSE_UP) exec -T dev make --no-print-directory doctor >/dev/null && ok "studio doctor passes in the sandbox" || bad "studio doctor fails in the sandbox — make shell, then make doctor"; \
	  $(COMPOSE_UP) exec -T dev bash /workspace/scripts/agents-status.sh || status=1; \
	else note "sandbox is not running — make dev-up (the studio and logins are checked while it runs)"; fi; \
	exit $$status
