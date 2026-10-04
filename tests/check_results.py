#!/usr/bin/env python3
"""Vérifie les flux stream-json produits par run-tests.sh selon les critères de cases.json.

Usage : python3 tests/check_results.py <dossier de résultats> [cas ...]
Écrit <dossier>/summary.json et affiche un tableau réussite / échec par critère.
"""

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load_events(path):
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return events


def analyse(events):
    info = {"tools": [], "texts": [], "hooks": [], "skills_listed": [], "result": "", "denials": [],
            "cost_usd": None, "turns": None, "model": None}
    for e in events:
        kind, sub = e.get("type"), e.get("subtype")
        if kind == "system" and sub == "init":
            info["skills_listed"] = e.get("skills", [])
            info["model"] = e.get("model")
        elif kind == "system" and sub == "hook_response":
            info["hooks"].append({"event": e.get("hook_event"), "output": e.get("output", "")})
        elif kind == "assistant":
            for block in e.get("message", {}).get("content", []):
                if block.get("type") == "text":
                    info["texts"].append(block.get("text", ""))
                elif block.get("type") == "tool_use":
                    info["tools"].append({"name": block.get("name"), "input": block.get("input", {})})
        elif kind == "result":
            info["result"] = e.get("result", "") or ""
            info["denials"] = e.get("permission_denials", [])
            info["cost_usd"] = e.get("total_cost_usd")
            info["turns"] = e.get("num_turns")
    return info


def skills_loaded(info):
    """Skills chargés : appel de l'outil Skill, ou lecture complète d'un SKILL.md."""
    loaded = []
    for tool in info["tools"]:
        if tool["name"] == "Skill":
            loaded.append(str(tool["input"].get("skill") or tool["input"].get("command") or tool["input"]))
        elif tool["name"] == "Read" and str(tool["input"].get("file_path", "")).endswith("SKILL.md"):
            loaded.append(Path(tool["input"]["file_path"]).parent.name + " (lu)")
    return loaded


def option_headers(text):
    numbers = set()
    for line in text.splitlines():
        # Options numérotées (1., 2.) ou lettrées (A., B.), en gras ou en titre.
        m = re.match(r"^\s*(?:#{1,4}\s*)?(?:\*\*)?\s*(?:Option\s+)?([1-9]|[A-E])\s*[\.\)\-:]", line)
        # Options présentées en tableau : | **A** | ... |
        m = m or re.match(r"^\s*\|\s*(?:\*\*)?\s*(?:Option\s+)?([1-9]|[A-E])(?:\s*(?:\*\*)?\s*\||[\.\):])", line)
        if m:
            numbers.add(m.group(1))
    return len(numbers)


def run_checks(case, info, files):
    checks, results = case.get("checks", {}), []
    all_text = "\n".join(info["texts"] + [info["result"]])
    loaded = skills_loaded(info)
    names = [t["name"] for t in info["tools"]]
    bash = [str(t["input"].get("command", "")) for t in info["tools"] if t["name"] == "Bash"]

    def add(name, ok, detail=""):
        results.append({"critere": name, "ok": bool(ok), "detail": detail})

    for key, value in checks.items():
        if key == "skill_invoked_any":
            hit = [s for s in loaded if any(v in s for v in value)]
            add(f"skill chargé parmi {value}", hit, ", ".join(loaded) or "aucun")
        elif key == "no_skill_invoked":
            add("aucun skill chargé", not loaded, ", ".join(loaded) or "aucun")
        elif key == "text_regex":
            add(f"texte contient /{value}/", re.search(value, all_text))
        elif key == "no_text_regex":
            m = re.search(value, all_text)
            add(f"texte ne contient pas /{value}/", not m, m.group(0) if m else "")
        elif key == "file_created_regex":
            hit = [f for f in files if re.search(value, f)]
            add(f"fichier créé /{value}/", hit, ", ".join(hit) or "aucun")
        elif key == "no_file_created_regex":
            hit = [f for f in files if re.search(value, f)]
            add(f"aucun fichier créé /{value}/", not hit, ", ".join(hit) or "aucun")
        elif key == "last_line_question":
            # Le dernier paragraphe (hors ligne « Sources ») doit poser la question du choix.
            lines = [l.strip() for l in info["result"].strip().splitlines() if l.strip()]
            # Ignore une liste de sources finale.
            for i in range(len(lines) - 1, -1, -1):
                if re.match(r"^(\*\*)?sources?\b", lines[i], re.I):
                    lines = lines[:i]
                    break
            tail = " ".join(lines[-2:])
            add("se termine par une question", "?" in tail, tail[-160:])
        elif key == "max_option_headers":
            n = option_headers(info["result"])
            add(f"au plus {value} options", 1 <= n <= value, f"{n} option(s) détectée(s)")
        elif key == "no_tool_any":
            used = [n for n in names if n in value]
            add(f"aucun outil {value}", not used, ", ".join(used) or "aucun")
        elif key == "no_bash_regex":
            hit = [c for c in bash if re.search(value, c)]
            add(f"aucune commande /{value}/", not hit, " | ".join(hit)[:200])
        elif key == "hook_stdout_regex":
            hit = [h for h in info["hooks"] if h["event"] == "UserPromptSubmit" and re.search(value, h["output"])]
            add("hook UserPromptSubmit exécuté et injecté", hit)
        elif key == "claude_md_regex":
            md = case.get("_claude_md", "")
            m = re.search(value, md, re.M)
            add(f"CLAUDE.md contient /{value}/", m, m.group(0) if m else "")
        elif key == "claude_md_unchanged_outside_block":
            add("reste de CLAUDE.md intact", case.get("_claude_md_outside_ok", False))
        elif key == "skill_listed":
            hit = [s for s in info["skills_listed"] if value in s]
            add(f"skill {value} reconnu au démarrage", hit, ", ".join(hit))
    return results, loaded


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "results"
    wanted = set(sys.argv[2:])
    cases = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))["cases"]
    summary, all_ok = [], True
    for case in cases:
        if wanted and case["id"] not in wanted:
            continue
        stream = out / f"{case['id']}.jsonl"
        if not stream.exists():
            print(f"\n## {case['id']} : pas de résultat")
            all_ok = False
            continue
        info = analyse(load_events(stream))
        files_path = out / f"{case['id']}.files"
        files = files_path.read_text(encoding="utf-8").split() if files_path.exists() else []
        md_path = out / f"{case['id']}.claude.md"
        if md_path.exists():
            md = md_path.read_text(encoding="utf-8")
            case["_claude_md"] = md
            original = (HERE.parent / "instructions" / "claude-code-CLAUDE.md").read_text(encoding="utf-8")
            strip = lambda t: [l for l in t.splitlines() if not l.startswith("Réglages durables")]
            case["_claude_md_outside_ok"] = strip(md) == strip(original)
        results, loaded = run_checks(case, info, files)
        ok = all(r["ok"] for r in results)
        all_ok &= ok
        print(f"\n## {case['id']} : {'RÉUSSI' if ok else 'ÉCHEC'}  ({case['but']})")
        for r in results:
            print(f"  [{'ok' if r['ok'] else 'KO'}] {r['critere']}" + (f" : {r['detail']}" if r["detail"] else ""))
        print(f"  outils : {', '.join(t['name'] for t in info['tools']) or 'aucun'} ; refus de permission : {len(info['denials'])}")
        summary.append({"id": case["id"], "ok": ok, "checks": results, "skills_loaded": loaded,
                        "tools": [t["name"] for t in info["tools"]], "model": info["model"],
                        "turns": info["turns"], "cost_usd": info["cost_usd"],
                        "final_text": info["result"]})
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
