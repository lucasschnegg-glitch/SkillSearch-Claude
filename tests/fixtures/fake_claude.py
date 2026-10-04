#!/usr/bin/env python3
"""Faux exécutable « claude » pour tester run_evals.py sans modèle (voir test_check_results.py).

Écrit un flux stream-json minimal : init (avec le plugin si --plugin-dir), réponse du hook (sauf
SKILL_ORCHESTRATOR_HOOK=off), un texte, un result. FAKE_CLAUDE_MODE=auth simule une session OAuth
expirée ; FAKE_CLAUDE_LOG=<fichier> journalise les arguments, l'entrée standard et quelques variables.
"""

import json
import os
import sys

args = sys.argv[1:]
if args[:1] == ["--version"]:
    print("0.0.0 (faux Claude Code)")
    sys.exit(0)

stdin = sys.stdin.read()  # /dev/null attendu : lecture immédiate et vide
log = os.environ.get("FAKE_CLAUDE_LOG")
if log:
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps({"args": args, "stdin": stdin, "cwd": os.getcwd(),
                            "hook": os.environ.get("SKILL_ORCHESTRATOR_HOOK"),
                            "claudecode": os.environ.get("CLAUDECODE")}, ensure_ascii=False) + "\n")


def emit(event):
    print(json.dumps(event, ensure_ascii=False), flush=True)


plugin = "--plugin-dir" in args
skills = ["anthropic-skills:xlsx", "anthropic-skills:docx"] + (["skill-orchestrator:skill-orchestrator"] if plugin else [])
emit({"type": "system", "subtype": "init", "skills": skills, "model": "faux",
      "plugins": [{"name": "skill-orchestrator", "path": args[args.index("--plugin-dir") + 1]}] if plugin else []})
if os.environ.get("FAKE_CLAUDE_MODE") == "auth":
    emit({"type": "result", "subtype": "success", "is_error": True, "total_cost_usd": 0, "num_turns": 0,
          "result": "Failed to authenticate: OAuth session expired and could not be refreshed"})
    sys.exit(1)
if plugin and "--include-hook-events" in args and os.environ.get("SKILL_ORCHESTRATOR_HOOK") != "off":
    context = "[Orchestration des skills] Si la demande est simple, réponds directement."
    out = json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": context}})
    emit({"type": "system", "subtype": "hook_response", "hook_event": "UserPromptSubmit", "output": out, "stdout": out})
answer = "391" if "17 × 23" in args[1] else "ok"
emit({"type": "assistant", "message": {"content": [{"type": "text", "text": answer}]}})
emit({"type": "result", "subtype": "success", "is_error": False, "total_cost_usd": 0.01, "num_turns": 1,
      "result": answer, "permission_denials": []})
