<!--
Claude Code reads this file; opencode and Codex read AGENTS.md directly. It
holds no rules of its own: it imports the files every other agent follows, so
the agents cannot drift apart. Add a rule to AGENTS.md or an instruction file,
never here. tests/test_workflow.py fails when an instruction file is not
imported.
-->

@AGENTS.md
@.opencode/instructions/workflow.md
@.opencode/instructions/testing.md
