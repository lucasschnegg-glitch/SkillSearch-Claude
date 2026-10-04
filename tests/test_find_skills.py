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
        # Chemins résolus des deux côtés : sous macOS, /var est un lien vers /private/var.
        base = os.path.realpath(self.tmp.name)
        data["results"] = [r for r in data["results"] if os.path.realpath(r["path"]).startswith(base)]
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


class ClassementTests(unittest.TestCase):
    """Classement : mots vides, traductions, expressions, bonus du nom, égalités."""

    SKILLS = {
        "sheets-tool": "Create and edit spreadsheet files (.xlsx) with formulas and charts.",
        "cover-letter-writer": "Writes a tailored cover letter for a job application.",
        "motivation-coach": "Keeps your motivation high with daily habit tracking.",
        "outil-mise-en-page": "Outil de mise en page pour les rapports de stage.",
        "docx": "Create and edit Word documents.",
        "report-maker": "Generates reports and exports them to docx: docx templates, docx styles, docx tables.",
        "resume-builder": "Builds a professional resume (CV) tailored to a job offer.",
        "lecture-summarizer": "Summarizes course lectures into study notes and summaries.",
        # Écrits dans cet ordre pour que l'ordre du disque ne soit pas l'ordre alphabétique.
        "beta-twin": "Twin helper for quantum widgets.",
        "alpha-twin": "Twin helper for quantum widgets.",
    }

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.catalog = root / "catalogue"
        for name, description in self.SKILLS.items():
            write(self.catalog / name / "SKILL.md", f"---\nname: {name}\ndescription: {description}\n---\n")
        # Description écrite à la ligne suivante, indentée et entre guillemets (YAML valide).
        # Skill rangé dans un dossier caché : Claude Code ne le charge pas, la recherche non plus.
        write(self.catalog / ".archive/sheets-archive/SKILL.md",
              "---\nname: sheets-archive\ndescription: Old spreadsheet tool.\n---\n")
        write(self.catalog / "multi-ligne/SKILL.md",
              '---\nname: multi-ligne\ndescription:\n  "Describes a skill on an indented,\n'
              '  quoted continuation line."\n---\n')
        self.config = root / "config"
        self.config.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def names(self, *args, seed="0"):
        env = {**os.environ, "CLAUDE_CONFIG_DIR": str(self.config), "HOME": str(self.config),
               "PYTHONHASHSEED": seed}
        out = subprocess.run([sys.executable, str(SCRIPT), "--json", "--root", str(self.catalog), *args],
                             capture_output=True, text=True, cwd=self.tmp.name, env=env, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        base = os.path.realpath(self.tmp.name)
        results = json.loads(out.stdout)["results"]
        return [r["name"] for r in results if os.path.realpath(r["path"]).startswith(base)]

    def test_mots_vides_seuls(self):
        self.assertEqual(self.names("de"), [])
        self.assertEqual(self.names("de", "la", "the"), [])

    def test_synonyme_francais(self):
        self.assertEqual(self.names("tableur")[0], "sheets-tool")

    def test_expression_de_plusieurs_mots(self):
        res = self.names("lettre", "de", "motivation")
        self.assertEqual(res[0], "cover-letter-writer")
        self.assertLess(res.index("cover-letter-writer"), res.index("motivation-coach"))
        self.assertEqual(self.names("lettre de motivation")[0], "cover-letter-writer")

    def test_bonus_du_nom(self):
        res = self.names("docx")
        self.assertEqual(res[:2], ["docx", "report-maker"])

    def test_egalite_ordre_alphabetique(self):
        runs = [self.names("quantum", "widgets", seed=seed) for seed in ("0", "1", "123")]
        self.assertEqual(runs[0], ["alpha-twin", "beta-twin"])
        self.assertEqual(runs[0], runs[1])
        self.assertEqual(runs[0], runs[2])

    def test_resume_de_cours_n_est_pas_un_cv(self):
        res = self.names("résumé", "de", "cours")
        self.assertEqual(res[0], "lecture-summarizer")
        # Avec un contexte d'emploi, « résumé » redevient un CV.
        self.assertEqual(self.names("résumé", "cv", "job")[0], "resume-builder")

    def test_dossier_cache_ignore(self):
        self.assertNotIn("sheets-archive", self.names("spreadsheet"))

    def test_copie_rangee_dans_un_skill_ignoree(self):
        # Copie d'un autre skill dans _external/ : elle ne doit ni apparaître ni remplacer l'original.
        write(self.catalog / "docx/_external/report-maker/SKILL.md",
              "---\nname: report-maker\ndescription: Vendored copy, docx docx docx.\n---\n")
        hits = [p for p in self.paths("report-maker") if "_external" in p]
        self.assertEqual(hits, [])

    def paths(self, *args):
        env = {**os.environ, "CLAUDE_CONFIG_DIR": str(self.config), "HOME": str(self.config)}
        out = subprocess.run([sys.executable, str(SCRIPT), "--json", "--root", str(self.catalog), *args],
                             capture_output=True, text=True, cwd=self.tmp.name, env=env, timeout=30)
        return [r["path"] for r in json.loads(out.stdout)["results"]]

    def test_description_a_la_ligne(self):
        env = {**os.environ, "CLAUDE_CONFIG_DIR": str(self.config), "HOME": str(self.config)}
        out = subprocess.run([sys.executable, str(SCRIPT), "--json", "--all", "--root", str(self.catalog)],
                             capture_output=True, text=True, cwd=self.tmp.name, env=env, timeout=30)
        skill = next(r for r in json.loads(out.stdout)["results"] if r["name"] == "multi-ligne")
        self.assertEqual(skill["description"], "Describes a skill on an indented, quoted continuation line.")


if __name__ == "__main__":
    unittest.main(verbosity=1)
