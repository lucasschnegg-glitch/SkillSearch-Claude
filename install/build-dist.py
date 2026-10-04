#!/usr/bin/env python3
"""Construit les archives à téléverser dans l'application Claude (Cowork).

  python3 install/build-dist.py

Produit dans dist/ :
  - skill-orchestrator-plugin.zip : le plugin complet (skill + hook), pour
    Personnaliser > Plugins > Ajouter > Upload plugin. Choix recommandé.
  - skill-orchestrator-skill.zip  : le skill seul, pour Personnaliser > Skills,
    uniquement si l'ajout de plugins n'est pas possible (pas de hook dans ce cas).
N'installe jamais les deux : le skill serait présent en double.
"""

import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PLUGIN = REPO / "plugins" / "skill-orchestrator"
SKILL = PLUGIN / "skills" / "skill-orchestrator"
DIST = REPO / "dist"
SKIP = {"__pycache__", ".DS_Store"}
# Date fixe : les archives restent identiques tant que le contenu ne change pas.
FIXED_DATE = (2026, 1, 1, 0, 0, 0)


def build(source, archive, top):
    files = sorted(p for p in source.rglob("*") if p.is_file() and not SKIP.intersection(p.parts))
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            info = zipfile.ZipInfo(f"{top}/{path.relative_to(source).as_posix()}", FIXED_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            # Conserve le bit exécutable des scripts.
            info.external_attr = (0o755 if path.stat().st_mode & 0o111 else 0o644) << 16
            zf.writestr(info, path.read_bytes())
    print(f"{archive.relative_to(REPO)} : {len(files)} fichiers")


def main():
    DIST.mkdir(exist_ok=True)
    build(PLUGIN, DIST / "skill-orchestrator-plugin.zip", "skill-orchestrator")
    build(SKILL, DIST / "skill-orchestrator-skill.zip", "skill-orchestrator")


if __name__ == "__main__":
    main()
