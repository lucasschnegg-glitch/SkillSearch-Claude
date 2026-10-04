#!/usr/bin/env python3
"""Recherche locale dans le catalogue de skills (bibliothèque standard uniquement).

Parcourt les dossiers où Claude Code et Cowork rangent les skills installés,
lit le frontmatter de chaque SKILL.md et classe les skills selon les mots-clés.
Aucun accès réseau, aucune écriture.

Exemples :
  python3 find_skills.py presentation slides pptx
  python3 find_skills.py --all
  python3 find_skills.py --json --limit 5 excel tableau
  python3 find_skills.py --root /chemin/vers/skills docx
"""

import argparse
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", ".trash", ".staging", "__pycache__", ".venv", "venv"}
MAX_DEPTH = 8


def default_roots():
    """Dossiers de skills installés, du plus général au plus local."""
    home = Path.home()
    config = Path(os.environ.get("CLAUDE_CONFIG_DIR", home / ".claude"))
    roots = [
        (config / "skills", "user"),
        (config / "plugins" / "cache", "plugin"),
        (config / "plugins" / "synced", "plugin-synced"),
        (Path("/mnt/skills"), "app"),
    ]
    # Skills du projet : .claude/skills du dossier courant et de ses parents.
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        candidate = parent / ".claude" / "skills"
        if candidate.is_dir() and candidate != config / "skills":
            roots.append((candidate, "project"))
    return roots


def iter_skill_files(root, depth=0):
    try:
        entries = list(os.scandir(root))
    except (FileNotFoundError, NotADirectoryError, PermissionError):
        return
    for entry in entries:
        if entry.is_file() and entry.name == "SKILL.md":
            yield Path(entry.path)
        elif entry.is_dir(follow_symlinks=False) and entry.name not in SKIP_DIRS and depth < MAX_DEPTH:
            yield from iter_skill_files(entry.path, depth + 1)


def parse_frontmatter(text):
    """Lecture minimale du frontmatter YAML : clés de premier niveau, scalaires et blocs > ou |."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    data, key, block = {}, None, []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        match = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if match and not line.startswith((" ", "\t")):
            if key is not None and block:
                data[key] = " ".join(part.strip() for part in block).strip()
            key, value = match.group(1), match.group(2).strip()
            block = []
            if value in (">", ">-", "|", "|-", ">+", "|+"):
                data[key] = ""
            else:
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1].replace('\\"', '"')
                data[key] = value
                key = None
        elif key is not None:
            block.append(line)
    if key is not None and block:
        data[key] = " ".join(part.strip() for part in block).strip()
    return data


def fold(text):
    """Minuscules sans accents, pour comparer « présentation » et « presentation »."""
    normalized = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in normalized if not unicodedata.combining(c))


def origin_label(path, kind):
    parts = path.parts
    if kind == "plugin" and "cache" in parts:
        # cache/<marketplace>/<plugin>/<version>/skills/<skill>/SKILL.md
        idx = parts.index("cache")
        if len(parts) > idx + 2:
            return f"plugin {parts[idx + 2]}@{parts[idx + 1]}"
    if kind == "user" and "synced" in parts:
        return "compte claude.ai (synchronisé)"
    return {"user": "personnel", "project": "projet", "app": "application",
            "plugin-synced": "plugin synchronisé"}.get(kind, kind)


def collect(roots):
    skills, seen = [], {}
    for root, kind in roots:
        if not root.is_dir():
            continue
        for skill_file in iter_skill_files(root):
            try:
                text = skill_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            meta = parse_frontmatter(text)
            name = meta.get("name") or skill_file.parent.name
            origin = origin_label(skill_file, kind)
            # Le cache des plugins peut garder plusieurs versions : on garde la plus récente.
            dedup_key = (name, origin)
            mtime = skill_file.stat().st_mtime
            if dedup_key in seen:
                previous = seen[dedup_key]
                if previous["_mtime"] >= mtime:
                    continue
                skills.remove(previous)
            entry = {
                "name": name,
                "description": meta.get("description", ""),
                "origin": origin,
                "path": str(skill_file.parent),
                "model_invocable": meta.get("disable-model-invocation", "").lower() != "true",
                "_mtime": mtime,
            }
            seen[dedup_key] = entry
            skills.append(entry)
    return skills


def score(skill, keywords):
    name, desc = fold(skill["name"]), fold(skill["description"])
    total, matched = 0, 0
    for keyword in keywords:
        hit = False
        if keyword in name:
            total += 3
            hit = True
        count = desc.count(keyword)
        if count:
            total += min(count, 3)
            hit = True
        matched += hit
    if keywords and matched == len(keywords) and len(keywords) > 1:
        total += 2
    return total


def main():
    parser = argparse.ArgumentParser(description="Recherche dans les skills installés localement.")
    parser.add_argument("keywords", nargs="*", help="mots-clés (français et anglais conseillés)")
    parser.add_argument("--all", action="store_true", help="lister tous les skills trouvés")
    parser.add_argument("--limit", type=int, default=15, help="nombre maximal de résultats (défaut 15)")
    parser.add_argument("--json", action="store_true", help="sortie JSON")
    parser.add_argument("--root", action="append", default=[], help="dossier supplémentaire à parcourir")
    args = parser.parse_args()

    roots = default_roots() + [(Path(r).expanduser(), "extra") for r in args.root]
    skills = collect(roots)
    keywords = [fold(k) for k in args.keywords if k.strip()]

    if args.all or not keywords:
        results = sorted(skills, key=lambda s: s["name"])
    else:
        ranked = [(score(s, keywords), s) for s in skills]
        results = [s for value, s in sorted(ranked, key=lambda item: -item[0]) if value > 0][: args.limit]

    for skill in results:
        skill.pop("_mtime", None)

    if args.json:
        json.dump({"count": len(results), "scanned": len(skills), "results": results},
                  sys.stdout, ensure_ascii=False, indent=2)
        print()
        return

    print(f"{len(results)} résultat(s) sur {len(skills)} skills trouvés.")
    for skill in results:
        flag = "" if skill["model_invocable"] else " [invocation manuelle seulement]"
        desc = skill["description"]
        if len(desc) > 220:
            desc = desc[:217] + "..."
        print(f"- {skill['name']} ({skill['origin']}){flag}\n  {desc or '(sans description)'}\n  {skill['path']}")


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        # Sortie tronquée par un pipe (head, etc.) : ce n'est pas une erreur.
        sys.stderr.close()
