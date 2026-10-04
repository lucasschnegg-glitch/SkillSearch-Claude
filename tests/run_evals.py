#!/usr/bin/env python3
"""Lance les scénarios de tests/cases.json avec claude -p (Python 3.9+, macOS et Linux, sans dépendance).

Chaque cas ouvre une session neuve dans un projet temporaire qui contient :
  - CLAUDE.md : le bloc instructions/claude-code-CLAUDE.md (bras full et claude-md) ou un fichier vide ;
  - un dossier .claude/skills vide (pour tester l'ajout d'un skill en cours de session) ;
  - les fichiers d'entrée du cas (champ « files »).
Le plugin est chargé pour la session seulement avec --plugin-dir (bras full et plugin) : rien
n'est installé. Les messages suivants (champ « followup ») sont envoyés avec --resume.

Bras (--arm) :
  full       bloc CLAUDE.md + plugin (configuration recommandée)
  claude-md  bloc CLAUDE.md seul
  plugin     plugin seul (skill + hook), CLAUDE.md vide
  baseline   ni l'un ni l'autre : CLAUDE.md vide, pas de plugin

Résultats : <out>/<modèle>/<bras>/run<i>/<cas>.jsonl (+ .stderr, .files, .claude.md), meta.json et
summary.json par passage. Un cas déjà terminé (fichier .files présent) n'est pas relancé, sauf --force :
une session interrompue se reprend en relançant la même commande.

Les erreurs d'infrastructure (authentification, délai, limite de débit, API) sont classées à part et
exclues des taux de réussite. Une vérification préalable (un appel « ok ») arrête tout si Claude Code
n'est pas authentifié.
"""

import argparse
import concurrent.futures
import datetime
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
import check_results as checker  # noqa: E402

ARMS = checker.ARMS
PLUGIN_DIR = REPO / "plugins" / checker.ORCHESTRATOR
INSTRUCTIONS = REPO / "instructions" / "claude-code-CLAUDE.md"

# Variables d'une session Claude Code hôte (application de bureau, terminal) qui changeraient le
# comportement des sessions de test : effort, outils supplémentaires, identité de session. Les
# variables d'authentification et de proxy (ANTHROPIC_*, *_OAUTH_*, *_UUID) sont conservées.
SCRUB_ENV = (
    "CLAUDECODE", "CLAUDE_EFFORT", "CLAUDE_PID", "AI_AGENT", "CLAUDE_AGENT_SDK_VERSION", "BAGGAGE",
    "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_HOST_SESSION_ID",
    "CLAUDE_CODE_CHILD_SESSION", "CLAUDE_CODE_SESSION_ATTENDED", "CLAUDE_CODE_MESSAGING_SOCKET",
    "CLAUDE_CODE_MESSAGING_TOKEN", "CLAUDE_CODE_ENABLE_ASK_USER_QUESTION_TOOL",
    "CLAUDE_CODE_TERMINAL_MCP_TOOLS", "CLAUDE_CODE_EMIT_TOOL_USE_SUMMARIES", "CLAUDE_CODE_REPORT_FINDINGS",
    "CLAUDE_CODE_DISABLE_CRON", "CLAUDE_CODE_EAGER_FLUSH", "CLAUDE_CODE_ENABLE_SDK_FILE_CHECKPOINTING",
    "CLAUDE_PREVIEW_CLASSIFIER_FLOOR", "CLAUDE_CODE_DESKTOP_APP_VERSION", "SKILL_ORCHESTRATOR_HOOK")

LOGIN_MESSAGE = ("Claude Code n'est pas authentifié (session OAuth expirée ou absente). Ouvre un terminal, "
                 "lance `claude`, tape `/login`, puis relance cette commande.")

EXAMPLES = """exemples :
  python3 tests/run_evals.py --dry-run --arm all --split all
  python3 tests/run_evals.py --model claude-sonnet-5-5 --arm full,baseline --cases simple-sans-skill,rapport-skills
  python3 tests/run_evals.py --model claude-opus-5-5 --arm all --split all --repeat 5 --jobs 6
  python3 tests/aggregate.py tests/results
"""

_running = set()
_running_lock = threading.Lock()
_print_lock = threading.Lock()


def say(*parts):
    with _print_lock:
        print(*parts, flush=True)


# ---------------------------------------------------------------- arguments et sélection

def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Scénarios de comportement de skill-orchestrator avec claude -p.",
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=EXAMPLES)
    p.add_argument("ids", nargs="*", help="identifiants de cas (compatibilité avec run-tests.sh)")
    p.add_argument("--model", default=os.environ.get("MODEL", "claude-opus-5-5"), help="modèle (défaut : %(default)s)")
    p.add_argument("--arm", default="full", help="full, claude-md, plugin, baseline, liste séparée par des virgules, ou all")
    p.add_argument("--repeat", type=int, default=1, help="passages par cas et par bras (défaut : 1)")
    p.add_argument("--first-run", type=int, default=1, help="numéro du premier passage (pour ajouter des répétitions)")
    p.add_argument("--cases", default="", help="cas à lancer, séparés par des virgules")
    p.add_argument("--split", choices=["dev", "heldout", "all"],
                   help="dev (défaut sans --cases), heldout, all (défaut avec --cases)")
    p.add_argument("--jobs", type=int, default=int(os.environ.get("MAX_JOBS", "4")), help="sessions en parallèle")
    p.add_argument("--max-budget-usd", type=float, help="plafond de dépense par appel de claude -p")
    p.add_argument("--timeout", type=int, default=1500, help="délai par appel de claude -p, en secondes")
    p.add_argument("--out", default=os.environ.get("OUT_DIR") or str(HERE / "results"), help="racine des résultats")
    p.add_argument("--work-root", default=os.environ.get("WORK_ROOT"), help="dossier des projets temporaires")
    p.add_argument("--setting-sources", help="passé à claude (ex. project,local pour ignorer ~/.claude/settings.json)")
    p.add_argument("--claude", default=os.environ.get("CLAUDE_BIN", "claude"), help="exécutable claude")
    p.add_argument("--force", action="store_true", help="relancer les cas déjà terminés")
    p.add_argument("--dry-run", action="store_true", help="afficher les commandes sans rien lancer ni écrire")
    p.add_argument("--no-preflight", action="store_true", help="sauter l'appel de vérification préalable")
    p.add_argument("--keep-env", action="store_true", help="ne pas nettoyer les variables de la session hôte")
    p.add_argument("--allow-contamination", action="store_true",
                   help="lancer les bras sans plugin même si skill-orchestrator est installé pour l'utilisateur")
    p.add_argument("--max-infra", type=int, default=5, help="arrêt après ce nombre d'erreurs d'infrastructure")
    p.add_argument("--no-check", action="store_true", help="ne pas vérifier les résultats à la fin")
    args = p.parse_args(argv)
    if args.repeat < 1 or args.jobs < 1:
        p.error("--repeat et --jobs doivent valoir au moins 1")
    arms = ARMS if args.arm == "all" else tuple(a.strip() for a in args.arm.split(",") if a.strip())
    unknown = [a for a in arms if a not in ARMS]
    if unknown or not arms:
        p.error(f"bras inconnu : {', '.join(unknown) or args.arm} (valeurs : {', '.join(ARMS)}, all)")
    args.arms = arms
    found = shutil.which(args.claude)  # chemin absolu : chaque session tourne dans un autre dossier
    args.claude = os.path.abspath(found) if found and os.sep in args.claude else (found or args.claude)
    args.ids = [i for i in args.ids] + [c.strip() for c in args.cases.split(",") if c.strip()]
    if args.split is None:
        args.split = "all" if args.ids else "dev"
    return args


def select_cases(args, cases):
    known = {c["id"] for c in cases}
    missing = [i for i in args.ids if i not in known]
    if missing:
        sys.exit(f"Cas inconnu(s) : {', '.join(missing)}")
    chosen = [c for c in cases if (not args.ids or c["id"] in args.ids)
              and (args.split == "all" or c.get("split", "dev") == args.split)]
    if not chosen:
        sys.exit("Aucun cas sélectionné (vérifie --cases et --split).")
    return chosen


def slug(text):
    return re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-") or "modele"


# ---------------------------------------------------------------- environnement

def paths():
    home = str(Path.home())
    return {"repo": str(REPO), "home": home, "plugin": str(PLUGIN_DIR),
            "scripts": str(PLUGIN_DIR / "skills" / checker.ORCHESTRATOR / "scripts")}


def expand(value, mapping):
    for key, path in mapping.items():
        value = value.replace("{" + key + "}", path)
    return value


def child_env(case, keep_env):
    env = dict(os.environ)
    scrubbed = []
    if not keep_env:
        for name in SCRUB_ENV:
            if name in env:
                scrubbed.append(name)
                del env[name]
    mapping = paths()
    for key, value in (case.get("env") or {}).items() if case else []:
        env[key] = expand(str(value), mapping)
    return env, scrubbed


def tree_hash(root):
    digest = hashlib.sha256()
    for path in sorted(p for p in Path(root).rglob("*") if p.is_file() and "__pycache__" not in p.parts):
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def git_state():
    try:
        head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], capture_output=True,
                              text=True, timeout=10).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain", "--", "plugins", "instructions"],
                               capture_output=True, text=True, timeout=10).stdout.strip()
        return head + ("+modifié" if dirty else "")
    except (OSError, subprocess.SubprocessError):
        return None


def versions():
    return {"plugin": tree_hash(PLUGIN_DIR), "instructions": hashlib.sha256(INSTRUCTIONS.read_bytes()).hexdigest()[:12],
            "git": git_state()}


def claude_version(claude):
    try:
        return subprocess.run([claude, "--version"], capture_output=True, text=True, timeout=30,
                              stdin=subprocess.DEVNULL).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def user_environment():
    """Ce qui, dans ~/.claude (lecture seule), peut fausser les bras ou les refus de permission."""
    home = Path.home() / ".claude"
    info = {"global_claude_md_block": False, "permissions_warning": None, "user_skills": None}
    md = home / "CLAUDE.md"
    try:
        info["global_claude_md_block"] = checker.BLOCK_START in md.read_text(encoding="utf-8")
    except OSError:
        pass
    try:
        settings = json.loads((home / "settings.json").read_text(encoding="utf-8"))
        perm = settings.get("permissions") or {}
        broad = [r for r in perm.get("allow") or [] if re.match(r"^(Bash|Write|Edit|WebFetch)(\((\.\*|\*|domain:\*)\))?$", r)]
        if perm.get("defaultMode") == "bypassPermissions" or broad:
            info["permissions_warning"] = (f"~/.claude/settings.json : defaultMode={perm.get('defaultMode')}, "
                                           f"règles larges {broad}. Les refus de permission prévus par les cas "
                                           "peuvent ne pas se produire (option --setting-sources project,local).")
    except (OSError, ValueError):
        pass
    try:
        info["user_skills"] = sorted(p.name for p in (home / "skills").iterdir())
    except OSError:
        pass
    return info


# ---------------------------------------------------------------- commandes

def allowed_tools(case, mapping):
    value = case.get("allowed_tools") or []
    tools = value.split() if isinstance(value, str) else list(value)
    return [expand(t, mapping) for t in tools]


def common_args(case, arm, args, mapping):
    cmd = ["--model", args.model, "--max-turns", str(case.get("max_turns", 10)),
           "--permission-mode", case.get("permission_mode", "default")]
    tools = allowed_tools(case, mapping)
    if tools:
        cmd += ["--allowedTools"] + tools
    if arm in checker.PLUGIN_ARMS:
        cmd += ["--plugin-dir", mapping["plugin"]]
    for d in case.get("add_dirs") or []:
        cmd += ["--add-dir", expand(d, mapping)]
    if args.max_budget_usd:
        cmd += ["--max-budget-usd", str(args.max_budget_usd)]
    if args.setting_sources:
        cmd += ["--setting-sources", args.setting_sources]
    cmd += ["--output-format", "stream-json", "--verbose", "--include-hook-events"]
    return cmd


def prompts(case, mapping):
    return [expand(case["prompt"], mapping)] + [expand(f, mapping) for f in checker.followups(case)]


def invocation(args, text, session, first, common):
    return [args.claude, "-p", text] + (["--session-id", session] if first else ["--resume", session]) + common


def kill_group(proc):
    for sig, wait in ((signal.SIGTERM, 10), (signal.SIGKILL, 5)):
        try:
            os.killpg(proc.pid, sig)
        except (ProcessLookupError, PermissionError):
            return
        try:
            proc.wait(timeout=wait)
            return
        except subprocess.TimeoutExpired:
            continue


def run_process(cmd, cwd, env, stdout, stderr, timeout):
    start = time.time()
    proc = subprocess.Popen(cmd, cwd=str(cwd), env=env, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                            start_new_session=True)
    with _running_lock:
        _running.add(proc)
    try:
        try:
            code = proc.wait(timeout=timeout)
            timed_out = False
        except subprocess.TimeoutExpired:
            kill_group(proc)
            code, timed_out = proc.wait(), True
    finally:
        with _running_lock:
            _running.discard(proc)
    return code, timed_out, round(time.time() - start, 1)


# ---------------------------------------------------------------- un cas

def prepare_project(work, case, arm):
    if work.parent.exists():
        shutil.rmtree(work.parent)
    (work / ".claude" / "skills").mkdir(parents=True)
    claude_md = INSTRUCTIONS.read_text(encoding="utf-8") if arm in checker.BLOCK_ARMS else ""
    if claude_md and case.get("reglages"):
        # Réglages durables propres au cas (par exemple sélection = automatique pour les
        # scénarios écrits avant la question de départ).
        claude_md = re.sub(r"(?m)^Réglages durables : .*$", lambda _: "Réglages durables : " + case["reglages"],
                           claude_md, count=1)
    (work / "CLAUDE.md").write_text(claude_md, encoding="utf-8")
    for name, content in (case.get("files") or {}).items():
        path = work / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def list_files(work):
    found = []
    for root, dirs, files in os.walk(work):
        for name in files:
            full = Path(root) / name
            if name != "CLAUDE.md" and full.is_file() and not full.is_symlink():
                found.append("./" + str(full.relative_to(work)))
    return sorted(found)


def last_segment_infra(stream):
    events = checker.load_events(stream)
    _, segments = checker.analyse(events)
    return checker.invocation_infra(segments[-1]) if segments else {"kind": "incomplete", "detail": "flux vide"}


def run_task(task, args, state):
    try:
        return _run_task(task, args, state)
    except Exception as exc:  # une erreur du harnais ne doit pas arrêter les autres sessions
        return {"label": f"[{task['arm']}/run{task['run']}] {task['case']['id']}",
                "status": f"erreur du harnais : {type(exc).__name__} : {exc}"}


def _run_task(task, args, state):
    case, arm, run_index, out_dir, work = task["case"], task["arm"], task["run"], task["out"], task["work"]
    cid = case["id"]
    label = f"[{arm}/run{run_index}] {cid}"
    if state["stop"].is_set():
        return {"label": label, "status": "annulé"}
    mapping = paths()
    env, _ = child_env(case, args.keep_env)
    prepare_project(work, case, arm)
    common = common_args(case, arm, args, mapping)
    session = str(uuid.uuid4())
    stream, stderr_path = out_dir / f"{cid}.jsonl", out_dir / f"{cid}.stderr"
    for stale in (out_dir / f"{cid}.files", out_dir / f"{cid}.claude.md"):
        if stale.exists():
            stale.unlink()
    infra = None
    stream.write_bytes(b"")
    stderr_path.write_bytes(b"")
    # Ajout seulement (O_APPEND) : les lignes harness et la sortie de claude ne s'écrasent pas.
    with open(stream, "ab") as out_f, open(stderr_path, "ab") as err_f:
        for turn, text in enumerate(prompts(case, mapping), 1):
            marker = {"type": "harness", "subtype": "turn_start", "turn": turn, "arm": arm, "run": run_index,
                      "model": args.model, "session_id": session, "version": state["versions"]}
            if turn == 1:  # CLAUDE.md réellement placé dans le projet, pour la vérification
                marker["claude_md_seed"] = (work / "CLAUDE.md").read_text(encoding="utf-8")
            out_f.write((json.dumps(marker, ensure_ascii=False) + "\n").encode("utf-8"))
            out_f.flush()
            cmd = invocation(args, text, session, turn == 1, common)
            code, timed_out, duration = run_process(cmd, work, env, out_f, err_f, args.timeout)
            end = {"type": "harness", "subtype": "turn_end", "turn": turn, "exit_code": code,
                   "timed_out": timed_out, "duration_s": duration}
            out_f.write((json.dumps(end) + "\n").encode("utf-8"))
            out_f.flush()
            infra = last_segment_infra(stream)
            if infra:
                break
    shutil.copyfile(work / "CLAUDE.md", out_dir / f"{cid}.claude.md")
    (out_dir / f"{cid}.files").write_text("\n".join(list_files(work)) + "\n", encoding="utf-8")
    if infra:
        with state["lock"]:
            state["infra"] += 1
            if infra["kind"] == "auth" or state["infra"] >= args.max_infra:
                state["stop"].set()
        return {"label": label, "status": f"infra ({infra['kind']}) : {infra['detail'][:160]}",
                "auth": infra["kind"] == "auth"}
    return {"label": label, "status": "terminé"}


# ---------------------------------------------------------------- vérification préalable

def preflight(args, env):
    """Un appel minimal : authentification, et plugin déjà installé pour l'utilisateur ?"""
    cmd = [args.claude, "-p", "Réponds seulement : ok", "--model", args.model, "--max-turns", "1",
           "--output-format", "stream-json", "--verbose"]
    if args.setting_sources:
        cmd += ["--setting-sources", args.setting_sources]
    if args.dry_run:
        say("# vérification préalable (cwd : dossier temporaire vide)")
        say(" ".join(shlex.quote(c) for c in cmd) + " < /dev/null")
        return None
    tmp = Path(tempfile.mkdtemp(prefix="skill-orch-preflight-"))
    try:
        with open(tmp / "out.jsonl", "wb") as out_f, open(tmp / "err.txt", "wb") as err_f:
            code, timed_out, _ = run_process(cmd, tmp, env, out_f, err_f, 300)
        events = checker.load_events(tmp / "out.jsonl")
        stderr = (tmp / "err.txt").read_text(encoding="utf-8", errors="replace")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    whole, segments = checker.analyse(events)
    infra = checker.classify_infra(True, segments, 1, stderr)
    if timed_out:
        infra = {"kind": "timeout", "detail": "aucune réponse en 300 s"}
    if infra:
        if infra["kind"] == "auth":
            sys.exit(f"Vérification préalable : {LOGIN_MESSAGE}\nAucun scénario n'a été lancé.")
        sys.exit(f"Vérification préalable : erreur d'infrastructure ({infra['kind']}) : {infra['detail']}\n"
                 f"Aucun scénario n'a été lancé. Réessaie plus tard, ou passe --no-preflight.")
    listed = {checker.short_name(s) for s in whole["skills_listed"]}
    plugin = any(checker.ORCHESTRATOR in json.dumps(p) for p in whole["plugins"])
    say(f"Vérification préalable : authentifié ; {len(whole['skills_listed'])} skills listés au démarrage ; "
        f"coût {round(whole['cost_usd'], 4)} $.")
    return {"skills_listed": len(whole["skills_listed"]), "orchestrator_installed": plugin or checker.ORCHESTRATOR in listed}


# ---------------------------------------------------------------- principal

def write_meta(out_dir, model, arm, run_index, cases, extra):
    path = out_dir / "meta.json"
    meta = checker.read_meta(out_dir)
    meta.update({"model": model, "arm": arm, "run": run_index, "repo": str(REPO), "home": str(Path.home()),
                 "plugin": str(PLUGIN_DIR), **extra})
    meta["cases"] = sorted(set(meta.get("cases") or []) | {c["id"] for c in cases})
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv=None):
    args = parse_args(argv)
    cases = select_cases(args, checker.load_cases())
    out_root = Path(args.out)
    model_dir = out_root / slug(args.model)
    work_root = Path(args.work_root) if args.work_root else Path(tempfile.gettempdir()) / "skill-orchestrator-evals"
    env, scrubbed = child_env(None, args.keep_env)
    user = user_environment()
    mapping = paths()

    tasks, skipped = [], 0
    for run_index in range(args.first_run, args.first_run + args.repeat):
        for case in cases:
            for arm in args.arms:  # bras entrelacés : conditions comparables dans le temps
                out_dir = model_dir / arm / f"run{run_index}"
                done = (out_dir / f"{case['id']}.files").exists()
                if done and not args.force:
                    skipped += 1
                    continue
                tasks.append({"case": case, "arm": arm, "run": run_index, "out": out_dir,
                              "work": work_root / slug(args.model) / arm / f"run{run_index}" / case["id"] / "projet"})
    calls = sum(len(prompts(t["case"], mapping)) for t in tasks)

    say(f"Modèle {args.model} ; bras {', '.join(args.arms)} ; {len(cases)} cas ({args.split}) ; "
        f"{args.repeat} passage(s) ; {len(tasks)} sessions à lancer ({skipped} déjà faites) ; "
        f"{calls} appels de claude -p (+1 vérification préalable).")
    if user["permissions_warning"]:
        say("Attention : " + user["permissions_warning"])
    contaminated = [a for a in args.arms if (a not in checker.PLUGIN_ARMS and checker.ORCHESTRATOR in (user["user_skills"] or []))
                    or (a not in checker.BLOCK_ARMS and user["global_claude_md_block"])]
    if contaminated and not args.allow_contamination and not args.dry_run:
        sys.exit(f"Bras {', '.join(contaminated)} contaminés : skill-orchestrator est installé dans ~/.claude "
                 "(skill ou bloc CLAUDE.md). Retire-le le temps des tests, ou passe --allow-contamination.")

    if args.dry_run:
        if contaminated:
            say(f"Attention : bras {', '.join(contaminated)} contaminés (skill-orchestrator installé dans ~/.claude).")
        say(f"Variables retirées de l'environnement : {', '.join(scrubbed) or 'aucune'}")
        preflight(args, env)
        for t in tasks:
            case, arm = t["case"], t["arm"]
            common = common_args(case, arm, args, mapping)
            claude_md = "bloc instructions/claude-code-CLAUDE.md" if arm in checker.BLOCK_ARMS else "vide"
            say(f"\n# [{arm}/run{t['run']}] {case['id']} ({case.get('split', 'dev')}) -> {t['out']}")
            say(f"# cwd : {t['work']} ; CLAUDE.md : {claude_md} ; fichiers : "
                f"{', '.join(['.claude/skills/'] + list(case.get('files') or {}))}")
            if case.get("env"):
                say("# env : " + " ".join(f"{k}={v}" for k, v in case["env"].items()))
            session = "<uuid>"
            for turn, text in enumerate(prompts(case, mapping), 1):
                cmd = invocation(args, text, session, turn == 1, common)
                say(" ".join(shlex.quote(c) for c in cmd) + " < /dev/null")
        say(f"\n{calls} appels de claude -p seraient lancés (aucun n'a été lancé).")
        return 0

    if not shutil.which(args.claude):
        sys.exit(f"Exécutable introuvable : {args.claude} (option --claude).")
    if not tasks:
        say("Rien à lancer.")
    pre = None
    if tasks and not args.no_preflight:
        pre = preflight(args, env)
        if pre and pre["orchestrator_installed"] and not args.allow_contamination \
                and any(a not in checker.PLUGIN_ARMS for a in args.arms):
            sys.exit("skill-orchestrator est déjà chargé sans --plugin-dir (plugin installé pour l'utilisateur) : "
                     "les bras sans plugin seraient contaminés. Désactive-le, ou passe --allow-contamination.")

    state = {"stop": threading.Event(), "lock": threading.Lock(), "infra": 0, "versions": versions()}
    extra = {"date": datetime.datetime.now().isoformat(timespec="seconds"), "claude_version": claude_version(args.claude),
             "platform": platform.platform(), "python": platform.python_version(), "scrubbed_env": scrubbed,
             "setting_sources": args.setting_sources, "max_budget_usd": args.max_budget_usd, "timeout_s": args.timeout,
             "global_claude_md_block": user["global_claude_md_block"], "permissions_warning": user["permissions_warning"],
             "versions": state["versions"], "preflight": pre}
    touched = {}
    for t in tasks:
        touched.setdefault((t["arm"], t["run"]), (t["out"], []))[1].append(t["case"])
    for (arm, run_index), (out_dir, run_cases) in touched.items():
        out_dir.mkdir(parents=True, exist_ok=True)
        write_meta(out_dir, args.model, arm, run_index, run_cases, extra)

    user_skills_before = set(user["user_skills"] or [])
    auth_failed = False
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            futures = [pool.submit(run_task, t, args, state) for t in tasks]
            for future in concurrent.futures.as_completed(futures):
                outcome = future.result()
                auth_failed |= bool(outcome.get("auth"))
                say(f"{outcome['label']} : {outcome['status']}")
    except KeyboardInterrupt:
        state["stop"].set()
        with _running_lock:
            for proc in list(_running):
                kill_group(proc)
        say("Interrompu : relance la même commande pour reprendre (les cas terminés sont conservés).")
        return 130
    added = sorted(set(user_environment()["user_skills"] or []) - user_skills_before)
    if added:
        say(f"\nAttention : dossiers apparus dans ~/.claude/skills pendant les tests : {', '.join(added)}. "
            "Un cas a peut-être installé un skill hors du projet : vérifie-les et retire-les à la main.")
    if auth_failed:
        say("\n" + LOGIN_MESSAGE + " Les cas non lancés le seront en relançant la même commande.")
    elif state["stop"].is_set():
        say(f"\nArrêt après {state['infra']} erreurs d'infrastructure ; relance plus tard la même commande.")

    if args.no_check:
        return 0
    entries = []
    for (arm, run_index), (out_dir, run_cases) in sorted(touched.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        entries += checker.check_run_dir(out_dir, {c["id"] for c in run_cases}, quiet=True)
    counts = {s: sum(1 for e in entries if e["status"] == s) for s in ("pass", "fail", "infra")}
    say(f"\nRéussis : {counts['pass']} ; échecs : {counts['fail']} ; erreurs d'infrastructure (exclues) : "
        f"{counts['infra']}.\nSynthèse : python3 tests/aggregate.py {shlex.quote(str(out_root))} --model {slug(args.model)}")
    return checker.exit_code(entries)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:  # sortie coupée (| head)
        sys.stdout = open(os.devnull, "w")
        sys.exit(0)
