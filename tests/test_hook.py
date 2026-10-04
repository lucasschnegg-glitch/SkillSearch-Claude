#!/usr/bin/env python3
"""Tests du hook (skill-reminder.sh + skill_reminder.py) : rappel, indices neutres, négations,
robustesse de lecture (échappements JSON, locale C, multiligne) et repli sans Python.

  python3 tests/test_hook.py
"""

import json
import os
import shutil
import subprocess
import sys
import time
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins/skill-orchestrator/scripts"
HOOK = SCRIPTS / "skill-reminder.sh"
sys.path.insert(0, str(SCRIPTS))
import skill_reminder  # noqa: E402

X = "orchestration"
C, A, I, O, N, E, R, K, P = ("mode choix", "mode automatique", "recherche Internet de skills",
                             "skills installés seulement", "aucun skill", "skill nommé",
                             "rapport des skills utilisés", "contrôle des skills", "préférence durable")

# (message, {(libellé, négation possible)})
CASES = [
    ("Combien font 17 x 23 ?", set()),
    ("Mode choix pour cette tâche : prépare une présentation", {(C, False)}),
    ("Propose-moi plusieurs skills pour ce rapport", {(C, False)}),
    ("Je veux choisir les skills.", {(C, False)}),
    ("MODE CHOIX et Désactive la recherche Internet", {(C, False), (I, True)}),
    ("Mode automatique avec recherche Internet. Fais un BPMN", {(A, False), (I, False)}),
    ("Mode automatique.", {(A, False)}),
    ("Désactive la recherche Internet.", {(I, True)}),
    ("Utilise uniquement mes skills installés.", {(O, False)}),
    ("Cherche un skill sur Internet si nécessaire.", {(I, False)}),
    ("Trouve et installe un skill adapté.", {(I, False)}),
    ("Active la recherche Internet pour cette tâche.", {(I, False)}),
    ("N’utilise aucun skill pour cette tâche.", {(N, False)}),
    ("N'utilise aucun skill.", {(N, False)}),
    ("Utilise le skill docx.", {(E, False)}),
    ("Quels skills as-tu utilisés et pourquoi ?", {(R, False)}),
    ("Enregistre ce réglage par défaut désormais.", {(P, False)}),
    ("Use the docx skill please", {(E, False)}),
    ("Which skills did you use?", {(R, False)}),
    ("Search the web for a skill that converts BPMN", {(I, False)}),
    # Une question sur le mode : repérée, sans négation ; le rappel demande d'interpréter.
    ("Comment fonctionne ton mode choix pour les skills ? Explique sans l'activer.", {(C, False)}),
    ("Pas besoin du mode choix, fais au mieux.", {(C, True)}),
    ("Pas besoin de chercher un skill sur Internet.", {(I, True)}),
    ("N'active pas la recherche Internet.", {(I, True)}),
    ("Explique-moi comment marche Internet", set()),
    ("Je cherche un skill de cuisine dans mon livre", set()),
    ("Vérifie que mes skills sont fonctionnels et non piratés.", {(K, False)}),
    ("Audite le skill gepeto.", {(K, False)}),
    # Erreurs de l'ancien hook (revue du 4 octobre 2026) : sens inversé ou faux positif.
    ("No need for choice mode, just do it", {(C, True)}),
    ("Inutile de passer en mode choix", {(C, True)}),
    ("Je ne veux pas du mode choix", {(C, True)}),
    ("Pas la peine d'activer le mode choix", {(C, True)}),
    ("Désactive le mode automatique", {(A, True)}),
    ("Don't search the internet for skills", {(I, True)}),
    ("N'installe pas de skill depuis Internet", {(I, True)}),
    ("Laisse-moi choisir le titre du rapport", set()),
    ("Check the skills section of my CV", set()),
    ("Recherche les soft skills les plus demandés en ligne", set()),
    ("Use the skill you think is best", set()),
    ("Mémorise mes préférences de mise en page", set()),
    ("Liste les compétences (skills) clés pour un poste d'actuaire", set()),
    ("Mode choix, et pas de recherche Internet.", {(C, False), (I, True)}),
    ("VÉRIFIE MES SKILLS", {(K, False)}),
    # Orchestration demandée ou refusée en toutes lettres ; le nom du skill ne compte pas.
    ("Orchestre cette mission : crée une fiche de révision", {(X, False)}),
    ("Sans orchestration, fais un résumé du chapitre 4", {(X, True)}),
    ("Audite le skill skill-orchestrator", {(K, False)}),
]

# (message, livrable attendu ou None) : début possible d'une mission.
MISSIONS = [
    ("Rédige un rapport Word de deux pages sur Solvabilité II", "rapport"),
    ("Prépare une présentation de 10 diapositives sur la réassurance", "presentation"),
    ("Corrige l'exercice 3 de la série 2", "exercice"),
    ("Write a report on climate risk", "report"),
    ("Combien font 17 x 23 ?", None),
    ("Qu'est-ce qu'un rapport ORSA ?", None),
    ("Comment fonctionne ton mode choix ?", None),
    ("Ajoute une conclusion", None),
    ("Fais 17x23", None),
    ("/skill-orchestrator:orchestrer Rédige un rapport Word", None),
]


def run_hook(prompt=None, env=None, raw=None, ascii_json=False):
    if raw is None:
        raw = json.dumps({"session_id": "s", "transcript_path": "/home/u/.claude/projects/-mode-choix/x.jsonl",
                          "cwd": "/home/u/mode choix internet", "hook_event_name": "UserPromptSubmit",
                          "prompt": prompt, "prompt_source": "user_input"}, ensure_ascii=ascii_json)
    result = subprocess.run(["sh", str(HOOK)], input=raw.encode("utf-8"), capture_output=True,
                            env={**os.environ, **(env or {})}, timeout=10)
    return result.returncode, result.stdout.decode("utf-8")


def context_of(out):
    """Texte ajouté au contexte, lu dans la sortie JSON du hook."""
    if not out.strip():
        return ""
    data = json.loads(out)
    hso = data["hookSpecificOutput"]
    assert hso["hookEventName"] == "UserPromptSubmit"
    return hso["additionalContext"]


class LogicTests(unittest.TestCase):
    def test_cases(self):
        for prompt, expected in CASES:
            with self.subTest(prompt=prompt):
                self.assertEqual(set(skill_reminder.find_controls(prompt)), expected)

    def test_missions(self):
        for prompt, expected in MISSIONS:
            with self.subTest(prompt=prompt):
                found = skill_reminder.find_mission(prompt)
                if expected is None:
                    self.assertIsNone(found)
                else:
                    self.assertIsNotNone(found)
                    self.assertTrue(found.startswith(expected[:6]), found)

    def test_multiligne(self):
        self.assertEqual(skill_reminder.find_controls("Mode\nchoix pour ce rapport"), [(C, False)])


class HookTests(unittest.TestCase):
    def test_sortie_json_et_rappel(self):
        code, out = run_hook("Explique-moi la réassurance proportionnelle")
        self.assertEqual(code, 0)
        ctx = context_of(out)
        self.assertEqual(ctx, skill_reminder.REMINDER)
        self.assertLess(len(ctx), 300)  # rappel court : il est injecté à chaque message
        self.assertNotIn("désactivée", ctx)  # pas de réglages par défaut qui contrediraient CLAUDE.md

    def test_indice_de_mission(self):
        ctx = context_of(run_hook("Rédige un rapport Word sur Solvabilité II")[1])
        self.assertIn("début d'une mission (livrable repéré : « rapport »)", ctx)
        self.assertIn("question de départ", ctx)
        self.assertNotIn("début d'une mission", context_of(run_hook("Combien font 17 x 23 ?")[1]))
        hints = context_of(run_hook("Rédige un rapport Word", env={"SKILL_ORCHESTRATOR_HOOK": "hints"})[1])
        self.assertNotIn(skill_reminder.REMINDER, hints)
        self.assertIn("début d'une mission", hints)

    def test_indices_neutres(self):
        ctx = context_of(run_hook("Pas besoin du mode choix, fais au mieux.")[1])
        self.assertIn("« mode choix » (négation possible)", ctx)
        self.assertNotIn("demandé", ctx)

    def test_echappements_unicode(self):
        ctx = context_of(run_hook("Désactive la recherche Internet", ascii_json=True)[1])
        self.assertIn("recherche Internet de skills", ctx)

    def test_locale_c(self):
        ctx = context_of(run_hook("VÉRIFIE MES SKILLS", env={"LC_ALL": "C", "LANG": "C"})[1])
        self.assertIn("contrôle des skills", ctx)

    def test_desactivation(self):
        self.assertEqual(run_hook("Mode choix", env={"SKILL_ORCHESTRATOR_HOOK": "off"}), (0, ""))

    def test_mode_indices_seulement(self):
        env = {"SKILL_ORCHESTRATOR_HOOK": "hints"}
        self.assertEqual(run_hook("Explique-moi la réassurance", env=env), (0, ""))
        ctx = context_of(run_hook("Mode choix", env=env)[1])
        self.assertNotIn(skill_reminder.REMINDER, ctx)
        self.assertIn("mode choix", ctx)

    def test_entree_vide_ou_invalide(self):
        for raw in ("", "pas du json", '{"prompt": 42}', "[]"):
            with self.subTest(raw=raw):
                code, out = run_hook(raw=raw)
                self.assertEqual(code, 0)
                self.assertEqual(context_of(out), skill_reminder.REMINDER)

    def test_repli_sans_python(self):
        for py in ("/chemin/inexistant/python3", "false"):
            with self.subTest(py=py):
                code, out = run_hook("Mode choix", env={"SKILL_ORCHESTRATOR_PYTHON": py})
                self.assertEqual(code, 0)
                # Le repli du lanceur reprend exactement le rappel du module.
                self.assertEqual(context_of(out), skill_reminder.REMINDER)

    def test_repli_sans_python_mode_indices(self):
        env = {"SKILL_ORCHESTRATOR_PYTHON": "false", "SKILL_ORCHESTRATOR_HOOK": "hints"}
        self.assertEqual(run_hook("Mode choix", env=env), (0, ""))

    def test_taille(self):
        _, out = run_hook("Mode choix, mode automatique avec recherche Internet, n'utilise aucun skill, "
                          "quels skills as-tu utilisés, enregistre ce réglage par défaut")
        self.assertLess(len(context_of(out)), 1000)

    def test_latence(self):
        start = time.monotonic()
        run_hook("x" * 200_000 + " mode choix")
        self.assertLess(time.monotonic() - start, 3)

    @unittest.skipUnless(shutil.which("dash") and shutil.which("bash"), "dash et bash requis")
    def test_shells(self):
        outputs = set()
        payload = json.dumps({"prompt": "MODE CHOIX et Désactive la recherche Internet"}, ensure_ascii=False)
        for shell in (["dash"], ["bash", "--posix"], ["bash"]):
            r = subprocess.run(shell + [str(HOOK)], input=payload, capture_output=True, text=True, timeout=10)
            outputs.add(r.stdout)
        self.assertEqual(len(outputs), 1)


if __name__ == "__main__":
    unittest.main(verbosity=1)
