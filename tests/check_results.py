#!/usr/bin/env python3
"""Vérifie les flux stream-json produits par run-tests.sh selon les critères de cases.json.

Usage : python3 tests/check_results.py <dossier de résultats> [cas ...]
Met à jour <dossier>/summary.json et affiche un tableau réussite / échec par critère.

Critères :
  « checks »       : sur toute la conversation ;
  « turn_checks »  : par message de l'utilisateur, {"1": {...}, "2": {...}} ;
  « any_of »       : liste de groupes de critères, au moins un groupe doit réussir.
"""

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = "skill-orchestrator"
CATALOG_TOOLS = {"SearchSkills", "ListSkills"}


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


def new_info():
    return {"tools": [], "texts": [], "hooks": [], "skills_listed": [], "result": "", "denials": [],
            "cost_usd": 0.0, "turns": 0, "model": None}


def analyse(events):
    """Renvoie (conversation entière, liste des segments par message)."""
    whole, segments, current = new_info(), [], new_info()
    for e in events:
        kind, sub = e.get("type"), e.get("subtype")
        targets = (whole, current)
        if kind == "system" and sub == "init":
            for t in targets:
                t["skills_listed"] = e.get("skills", [])
                t["model"] = e.get("model")
        elif kind == "system" and sub == "hook_response":
            for t in targets:
                t["hooks"].append({"event": e.get("hook_event"), "output": e.get("output", "")})
        elif kind == "assistant":
            for block in e.get("message", {}).get("content", []):
                for t in targets:
                    if block.get("type") == "text":
                        t["texts"].append(block.get("text", ""))
                    elif block.get("type") == "tool_use":
                        t["tools"].append({"name": block.get("name"), "input": block.get("input", {})})
        elif kind == "result":
            for t in targets:
                t["result"] = e.get("result", "") or ""
                t["denials"] = t["denials"] + (e.get("permission_denials") or [])
                t["cost_usd"] += e.get("total_cost_usd") or 0
                t["turns"] += e.get("num_turns") or 0
            segments.append(current)
            current = new_info()
    return whole, segments


def skills_loaded(info):
    """Skills chargés : appel de l'outil Skill, ou lecture d'un SKILL.md."""
    loaded = []
    for tool in info["tools"]:
        if tool["name"] == "Skill":
            loaded.append(str(tool["input"].get("skill") or tool["input"].get("command") or tool["input"]))
        elif tool["name"] == "Read" and str(tool["input"].get("file_path", "")).endswith("SKILL.md"):
            loaded.append(Path(tool["input"]["file_path"]).parent.name + " (lu)")
    return loaded


def catalog_searches(info):
    """Recherches dans le catalogue : outils dédiés, find_skills.py, Grep ou Glob sur des SKILL.md."""
    count = 0
    for tool in info["tools"]:
        name, data = tool["name"], json.dumps(tool["input"], ensure_ascii=False)
        if name in CATALOG_TOOLS:
            count += 1
        elif name == "Bash" and "find_skills.py" in data:
            count += 1
        elif name in ("Grep", "Glob") and "SKILL.md" in data:
            count += 1
    return count


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


def run_checks(checks, case, info, files, prefix=""):
    results = []
    all_text = "\n".join(info["texts"] + [info["result"]])
    loaded = skills_loaded(info)
    useful = [s for s in loaded if ORCHESTRATOR not in s]
    names = [t["name"] for t in info["tools"]]
    bash = [str(t["input"].get("command", "")) for t in info["tools"] if t["name"] == "Bash"]

    def add(name, ok, detail=""):
        results.append({"critere": prefix + name, "ok": bool(ok), "detail": detail})

    for key, value in checks.items():
        if key == "skill_invoked_any":
            hit = [s for s in loaded if any(v in s for v in value)]
            add(f"skill chargé parmi {value}", hit, ", ".join(loaded) or "aucun")
        elif key == "skill_not_invoked":
            hit = [s for s in loaded if any(v in s for v in value)]
            add(f"aucun skill parmi {value}", not hit, ", ".join(loaded) or "aucun")
        elif key == "no_skill_invoked":
            add("aucun skill chargé", not loaded, ", ".join(loaded) or "aucun")
        elif key == "max_useful_skills":
            distinct = sorted(set(s.replace(" (lu)", "").split(":")[-1] for s in useful))
            add(f"au plus {value} skills utiles", len(distinct) <= value, ", ".join(distinct) or "aucun")
        elif key == "max_catalog_searches":
            n = catalog_searches(info)
            add(f"au plus {value} recherches de catalogue", n <= value, f"{n} recherche(s)")
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
            # Le dernier paragraphe (hors liste de sources finale) doit poser une question.
            lines = [l.strip() for l in info["result"].strip().splitlines() if l.strip()]
            for i in range(len(lines) - 1, -1, -1):
                if re.match(r"^(\*\*)?sources?\b", lines[i], re.I):
                    lines = lines[:i]
                    break
            # La question peut être suivie de quelques précisions (liste, valeur par défaut de contenu).
            tail = " ".join(lines[-8:])
            add("se termine par une question", "?" in tail, tail[-160:])
        elif key == "max_option_headers":
            n = option_headers(info["result"])
            add(f"au plus {value} options", 1 <= n <= value, f"{n} option(s) détectée(s)")
        elif key == "no_tool_any":
            used = [n for n in names if n in value]
            add(f"aucun outil {value}", not used, ", ".join(used) or "aucun")
        elif key == "tool_any":
            used = [n for n in names if n in value]
            add(f"outil utilisé parmi {value}", used, ", ".join(used) or "aucun")
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
        else:
            add(f"critère inconnu {key}", False)
    return results


def check_case(case, out):
    stream = out / f"{case['id']}.jsonl"
    if not stream.exists():
        return None
    whole, segments = analyse(load_events(stream))
    files_path = out / f"{case['id']}.files"
    files = files_path.read_text(encoding="utf-8").split() if files_path.exists() else []
    md_path = out / f"{case['id']}.claude.md"
    if md_path.exists():
        md = md_path.read_text(encoding="utf-8")
        case["_claude_md"] = md
        original = (HERE.parent / "instructions" / "claude-code-CLAUDE.md").read_text(encoding="utf-8")
        strip = lambda t: [l for l in t.splitlines() if not l.startswith("Réglages durables")]
        case["_claude_md_outside_ok"] = strip(md) == strip(original)

    results = run_checks(case.get("checks", {}), case, whole, files)
    for turn, checks in case.get("turn_checks", {}).items():
        index = int(turn) - 1
        if index >= len(segments):
            results.append({"critere": f"message {turn} : présent", "ok": False, "detail": "absent"})
            continue
        results += run_checks(checks, case, segments[index], files, prefix=f"message {turn} : ")
    if case.get("any_of"):
        groups = [run_checks(g, case, whole, files) for g in case["any_of"]]
        best = max(groups, key=lambda g: sum(r["ok"] for r in g))
        ok = any(all(r["ok"] for r in g) for g in groups)
        detail = "; ".join(f"{r['critere']} {'ok' if r['ok'] else 'KO'}" for r in best)
        results.append({"critere": "au moins un groupe de critères", "ok": ok, "detail": detail[:300]})
    return whole, segments, results


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "results"
    wanted = set(sys.argv[2:])
    cases = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))["cases"]
    summary_path = out / "summary.json"
    previous = {}
    if summary_path.exists():
        previous = {c["id"]: c for c in json.loads(summary_path.read_text(encoding="utf-8"))}
    all_ok = True
    for case in cases:
        if wanted and case["id"] not in wanted:
            continue
        checked = check_case(case, out)
        if checked is None:
            print(f"\n## {case['id']} : pas de résultat")
            all_ok = False
            continue
        whole, segments, results = checked
        ok = all(r["ok"] for r in results)
        all_ok &= ok
        print(f"\n## {case['id']} : {'RÉUSSI' if ok else 'ÉCHEC'}  ({case['but']})")
        for r in results:
            print(f"  [{'ok' if r['ok'] else 'KO'}] {r['critere']}" + (f" : {r['detail']}" if r["detail"] else ""))
        print(f"  outils : {', '.join(t['name'] for t in whole['tools']) or 'aucun'} ; "
              f"refus de permission : {len(whole['denials'])} ; messages : {len(segments)}")
        previous[case["id"]] = {
            "id": case["id"], "ok": ok, "checks": results, "skills_loaded": skills_loaded(whole),
            "tools": [t["name"] for t in whole["tools"]], "model": whole["model"],
            "turns": whole["turns"], "cost_usd": round(whole["cost_usd"], 4),
            "final_texts": [s["result"] for s in segments]}
    order = [c["id"] for c in cases]
    merged = sorted(previous.values(), key=lambda c: order.index(c["id"]) if c["id"] in order else 999)
    summary_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
