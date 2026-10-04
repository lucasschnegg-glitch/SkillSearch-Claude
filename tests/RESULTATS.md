# Résultats de validation (4 octobre 2026)

Environnement : session Claude Code 2.1.289 dans un conteneur cloud (Linux), avec environ 550 skills visibles (catalogue claude.ai synchronisé, skills de l'application et plugin). Modèles : `claude-opus-5-5` et `claude-sonnet-5-5`. Méthode : `tests/run-tests.sh`, une session `claude -p` neuve par cas, plugin chargé avec `--plugin-dir`, bloc d'instructions placé dans le `CLAUDE.md` du projet de test.

## Vérifications techniques

| Vérification | Résultat |
|---|---|
| Manifeste du plugin et de la marketplace (`claude plugin validate --strict`) | réussi |
| Plugin chargé depuis le dossier et depuis l'archive `dist/skill-orchestrator-plugin.zip` | réussi : skill `skill-orchestrator:skill-orchestrator` listé, hook exécuté |
| Hook : 13 messages simulés (commandes en langage naturel, demande neutre, chemins contenant « mode choix ») | réussi : indices corrects, aucun faux positif sur les chemins |
| Hook sous `dash`, `bash --posix` et `bash` | réussi |
| Désactivation du rappel par `SKILL_ORCHESTRATOR_HOOK=off` dans les réglages | réussi : sortie vide |
| Script d'installation : contenu existant préservé, réinstallation sans doublon, réglage durable conservé, désinstallation qui restitue le fichier d'origine, refus si marqueurs incomplets | réussi |
| `find_skills.py` sur le catalogue réel (570 fichiers SKILL.md) | réussi |

## Scénarios de comportement

Deuxième passage, après corrections (voir plus bas). Les flux complets ne sont pas versionnés ; les résumés sont dans `results/opus/summary.json` et `results/sonnet/summary.json`.

| Scénario | Opus 5.5 | Sonnet 5.5 | Observé |
|---|---|---|---|
| `auto-pertinent` : rapport Word | réussi | réussi | `docx` chargé, annonce « Skills retenus : `docx` (...) », fichier créé sans demande de validation |
| `simple-sans-skill` : « Combien font 17 × 23 ? » | réussi | réussi | réponse directe, aucun skill, aucune annonce |
| `mode-choix-attente` : présentation PowerPoint | réussi | réussi | trois options concurrentes, recommandation, question, aucun fichier produit |
| `mode-choix-autre-formulation` : « Propose-moi plusieurs skills... » | réussi | réussi | idem, avec distinction concurrentes et complémentaires |
| `aucun-skill` : « N'utilise aucun skill » | réussi | réussi | aucun skill chargé |
| `internet-desactive` : besoin BPMN non couvert | réussi | réussi | aucune recherche Web, limite signalée, activation proposée |
| `skill-nouveau-reconnu` : skill créé en cours de session | réussi | réussi | skill chargé et appliqué dans la même session ; le premier appel peut répondre « Unknown skill » pendant quelques secondes, le second réussit |
| `persistance-nouvelle-session` | réussi | réussi | hook exécuté, réglages par défaut énoncés correctement, skill listé au démarrage |
| `mode-choix-internet` : BPMN avec Internet | réussi | réussi | catalogue du compte puis Web, candidats avec source et licence, aucune installation avant le choix |

## Corrections apportées pendant les tests

1. **Options proposées sur le seul nom (défaut réel, Sonnet, premier passage).** Dans deux cas, Sonnet a présenté des skills dont il n'avait lu que le nom (« Je n'ai que les noms de ces skills »), parce que la liste de Claude Code ne montre plus les descriptions au-delà de son budget. Correction : le skill et les instructions exigent désormais de lire la description de chaque candidat avant de le proposer, et un critère de test le contrôle. Au deuxième passage, Sonnet a utilisé `SearchSkills` et a lu les descriptions.
2. **Agrégateurs de skills.** Un passage avec Internet a cité des annuaires plutôt que les dépôts sources. `references/internet.md` demande maintenant de remonter au dépôt source.
3. **Critères de test trop stricts.** Les premiers critères exigeaient que la dernière ligne soit une question et que les options soient numérotées. Les réponses correctes en tableau, avec des lettres ou suivies d'une liste de sources, échouaient à tort. Les critères ont été assouplis sans changer le comportement attendu.

## Limites des tests

- Les tests tournent dans Claude Code, pas dans Cowork : le comportement dans Cowork, et en particulier l'exécution du hook `UserPromptSubmit`, reste à vérifier à la main (voir le README).
- Le bloc d'instructions était dans le `CLAUDE.md` du projet de test, pas dans `~/.claude/CLAUDE.md`. Les deux sont chargés de la même façon, mais l'installation sur ta machine reste à faire.
- Dans le scénario Internet, `git clone` et `gh` étaient refusés par la configuration du test, et GitHub a renvoyé une erreur 403 à la lecture directe des pages. L'examen complet d'un candidat avant installation n'a donc pas pu aller jusqu'au bout. Aucune installation depuis Internet n'a été testée : le scénario de reconnaissance porte sur un skill créé localement.
- Un passage par modèle et par scénario : les modèles ne sont pas déterministes, d'autres formulations peuvent donner d'autres résultats.
