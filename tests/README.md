# Tests

Tests unitaires, sans modèle (quelques secondes) :

```sh
sh tests/run-unit-tests.sh
```

Ils couvrent le hook (`test_hook.py`), la recherche de skills (`test_find_skills.py`, et `eval_find_skills.py` pour mesurer le classement sur ton catalogue), l'audit (`test_audit_skill.py`), la vérification d'origine (`test_compare_upstream.py`), l'installation vérifiée d'un skill (`test_install_skill.py`), le script d'installation des instructions (`test_install.sh`), l'intégrité (`install/verify-integrity.py`), les manifestes, et le banc d'essai lui-même (`test_check_results.py` : critères sur des flux fabriqués, synthèse, lanceur avec le faux `claude` de `fixtures/fake_claude.py`).

## Scénarios de comportement

Exécutés avec `claude -p` par `run_evals.py` (Python 3.9 ou plus, macOS et Linux ; `run-tests.sh` n'est qu'une enveloppe). Chaque cas ouvre une session neuve dans un projet temporaire :

- `CLAUDE.md` du projet = le bloc `instructions/claude-code-CLAUDE.md`, ou un fichier vide selon le bras. Il remplace ici `~/.claude/CLAUDE.md` : Claude Code charge les deux fichiers de la même manière ;
- plugin chargé pour la session seulement avec `--plugin-dir`, donc rien n'est installé ;
- outils autorisés limités par cas (`allowed_tools`), variables propres au cas (`env`), messages suivants envoyés avec `--resume`.

Bras (`--arm`, liste séparée par des virgules ou `all`) :

| Bras | Bloc CLAUDE.md | Plugin (skill + hook) |
|---|---|---|
| `full` | oui | oui |
| `claude-md` | oui | non |
| `plugin` | non | oui |
| `baseline` | non (fichier vide) | non |

```sh
python3 tests/run_evals.py --dry-run --arm all --split all          # commandes qui seraient lancées, rien n'est écrit
python3 tests/run_evals.py --model claude-sonnet-5-5 --arm full,baseline \
  --cases simple-sans-skill,rapport-skills,audit-a-la-demande       # essai rapide
python3 tests/run_evals.py --model claude-opus-5-5 --arm all --split all --repeat 5 --jobs 6
python3 tests/aggregate.py tests/results                            # synthèse (Markdown ; --json fichier)
python3 tests/check_results.py --tree tests/results                 # revérifier sans relancer
```

Autres options : `--split dev|heldout|all` (défaut `dev`, ou `all` avec `--cases`), `--first-run` pour ajouter des répétitions, `--max-budget-usd` par appel, `--timeout` (1500 s), `--force`. Une commande interrompue se reprend telle quelle : les cas terminés ne sont pas relancés.

**Coût** : le nombre d'appels vaut bras × répétitions × (cas + messages suivants), plus un appel de vérification. Les 33 cas font 39 appels par bras et par répétition ; `--arm all --repeat 5` en fait donc 780. `--dry-run` affiche le total avant de dépenser quoi que ce soit.

Résultats : `results/<modèle>/<bras>/run<i>/` avec `<cas>.jsonl` (flux `stream-json`, plus des lignes `harness` qui séparent les messages), `.stderr`, `.files`, `.claude.md`, `meta.json` (versions du plugin et des instructions, réglages du passage ; non versionné, car il contient des chemins et réglages de la machine) et `summary.json`. Les anciens `results/opus/summary.json` et `results/sonnet/summary.json` restent lisibles (`aggregate.py --include-legacy`), mais ils ont été jugés avec les anciens critères.

## Critères

- `cases.json` : prompts, `followup`, `files`, `add_dirs`, `env`, `split`, `reglages` (remplace la ligne « Réglages durables » du bloc pour ce cas : les scénarios écrits pour le mode automatique gardent `sélection = automatique`) et critères : `checks` (toute la conversation), `turn_checks` (par message, à préférer dès qu'il y en a plusieurs), `any_of` (issues acceptables), `plugin_checks` (bras avec plugin seulement), `requires_skills` (skill qui doit exister sur la machine).
- Chemins portables : `{repo}`, `{home}`, `{plugin}`, `{scripts}` sont remplacés au lancement.
- Skills : « invoqué » = appel réussi de l'outil Skill ; « lu » = lecture d'un `SKILL.md` ; « chargé » = l'un ou l'autre. `skill_invoked_any`, `skill_not_invoked`, `no_skill_invoked` et `max_useful_skills` portent sur « chargé » (le skill demande de lire un skill par l'un ou l'autre moyen) ; `skill_tool_any` et `skill_tool_not_invoked` sur l'outil Skill seul (un skill en cours d'audit ne doit jamais être invoqué) ; `skill_read_any` sur les lectures. Les noms sont comparés exactement (`pptx` ne reconnaît pas `academic-pptx`).
- Recherches de catalogue : `SearchSkills`, `ListSkills`, `find_skills.py`, Grep/Glob et commandes Bash (`find`, `grep`, `ls`...) sur des dossiers de skills.
- Contrôles d'ordre et de sécurité : `bash_order` (audit exécuté avant toute copie vers `.claude/skills` ou tout `install_skill.py --accept-alerts`), `no_new_skill_tool` (un skill téléchargé ou installé n'est jamais chargé par l'outil Skill), `no_bypass_after_denial`, `source_file_if_installed` (`SOURCE.json` ou `SOURCE.md`), `no_write_outside` (rien dans `~/.claude`), `report_skills_subset` (skills cités dans le rapport ⊆ skills chargés ; les phrases négatives et les sections « écartés » sont ignorées).
- Les cas `heldout` ont été écrits avant tout passage et ne servent pas à régler le skill : ne les modifie pas d'après leurs résultats.

## Lire la synthèse

- Chaque case donne réussis / passages valides et le taux avec son intervalle de Wilson à 95 %. Avec 5 passages, 5/5 donne [57 – 100] : un écart de quelques passages ne prouve rien.
- Le lift `full − baseline` est la différence de taux, en points, avec l'intervalle de Newcombe : l'apport du plugin est établi pour un cas seulement si l'intervalle exclut 0. Le total groupé suppose des passages indépendants : c'est une indication, les intervalles par cas font foi.
- Les erreurs d'infrastructure (authentification, délai, limite de débit, erreur d'API, budget, flux absent, bras contaminé, skill requis absent) sont listées à part et exclues des dénominateurs. Si l'authentification échoue, tout s'arrête : lance `claude` puis `/login` dans un terminal.

## Environnement

- Les sessions de test héritent de `~/.claude` : skills, plugins activés, hooks et règles de permission. Le lanceur n'y écrit rien, mais signale tout dossier apparu dans `~/.claude/skills` pendant les tests. Le lanceur arrête les bras sans plugin si `skill-orchestrator` y est déjà installé, et signale un `defaultMode` ou des règles `allow` larges qui empêcheraient les refus de permission attendus (`--setting-sources project,local` les ignore, au risque de masquer aussi les skills de l'utilisateur).
- Les variables d'une session Claude Code hôte qui changent le comportement (effort, identité de session, outils de l'application) sont retirées ; `--keep-env` les garde.
