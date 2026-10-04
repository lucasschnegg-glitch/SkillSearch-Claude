#!/usr/bin/env python3
"""Vérifie l'origine de skills installés en les comparant à leurs dépôts sources.

Clone d'abord les dépôts sources (historique complet) dans un dossier, par exemple :
  git clone https://github.com/anthropics/skills.git depots/anthropics_skills
puis :
  python3 compare_upstream.py <dossier des dépôts> <racine des skills installés> [...] > origine.json
  python3 compare_upstream.py --resume origine.json
  --reference <dossier> ajoute une copie de référence sans historique (par exemple /mnt/skills,
  les skills fournis par l'application), répétable.

Pour chaque skill, cherche un dossier du même nom dans les dépôts et compare les fichiers.
Statuts : identique à la version actuelle ; identique à une version publiée antérieure
(fichier retrouvé dans l'historique, même après un déplacement) ; identique, fichiers en
moins ; écarts non expliqués ; source non trouvée. Le téléversement sur claude.ai modifie
légèrement les fichiers (guillemets du frontmatter, gabarits <...> retirés de la
description, liens « ../ » réécrits en « _external/ ») : ces réécritures précises sont
neutralisées. Les lignes ajoutées par rapport à la source passent aux motifs de
audit_skill.py. Aucun code des skills n'est exécuté.
"""

import difflib
import hashlib
import json
import os
import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_skill  # noqa: E402

IGNORE = {"__pycache__", ".DS_Store", ".git"}


def files_of(d):
    out = {}
    for dirpath, dirnames, filenames in os.walk(d):
        dirnames[:] = [x for x in dirnames if x not in IGNORE]
        for f in filenames:
            if f in IGNORE or f.endswith(".pyc"):
                continue
            p = Path(dirpath) / f
            out[str(p.relative_to(d))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out




LOCAL_LINK = re.compile(r"\]\((?![a-z][a-z0-9+.-]*:)[^)\s]*\)", re.I)


def normalize_links(line, installed):
    """Le téléversement réécrit les liens internes (« ../x » devient « _external/x », ou le lien
    est retiré). Seules les cibles locales sont neutralisées : un lien vers une URL
    (https://, mailto:...) reste comparé, pour qu'un lien malveillant ajouté soit vu."""
    return LOCAL_LINK.sub("]()", line).replace("`", "")


def split_skill_md(text, installed=False):
    """(frontmatter interprété, corps) : le téléversement normalise le frontmatter
    (guillemets retirés, gabarits <...> retirés de la description)."""
    meta, end = audit_skill.parse_frontmatter(text)
    lines = text.splitlines()
    body = lines[end + 1:] if meta is not None else lines
    clean = {}
    for k, v in (meta or {}).items():
        v = re.sub(r"<[^<>]{1,40}>", "", v.strip().strip("\"'"))
        clean[k] = re.sub(r"\s+", " ", v).strip()
    return clean, [normalize_links(l.rstrip(), installed) for l in body]


def same_content(rel, a_bytes, b_bytes):
    if a_bytes == b_bytes:
        return True
    if Path(rel).name == "SKILL.md" or Path(rel).suffix == ".md":
        a = split_skill_md(a_bytes.decode("utf-8", "replace"))
        b = split_skill_md(b_bytes.decode("utf-8", "replace"), installed=True)
        # Le corps doit être identique ; dans le frontmatter, seules les valeurs communes comptent.
        common = set(a[0]) & set(b[0])
        return a[1] == b[1] and all(a[0][k] == b[0][k] for k in common)
    return False


@lru_cache(maxsize=None)
def repo_root(path):
    out = subprocess.run(["git", "-C", path, "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    return out.stdout.strip() or None


def git_blob_hash(data):
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


@lru_cache(maxsize=None)
def all_blobs(root):
    """Empreintes de tous les fichiers jamais publiés dans le dépôt, et SKILL.md par dossier."""
    out = subprocess.run(["git", "-C", root, "rev-list", "--all", "--objects"], capture_output=True, text=True).stdout
    blobs, skill_mds = set(), {}
    for line in out.splitlines():
        parts = line.split(" ", 1)
        blobs.add(parts[0])
        if len(parts) == 2 and parts[1].endswith("SKILL.md"):
            skill_mds.setdefault(Path(parts[1]).parent.name, []).append(parts[0])
    return blobs, skill_mds


def history_match(upstream_dir, rel, installed_bytes, names=()):
    match = history_match_path(upstream_dir, rel, installed_bytes)
    if match:
        return match
    root = repo_root(str(upstream_dir))
    if not root:
        return None
    blobs, skill_mds = all_blobs(root)
    if git_blob_hash(installed_bytes) in blobs:
        return {"commit": "historique", "date": "chemin différent"}
    if Path(rel).name == "SKILL.md":
        for name in names:
            for blob in skill_mds.get(name, []):
                old = subprocess.run(["git", "-C", root, "cat-file", "-p", blob], capture_output=True).stdout
                if same_content(rel, old, installed_bytes):
                    return {"commit": "historique", "date": "chemin différent"}
    return None


def history_match_path(upstream_dir, rel, installed_bytes):
    """Cherche dans l'historique du dépôt une version du fichier identique à la copie installée."""
    root = repo_root(str(upstream_dir))
    if not root:
        return None
    path = str((Path(upstream_dir) / rel).resolve().relative_to(Path(root).resolve()))
    log = subprocess.run(["git", "-C", root, "log", "--all", "--format=%H %cs", "--", path],
                         capture_output=True, text=True).stdout.split("\n")
    for line in log:
        if not line.strip():
            continue
        commit, date = line.split()
        blob = subprocess.run(["git", "-C", root, "show", f"{commit}:{path}"], capture_output=True).stdout
        if blob and same_content(rel, blob, installed_bytes):
            return {"commit": commit[:10], "date": date}
    return None


def skill_name(d):
    meta, _ = audit_skill.parse_frontmatter((d / "SKILL.md").read_text(encoding="utf-8", errors="replace"))
    return (meta or {}).get("name") or d.name


def index_upstream(root, references=()):
    idx = {}
    sources = [r for r in sorted(Path(root).iterdir()) if r.is_dir()] + [Path(r) for r in references]
    for repo in sources:
        for d in audit_skill.find_skills([repo]):
            for key in {d.name, skill_name(d)}:
                idx.setdefault(key, []).append(d)
    return idx


def suspicious_additions(installed, upstream, rel):
    try:
        a = (upstream / rel).read_text(encoding="utf-8", errors="replace").splitlines()
        b = (installed / rel).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    added = "\n".join(l[1:] for l in difflib.unified_diff(a, b, lineterm="", n=0)
                      if l.startswith("+") and not l.startswith("+++"))
    hits = []
    for pattern, severity, message in audit_skill.CODE:
        if severity in ("critique", "élevée") and re.search(pattern, added, re.I):
            hits.append(message)
    for pattern, severity in audit_skill.INJECTION:
        if severity in ("critique", "élevée") and re.search(pattern, added, re.I):
            hits.append("formule d'injection ajoutée")
    if audit_skill.HIDDEN_CHARS.search(added):
        hits.append("caractère invisible ajouté")
    return hits


def compare(installed, candidates):
    results = [compare_one(installed, up) for up in candidates]
    rank = {"identique à la version actuelle": 0, "identique, fichiers en moins": 1,
            "identique à une version publiée antérieure": 2, "écarts non expliqués": 3}
    return min(results, key=lambda r: (rank[r["statut"]], len(r["non_expliques"])))


def compare_one(installed, up_dir):
    mine = files_of(installed)
    best = None
    for up in [up_dir]:
        theirs = files_of(up)
        same = [f for f in mine if theirs.get(f) == mine[f]]
        score = len(same) / max(len(set(mine) | set(theirs)), 1)
        if best is None or score > best[0]:
            best = (score, up, theirs)
    score, up, theirs = best
    changed = sorted(f for f in mine if f in theirs and theirs[f] != mine[f]
                     and not same_content(f, (installed / f).read_bytes(), (up / f).read_bytes()))
    extra = sorted(f for f in mine if f not in theirs)
    missing = sorted(f for f in theirs if f not in mine)
    # Fichiers modifiés ou en plus : correspondent-ils à une version publiée plus ancienne ?
    history, unexplained = {}, []
    for rel in changed + [f for f in extra if not f.startswith("_external/")]:
        match = history_match(up, rel, (installed / rel).read_bytes(), (installed.name, up.name))
        if match:
            history[rel] = match
        else:
            unexplained.append(rel)
    if not changed and not extra:
        status = "identique à la version actuelle" if not missing else "identique, fichiers en moins"
    elif not unexplained:
        status = "identique à une version publiée antérieure"
    else:
        status = "écarts non expliqués"
    alerts = {}
    for rel in changed + extra:
        if Path(rel).suffix.lower() in audit_skill.SCRIPT_SUFFIXES | {".md"}:
            if rel in extra:
                rep = audit_skill.Report(installed)
                audit_skill.check_file(installed, installed / rel, rep, False)
                hits = [f["message"] for f in rep.findings if f["gravite"] in ("critique", "élevée")]
            else:
                hits = suspicious_additions(installed, up, rel)
            if hits:
                alerts[rel] = sorted(set(hits))
    return {"statut": status, "source": str(up), "fichiers_modifies": changed, "fichiers_en_plus": extra,
            "fichiers_absents": missing, "versions_anterieures": history, "non_expliques": unexplained,
            "ajouts_suspects": alerts}


def resume(path):
    import collections
    data = json.load(open(path, encoding="utf-8"))
    counts = collections.Counter(r["statut"] for r in data)
    for status, n in counts.most_common():
        print(f"{n:4}  {status}")
    for r in data:
        if r.get("ajouts_suspects"):
            print(f"  ajouts suspects dans {r['skill']} : {r['ajouts_suspects']}")


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--resume":
        resume(sys.argv[2])
        return
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    args = sys.argv[1:]
    references = []
    while "--reference" in args:
        i = args.index("--reference")
        references.append(args[i + 1])
        del args[i:i + 2]
    upstream_root, roots = args[0], args[1:]
    idx = index_upstream(upstream_root, references)
    results = []
    for d in audit_skill.find_skills(roots):
        name = skill_name(d)
        candidates = idx.get(name, []) + [c for c in idx.get(d.name, []) if c not in idx.get(name, [])]
        entry = {"skill": name, "chemin": str(d)}
        if candidates:
            entry.update(compare(d, candidates))
        else:
            entry["statut"] = "source non trouvée"
        results.append(entry)
    json.dump(results, sys.stdout, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
