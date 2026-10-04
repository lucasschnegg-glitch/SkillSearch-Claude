#!/usr/bin/env python3
"""Vérifie que les fichiers du plugin et les archives n'ont pas été modifiés.

  python3 install/verify-integrity.py                    vérifie ce dossier
  python3 install/verify-integrity.py --zip <archive>    vérifie aussi une archive téléchargée
  python3 install/verify-integrity.py --installed <dossier du plugin installé>

Compare chaque fichier à SHA256SUMS, puis vérifie que les archives de dist/ contiennent
exactement les fichiers du plugin. Code de sortie 0 si tout correspond.

Limite : SHA256SUMS est dans le même dépôt. Il détecte une corruption ou une
modification locale, pas une modification du dépôt lui-même. Pour cela, compare aussi
le commit à celui qui t'a été communiqué (git rev-parse HEAD).
"""

import argparse
import hashlib
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PLUGIN_PREFIX = "plugins/skill-orchestrator/"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load_sums():
    sums = {}
    for line in (REPO / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        if line.strip():
            digest, path = line.split(None, 1)
            sums[path.strip()] = digest
    return sums


def check_zip(archive, sums, problems):
    expected = {p[len(PLUGIN_PREFIX):]: d for p, d in sums.items() if p.startswith(PLUGIN_PREFIX)}
    with zipfile.ZipFile(archive) as zf:
        names = {n.split("/", 1)[1]: n for n in zf.namelist() if "/" in n and not n.endswith("/")}
        skill_only = "SKILL.md" in names and ".claude-plugin/plugin.json" not in names
        if skill_only:
            expected = {p[len("skills/skill-orchestrator/"):]: d for p, d in expected.items()
                        if p.startswith("skills/skill-orchestrator/")}
        for rel, digest in expected.items():
            if rel not in names:
                problems.append(f"{archive.name} : fichier manquant {rel}")
            elif sha(zf.read(names[rel])) != digest:
                problems.append(f"{archive.name} : contenu différent {rel}")
        for rel in names:
            if rel not in expected:
                problems.append(f"{archive.name} : fichier inattendu {rel}")


def main():
    parser = argparse.ArgumentParser(description="Vérifie l'intégrité du plugin skill-orchestrator.")
    parser.add_argument("--zip", action="append", default=[], help="archive supplémentaire à vérifier")
    parser.add_argument("--installed", help="dossier du plugin installé (par exemple dans le cache de Claude Code)")
    args = parser.parse_args()

    sums, problems = load_sums(), []
    for path, digest in sums.items():
        p = REPO / path
        if not p.is_file():
            problems.append(f"absent : {path}")
        elif sha(p.read_bytes()) != digest:
            problems.append(f"modifié : {path}")
    plugin_files = {p.relative_to(REPO).as_posix() for p in (REPO / PLUGIN_PREFIX).rglob("*")
                    if p.is_file() and "__pycache__" not in p.parts}
    for extra in sorted(plugin_files - set(sums)):
        problems.append(f"fichier non répertorié dans le plugin : {extra}")
    for archive in sorted((REPO / "dist").glob("*.zip")) + [Path(z) for z in args.zip]:
        check_zip(archive, sums, problems)
    if args.installed:
        base = Path(args.installed)
        for path, digest in sums.items():
            if path.startswith(PLUGIN_PREFIX):
                q = base / path[len(PLUGIN_PREFIX):]
                if not q.is_file() or sha(q.read_bytes()) != digest:
                    problems.append(f"installé, différent ou absent : {path[len(PLUGIN_PREFIX):]}")

    if problems:
        print("ÉCHEC de la vérification :")
        for p in problems:
            print(f"  - {p}")
        sys.exit(1)
    print(f"OK : {len(sums)} empreintes vérifiées, archives conformes.")


if __name__ == "__main__":
    main()
