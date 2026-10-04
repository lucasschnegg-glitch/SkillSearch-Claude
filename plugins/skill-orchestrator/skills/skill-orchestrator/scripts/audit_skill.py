#!/usr/bin/env python3
"""Audit statique d'un ou plusieurs skills : fonctionnement et sécurité.

Bibliothèque standard uniquement. Aucun accès réseau, aucune écriture, aucun code du
skill n'est exécuté : les scripts Python sont seulement compilés en mémoire, les
scripts shell vérifiés avec « bash -n » (analyse sans exécution).

Usage :
  python3 audit_skill.py <dossier de skill> [...]        un ou plusieurs skills
  python3 audit_skill.py --catalog <dossier racine> [...]  tous les SKILL.md sous ces dossiers
  python3 audit_skill.py --json ...                       sortie JSON
  python3 audit_skill.py --min-severity élevée ...        n'affiche que les alertes élevées et critiques
  python3 audit_skill.py --trust <dossier> ...            skill relu par l'utilisateur : gravités réduites

Verdict par skill :
  ÉCHEC  au moins une alerte critique (à ne pas utiliser avant examen) ;
  ALERTE au moins une alerte élevée ou moyenne (à examiner) ;
  OK     rien de notable (une analyse statique ne prouve pas l'absence de risque).

Les marqueurs de suppression (« noqa », « nosec »...) ne sont jamais pris en compte :
leur présence est elle-même signalée, car un skill malveillant peut s'en servir pour
se cacher d'un scanner.

Ce que le skill dit de lui-même (« outil de sécurité », « scanner »...) ne réduit jamais
une gravité : un skill malveillant peut l'écrire. Seule une décision extérieure au skill
le fait : --trust, que l'utilisateur donne après avoir relu le skill.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
import warnings
from pathlib import Path

SEVERITIES = ["info", "moyenne", "élevée", "critique"]
TEXT_SUFFIXES = {".md", ".txt", ".py", ".sh", ".bash", ".zsh", ".js", ".mjs", ".cjs", ".ts",
                 ".json", ".yaml", ".yml", ".toml", ".html", ".css", ".ps1", ".rb", ".xml", ".csv"}
SCRIPT_SUFFIXES = {".py", ".sh", ".bash", ".zsh", ".js", ".mjs", ".cjs", ".ts", ".ps1", ".rb"}
BINARY_MAGIC = {b"\x7fELF": "exécutable ELF", b"MZ": "exécutable Windows", b"\xcf\xfa\xed\xfe": "exécutable Mach-O",
                b"\xfe\xed\xfa\xcf": "exécutable Mach-O", b"\xca\xfe\xba\xbe": "exécutable Mach-O universel"}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".trash", ".staging"}
MAX_FILE_BYTES = 2_000_000

# Caractères invisibles ou de contrôle de direction, utilisés pour cacher du texte.
HIDDEN_CHARS = re.compile("[\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\U000e0000-\U000e007f]")

# Instructions qui tentent de détourner l'agent (français et anglais).
INJECTION = [
    (r"\b(ignore|disregard|forget)\b[^.\n]{0,40}\b(previous|prior|above|earlier|all|system|user)\b[^.\n]{0,20}\b(instructions?|prompts?|rules?|messages?)", "critique"),
    (r"\bignore[rz]?\b[^.\n]{0,30}\b(les |toutes les )?(instructions|consignes|règles) (précédentes|antérieures|du système|de l'utilisateur)", "critique"),
    (r"\b(do not|don't|never)\b[^.\n]{0,30}\b(tell|inform|show|reveal|mention)\b[^.\n]{0,30}\b(the )?user\b", "moyenne"),
    (r"\b(without|sans)\b[^.\n]{0,20}\b(telling|informing|prévenir|informer)\b[^.\n]{0,15}\b(the user|l'utilisateur)", "élevée"),
    (r"\bne (dis|révèle|montre|mentionne) (rien|pas)\b[^.\n]{0,30}\bl'utilisateur", "moyenne"),
    (r"\b(hide|conceal|cache|dissimule)[rz]?\b[^.\n]{0,30}\b(from the user|à l'utilisateur|de l'utilisateur)", "élevée"),
    (r"\bnew system prompt\b|\bDAN mode\b|\bdeveloper mode enabled\b", "élevée"),
    (r"\byou are now\b|\bjailbreak\b", "moyenne"),
    (r"\b(disable|bypass|skip|turn off|désactive[rz]?|contourne[rz]?)\b[^.\n]{0,30}\b(safety|security|guardrails?|permissions?|sandbox|sécurité|garde-fous)\b", "élevée"),
    (r"\b(send|upload|exfiltrate|transmit|envoie[rz]?|transmet[s]?|téléverse[rz]?)\b[^.\n]{0,40}\b(credentials?|secrets?|tokens?|api keys?|passwords?|ssh keys?|identifiants|mots de passe|clés)\b[^.\n]{0,40}\b(to|vers|à) (https?://|a remote|an external|un serveur|une adresse|ce webhook|this webhook)", "critique"),
    (r"\b(dangerously-skip-permissions|bypassPermissions|--no-sandbox)\b", "élevée"),
]

# Motifs dans le code ou les commandes.
CODE = [
    (r"\b(curl|wget)\b[^\n|]*\|\s*(sudo\s+)?(ba|z)?sh\b", "critique", "télécharge puis exécute un script distant"),
    (r"\b(iwr|Invoke-WebRequest|irm|Invoke-RestMethod)\b[^\n|]*\|\s*(iex|Invoke-Expression)", "critique", "télécharge puis exécute un script distant (PowerShell)"),
    (r"base64\s*(-d|--decode)[^\n]*\|\s*(ba|z)?sh|b64decode\([^)]*\)[^\n]{0,40}\b(exec|eval)\b|\b(exec|eval)\s*\([^)]*b64decode", "critique", "décode puis exécute du contenu caché"),
    (r"\b(exec|eval)\s*\(\s*(requests\.get|urllib|urlopen|fetch|http)", "critique", "exécute du code téléchargé"),
    (r"(~|\$HOME|expanduser\([\"']~)[/\\]?\.?(ssh|aws|gnupg|kube|docker)[/\\]|id_rsa|id_ed25519|\.netrc|\.aws/credentials", "critique", "accède à des fichiers d'identifiants"),
    (r"\bsecurity\s+find-(generic|internet)-password\b|(Chrome|Chromium|Firefox|BraveSoftware|Edge)[^\n]{0,60}(Login Data|Cookies|cookies\.sqlite|Local State)|keychain-db", "critique", "lit le trousseau ou les données du navigateur"),
    (r"(\.bashrc|\.zshrc|\.bash_profile|\.profile|\.zprofile)\b[^\n]{0,20}(>>|write|open\(|append)|(>>|tee -a)\s*~?/?[^\s]*\.(bashrc|zshrc|profile)", "élevée", "modifie les fichiers de démarrage du shell"),
    (r"\bcrontab\b|\blaunchctl\s+(load|bootstrap)|\bsystemctl\s+(enable|start)|LaunchAgents|/etc/cron", "élevée", "installe une tâche persistante"),
    (r"\.claude/(settings(\.local)?\.json|CLAUDE\.md|hooks)|claude_desktop_config\.json", "élevée", "touche à la configuration de Claude"),
    (r"\brm\s+-rf?\s+(--no-preserve-root\s+)?(/|~|\$HOME)(\s|$|/\*)", "critique", "suppression récursive du disque ou du dossier personnel"),
    (r"\bsudo\b|\bchmod\s+(-R\s+)?777\b|\bchown\s+root\b", "élevée", "demande des droits administrateur"),
    (r"--no-sandbox|--disable-setuid-sandbox", "moyenne", "désactive le bac à sable du navigateur"),
    (r"\bnc\s+-e\b|/dev/tcp/|\bsocat\b[^\n]*exec|\bbash\s+-i\s*>&", "critique", "ouvre un shell distant"),
    (r"\b(pickle|marshal)\.loads?\s*\(", "moyenne", "désérialisation non sûre"),
    (r"\bpip3?\s+install\b|\bnpm\s+(install|i)\s+(-g|--global)\b|\bbrew\s+install\b|\bapt(-get)?\s+install\b", "moyenne", "installe des dépendances"),
    (r"\b(os\.system|subprocess\.(call|run|Popen|check_output)\([^)]*shell\s*=\s*True)", "moyenne", "commande shell construite dynamiquement"),
    (r"\b(eval|exec)\s*\(", "info", "exécution dynamique de code"),
]

NETWORK = re.compile(r"\b(requests\.(get|post|put|patch|delete)|urllib\.request|urlopen|http\.client|httpx\.|aiohttp|"
                     r"socket\.(socket|create_connection)|fetch\(|axios|XMLHttpRequest|curl\b|wget\b|Invoke-WebRequest)")
URL = re.compile(r"https?://([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
SUPPRESSION = re.compile(r"(noqa|nosec|nosemgrep|auditor:\s*ignore[-\w]*|scanner:\s*ignore[-\w]*)\b[^\n]{0,30}", re.I)
# Indices qu'une formule dangereuse est citée pour mettre en garde, pas pour être suivie.
DEFENSIVE = re.compile(r"(such as|for example|e\.g\.|like \"|contains?|containing|if (the|a|an) [^.\n]{0,40}(says|contains)|"
                       r"do not (follow|obey|file)|never (follow|obey)|untrusted|malicious|attack|detect|warn|"
                       r"par exemple|comme «|contient|contenant|ne (la |les )?suis pas|n'obéis|malveillant|attaque|détect|"
                       r"cherche(nt)? à|signaux|red flags?|écarte|refuse)", re.I)
QUOTES = "\"'«»“”‘’`"
LONG_BLOB = re.compile(r"[A-Za-z0-9+/=]{400,}")
# Formats de clés d'API connus ; les valeurs d'exemple (EXAMPLE, xxxx, 1234...) sont ignorées.
SECRET = re.compile(r"\b(AIza[0-9A-Za-z_-]{35}|sk-ant-[A-Za-z0-9_-]{30,}|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{40,}|"
                    r"xox[bp]-[0-9A-Za-z-]{20,}|AKIA[0-9A-Z]{16}|sk-(proj-)?[A-Za-z0-9]{40,})\b")
PLACEHOLDER = re.compile(r"(replace with|todo|tbd|lorem ipsum|à compléter|description of the skill)", re.I)
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
# Domaines courants, pas suspects en soi (documentation, dépôts, registres).
COMMON_HOSTS = ("github.com", "githubusercontent.com", "anthropic.com", "claude.com", "claude.ai", "python.org",
                "pypi.org", "npmjs.com", "npmjs.org", "w3.org", "schema.org", "wikipedia.org", "mozilla.org",
                "microsoft.com", "google.com", "googleapis.com", "openxmlformats.org", "example.com", "localhost")


def parse_frontmatter(text):
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, 0
    data, key, block = {}, None, []
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            if key is not None and block:
                data[key] = " ".join(b.strip() for b in block).strip()
            return data, i
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if m and not line.startswith((" ", "\t")):
            if key is not None and block:
                data[key] = " ".join(b.strip() for b in block).strip()
            key, value, block = m.group(1), m.group(2).strip(), []
            if value in (">", ">-", "|", "|-", ">+", "|+", ""):
                data[key] = ""
            else:
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                data[key] = value
                key = None
        elif key is not None:
            block.append(line)
    return None, 0  # frontmatter non fermé


class Report:
    def __init__(self, path):
        self.path = str(path)
        self.name = Path(path).name
        self.findings = []
        self.hosts = set()

    def add(self, severity, category, message, where="", excerpt=""):
        self.findings.append({"gravite": severity, "categorie": category, "message": message,
                              "fichier": where, "extrait": excerpt[:160]})

    @property
    def verdict(self):
        levels = {f["gravite"] for f in self.findings}
        if "critique" in levels:
            return "ÉCHEC"
        if levels & {"élevée", "moyenne"}:
            return "ALERTE"
        return "OK"

    def to_dict(self):
        return {"skill": self.name, "chemin": self.path, "verdict": self.verdict,
                "domaines": sorted(self.hosts), "alertes": self.findings}


def iter_files(root):
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            yield Path(dirpath) / name
        for name in dirnames:
            p = Path(dirpath) / name
            if p.is_symlink():
                yield p


def line_of(text, index):
    return text.count("\n", 0, index) + 1


def check_structure(skill_dir, report):
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        report.add("élevée", "structure", "SKILL.md absent", "SKILL.md")
        return ""
    text = skill_md.read_text(encoding="utf-8", errors="replace")
    meta, end = parse_frontmatter(text)
    if meta is None:
        report.add("élevée", "structure", "frontmatter YAML absent ou non fermé", "SKILL.md")
        return text
    name, desc = meta.get("name", ""), meta.get("description", "")
    if not name:
        report.add("moyenne", "structure", "champ name absent", "SKILL.md")
    elif not NAME_RE.match(name) or len(name) > 64:
        report.add("info", "structure", f"nom non conforme à la convention (minuscules et tirets, 64 caractères) : {name}", "SKILL.md")
    if name and name != skill_dir.name and not skill_dir.name.startswith(name):
        report.add("info", "structure", f"le nom « {name} » diffère du dossier « {skill_dir.name} »", "SKILL.md")
    if not desc:
        report.add("moyenne", "fonctionnement", "description absente : le skill ne se déclenchera pas", "SKILL.md")
    elif PLACEHOLDER.search(desc) and len(desc) < 200:
        report.add("moyenne", "fonctionnement", "description de remplacement (modèle non rempli)", "SKILL.md", desc)
    if len(desc) > 1024:
        report.add("info", "structure", f"description de {len(desc)} caractères (au-delà de 1 024, peut être tronquée ou refusée)", "SKILL.md")
    if meta.get("hooks") is not None or re.search(r"^hooks:", text[: text.find("\n---", 4) + 1], re.M):
        report.add("moyenne", "exécution", "le skill déclare des hooks : du code s'exécute quand il est chargé", "SKILL.md")
    allowed = meta.get("allowed-tools", "")
    if re.search(r"\bBash\b(?!\()", allowed) or "Bash(*)" in allowed:
        report.add("moyenne", "exécution", f"allowed-tools autorise Bash sans restriction : {allowed}", "SKILL.md")
    else:
        # Outils accordés sans confirmation qui donnent accès au réseau ou à un shell arbitraire.
        risky = sorted(set(re.findall(r"Bash\([^)]*\b(?:curl|wget|ssh|scp|rsync|nc|sudo|rm|sh|bash|zsh|python3?|node|eval)\b[^)]*\)"
                                      r"|\bWebFetch\b|\bWebSearch\b", allowed)))
        if risky:
            report.add("moyenne", "exécution", "allowed-tools accorde sans confirmation : " + ", ".join(risky), "SKILL.md")
    body = "\n".join(text.splitlines()[end + 1:])
    if len(body.strip()) < 80:
        report.add("moyenne", "fonctionnement", "corps du skill presque vide", "SKILL.md")
    for m in re.finditer(r"^!`([^`]+)`|\s!`([^`]+)`", body, re.M):
        report.add("moyenne", "exécution", "commande exécutée au chargement du skill (syntaxe !`...`)", "SKILL.md", m.group(0).strip())
    return text


def check_references(skill_dir, text, report):
    """Fichiers cités dans SKILL.md (liens et chemins relatifs) qui n'existent pas."""
    candidates = set()
    for m in re.finditer(r"\]\(([^)\s#]+)\)", text):
        candidates.add(m.group(1))
    for m in re.finditer(r"`((?:\./)?(?:scripts|references|assets|templates|examples|reference|docs|lib|bin)/[^`\s]+)`", text):
        candidates.add(m.group(1))
    # Chemins écrits depuis la racine du projet : skills/<nom>/scripts/x.py, .claude/skills/<nom>/...
    own = re.escape(skill_dir.name)
    for m in re.finditer(r"(?:^|[\s`(\"'])(?:\.claude/)?skills/" + own + r"/([^\s`)\"']+)", text):
        candidates.add(m.group(1))
    for ref in sorted(candidates):
        if re.match(r"^[a-z]+:", ref) or ref.startswith(("/", "~", "$", "<", "{")) or "*" in ref or "<" in ref:
            continue
        ref = ref.split()[0].rstrip(".,;:")
        if not (skill_dir / ref).exists():
            report.add("moyenne", "fonctionnement", f"fichier référencé introuvable : {ref}", "SKILL.md")


def check_syntax(path, rel, report):
    suffix = path.suffix.lower()
    try:
        source = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return
    if suffix == ".py":
        try:
            # Les avertissements du compilateur (séquences d'échappement...) ne concernent pas l'audit.
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                compile(source, str(path), "exec", dont_inherit=True)
        except SyntaxError as exc:
            report.add("moyenne", "fonctionnement", f"erreur de syntaxe Python ligne {exc.lineno} : {exc.msg}", rel)
    elif suffix in (".sh", ".bash") and shutil.which("bash"):
        result = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            report.add("moyenne", "fonctionnement", "erreur de syntaxe shell", rel, result.stderr.strip())
    elif suffix == ".json":
        try:
            json.loads(source)
        except json.JSONDecodeError as exc:
            report.add("moyenne", "fonctionnement", f"JSON invalide ligne {exc.lineno}", rel)


SELF_SOURCE = Path(__file__).resolve().read_bytes()


def check_file(skill_dir, path, report, trusted):
    rel = str(path.relative_to(skill_dir))
    if path.is_symlink():
        target = Path(os.path.realpath(path))
        base = skill_dir.resolve()
        # Comparaison par composants : « skill-evil » n'est pas dans « skill ».
        if target != base and base not in target.parents:
            report.add("critique", "fichiers", f"lien symbolique vers l'extérieur du skill : {target}", rel)
        return
    try:
        size = path.stat().st_size
    except OSError:
        return
    if size > MAX_FILE_BYTES:
        report.add("info", "fichiers", f"fichier volumineux ({size // 1024} Ko)", rel)
        return
    raw = path.read_bytes()
    if raw == SELF_SOURCE:
        # Copie identique de cet outil : ses motifs de détection sont des données.
        report.add("info", "contexte", "copie de l'outil d'audit : motifs de détection non analysés", rel)
        return
    for magic, label in BINARY_MAGIC.items():
        if raw.startswith(magic) and path.suffix.lower() not in (".png", ".jpg", ".gif", ".pdf", ".ttf", ".otf", ".woff", ".woff2"):
            report.add("critique", "fichiers", f"{label} dans le skill", rel)
            return
    if path.suffix.lower() in (".so", ".dll", ".dylib", ".exe"):
        report.add("critique", "fichiers", "bibliothèque ou exécutable binaire", rel)
        return
    if not path.suffix and size < 300:
        content = raw.decode("utf-8", errors="replace").strip()
        if "\n" not in content and re.match(r"^\.{1,2}/[\w./-]+$", content):
            # Lien symbolique transformé en fichier texte (fréquent après un téléversement).
            report.add("moyenne", "fonctionnement", f"lien symbolique aplati en fichier texte (cible : {content}) : le contenu attendu est absent", rel)
            return
    if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in ("SKILL.md", "LICENSE", "Makefile"):
        return
    text = raw.decode("utf-8", errors="replace")

    for m in SECRET.finditer(text):
        value = m.group(0)
        if re.search(r"EXAMPLE|xxxx|XXXX|1234|abcd|ABCD|0000|your|YOUR", value) or len(set(value[4:])) < 8:
            continue
        report.add("moyenne", "secret", "clé d'API d'apparence réelle dans le skill (secret exposé, à ne pas réutiliser)",
                   f"{rel}:{line_of(text, m.start())}", value[:8] + "…")
        break

    hidden = HIDDEN_CHARS.search(text)
    if hidden:
        code = f"U+{ord(hidden.group(0)):04X}"
        report.add("élevée", "dissimulation", f"caractère invisible ou de direction {code} (peut cacher du texte)",
                   f"{rel}:{line_of(text, hidden.start())}")
    if not trusted:
        for m in SUPPRESSION.finditer(text):
            before = text[max(0, m.start() - 3): m.start()]
            if path.suffix.lower() not in SCRIPT_SUFFIXES and any(q in before for q in QUOTES):
                continue  # marqueur cité dans la documentation, sans effet
            low = m.group(0).lower()
            if "sec-auditor" in low or "nosec" in low or "auditor" in low or "scanner" in low:
                report.add("moyenne", "dissimulation", "marqueur qui masque des lignes aux scanners de sécurité",
                           f"{rel}:{line_of(text, m.start())}", m.group(0))
                break

    if path.suffix.lower() in (".md", ".txt", ".html", ".yaml", ".yml") or path.name == "SKILL.md":
        scan = text
        comments = re.finditer(r"<!--(.*?)-->", text, re.S) if path.suffix.lower() == ".md" else []
        for m in comments:
            if re.search(r"\b(claude|assistant|the agent|l'agent|ignore|you must|tu dois|vous devez|do not tell|instructions?)\b", m.group(1), re.I) \
                    and not SUPPRESSION.search(m.group(1)):
                report.add("moyenne", "dissimulation", "commentaire HTML invisible qui contient des consignes",
                           f"{rel}:{line_of(text, m.start())}", m.group(1).strip())
        for pattern, severity in INJECTION:
            for m in re.finditer(pattern, scan, re.I):
                line_start = scan.rfind("\n", 0, m.start()) + 1
                line_end = scan.find("\n", m.end())
                line = scan[line_start: line_end if line_end != -1 else len(scan)]
                quoted = any(q in scan[max(line_start, m.start() - 3): m.start()] for q in QUOTES)
                defensive = bool(DEFENSIVE.search(line))
                if quoted and defensive:
                    # Citée pour la détecter ou s'en protéger : simple information.
                    report.add("info", "injection", "formule d'injection citée en exemple ou en mise en garde",
                               f"{rel}:{line_of(text, m.start())}", m.group(0))
                    continue
                if quoted or defensive or trusted:
                    # Un seul indice ne suffit pas : ces indices sont faciles à imiter.
                    report.add("moyenne", "injection", "formule d'injection, apparemment citée : à vérifier",
                               f"{rel}:{line_of(text, m.start())}", m.group(0))
                    break
                report.add(severity, "injection", "formulation qui cherche à détourner l'agent",
                           f"{rel}:{line_of(text, m.start())}", m.group(0))
                break

    if path.suffix.lower() in SCRIPT_SUFFIXES or path.name == "SKILL.md":
        is_doc = path.suffix.lower() not in SCRIPT_SUFFIXES
        for pattern, severity, message in CODE:
            m = re.search(pattern, text, re.I)
            if m:
                sev = severity
                if is_doc and severity != "info":
                    sev = SEVERITIES[max(1, SEVERITIES.index(severity) - 1)]
                if trusted and sev == "critique":
                    sev = "moyenne"
                report.add(sev, "code", message, f"{rel}:{line_of(text, m.start())}", m.group(0))
        if path.suffix.lower() in SCRIPT_SUFFIXES:
            if NETWORK.search(text):
                hosts = set(h.lower() for h in URL.findall(text))
                report.hosts |= hosts
                unknown = sorted(h for h in hosts if not h.endswith(COMMON_HOSTS))
                detail = ", ".join(unknown) if unknown else "domaines courants ou non précisés"
                report.add("info", "réseau", f"accès réseau dans un script ({detail})", rel)
            blob = LONG_BLOB.search(text)
            if blob and path.suffix.lower() != ".json":
                report.add("moyenne", "dissimulation", "longue chaîne encodée dans un script", f"{rel}:{line_of(text, blob.start())}", blob.group(0)[:60])
            check_syntax(path, rel, report)
    elif path.suffix.lower() == ".json":
        check_syntax(path, rel, report)


def audit(skill_dir, trusted=False):
    """trusted : décision de l'utilisateur (--trust), jamais déduite du contenu du skill."""
    skill_dir = Path(skill_dir)
    report = Report(skill_dir)
    text = check_structure(skill_dir, report)
    if text:
        check_references(skill_dir, text, report)
    claims_security = bool(re.search(r"security|sécurité|audit|scanner|threat", text[:1500], re.I)) and \
        bool(re.search(r"prompt injection|injection", text, re.I))
    for path in iter_files(skill_dir):
        check_file(skill_dir, path, report, trusted)
    if trusted:
        report.add("info", "contexte", "skill déclaré de confiance par l'utilisateur (--trust) : gravités réduites")
    elif claims_security:
        report.add("info", "contexte", "le skill se présente comme un outil de sécurité : ses motifs dangereux "
                   "peuvent être des citations. Gravités maintenues ; après relecture, --trust <dossier> les réduit")
    # Dédoublonne les alertes identiques.
    seen, unique = set(), []
    for f in report.findings:
        key = (f["gravite"], f["message"], f["fichier"])
        if key not in seen:
            seen.add(key)
            unique.append(f)
    report.findings = unique
    return report


def find_skills(roots):
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            if "SKILL.md" in filenames:
                yield Path(dirpath)
                dirnames[:] = []  # un skill ne contient pas d'autre skill


def main():
    parser = argparse.ArgumentParser(description="Audit statique de skills (fonctionnement et sécurité).")
    parser.add_argument("paths", nargs="+", help="dossiers de skill, ou racines avec --catalog")
    parser.add_argument("--catalog", action="store_true", help="auditer tous les skills trouvés sous les dossiers")
    parser.add_argument("--json", action="store_true", help="sortie JSON")
    parser.add_argument("--min-severity", choices=["info", "moyenne", "élevée", "critique"], default="moyenne",
                        help="gravité minimale affichée (défaut : moyenne)")
    parser.add_argument("--trust", action="append", default=[], metavar="DOSSIER",
                        help="skill relu et jugé fiable par l'utilisateur : gravités réduites (répétable)")
    args = parser.parse_args()

    trusted = {Path(t).expanduser().resolve() for t in args.trust}
    dirs = list(find_skills(args.paths)) if args.catalog else [Path(p) for p in args.paths]
    reports = [audit(d, trusted=d.resolve() in trusted) for d in dirs]
    if args.json:
        json.dump([r.to_dict() for r in reports], sys.stdout, ensure_ascii=False, indent=2)
        print()
    else:
        threshold = SEVERITIES.index(args.min_severity)
        for r in reports:
            shown = [f for f in r.findings if SEVERITIES.index(f["gravite"]) >= threshold]
            if args.catalog and r.verdict == "OK" and not shown:
                continue
            print(f"\n{r.verdict:6}  {r.name}  ({r.path})")
            for f in shown:
                where = f" [{f['fichier']}]" if f["fichier"] else ""
                excerpt = f"\n          « {f['extrait']} »" if f["extrait"] else ""
                print(f"  - {f['gravite']:8} {f['categorie']} : {f['message']}{where}{excerpt}")
        counts = {v: sum(r.verdict == v for r in reports) for v in ("ÉCHEC", "ALERTE", "OK")}
        print(f"\n{len(reports)} skill(s) : {counts['ÉCHEC']} échec, {counts['ALERTE']} alerte, {counts['OK']} ok.")
    sys.exit(1 if any(r.verdict == "ÉCHEC" for r in reports) else 0)


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        sys.stderr.close()
