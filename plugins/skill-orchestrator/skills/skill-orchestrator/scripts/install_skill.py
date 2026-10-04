#!/usr/bin/env python3
"""Installe un skill déjà téléchargé, en installant exactement ce qui a été audité.

Bibliothèque standard uniquement. Aucun accès réseau, aucun code du skill exécuté.

  python3 install_skill.py <dossier du skill téléchargé> <racine des skills> [--name NOM]
                           [--source-url URL] [--accept-alerts] [--dry-run]
  python3 install_skill.py --hash <dossier>      empreinte de l'arborescence (hors SOURCE.json)
  python3 install_skill.py --verify <dossier>    compare le skill installé à son SOURCE.json

Déroulé : copie dans un dossier temporaire (instantané), audit de cette copie avec
audit_skill.py, empreinte, copie vers <racine>/<nom>, nouvelle empreinte comparée à la
première, puis écriture de SOURCE.json par ce script. Ce qui est installé est donc
identique, octet pour octet, à ce qui a été audité, même si le dossier d'origine change
entre-temps. Un SOURCE.json ou SOURCE.md fourni par le dépôt est ignoré : seule la
provenance écrite ici fait foi.

Refus : verdict ÉCHEC ; verdict ALERTE sans --accept-alerts (à passer seulement après avoir
lu chaque alerte) ; dossier de destination existant ; nom non conforme.
"""

import argparse
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_skill  # noqa: E402

VERSION = "1"
PROVENANCE = "SOURCE.json"
IGNORED = {".git", "__pycache__", ".DS_Store", ".venv", "venv", "node_modules"}
SHIPPED_PROVENANCE = {"SOURCE.json", "SOURCE.md"}


def tree_hash(root):
    """SHA-256 de l'arborescence : chemins, contenus, bit exécutable et cibles des liens."""
    root = Path(root)
    digest = hashlib.sha256()
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d not in IGNORED)
        base = Path(dirpath)
        entries = sorted(filenames + [d for d in dirnames if (base / d).is_symlink()])
        for name in entries:
            path = base / name
            rel = path.relative_to(root).as_posix()
            if rel == PROVENANCE or name in IGNORED:
                continue
            if path.is_symlink():
                digest.update(f"L {rel} -> {os.readlink(path)}\n".encode("utf-8"))
            else:
                executable = "x" if os.stat(path).st_mode & 0o111 else "-"
                content = hashlib.sha256(path.read_bytes()).hexdigest()
                digest.update(f"F {rel} {executable} {content}\n".encode("utf-8"))
    return digest.hexdigest()


def git_info(source):
    def git(*args):
        out = subprocess.run(["git", "-C", str(source), *args], capture_output=True, text=True)
        return out.stdout.strip() if out.returncode == 0 else ""
    if not shutil.which("git") or git("rev-parse", "--is-inside-work-tree") != "true":
        return {}
    return {"commit": git("rev-parse", "HEAD"),
            "modifie_localement": bool(git("status", "--porcelain", "--", ".")),
            "depot": git("remote", "get-url", "origin")}


def snapshot(source, staging):
    """Copie le skill dans staging ; renvoie les fichiers de provenance ignorés."""
    ignored = []

    def ignore(directory, names):
        skip = {n for n in names if n in IGNORED}
        if Path(directory).resolve() == source.resolve():
            shipped = {n for n in names if n in SHIPPED_PROVENANCE}
            ignored.extend(sorted(shipped))
            skip |= shipped
        return skip

    shutil.copytree(source, staging, symlinks=True, ignore=ignore)
    return ignored


def skill_name(directory):
    text = (directory / "SKILL.md").read_text(encoding="utf-8", errors="replace")
    meta, _ = audit_skill.parse_frontmatter(text)
    return (meta or {}).get("name") or directory.name


def install(source, root, name=None, source_url=None, accept_alerts=False, dry_run=False):
    source, root = Path(source).expanduser(), Path(root).expanduser()
    if not (source / "SKILL.md").is_file():
        return {"statut": "refusé", "raison": f"SKILL.md introuvable dans {source}"}
    name = name or skill_name(source)
    if not audit_skill.NAME_RE.match(name) or len(name) > 64:
        return {"statut": "refusé", "raison": f"nom non conforme (minuscules, chiffres, tirets) : {name}"}
    dest = root / name
    if dest.exists() or dest.is_symlink():
        return {"statut": "refusé", "raison": f"{dest} existe déjà : choisis un autre nom ou demande à l'utilisateur"}

    with tempfile.TemporaryDirectory(prefix="skill-install-") as tmp:
        staging = Path(tmp) / name
        ignored = snapshot(source, staging)
        report = audit_skill.audit(staging)
        alerts = [f for f in report.findings if f["gravite"] in ("moyenne", "élevée", "critique")]
        result = {"nom": name, "destination": str(dest), "verdict_audit": report.verdict,
                  "alertes": [f"{f['gravite']} : {f['message']} [{f['fichier']}]" for f in alerts],
                  "provenance_fournie_ignoree": ignored}
        if report.verdict == "ÉCHEC":
            return {**result, "statut": "refusé", "raison": "audit en ÉCHEC : ne pas installer"}
        if report.verdict == "ALERTE" and not accept_alerts:
            return {**result, "statut": "refusé",
                    "raison": "audit en ALERTE : lis chaque alerte, puis relance avec --accept-alerts si elles sont bénignes"}
        audited_hash = tree_hash(staging)
        result["empreinte"] = audited_hash
        if dry_run:
            return {**result, "statut": "simulation", "raison": "rien n'a été copié (--dry-run)"}

        root.mkdir(parents=True, exist_ok=True)
        shutil.copytree(staging, dest, symlinks=True)
    if tree_hash(dest) != audited_hash:
        shutil.rmtree(dest, ignore_errors=True)
        return {**result, "statut": "refusé", "raison": "la copie installée diffère de la copie auditée : retirée"}

    provenance = {"nom": name, "installe_le": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                  "source_locale": str(source.resolve()), "source_url": source_url or "",
                  **git_info(source), "empreinte_sha256": audited_hash,
                  "audit": {"verdict": report.verdict, "alertes_acceptees": result["alertes"]},
                  "installe_par": f"skill-orchestrator install_skill.py v{VERSION}"}
    (dest / PROVENANCE).write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {**result, "statut": "installé", "provenance": str(dest / PROVENANCE),
            "commit": provenance.get("commit", "")}


def verify(directory):
    directory = Path(directory).expanduser()
    path = directory / PROVENANCE
    if not path.is_file():
        return {"statut": "inconnu", "raison": f"pas de {PROVENANCE} : skill non installé par ce script"}
    expected = json.loads(path.read_text(encoding="utf-8")).get("empreinte_sha256", "")
    actual = tree_hash(directory)
    if actual == expected:
        return {"statut": "intact", "empreinte": actual}
    return {"statut": "modifié depuis l'installation", "attendu": expected, "actuel": actual}


def main():
    parser = argparse.ArgumentParser(description="Installe un skill audité, à l'identique.")
    parser.add_argument("source", nargs="?", help="dossier du skill téléchargé (contient SKILL.md)")
    parser.add_argument("root", nargs="?", help="racine des skills (~/.claude/skills ou .claude/skills)")
    parser.add_argument("--name", help="nom du dossier installé (défaut : name du frontmatter)")
    parser.add_argument("--source-url", help="URL du dépôt, notée dans SOURCE.json")
    parser.add_argument("--accept-alerts", action="store_true", help="installer malgré un verdict ALERTE, après lecture")
    parser.add_argument("--dry-run", action="store_true", help="auditer et calculer l'empreinte sans copier")
    parser.add_argument("--hash", metavar="DOSSIER", help="afficher l'empreinte d'une arborescence")
    parser.add_argument("--verify", metavar="DOSSIER", help="vérifier un skill installé contre son SOURCE.json")
    args = parser.parse_args()

    if args.hash:
        print(tree_hash(args.hash))
        return 0
    if args.verify:
        result = verify(args.verify)
    elif args.source and args.root:
        result = install(args.source, args.root, args.name, args.source_url, args.accept_alerts, args.dry_run)
    else:
        parser.print_help()
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["statut"] in ("installé", "simulation", "intact") else 1


if __name__ == "__main__":
    sys.exit(main())
