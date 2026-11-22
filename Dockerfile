# syntax=docker/dockerfile:1.6

# Dev sandbox for the studio and the AI agents that drive it.
#
# Everything a render needs is in the image: Python 3.13 with the studio and
# voice requirements, FFmpeg (libx264), eSpeak NG, Node 22 with the renderer
# packages, and Chromium for the SVG and 3D renderers. opencode, Claude Code and
# Codex are installed here too, so an agent works on the repository and nothing
# else: only the checkout is mounted, never the home directory or the Docker
# socket.
#
# Debian trixie ships Python 3.13, the newest version kokoro-onnx supports.
FROM node:26.13.1-trixie-slim

# Build-time ARGs are declared AFTER FROM: an ARG declared before it expands
# empty in every instruction below.
ARG GH_CLI_VERSION=v2.102.0
ARG TARGETARCH
# The host uid/gid, passed by docker-compose.yml so the image has a passwd entry
# and a home for the user the container runs as.
ARG HOST_UID=1000
ARG HOST_GID=1000

# --- AI coding agents, installed IN the image ---
# Pinned: an upgrade is a reviewed bump here (`make agents-upgrade` rewrites
# these lines) plus `make dev-build`. Drop an agent from SANDBOX_AGENTS to save
# image size; its `make <agent>` target then says it is not installed.
ARG SANDBOX_AGENTS="opencode claude codex"
ARG OPENCODE_VERSION=2.2.7
ARG CLAUDE_CODE_VERSION=2.1.325
ARG CODEX_VERSION=0.167.0

# Studio runtime: ffmpeg/ffprobe (Debian's build carries libx264), eSpeak NG for
# lip sync, Chromium for the browser renderers, Python for the studio itself.
# Fonts: a headless browser with no fonts renders text as nothing, and the frame
# still looks like a valid PNG. fonts-liberation answers a manifest that names
# Arial, Helvetica or Times with metric-compatible faces. A bare `sans-serif`
# resolves to DejaVu Sans here and to the host's default elsewhere (Noto Sans
# on Fedora), so a channel whose look matters names its font file.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    chromium \
    curl \
    espeak-ng \
    ffmpeg \
    fonts-dejavu-core \
    fonts-liberation \
    fonts-noto-color-emoji \
    git \
    make \
    python3 \
    python3-venv \
    zsh \
    && rm -rf /var/lib/apt/lists/*

RUN if [ -z "$TARGETARCH" ]; then \
      case "$(uname -m)" in \
        x86_64|amd64) TARGETARCH=amd64 ;; \
        aarch64|arm64) TARGETARCH=arm64 ;; \
        *) echo "Unsupported architecture: $(uname -m)" >&2; exit 1 ;; \
      esac; \
    fi \
    && curl -fsSL "https://github.com/cli/cli/releases/download/${GH_CLI_VERSION}/gh_${GH_CLI_VERSION#v}_linux_${TARGETARCH}.tar.gz" -o /tmp/gh.tar.gz \
    && tar -xzf /tmp/gh.tar.gz -C /tmp \
    && mv "/tmp/gh_${GH_CLI_VERSION#v}_linux_${TARGETARCH}/bin/gh" /usr/local/bin/gh \
    && rm -rf /tmp/gh.tar.gz "/tmp/gh_${GH_CLI_VERSION#v}_linux_${TARGETARCH}" \
    && gh --version

# --- runtime user (matches the host uid/gid from docker-compose.yml) ---
# The node base image ships a `node` user at uid 1000, the most common host uid.
# It is removed so devuser can take that uid; otherwise the shell greets the
# user as `node` with someone else's home.
RUN if getent passwd node >/dev/null; then userdel --remove node; fi \
    && if getent group node >/dev/null; then groupdel node; fi \
    && if ! getent group ${HOST_GID} >/dev/null; then groupadd --gid ${HOST_GID} devuser; fi \
    && if ! getent passwd ${HOST_UID} >/dev/null; then \
         useradd --uid ${HOST_UID} --gid ${HOST_GID} --create-home --shell /usr/bin/zsh devuser; \
       fi \
    && { getent passwd devuser >/dev/null \
         || { echo "ERROR: uid ${HOST_UID} is already used by another account, so 'devuser' cannot be created. Rebuild for a different host uid (make dev-build)." >&2; exit 1; }; } \
    && mkdir -p /home/devuser \
    && chown -R ${HOST_UID}:${HOST_GID} /home/devuser \
    && git config --system --add safe.directory /workspace

# --- Python: the studio and the voice engine, in one venv ---
COPY requirements.txt requirements-voice.txt /opt/studio/
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -r /opt/studio/requirements.txt -r /opt/studio/requirements-voice.txt

# --- Node: the renderer packages ---
# Installed at the path the node_modules volume is mounted on, so a NEW volume
# starts with them (Docker copies the image's directory into an empty volume).
# The stamp is the lockfile's hash: the entrypoint compares it with the lockfile
# in the checkout and re-runs `npm ci` when they differ, because an existing
# volume is never refreshed from a rebuilt image.
COPY package.json package-lock.json /workspace/
RUN cd /workspace \
    && npm ci --ignore-scripts --no-audit --no-fund \
    && sha256sum package-lock.json | cut -d' ' -f1 > node_modules/.package-lock.sha256 \
    && rm -rf /root/.npm

# --- the mount points, created in the image and owned by the runtime user ---
# Docker creates a missing mount destination as root, and the container runs as
# ${HOST_UID}, so the agent would die with `EACCES: permission denied` while the
# container still reports `Up`. Every destination in docker-compose*.yml is here.
RUN mkdir -p /home/devuser/.cache \
             /home/devuser/.config \
             /home/devuser/.config/gh \
             /home/devuser/.local \
             /home/devuser/.local/share \
             /home/devuser/.local/share/opencode \
             /home/devuser/.claude \
             /home/devuser/.codex \
    && chown -R ${HOST_UID}:${HOST_GID} \
         /home/devuser/.cache /home/devuser/.config /home/devuser/.local \
         /home/devuser/.claude /home/devuser/.codex /workspace/node_modules

# Codex is one static binary, installed system-wide. Every installer downloads
# to a FILE first: `curl … | bash` runs an empty script when the download fails.
RUN case " ${SANDBOX_AGENTS} " in *" codex "*) \
      case "${TARGETARCH:-$(uname -m)}" in \
        amd64|x86_64) CODEX_ARCH=x86_64 ;; \
        arm64|aarch64) CODEX_ARCH=aarch64 ;; \
        *) echo "Unsupported architecture for codex: ${TARGETARCH:-$(uname -m)}" >&2; exit 1 ;; \
      esac \
      && curl -fsSL "https://github.com/openai/codex/releases/download/rust-v${CODEX_VERSION}/codex-${CODEX_ARCH}-unknown-linux-musl.tar.gz" -o /tmp/codex.tar.gz \
      && tar -xzf /tmp/codex.tar.gz -C /tmp \
      && install -m 0755 "/tmp/codex-${CODEX_ARCH}-unknown-linux-musl" /usr/local/bin/codex \
      && rm -f /tmp/codex.tar.gz "/tmp/codex-${CODEX_ARCH}-unknown-linux-musl" \
      && codex --version ;; \
    esac

# --- prompt badge + terminal title, for devuser and root ---
COPY scripts/dev-sandbox-rc.sh /etc/profile.d/00-dev-sandbox.sh
RUN chsh -s /usr/bin/zsh root 2>/dev/null || true \
    && for rc in /root/.zshrc /root/.bashrc /root/.zprofile \
                 /home/devuser/.zshrc /home/devuser/.bashrc /home/devuser/.zprofile; do \
         printf '%s\n' '[ -f /etc/profile.d/00-dev-sandbox.sh ] && . /etc/profile.d/00-dev-sandbox.sh' >> "$rc"; \
       done \
    && chown ${HOST_UID}:${HOST_GID} \
        /home/devuser/.bashrc /home/devuser/.zshrc /home/devuser/.zprofile

USER devuser

# SANDBOX_PYTHON: the Makefile uses it in place of PYTHON (which points at the
# host venv, audio-models/venv) whatever .env says.
# STUDIO_CHROME: the browser renderers' Chrome. STUDIO_EDITOR_HOST: `make editor`
# listens on all interfaces inside the container; compose publishes the port on
# the host's 127.0.0.1 only.
# CLAUDE_CONFIG_DIR keeps Claude Code's login inside its volume (~/.claude).
ENV PATH=/opt/venv/bin:/home/devuser/.opencode/bin:/home/devuser/.local/bin:${PATH} \
    SANDBOX_PYTHON=/opt/venv/bin/python \
    STUDIO_CHROME=/usr/bin/chromium \
    STUDIO_EDITOR_HOST=0.0.0.0 \
    CLAUDE_CONFIG_DIR=/home/devuser/.claude \
    DISABLE_AUTOUPDATER=1 \
    OPENCODE_DISABLE_AUTOUPDATE=1

RUN case " ${SANDBOX_AGENTS} " in *" opencode "*) \
      curl -fsSL https://opencode.ai/v2/install -o /tmp/opencode-install.sh \
      && bash /tmp/opencode-install.sh --version "${OPENCODE_VERSION}" --no-modify-path \
      && rm -f /tmp/opencode-install.sh \
      && mkdir -p /home/devuser/.local/bin \
      && ln -sf /home/devuser/.opencode/bin/opencode /home/devuser/.local/bin/opencode \
      && opencode --version ;; \
    esac

RUN case " ${SANDBOX_AGENTS} " in *" claude "*) \
      curl -fsSL https://claude.ai/install.sh -o /tmp/claude-install.sh \
      && bash /tmp/claude-install.sh "${CLAUDE_CODE_VERSION}" \
      && rm -rf /tmp/claude-install.sh /home/devuser/.claude/downloads \
      && claude --version ;; \
    esac

WORKDIR /workspace

# A hash of the files this image is built from (IMAGE_INPUTS in sandbox.mk).
# `dev-up` does not rebuild, so the entry points compare this label with the
# files on disk and refuse a stale image instead of running it.
ARG DEV_IMAGE_INPUTS=unknown
LABEL dev.image-inputs="${DEV_IMAGE_INPUTS}"

CMD ["sleep", "infinity"]
