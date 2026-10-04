# Tests

Tests unitaires, sans modèle (quelques secondes) :

```sh
sh tests/run-unit-tests.sh
```

Ils couvrent le hook (`test_hook.py`), la recherche de skills (`test_find_skills.py`), l'audit (`test_audit_skill.py`), l'installation (`test_install.sh`), l'intégrité (`install/verify-integrity.py`) et les manifestes.

Scénarios de comportement exécutés avec `claude -p`. Chaque cas ouvre une session neuve dans un projet temporaire :

- `CLAUDE.md` du projet = le bloc `instructions/claude-code-CLAUDE.md`. Il remplace ici `~/.claude/CLAUDE.md` : Claude Code charge les deux fichiers de la même manière ;
- plugin chargé pour la session seulement avec `--plugin-dir`, donc rien n'est installé ;
- outils autorisés limités par cas (`allowed_tools`) ; les autres sont refusés sans question.

```sh
tests/run-tests.sh                         # tous les cas, modèle claude-opus-5-5
MODEL=claude-sonnet-5-5 tests/run-tests.sh # autre modèle
tests/run-tests.sh mode-choix-attente      # un cas
python3 tests/check_results.py tests/results   # revérifier sans relancer
```

- `cases.json` : prompts, messages suivants (`followup`), fichiers d'entrée (`files`), dossiers autorisés (`add_dirs`) et critères vérifiables (`checks`, `turn_checks` par message, `any_of` pour les issues acceptables).
- `check_results.py` : lit les flux `stream-json` (outils appelés, skills chargés, sortie du hook, fichiers créés, texte final).
- `results/<modèle>/summary.json` : résumés versionnés des derniers passages.
- `RESULTATS.md` : bilan commenté.
