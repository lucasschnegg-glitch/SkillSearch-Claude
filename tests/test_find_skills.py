#!/usr/bin/env python3
"""Tests de find_skills.py sur un catalogue fabriqué.

  python3 tests/test_find_skills.py
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "plugins/skill-orchestrator/skills/skill-orchestrator/scripts/find_skills.py"


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class FindSkillsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.config = root / "config"
        skills = self.config / "skills"
        write(skills / "presentations/SKILL.md",
              "---\nname: presentations\ndescription: >-\n  Crée des présentations PowerPoint\n  soignées (slides).\n---\nCorps\n")
        write(skills / "synced/compte/tableur/SKILL.md",
              '---\nname: tableur\ndescription: "Spreadsheet work: open, edit \\"xlsx\\" files."\n---\nCorps\n')
        write(skills / "manuel/SKILL.md",
              "---\nname: manuel\ndescription: Déploiement en production.\ndisable-model-invocation: true\n---\nCorps\n")
        # Deux versions d'un même plugin dans le cache : seule la plus récente compte.
        old = self.config / "plugins/cache/marche/outil/1.0.0/skills/rapport/SKILL.md"
        new = self.config / "plugins/cache/marche/outil/1.1.0/skills/rapport/SKILL.md"
        write(old, "---\nname: rapport\ndescription: Ancienne version.\n---\n")
        write(new, "---\nname: rapport\ndescription: Rapports Word (docx) vérifiés.\n---\n")
        os.utime(old, (1, 1))
        self.project = root / "projet"
        write(self.project / ".claude/skills/local/SKILL.md", "---\nname: local\ndescription: Skill du projet.\n---\n")

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self, *args):
        env = {**os.environ, "CLAUDE_CONFIG_DIR": str(self.config), "HOME": str(self.config.parent)}
        out = subprocess.run([sys.executable, str(SCRIPT), "--json", *args], capture_output=True, text=True,
                             cwd=self.project, env=env, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        data = json.loads(out.stdout)
        # Le script parcourt aussi les skills de l'application (/mnt/skills) : on les écarte ici.
        data["results"] = [r for r in data["results"] if r["path"].startswith(self.tmp.name)]
        data["count"] = len(data["results"])
        return data

    def test_liste_complete(self):
        names = sorted(r["name"] for r in self.run_script("--all")["results"])
        self.assertEqual(names, ["local", "manuel", "presentations", "rapport", "tableur"])

    def test_accents_et_bloc_replie(self):
        res = self.run_script("présentation")["results"]
        self.assertEqual(res[0]["name"], "presentations")
        self.assertIn("soignées", res[0]["description"])

    def test_guillemets_echappes(self):
        res = self.run_script("xlsx", "--limit", "50")["results"]
        self.assertEqual(res[0]["description"], 'Spreadsheet work: open, edit "xlsx" files.')
        self.assertIn("synchronisé", res[0]["origin"])

    def test_invocation_manuelle(self):
        res = self.run_script("production")["results"]
        self.assertFalse(res[0]["model_invocable"])

    def test_version_la_plus_recente(self):
        res = [r for r in self.run_script("--all")["results"] if r["name"] == "rapport"]
        self.assertEqual(len(res), 1)
        self.assertIn("docx", res[0]["description"])
        self.assertEqual(res[0]["origin"], "plugin outil@marche")

    def test_skill_du_projet(self):
        res = self.run_script("projet")["results"]
        self.assertEqual(res[0]["origin"], "projet")

    def test_aucun_resultat(self):
        self.assertEqual(self.run_script("introuvable-xyz")["count"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=1)
