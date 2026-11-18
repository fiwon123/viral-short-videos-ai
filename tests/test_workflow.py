"""Guards for the agent and sandbox setup.

Each check here guards a failure that is otherwise silent: a skill one agent
never loads, a secret-file rule that quietly stops applying, a sandbox image
that is never rebuilt, a mount point the container user cannot write.
"""

import ast
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILE_MOUNTS = {"/home/devuser/.gitconfig"}


def files_under(folder):
    return {path.relative_to(folder): path.read_bytes() for path in folder.rglob("*") if path.is_file()}


class AgentSetupTests(unittest.TestCase):
    def test_skills_are_mirrored_for_every_agent(self):
        # Codex reads .agents/skills, Claude Code and opencode read .claude/skills.
        # A skill in one folder only is a skill one agent never loads; two copies
        # that differ give two agents different instructions under one name.
        codex, claude = files_under(ROOT / ".agents" / "skills"), files_under(ROOT / ".claude" / "skills")
        self.assertTrue(codex, "no skills under .agents/skills")
        self.assertEqual(sorted(codex), sorted(claude),
                         "copy .agents/skills to .claude/skills (or the reverse) so both folders match")
        changed = [str(name) for name in codex if codex[name] != claude[name]]
        self.assertEqual(changed, [], "these skill files differ between .agents/skills and .claude/skills")

    def test_claude_imports_every_instruction_file(self):
        # Claude Code reads only CLAUDE.md; an instruction it does not import
        # reaches every agent but Claude.
        imports = set(re.findall(r"^@(\S+)$", (ROOT / "CLAUDE.md").read_text(), re.M))
        wanted = {"AGENTS.md"} | {f".opencode/instructions/{p.name}" for p in (ROOT / ".opencode" / "instructions").glob("*.md")}
        self.assertEqual(wanted - imports, set())

    def test_secret_files_are_denied(self):
        deny = json.loads((ROOT / ".claude" / "settings.json").read_text())["permissions"]["deny"]
        for rule in ("Read(**/.env)", "Read(**/.env.*)", "Read(**/.envrc)", "Edit(**/.env)", "Bash(printenv)", "Bash(env)"):
            self.assertIn(rule, deny)
        config = json.loads((ROOT / "opencode.json").read_text())
        for namespace in ("read", "edit"):
            self.assertEqual(config["permission"][namespace].get("*.env"), "deny")
            self.assertEqual(config["permission"][namespace].get("*.env.*"), "deny")

    def test_every_opencode_agent_has_one_prompt(self):
        agents = json.loads((ROOT / "opencode.json").read_text())["agent"]
        for name, spec in agents.items():
            self.assertTrue((ROOT / ".opencode" / "agents" / f"{name}.md").is_file(), name)
            self.assertNotIn("prompt", spec, f"{name}: the prompt lives in .opencode/agents/{name}.md only")


class SandboxTests(unittest.TestCase):
    def setUp(self):
        self.dockerfile = (ROOT / "Dockerfile").read_text()

    def image_inputs(self):
        make = re.search(r"^IMAGE_INPUTS \?= (.+)$", (ROOT / "sandbox.mk").read_text(), re.M).group(1).split()
        tree = ast.parse((ROOT / "scripts" / "dev-up.py").read_text())
        launcher = next(ast.literal_eval(node.value) for node in ast.walk(tree)
                        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "IMAGE_INPUTS")
        return make, launcher

    def test_image_inputs_match_and_cover_every_copy(self):
        # dev-up never rebuilds: an image input left out of the hash is an edit
        # that keeps running the old image.
        make, launcher = self.image_inputs()
        self.assertEqual(make, launcher, "sandbox.mk and scripts/dev-up.py must hash the same files in the same order")
        copied = {src for line in re.findall(r"^COPY (.+)$", self.dockerfile, re.M) for src in line.split()[:-1]}
        self.assertIn("Dockerfile", make)
        self.assertEqual(copied - set(make), set(), "add these COPY sources to IMAGE_INPUTS")

    def test_mount_points_exist_in_the_image(self):
        # Docker creates a missing mount destination as root; the container runs
        # as the host uid and then cannot write it.
        destinations = set()
        for name in ("docker-compose.yml", "docker-compose.agent.yml"):
            destinations.update(re.findall(r":(/(?:home|workspace)/[\w./-]+)", (ROOT / name).read_text()))
        self.assertTrue(destinations)
        block = re.search(r"RUN mkdir -p (.+?)\n\s*&& chown -R .+?\n(.+?)\n\n", self.dockerfile, re.S)
        created = set(re.findall(r"(/[\w./-]+)", block.group(1)))
        owned = set(re.findall(r"(/[\w./-]+)", block.group(2)))
        home = "/home/devuser"
        for target in destinations:
            if target in FILE_MOUNTS:
                # A file mount needs only its parent; the home is created and
                # chowned with the user.
                self.assertEqual(str(Path(target).parent), home, target)
                continue
            self.assertTrue(target in created or target in owned,
                            f"{target}: create it in the Dockerfile's mount-point block")
            self.assertTrue(any(target == o or target.startswith(o + "/") for o in owned),
                            f"{target}: chown it to the runtime user in the Dockerfile")

    def test_agents_are_pinned(self):
        for arg in ("OPENCODE_VERSION", "CLAUDE_CODE_VERSION", "CODEX_VERSION"):
            self.assertRegex(self.dockerfile, rf"(?m)^ARG {arg}=\d+\.\d+\.\d+$")

    def test_no_docker_socket_or_home_mount(self):
        for name in ("docker-compose.yml", "docker-compose.agent.yml"):
            text = (ROOT / name).read_text()
            self.assertNotIn("docker.sock", text)
            self.assertNotRegex(text, r"(?m)^\s*- \$\{HOST_HOME:-\$\{HOME\}\}:", "the home directory must not be mounted")


if __name__ == "__main__":
    unittest.main()
