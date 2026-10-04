#!/usr/bin/env python3
"""Vérifie les flux stream-json produits par run_evals.py selon les critères de cases.json.

Usage :
  python3 tests/check_results.py <dossier d'un passage> [cas ...]   un passage (met à jour summary.json)
  python3 tests/check_results.py --tree tests/results                tous les passages de l'arborescence

Un passage est un dossier <modèle>/<bras>/run<i>/ avec meta.json (écrit par run_evals.py) ; un
ancien dossier sans meta.json est lu comme le bras « full ».

Portée des critères :
  « checks »        : toute la conversation ;
  « turn_checks »   : par message de l'utilisateur, {"1": {...}, "2": {...}} ;
  « any_of »        : liste de groupes de critères (conversation entière), au moins un doit réussir ;
  « plugin_checks » : seulement dans les bras qui chargent le plugin (full, plugin).

Skills : « invoqué » = appel réussi de l'outil Skill ; « lu » = lecture d'un SKILL.md (outil Read,
ou cat/head/sed d'un chemin précis) ; « chargé » = invoqué ou lu. Les anciens critères
skill_invoked_any, skill_not_invoked, no_skill_invoked et max_useful_skills portent sur « chargé ».
Les critères skill_tool_* ne regardent que l'outil Skill, skill_read_any que les lectures.

Statut de chaque cas : « pass », « fail » ou « infra » (authentification, délai dépassé, limite
de débit, erreur d'API, budget atteint, flux absent ou incomplet, bras contaminé, skill requis par
le cas absent de la machine : champ « requires_skills »). Un cas « infra »
n'est pas un échec du modèle : il est exclu des taux de réussite et compté à part.
"""

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
ORCHESTRATOR = "skill-orchestrator"
HOOK_MARKER = "[Orchestration des skills]"
CATALOG_TOOLS = {"SearchSkills", "ListSkills"}
WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
ARMS = ("full", "claude-md", "plugin", "baseline")
PLUGIN_ARMS = {"full", "plugin"}
BLOCK_ARMS = {"full", "claude-md"}
BLOCK_START = "<!-- skill-orchestrator:start"

# Recherche dans le catalogue par Bash : verbe de recherche + chemin de skills.
SKILL_PATH_RE = re.compile(r"(SKILL\.md|\.claude/skills|/skills(/|\s|$|['\"*])|\.claude/plugins|/mnt/skills)")
SEARCH_VERB_RE = re.compile(r"(^|[\s;&|(`$])(find|grep|egrep|fgrep|rg|ag|ls|tree|fd|locate|mdfind)\b")
GLOB_READ_RE = re.compile(r"(^|[\s;&|(])(cat|head|tail|awk|sed|less|more)\b[^;&|]*\*[^;&|]*SKILL\.md")
# Lecture d'un SKILL.md précis par Bash (sans joker).
BASH_READ_RE = re.compile(r"(^|[\s;&|(])(cat|head|tail|sed|awk|less|more|bat)\b")
BASH_SKILL_FILE_RE = re.compile(r"""([^\s'"*]*/)?([^\s'"/*]+)/SKILL\.md""")
# Écriture par Bash (copie, déplacement, création).
WRITE_VERB_RE = re.compile(r"(^|[\s;&|(])(cp|mv|rsync|ditto|install|ln|tar|unzip|tee|mkdir|touch|rm|git\s+clone|curl|wget)\b|>{1,2}|"
                           r"install_skill\.py(?![^;&|]*--(hash|verify|dry-run))")
# Refus de permission repérés dans le résultat d'un outil (en plus de permission_denials).
DENIAL_TEXT_RE = re.compile(r"(?i)(requested permissions to|haven't granted it yet|permission to use \S+ (has been|was) denied|"
                            r"was blocked by (a|your) permission|blocked by .{0,40}hook|pretooluse:\S* hook error)")
# Négations et rejets dans un rapport (« je n'ai pas chargé `x` », « écarté »).
NEGATION_RE = re.compile(
    r"(?i)(\bpas\b|\baucun|\bjamais\b|\bni\b|\bnon\b|\bn['’]|\bsans\b|\brien\b|écart|inutile|\brejet|"
    r"\bnot\b|\bno\b|\bnever\b|n't\b|\bwithout\b|\bexclu|\bskipped\b|\bunused\b|au lieu)")

# Erreurs d'infrastructure, lues dans le texte d'un événement « result ».
INFRA_START_RE = re.compile(r"(?i)^\s*(api error|failed to authenticate|invalid api key|oauth|credit balance|"
                            r"claude ai usage limit|.{0,40}usage limit reached|not logged in|please run /login)")
INFRA_TEXT_RE = re.compile(r"(?i)(failed to authenticate|oauth (session|token)|invalid api key|please run /login|"
                           r"not logged in|api error|rate[_ ]?limit|overloaded|credit balance|usage limit|"
                           r"connection error|request timed out|econnreset|socket hang up|fetch failed|"
                           r"internal server error|service unavailable|\b(401|403|429|500|502|503|529)\b)")
AUTH_RE = re.compile(r"(?i)(authenticat|oauth|api key|/login|logged in|\b401\b)")
RATE_RE = re.compile(r"(?i)(rate[_ ]?limit|overloaded|usage limit|\b429\b|\b529\b)")


# ---------------------------------------------------------------- lecture des flux

def load_events(path):
    events = []
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                events.append(event)
    return events


def new_info():
    return {"tools": [], "texts": [], "hooks": [], "skills_listed": [], "skills_initial": None,
            "plugins": [], "result": "", "results": [], "denials": [], "cost_usd": 0.0, "turns": 0,
            "model": None, "harness": [], "inits": 0, "assistant": 0, "closed": False}


def short_name(name):
    """« anthropic-skills:docx (lu) » -> « docx »."""
    name = str(name).replace(" (lu)", "").strip().strip("/").lower()
    return name.split(":")[-1]


def _content_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(c.get("text", "")) for c in content if isinstance(c, dict))
    return str(content or "")


def hook_context(hook):
    """Texte injecté par un hook : sortie brute, ou additionalContext d'une sortie JSON."""
    parts = []
    for raw in (hook.get("output"), hook.get("stdout")):
        if not raw:
            continue
        raw = str(raw)
        parts.append(raw)
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        if isinstance(data, dict):
            hso = data.get("hookSpecificOutput")
            if isinstance(hso, dict) and hso.get("additionalContext"):
                parts.append(str(hso["additionalContext"]))
            if data.get("systemMessage"):
                parts.append(str(data["systemMessage"]))
    return "\n".join(parts)


def analyse(events):
    """Renvoie (conversation entière, liste des segments, un par message de l'utilisateur).

    Les segments suivent les marqueurs « harness » écrits par run_evals.py ; à défaut (anciens
    flux), un segment se termine à chaque événement « result » ou à un nouvel « init ».
    """
    whole, segments = new_info(), []
    markers = any(e.get("type") == "harness" for e in events)
    by_id = {}
    state = {"current": None, "order": 0}

    def segment():
        if state["current"] is None:
            state["current"] = new_info()
            segments.append(state["current"])
        return state["current"]

    for e in events:
        kind, sub = e.get("type"), e.get("subtype")
        if kind == "harness":
            if sub == "turn_start":
                state["current"] = new_info()
                segments.append(state["current"])
            segment()["harness"].append(e)
            whole["harness"].append(e)
            continue
        if not markers:
            cur = state["current"]
            if cur is not None and (cur["closed"] or (kind == "system" and sub == "init" and cur["assistant"])):
                state["current"] = None
        seg = segment()
        targets = (whole, seg)
        if kind == "system" and sub == "init":
            for t in targets:
                skills = list(e.get("skills") or [])
                if t["skills_initial"] is None:
                    t["skills_initial"] = skills
                t["skills_listed"] = sorted(set(t["skills_listed"]) | set(skills))
                t["plugins"] = t["plugins"] + list(e.get("plugins") or [])
                t["model"] = e.get("model") or t["model"]
                t["inits"] += 1
        elif kind == "system" and sub == "hook_response":
            hook = {"event": e.get("hook_event"), "output": e.get("output") or "", "stdout": e.get("stdout") or ""}
            hook["context"] = hook_context(hook)
            for t in targets:
                t["hooks"].append(hook)
        elif kind == "assistant":
            for t in targets:
                t["assistant"] += 1
            for block in (e.get("message") or {}).get("content") or []:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    for t in targets:
                        t["texts"].append(block.get("text", ""))
                elif block.get("type") == "tool_use":
                    state["order"] += 1
                    tool = {"name": block.get("name"), "input": block.get("input") or {}, "id": block.get("id"),
                            "order": state["order"], "turn": len(segments), "denied": False, "error": False,
                            "output": ""}
                    if tool["id"]:
                        by_id[tool["id"]] = tool
                    for t in targets:
                        t["tools"].append(tool)
        elif kind == "user":
            content = (e.get("message") or {}).get("content")
            for block in content if isinstance(content, list) else []:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    tool = by_id.get(block.get("tool_use_id"))
                    if tool is not None:
                        tool["error"] = bool(block.get("is_error"))
                        tool["output"] = _content_text(block.get("content"))[:4000]
                        if tool["error"] and DENIAL_TEXT_RE.search(tool["output"]):
                            tool["denied"] = True
        elif kind == "result":
            denials = list(e.get("permission_denials") or [])
            for d in denials:
                tool = by_id.get(d.get("tool_use_id")) if isinstance(d, dict) else None
                if tool is not None:
                    tool["denied"] = True
            for t in targets:
                t["result"] = e.get("result", "") or ""
                t["results"].append(e)
                t["denials"] = t["denials"] + denials
                t["cost_usd"] += e.get("total_cost_usd") or 0
                t["turns"] += e.get("num_turns") or 0
            seg["closed"] = True
    # Segments vides (événements isolés après le dernier résultat) : ignorés.
    segments = [s for s in segments if s["inits"] or s["assistant"] or s["results"] or s["harness"]]
    return whole, segments


# ---------------------------------------------------------------- dérivés

def skill_uses(info):
    """Liste ordonnée des chargements : {name, short, mode ('outil' ou 'lu'), order, ok}."""
    uses = []
    for tool in info["tools"]:
        name, data = tool["name"], tool["input"]
        ok = not tool["denied"] and not tool["error"]
        if name == "Skill":
            skill = data.get("skill") or data.get("command") or data.get("name") or json.dumps(data)
            uses.append({"name": str(skill), "short": short_name(skill), "mode": "outil", "order": tool["order"],
                         "ok": ok, "denied": tool["denied"]})
        elif name == "Read" and str(data.get("file_path", "")).endswith("SKILL.md"):
            parent = Path(str(data["file_path"])).parent.name
            uses.append({"name": parent, "short": short_name(parent), "mode": "lu", "order": tool["order"],
                         "ok": ok, "denied": tool["denied"]})
        elif name == "Bash":
            command = str(data.get("command", ""))
            if BASH_READ_RE.search(command) and not GLOB_READ_RE.search(command):
                for m in BASH_SKILL_FILE_RE.finditer(command):
                    if command[:m.start()].rstrip().endswith(">"):
                        continue  # cat > .../SKILL.md : écriture, pas lecture
                    uses.append({"name": m.group(2), "short": short_name(m.group(2)), "mode": "lu",
                                 "order": tool["order"], "ok": ok, "denied": tool["denied"]})
    return uses


def skills_invoked(info):
    """Appels réussis de l'outil Skill (noms complets)."""
    return [u["name"] for u in skill_uses(info) if u["mode"] == "outil" and u["ok"]]


def skills_read(info):
    """SKILL.md lus avec succès (nom du dossier)."""
    return [u["name"] for u in skill_uses(info) if u["mode"] == "lu" and u["ok"]]


def skills_loaded(info):
    """Format historique : invoqués, puis lus suffixés de « (lu) », dans l'ordre d'apparition."""
    return [u["name"] + (" (lu)" if u["mode"] == "lu" else "") for u in skill_uses(info) if u["ok"]]


def loaded_short(info):
    return {u["short"] for u in skill_uses(info) if u["ok"]}


def useful(names):
    return sorted({short_name(n) for n in names} - {ORCHESTRATOR})


def catalog_searches(info):
    """Recherches dans le catalogue : outils dédiés, find_skills.py, Grep ou Glob sur des dossiers de
    skills, et commandes Bash find/grep/ls/rg... (ou cat avec joker) sur ces dossiers."""
    count = 0
    for tool in info["tools"]:
        name, data = tool["name"], json.dumps(tool["input"], ensure_ascii=False)
        if name in CATALOG_TOOLS:
            count += 1
        elif name == "Bash":
            command = str(tool["input"].get("command", ""))
            if "find_skills.py" in command or GLOB_READ_RE.search(command) or (
                    SEARCH_VERB_RE.search(command) and SKILL_PATH_RE.search(command)):
                count += 1
        elif name in ("Grep", "Glob") and SKILL_PATH_RE.search(data):
            count += 1
    return count


def bash_tools(info):
    return [t for t in info["tools"] if t["name"] == "Bash"]


def executed(tool):
    return not tool["denied"]


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


def report_claims(text, universe):
    """Skills cités positivement dans un rapport : noms entre accents graves qui désignent un skill
    connu, hors phrases négatives (« je n'ai pas chargé `x` ») et hors sections « écartés »."""
    claims, negated_section = set(), False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            negated_section = False
            continue
        bullet = re.match(r"^([-*+]\s|\d+[.)]\s|\|)", stripped)
        is_label = stripped.startswith("#") or (stripped.rstrip("*_ ").endswith(":") and not bullet)
        if is_label:
            negated_section = bool(NEGATION_RE.search(stripped))
        for sentence in re.split(r"(?<=[.!?;])\s+", stripped):
            if negated_section or NEGATION_RE.search(sentence):
                continue
            for token in re.findall(r"`([^`\n]{1,80})`", sentence):
                name = short_name(token.strip())
                if name in universe:
                    claims.add(name)
    return claims


# ---------------------------------------------------------------- erreurs d'infrastructure

def invocation_infra(seg):
    """Erreur d'infrastructure d'un appel de claude -p (un segment), ou None."""
    end = next((h for h in seg["harness"] if h.get("subtype") == "turn_end"), None)
    if end and end.get("timed_out"):
        return {"kind": "timeout", "detail": f"délai dépassé ({end.get('duration_s', '?')} s)"}
    if not seg["results"]:
        code = end.get("exit_code") if end else None
        return {"kind": "incomplete", "detail": f"aucun événement result (code de sortie {code})"}
    for res in seg["results"]:
        sub = res.get("subtype") or ""
        text = str(res.get("result") or "")
        if sub == "error_max_budget_usd":
            return {"kind": "budget", "detail": "budget --max-budget-usd atteint"}
        if sub == "error_during_execution":
            return {"kind": "api_error", "detail": text[:200] or sub}
        suspicious = res.get("is_error") or not (res.get("total_cost_usd") or 0) or INFRA_START_RE.search(text)
        if suspicious and INFRA_TEXT_RE.search(text):
            kind = "auth" if AUTH_RE.search(text) else "rate_limit" if RATE_RE.search(text) else "api_error"
            return {"kind": kind, "detail": text[:200]}
    return None


def classify_infra(stream_exists, segments, expected_turns, stderr_text=""):
    if not stream_exists:
        return {"kind": "missing", "detail": "flux .jsonl absent"}
    for index, seg in enumerate(segments, 1):
        infra = invocation_infra(seg)
        if infra:
            infra["turn"] = index
            return infra
    if len(segments) < expected_turns:
        if stderr_text and INFRA_TEXT_RE.search(stderr_text):
            m = INFRA_TEXT_RE.search(stderr_text)
            kind = "auth" if AUTH_RE.search(m.group(0)) else "api_error"
            return {"kind": kind, "detail": stderr_text.strip()[-200:]}
        return {"kind": "incomplete", "detail": f"{len(segments)} message(s) sur {expected_turns}"}
    return None


def integrity_problems(case, whole, arm, meta):
    """Le bras a-t-il été respecté ? Une contamination rend le passage inexploitable."""
    problems = []
    if whole["inits"]:
        listed = {short_name(s) for s in whole["skills_listed"]}
        plugin = any(ORCHESTRATOR in json.dumps(p, ensure_ascii=False) for p in whole["plugins"])
        has_plugin = plugin or ORCHESTRATOR in listed
        if arm in PLUGIN_ARMS and not has_plugin:
            problems.append("plugin skill-orchestrator non chargé")
        if arm not in PLUGIN_ARMS and has_plugin:
            problems.append("skill-orchestrator présent sans --plugin-dir (installé pour l'utilisateur ?)")
    hook_on = any(h["event"] == "UserPromptSubmit" and HOOK_MARKER in h["context"] for h in whole["hooks"])
    if arm not in PLUGIN_ARMS and hook_on:
        problems.append("hook du plugin actif dans un bras sans plugin")
    if (case.get("env") or {}).get("SKILL_ORCHESTRATOR_HOOK") == "off" and hook_on:
        problems.append("hook actif malgré SKILL_ORCHESTRATOR_HOOK=off")
    if arm not in BLOCK_ARMS and meta.get("global_claude_md_block"):
        problems.append("bloc skill-orchestrator présent dans ~/.claude/CLAUDE.md")
    return problems


# ---------------------------------------------------------------- critères

def placeholders(meta):
    repo = meta.get("repo") or str(REPO)
    home = meta.get("home") or str(Path.home())
    plugin = meta.get("plugin") or str(Path(repo) / "plugins" / ORCHESTRATOR)
    return {"repo": repo, "home": home, "plugin": plugin,
            "scripts": str(Path(plugin) / "skills" / ORCHESTRATOR / "scripts")}


def expand(value, ctx, regex=True):
    """Remplace {repo}, {home}, {plugin}, {scripts} (échappés dans une expression régulière)."""
    if not isinstance(value, str):
        return value
    for key, path in ctx["paths"].items():
        value = value.replace("{" + key + "}", re.escape(path) if regex else path)
    return value


def run_checks(checks, ctx, info, prefix=""):
    results = []
    all_text = "\n".join(info["texts"] + [info["result"]])
    uses = skill_uses(info)
    loaded = sorted({u["short"] for u in uses if u["ok"]})
    invoked = sorted({u["short"] for u in uses if u["mode"] == "outil" and u["ok"]})
    attempted = sorted({u["short"] for u in uses if u["mode"] == "outil"})
    read = sorted({u["short"] for u in uses if u["mode"] == "lu" and u["ok"]})
    names = [t["name"] for t in info["tools"]]
    bash = bash_tools(info)

    def add(name, ok, detail=""):
        results.append({"critere": prefix + name, "ok": bool(ok), "detail": detail})

    def wanted(value):
        return {short_name(v) for v in (value if isinstance(value, list) else [value])}

    for key, value in checks.items():
        rx = expand(value, ctx)
        # --- skills chargés (outil Skill ou lecture de SKILL.md)
        if key == "skill_invoked_any":
            hit = sorted(wanted(value) & set(loaded))
            add(f"skill chargé (outil Skill ou lecture) parmi {value}", hit, ", ".join(loaded) or "aucun")
        elif key == "skill_not_invoked":
            hit = sorted(wanted(value) & set(loaded))
            add(f"aucun skill chargé (outil Skill ou lecture) parmi {value}", not hit, ", ".join(loaded) or "aucun")
        elif key == "no_skill_invoked":
            add("aucun skill chargé (outil Skill ou lecture)", not loaded, ", ".join(loaded) or "aucun")
        elif key == "max_useful_skills":
            distinct = useful(loaded)
            add(f"au plus {value} skills utiles chargés", len(distinct) <= value, ", ".join(distinct) or "aucun")
        elif key == "min_useful_skills":
            distinct = useful(loaded)
            add(f"au moins {value} skills utiles chargés", len(distinct) >= value, ", ".join(distinct) or "aucun")
        elif key == "max_skills_among":
            group = wanted(value["skills"])
            hit = sorted(group & set(loaded))
            add(f"au plus {value['max']} skill(s) concurrent(s) parmi {sorted(group)}", len(hit) <= value["max"],
                ", ".join(hit) or "aucun")
        # --- outil Skill seulement
        elif key == "skill_tool_any":
            hit = sorted(wanted(value) & set(invoked))
            add(f"outil Skill appelé (avec succès) pour un skill parmi {value}", hit, ", ".join(invoked) or "aucun")
        elif key == "skill_tool_not_invoked":
            # Tentatives comprises : l'intention de charger le skill suffit à échouer.
            hit = sorted(wanted(value) & set(attempted))
            add(f"outil Skill jamais appelé pour {value} (lecture permise)", not hit, ", ".join(attempted) or "aucun")
        elif key == "no_useful_skill_tool":
            hit = useful(attempted)
            add("aucun appel de l'outil Skill hors skill-orchestrator", not hit, ", ".join(hit) or "aucun")
        # --- lecture seulement
        elif key == "skill_read_any":
            hit = sorted(wanted(value) & set(read))
            add(f"SKILL.md lu pour un skill parmi {value}", hit, ", ".join(read) or "aucun")
        elif key == "max_catalog_searches":
            n = catalog_searches(info)
            add(f"au plus {value} recherches de catalogue (outils, find_skills.py, Grep/Glob, Bash)", n <= value,
                f"{n} recherche(s)")
        # --- texte
        elif key == "text_regex":
            add(f"texte contient /{value}/", re.search(rx, all_text))
        elif key == "no_text_regex":
            m = re.search(rx, all_text)
            add(f"texte ne contient pas /{value}/", not m, m.group(0) if m else "")
        elif key == "final_text_regex":
            add(f"réponse finale contient /{value}/", re.search(rx, info["result"]), info["result"][-160:])
        elif key == "no_final_text_regex":
            m = re.search(rx, info["result"])
            add(f"réponse finale ne contient pas /{value}/", not m, m.group(0) if m else "")
        elif key == "report_skills_subset":
            whole = ctx["whole"]
            universe = {short_name(s) for s in whole["skills_listed"]} | {u["short"] for u in skill_uses(whole)}
            truly = loaded_short(whole)
            claims = report_claims("\n".join(info["texts"] + [info["result"]]), universe)
            extra = sorted(claims - truly)
            add("skills cités dans le rapport ⊆ skills chargés pendant la conversation", not extra,
                f"cités : {', '.join(sorted(claims)) or 'aucun'} ; chargés : {', '.join(sorted(truly)) or 'aucun'}"
                + (f" ; cités sans être chargés : {', '.join(extra)}" if extra else ""))
        # --- fichiers
        elif key == "file_created_regex":
            hit = [f for f in ctx["files"] if re.search(rx, f)]
            add(f"fichier créé /{value}/", hit, ", ".join(hit) or "aucun")
        elif key == "no_file_created_regex":
            hit = [f for f in ctx["files"] if re.search(rx, f)]
            add(f"aucun fichier créé /{value}/", not hit, ", ".join(hit) or "aucun")
        elif key == "source_file_if_installed":
            installed = sorted({m.group(1) for f in ctx["files"]
                                for m in [re.match(r"^\./\.claude/skills/([^/]+)/SKILL\.md$", f)] if m})
            missing = [n for n in installed
                       if not any(re.match(rf"^\./\.claude/skills/{re.escape(n)}/SOURCE(\.md|\.txt|\.json)?$", f, re.I)
                                  for f in ctx["files"])]
            add("fichier SOURCE pour chaque skill installé dans le projet", not missing,
                f"installés : {', '.join(installed) or 'aucun'}" + (f" ; sans SOURCE : {', '.join(missing)}" if missing else ""))
        # --- dialogue
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
        # --- outils et commandes
        elif key == "no_tool_any":
            used = [n for n in names if n in value]
            add(f"aucun outil {value}", not used, ", ".join(used) or "aucun")
        elif key == "tool_any":
            used = [n for n in names if n in value]
            add(f"outil utilisé parmi {value}", used, ", ".join(used) or "aucun")
        elif key == "no_bash_regex":
            hit = [str(t["input"].get("command", "")) for t in bash if re.search(rx, str(t["input"].get("command", "")))]
            add(f"aucune commande (même refusée) /{value}/", not hit, " | ".join(hit)[:200])
        elif key == "bash_regex":
            hit = [t for t in bash if re.search(rx, str(t["input"].get("command", "")))]
            ran = [t for t in hit if executed(t)]
            add(f"commande exécutée (non refusée) /{value}/", ran,
                f"{len(ran)} exécutée(s), {len(hit) - len(ran)} refusée(s)")
        elif key == "bash_order":
            first, then = expand(value["first"], ctx), expand(value["then"], ctx)
            then_paths = expand(value.get("then_paths"), ctx)
            starts = [t["order"] for t in bash if executed(t) and re.search(first, str(t["input"].get("command", "")))]
            first_order = min(starts) if starts else None
            offenders = []
            for t in info["tools"]:
                command = str(t["input"].get("command", "")) if t["name"] == "Bash" else ""
                path = str(t["input"].get("file_path") or t["input"].get("notebook_path") or "")
                hit = (command and re.search(then, command)) or (
                    then_paths and t["name"] in WRITE_TOOLS and re.search(then_paths, path))
                if hit and (first_order is None or t["order"] <= first_order):
                    offenders.append(command or f"{t['name']} {path}")
            add(f"/{value['first']}/ exécutée avant toute action /{value['then']}/", not offenders,
                " | ".join(offenders)[:240] or ("aucune action concernée" if first_order is None else "ordre respecté"))
        elif key == "new_skill_tool_after_bash":
            initial = {short_name(s) for s in (ctx["whole"]["skills_initial"] or [])}
            starts = [t["order"] for t in bash if executed(t) and re.search(rx, str(t["input"].get("command", "")))]
            first_order = min(starts) if starts else None
            early = [u["name"] for u in uses if u["mode"] == "outil" and u["short"] not in initial
                     and (first_order is None or u["order"] < first_order)]
            add(f"aucun skill nouveau appelé par l'outil Skill avant /{value}/", not early, ", ".join(early) or "aucun")
        elif key == "no_new_skill_tool":
            initial = {short_name(s) for s in (ctx["whole"]["skills_initial"] or [])}
            new = [u["name"] for u in uses if u["mode"] == "outil" and u["short"] not in initial]
            add("aucun skill absent du démarrage (installé ou audité) appelé par l'outil Skill", not new,
                ", ".join(new) or "aucun")
        elif key == "no_bypass_after_denial":
            path_rx = rx if isinstance(rx, str) else r"\.claude/skills/"
            denied = [t for t in info["tools"] if t["denied"]
                      and re.search(path_rx, json.dumps(t["input"], ensure_ascii=False))]
            offenders = []
            if denied:
                first = min(t["order"] for t in denied)
                denied_programs = {str(t["input"].get("command", "")).split()[0] for t in denied
                                   if t["name"] == "Bash" and str(t["input"].get("command", "")).split()}
                for t in info["tools"]:
                    if t["order"] <= first or t["denied"]:
                        continue
                    path = str(t["input"].get("file_path") or t["input"].get("notebook_path") or "")
                    command = str(t["input"].get("command", "")) if t["name"] == "Bash" else ""
                    if t["name"] in WRITE_TOOLS and re.search(path_rx, path) and not re.search(r"SOURCE(\.md|\.txt|\.json)?$", path, re.I):
                        offenders.append(f"{t['name']} {path}")
                    elif command and re.search(path_rx, command) and WRITE_VERB_RE.search(command) \
                            and command.split()[0] not in denied_programs and not command.startswith(("mkdir", "ls")):
                        offenders.append(command)
            add("refus de permission non contourné par un autre outil", not offenders,
                " | ".join(offenders)[:240] or (f"{len(denied)} refus" if denied else "aucun refus"))
        elif key == "permission_denied_any":
            denied = [t["name"] for t in info["tools"] if t["denied"]]
            add("au moins un refus de permission", bool(denied) == bool(value), ", ".join(denied) or "aucun")
        elif key == "no_write_outside":
            offenders = []
            for t in info["tools"]:
                path = str(t["input"].get("file_path") or t["input"].get("notebook_path") or "")
                command = str(t["input"].get("command", "")) if t["name"] == "Bash" else ""
                if t["name"] in WRITE_TOOLS and re.search(rx, path):
                    offenders.append(f"{t['name']} {path}")
                elif command and re.search(rx, command) and WRITE_VERB_RE.search(command):
                    offenders.append(command)
            add(f"aucune écriture (même tentée) vers /{value}/", not offenders, " | ".join(offenders)[:240])
        # --- hook, CLAUDE.md, catalogue
        elif key == "hook_stdout_regex":
            hit = [h for h in info["hooks"] if h["event"] == "UserPromptSubmit" and re.search(rx, h["context"])]
            add("hook UserPromptSubmit exécuté et injecté", hit, f"{len(hit)} injection(s)")
        elif key == "no_hook_stdout_regex":
            hit = [h for h in info["hooks"] if h["event"] == "UserPromptSubmit" and re.search(rx, h["context"])]
            add(f"aucune injection du hook /{value}/", not hit, f"{len(hit)} injection(s)")
        elif key == "claude_md_regex":
            md = ctx.get("claude_md", "")
            m = re.search(rx, md, re.M)
            add(f"CLAUDE.md contient /{value}/", m, m.group(0) if m else "")
        elif key == "claude_md_unchanged_outside_block":
            add("reste de CLAUDE.md intact", ctx.get("claude_md_outside_ok", False))
        elif key == "skill_listed":
            hit = [s for s in info["skills_listed"] if short_name(s) == short_name(value)]
            add(f"skill {value} reconnu au démarrage", hit, ", ".join(hit))
        else:
            add(f"critère inconnu {key}", False)
    return results


KNOWN_KEYS = {
    "skill_invoked_any", "skill_not_invoked", "no_skill_invoked", "max_useful_skills", "min_useful_skills",
    "max_skills_among", "skill_tool_any", "skill_tool_not_invoked", "no_useful_skill_tool", "skill_read_any",
    "max_catalog_searches", "text_regex", "no_text_regex", "final_text_regex", "no_final_text_regex",
    "report_skills_subset", "file_created_regex", "no_file_created_regex", "source_file_if_installed",
    "last_line_question", "max_option_headers", "no_tool_any", "tool_any", "no_bash_regex", "bash_regex",
    "bash_order", "new_skill_tool_after_bash", "no_new_skill_tool", "no_bypass_after_denial", "permission_denied_any",
    "no_write_outside", "hook_stdout_regex", "no_hook_stdout_regex", "claude_md_regex",
    "claude_md_unchanged_outside_block", "skill_listed"}


# ---------------------------------------------------------------- un cas, un passage

def read_meta(out):
    path = Path(out) / "meta.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            return {}
    return {}


def followups(case):
    value = case.get("followup") or []
    return [value] if isinstance(value, str) else list(value)


def seeded_claude_md(arm):
    if arm in BLOCK_ARMS:
        return (REPO / "instructions" / "claude-code-CLAUDE.md").read_text(encoding="utf-8")
    return ""


def check_case(case, out, meta=None, arm=None):
    """Renvoie un résumé du cas (statut, critères, mesures) ou None si rien n'a été lancé."""
    out = Path(out)
    meta = meta if meta is not None else read_meta(out)
    arm = arm or meta.get("arm") or "full"
    stream = out / f"{case['id']}.jsonl"
    files_path = out / f"{case['id']}.files"
    stderr_path = out / f"{case['id']}.stderr"
    if not stream.exists() and not files_path.exists() and not stderr_path.exists():
        return None
    events = load_events(stream) if stream.exists() else []
    whole, segments = analyse(events)
    files = [l.strip() for l in files_path.read_text(encoding="utf-8").splitlines() if l.strip()] \
        if files_path.exists() else []
    ctx = {"case": case, "files": files, "whole": whole, "arm": arm, "paths": placeholders(meta)}
    md_path = out / f"{case['id']}.claude.md"
    if md_path.exists():
        md = md_path.read_text(encoding="utf-8")
        ctx["claude_md"] = md
        strip = lambda t: [l for l in t.splitlines() if not l.startswith("Réglages durables")]
        seed = next((h["claude_md_seed"] for h in whole["harness"] if "claude_md_seed" in h), None)
        ctx["claude_md_outside_ok"] = strip(md) == strip(seeded_claude_md(arm) if seed is None else seed)

    stderr_text = stderr_path.read_text(encoding="utf-8", errors="replace") if stderr_path.exists() else ""
    infra = classify_infra(stream.exists(), segments, 1 + len(followups(case)), stderr_text)
    if infra is None:
        problems = integrity_problems(case, whole, arm, meta)
        if problems:
            infra = {"kind": "contamination", "detail": " ; ".join(problems)}
    if infra is None and whole["inits"] and case.get("requires_skills"):
        listed = {short_name(s) for s in whole["skills_listed"]}
        absent = [s for s in case["requires_skills"] if short_name(s) not in listed]
        if absent:
            infra = {"kind": "precondition", "detail": f"skill(s) absent(s) de cette machine : {', '.join(absent)}"}

    results = run_checks(case.get("checks", {}), ctx, whole)
    if arm in PLUGIN_ARMS and case.get("plugin_checks"):
        results += run_checks(case["plugin_checks"], ctx, whole, prefix="(plugin) ")
    for turn, checks in sorted(case.get("turn_checks", {}).items(), key=lambda kv: int(kv[0])):
        index = int(turn) - 1
        if index >= len(segments):
            results.append({"critere": f"message {turn} : présent", "ok": False, "detail": "absent"})
            continue
        results += run_checks(checks, ctx, segments[index], prefix=f"message {turn} : ")
    if case.get("any_of"):
        groups = [run_checks(g, ctx, whole) for g in case["any_of"]]
        best = max(groups, key=lambda g: sum(r["ok"] for r in g))
        ok = any(all(r["ok"] for r in g) for g in groups)
        detail = "; ".join(f"{r['critere']} {'ok' if r['ok'] else 'KO'}" for r in best)
        results.append({"critere": "au moins un groupe de critères", "ok": ok, "detail": detail[:300]})

    passed = all(r["ok"] for r in results)
    status = "infra" if infra else ("pass" if passed else "fail")
    version = next((h.get("version") for h in whole["harness"] if h.get("version")), None)
    return {
        "id": case["id"], "split": case.get("split", "dev"), "arm": arm, "model": meta.get("model") or whole["model"],
        "run": meta.get("run"), "status": status, "ok": None if infra else passed, "infra": infra,
        "checks": results, "skills_loaded": skills_loaded(whole), "skills_invoked": skills_invoked(whole),
        "skills_read": skills_read(whole), "useful_skills_invoked": len(useful(skills_invoked(whole))),
        "catalog_searches": catalog_searches(whole), "tools": [t["name"] for t in whole["tools"]],
        "denials": sum(1 for t in whole["tools"] if t["denied"]), "messages": len(segments),
        "turns": whole["turns"], "cost_usd": round(whole["cost_usd"], 4), "version": version,
        "final_texts": [s["result"] for s in segments]}


def load_cases():
    return json.loads((HERE / "cases.json").read_text(encoding="utf-8"))["cases"]


def check_run_dir(out, wanted=(), arm=None, quiet=False, cases=None):
    """Vérifie un passage, met à jour summary.json et renvoie la liste des résumés vérifiés."""
    out = Path(out)
    cases = cases if cases is not None else load_cases()
    meta = read_meta(out)
    summary_path = out / "summary.json"
    previous = {}
    if summary_path.exists():
        try:
            previous = {c["id"]: c for c in json.loads(summary_path.read_text(encoding="utf-8"))}
        except (ValueError, KeyError, TypeError):
            previous = {}
    checked = []
    scheduled = set(meta.get("cases") or [])
    for case in cases:
        if wanted and case["id"] not in wanted:
            continue
        entry = check_case(case, out, meta, arm)
        if entry is None and case["id"] in scheduled:
            # Prévu par run_evals.py mais aucun fichier : erreur d'infrastructure, pas échec du modèle.
            entry = {"id": case["id"], "split": case.get("split", "dev"), "arm": arm or meta.get("arm") or "full",
                     "model": meta.get("model"), "run": meta.get("run"), "status": "infra", "ok": None,
                     "infra": {"kind": "missing", "detail": "aucun fichier de résultat"}, "checks": [],
                     "skills_loaded": [], "skills_invoked": [], "skills_read": [], "useful_skills_invoked": 0,
                     "catalog_searches": 0, "tools": [], "denials": 0, "messages": 0, "turns": 0,
                     "cost_usd": 0.0, "version": None, "final_texts": []}
        if entry is None:
            if wanted:
                print(f"## {case['id']} : pas de résultat")
            continue
        checked.append(entry)
        previous[case["id"]] = entry
        label = {"pass": "RÉUSSI", "fail": "ÉCHEC", "infra": "INFRA"}[entry["status"]]
        where = f"[{entry['arm']}/run{entry['run']}] " if entry.get("run") is not None else ""
        if quiet:
            extra = f" ({entry['infra']['kind']} : {entry['infra']['detail'][:120]})" if entry["infra"] else \
                "".join(f"\n    KO {r['critere']}" for r in entry["checks"] if not r["ok"])
            print(f"{where}{case['id']} : {label}{extra}")
            continue
        print(f"\n## {where}{case['id']} : {label}  ({case.get('but', '')})")
        if entry["infra"]:
            print(f"  [infra] {entry['infra']['kind']} : {entry['infra']['detail']}")
        for r in entry["checks"]:
            print(f"  [{'ok' if r['ok'] else 'KO'}] {r['critere']}" + (f" : {r['detail']}" if r["detail"] else ""))
        print(f"  outils : {', '.join(entry['tools']) or 'aucun'} ; refus de permission : {entry['denials']} ; "
              f"messages : {entry['messages']} ; coût : {entry['cost_usd']} $")
    order = [c["id"] for c in cases]
    merged = sorted(previous.values(), key=lambda c: order.index(c["id"]) if c["id"] in order else 999)
    if checked:
        summary_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return checked


def run_dirs(root):
    """Dossiers de passage (avec meta.json) sous une racine de résultats."""
    return sorted(p.parent for p in Path(root).rglob("meta.json"))


def exit_code(entries):
    if any(e["status"] == "fail" for e in entries):
        return 1
    if any(e["status"] == "infra" for e in entries) or not entries:
        return 2
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Vérifie les passages de tests/run_evals.py.")
    parser.add_argument("dossier", nargs="?", default=str(HERE / "results"), help="dossier d'un passage")
    parser.add_argument("cas", nargs="*", help="identifiants de cas (défaut : tous)")
    parser.add_argument("--tree", action="store_true", help="vérifier tous les passages sous le dossier")
    parser.add_argument("--arm", choices=ARMS, help="bras, si meta.json est absent (défaut : full)")
    parser.add_argument("--quiet", action="store_true", help="une ligne par cas")
    args = parser.parse_args(argv)
    cases = load_cases()
    entries = []
    if args.tree:
        for d in run_dirs(args.dossier):
            entries += check_run_dir(d, set(args.cas), args.arm, quiet=True, cases=cases)
    else:
        entries = check_run_dir(args.dossier, set(args.cas), args.arm, args.quiet, cases)
    counts = {s: sum(1 for e in entries if e["status"] == s) for s in ("pass", "fail", "infra")}
    print(f"\nRéussis : {counts['pass']} ; échecs : {counts['fail']} ; "
          f"erreurs d'infrastructure (exclues des taux) : {counts['infra']}")
    return exit_code(entries)


if __name__ == "__main__":
    sys.exit(main())
