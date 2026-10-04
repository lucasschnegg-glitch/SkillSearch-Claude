#!/usr/bin/env python3
"""Tests du hook skill-reminder.sh : rappel toujours présent, indices corrects, négations.

  python3 tests/test_hook.py
"""

import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "plugins/skill-orchestrator/scripts/skill-reminder.sh"

# (message, indices attendus) ; « aucun » = aucun indice.
CASES = [
    ("Combien font 17 x 23 ?", set()),
    ("Mode choix pour cette tâche : prépare une présentation", {"choix"}),
    ("Propose-moi plusieurs skills pour ce rapport", {"choix"}),
    ("Je veux choisir les skills.", {"choix"}),
    ("MODE CHOIX et Désactive la recherche Internet", {"choix", "internet-off"}),
    ("Mode automatique avec recherche Internet. Fais un BPMN", {"auto", "internet-on"}),
    ("Mode automatique.", {"auto"}),
    ("Désactive la recherche Internet.", {"internet-off"}),
    ("Utilise uniquement mes skills installés.", {"internet-off"}),
    ("Cherche un skill sur Internet si nécessaire.", {"internet-on"}),
    ("Trouve et installe un skill adapté.", {"internet-on"}),
    ("Active la recherche Internet pour cette tâche.", {"internet-on"}),
    ("N’utilise aucun skill pour cette tâche.", {"aucun"}),
    ("N'utilise aucun skill.", {"aucun"}),
    ("Utilise le skill docx.", {"explicite"}),
    ("Quels skills as-tu utilisés et pourquoi ?", {"rapport"}),
    ("Enregistre ce réglage par défaut désormais.", {"durable"}),
    ("Use the docx skill please", {"explicite"}),
    ("Which skills did you use?", {"rapport"}),
    ("Search the web for a skill that converts BPMN", {"internet-on"}),
    # Négations et questions : pas d'activation.
    ("Comment fonctionne ton mode choix pour les skills ? Explique sans l'activer.", {"question-choix"}),
    ("Pas besoin du mode choix, fais au mieux.", {"question-choix"}),
    ("Pas besoin de chercher un skill sur Internet.", set()),
    ("N'active pas la recherche Internet.", set()),
    ("Explique-moi comment marche Internet", set()),
    ("Je cherche un skill de cuisine dans mon livre", set()),
    ("Vérifie que mes skills sont fonctionnels et non piratés.", {"audit"}),
    ("Audite le skill gepeto.", {"audit", "explicite-non"} - {"explicite-non"}),
]

LABELS = {
    "choix": "mode choix demandé",
    "auto": "retour au mode automatique",
    "internet-off": "option Internet désactivée",
    "internet-on": "option Internet activée",
    "aucun": "aucun skill pour cette tâche",
    "explicite": "skill demandé explicitement",
    "rapport": "rapport demandé",
    "durable": "préférence durable possible",
    "question-choix": "parle du mode choix sans le demander",
    "audit": "contrôle de skills demandé",
}


def run_hook(prompt, env=None):
    payload = json.dumps({"session_id": "s", "transcript_path": "/home/u/.claude/projects/-mode-choix/x.jsonl",
                          "cwd": "/home/u/mode choix internet", "hook_event_name": "UserPromptSubmit",
                          "prompt": prompt, "prompt_source": "user_input"}, ensure_ascii=False)
    result = subprocess.run(["sh", str(HOOK)], input=payload, capture_output=True, text=True,
                            env={**os.environ, **(env or {})}, timeout=10)
    return result.returncode, result.stdout


class HookTests(unittest.TestCase):
    def test_cases(self):
        for prompt, expected in CASES:
            with self.subTest(prompt=prompt):
                code, out = run_hook(prompt)
                self.assertEqual(code, 0)
                self.assertTrue(out.startswith("[Orchestration des skills]"), out)
                found = {key for key, label in LABELS.items() if label in out}
                self.assertEqual(found, expected, out)

    def test_desactivation(self):
        code, out = run_hook("Mode choix", env={"SKILL_ORCHESTRATOR_HOOK": "off"})
        self.assertEqual((code, out), (0, ""))

    def test_entree_vide(self):
        result = subprocess.run(["sh", str(HOOK)], input="", capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0)
        self.assertIn("[Orchestration des skills]", result.stdout)

    def test_taille(self):
        _, out = run_hook("Mode choix, mode automatique avec recherche Internet, n'utilise aucun skill, "
                          "quels skills as-tu utilisés, enregistre ce réglage par défaut")
        self.assertLess(len(out), 2000)

    @unittest.skipUnless(shutil.which("dash") and shutil.which("bash"), "dash et bash requis")
    def test_shells(self):
        outputs = set()
        for shell in (["dash"], ["bash", "--posix"], ["bash"]):
            payload = json.dumps({"prompt": "MODE CHOIX et Désactive la recherche Internet"}, ensure_ascii=False)
            r = subprocess.run(shell + [str(HOOK)], input=payload, capture_output=True, text=True, timeout=10)
            outputs.add(r.stdout)
        self.assertEqual(len(outputs), 1)


if __name__ == "__main__":
    unittest.main(verbosity=1)
