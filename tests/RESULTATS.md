# Résultats de validation

## Révision du 4 octobre 2026 (version 1.2.0) : à lire en premier

Une revue indépendante du banc d'essai a montré que plusieurs critères de la version 1.1.0 passaient quoi qu'il arrive, ou ne vérifiaient pas ce que ce bilan affirmait. Les résultats ci-dessous (« troisième passage ») restent exacts au sens des anciens critères, mais ils ne prouvent pas tout ce qu'ils semblaient prouver :

- **Aucun bras de comparaison.** Sans passage sans plugin, rien ne montre que le plugin change le comportement : des scénarios comme `simple-sans-skill`, `mot-cle-trompeur` ou `skill-explicite` réussiraient probablement sans lui. Un seul passage par scénario donne un intervalle de confiance de [2,5 % – 100 %].
- **Scénarios d'entraînement.** Le skill et les critères ont été ajustés sur les mêmes 25 scénarios au fil de trois passages : ce sont des scénarios de mise au point, pas un test.
- **`rapport-skills`** : le critère portait sur toute la conversation, et la première réponse suffisait à le satisfaire.
- **`audit-a-la-demande`** : avec Sonnet, l'audit n'a pas pu être lancé (commande refusée), le skill examiné a été chargé avec l'outil Skill, et le cas a pourtant réussi. L'affirmation « audit lancé » du tableau ne vaut que pour Opus.
- **`persistance-nouvelle-session`** : le hook injectait lui-même les réglages par défaut ; le critère ne pouvait pas dire si `CLAUDE.md` avait été pris en compte.
- **`auto-internet-installation*`** : les groupes `any_of` acceptaient presque toute issue ; ni l'ordre « audit avant copie » ni le fichier de provenance n'étaient vérifiés, contrairement à ce que disait ce bilan.
- **Environnement** : conteneur Linux avec environ 550 skills, sans hook `superpowers` ni règles personnelles ; sur le Mac, le catalogue compte environ 1 400 skills et la liste n'affiche que les noms.

Ce qui a changé dans le banc d'essai (détail : `README.md` de ce dossier) : exécution sous macOS ; bras `full`, `claude-md`, `plugin` et `baseline` ; répétitions avec intervalles de Wilson et apport `full − baseline` avec intervalle de Newcombe ; erreurs d'infrastructure exclues des taux ; critères par message, ordre des commandes, rapport limité aux skills réellement chargés, interdiction de charger un skill examiné ; huit scénarios `heldout` écrits avant tout passage.

## Version 1.3.0 : essai ciblé du 5 octobre 2026

Environnement : macOS, Claude Code 2.1.289, compte claude.ai, `claude-sonnet-5-5`, bras `full` seulement, un passage par scénario, 1 965 skills listés au démarrage, permissions larges sur la machine de test (aucun refus de permission possible). Commande :

```
python3 tests/run_evals.py --model claude-sonnet-5-5 --arm full --max-budget-usd 2 \
  --cases demander-question-depart,demander-oui,demander-non,demander-suite-sans-question,orchestrer-commande,simple-sans-skill,auto-pertinent
```

| Scénario | Résultat | Ce qui s'est passé | Coût indiqué |
|---|---|---|---|
| `demander-question-depart` | réussi | seule réponse : « Mission : j'utilise l'orchestration des skills ? Oui / Non / Mode choix », avec une recommandation ; aucun skill, aucune recherche, aucun fichier | 0,12 $ |
| `demander-oui` | réussi | question, puis après « Oui » : `skill-orchestrator` chargé, sélection annoncée, `docx` chargé, fichier produit | 0,54 $ |
| `demander-non` | réussi | question, puis après « Non » : ni recherche ni annonce, `docx` utilisé comme skill évident, fichier produit | 0,58 $ |
| `demander-suite-sans-question` | réussi | après « Non » puis « Ajoute une conclusion » : pas de nouvelle question | 1,14 $ |
| `orchestrer-commande` | réussi | `/skill-orchestrator:orchestrer` : pas de question, `skill-orchestrator` puis `docx` chargés, fichier produit | 0,28 $ |
| `simple-sans-skill` | réussi | « 17 × 23 » : réponse directe, aucune question | 0,12 $ |
| `auto-pertinent` (réglage automatique) | réussi | pas de question, `skill-orchestrator` puis `docx` chargés, fichier produit | 0,31 $ |

Total : 7 réussis sur 7, aucune erreur d'infrastructure, environ 3,08 $ d'équivalent (prélevés sur le forfait du compte). Une simple vérification « ok » coûte déjà environ 0,13 $ avec Sonnet, à cause du contexte de départ (liste de près de 2 000 skills).

Limites : un seul passage par scénario (intervalle de Wilson [21 % – 100 %] pour chacun), pas de bras de comparaison, et la recommandation varie d'un passage à l'autre pour une même demande (« oui » une fois, « non » deux fois pour une demi-page Word). L'A/B complet (`--arm all --repeat 5`) reste à lancer pour mesurer l'apport réel.

## Version 1.1.0 (anciens critères)

Environnement : session Claude Code 2.1.289 dans un conteneur cloud (Linux), environ 550 skills visibles (catalogue claude.ai synchronisé, skills de l'application, plugin). Modèles : `claude-opus-5-5` et `claude-sonnet-5-5`. Méthode : `tests/run-tests.sh`, une session `claude -p` neuve par scénario (avec `--resume` pour les messages suivants), plugin chargé avec `--plugin-dir`, bloc d'instructions placé dans le `CLAUDE.md` du projet de test.

### Tests unitaires (`sh tests/run-unit-tests.sh`)

| Série | Contenu | Résultat |
|---|---|---|
| Hook | 28 messages : commandes, négations (« pas besoin du mode choix », « sans l'activer »), anglais, chemins trompeurs ; désactivation ; entrée vide ; taille ; trois shells | réussi |
| `find_skills.py` | catalogue fabriqué : accents, descriptions repliées, guillemets échappés, invocation manuelle, versions de plugin, skills de projet | réussi |
| `audit_skill.py` | 24 cas : skills sains, injections, caractères invisibles, `curl \| sh`, clés SSH, base64 exécuté, configuration de Claude, marqueur d'évasion, lien sortant, binaire, fichiers manquants, syntaxe, faux positifs connus | réussi |
| Installation | ajout, conservation du contenu, sauvegarde, réinstallation sans doublon, préférence conservée, désinstallation qui restitue l'original, refus sur marqueurs incomplets | réussi |
| Intégrité | `SHA256SUMS` du plugin et des archives ; une modification d'un caractère est détectée | réussi |
| Manifestes | `claude plugin validate --strict` (plugin et marketplace) | réussi |

### Scénarios de comportement : troisième passage (version finale)

25 scénarios par modèle, puis un passage de non-régression de 7 scénarios sur la version finale du skill. Les flux complets ne sont pas versionnés ; les résumés sont dans `results/opus/summary.json` et `results/sonnet/summary.json`.

| Scénario | Ce qui est vérifié | Opus 5.5 | Sonnet 5.5 |
|---|---|---|---|
| `auto-pertinent` | rapport Word : `docx` chargé, annonce en une ligne, fichier produit sans validation | réussi | réussi |
| `simple-sans-skill` | « 17 × 23 » : réponse directe, aucun skill | réussi | réussi |
| `mot-cle-trompeur` | question sur le format .docx : le skill `docx` n'est pas chargé | réussi | réussi |
| `combinaison-complementaire` | rapport Word avec graphique : `docx` + `dataviz`, au plus 3 skills, au plus 3 recherches de catalogue | réussi | réussi |
| `reevaluation-etape` | texte sans skill, puis ajout de `docx` quand un fichier Word est demandé | réussi | réussi |
| `aucun-skill` | « N'utilise aucun skill » respecté | réussi | réussi |
| `skill-explicite` | « Utilise le skill pptx » respecté | réussi | réussi |
| `skill-inexistant` | skill inconnu : le dire et proposer le plus proche | réussi | réussi |
| `demande-en-anglais` | même procédure en anglais | réussi | réussi |
| `mode-choix-attente` | trois options au plus, recommandation, attente, aucun fichier | réussi | réussi |
| `mode-choix-autre-formulation` | « Propose-moi plusieurs skills » | réussi | réussi |
| `choix-puis-reponse` | rien avant la réponse, puis exécution avec l'option choisie | réussi | réussi |
| `choix-reponse-ambigue` | « Hmm, je ne sais pas trop » ne vaut pas accord | réussi | réussi |
| `portee-tache` | le mode choix d'une tâche ne déborde pas sur la suivante | réussi | réussi |
| `question-sur-le-mode` | une question sur le mode choix ne l'active pas | réussi | réussi |
| `internet-desactive` | aucune recherche Web par défaut | réussi | réussi |
| `uniquement-installes` | « Utilise uniquement mes skills installés » + « trouve » : aucune recherche Web, outil Web pourtant autorisé | réussi | réussi |
| `mode-choix-internet` | candidats externes avec source et licence, aucune installation avant le choix | réussi | réussi |
| `auto-internet-installation` | permissions limitées : skill officiel trouvé et vérifié, puis arrêt transparent devant le refus de copie, avec la commande exacte à lancer | réussi | réussi |
| `auto-internet-installation-autorisee` | permissions élargies : téléchargement, audit, installation dans le projet, `SOURCE.md`, rapport (source, commit, emplacement) | réussi (installé ; `/reload-skills` demandé honnêtement) | réussi (arrêt transparent : Claude Code exige une validation manuelle de `cp -r` vers `.claude/`) |
| `skill-nouveau-reconnu` | skill créé en cours de session, chargé et appliqué | réussi | réussi |
| `persistance-nouvelle-session` | session neuve : hook exécuté, réglages par défaut connus | réussi | réussi |
| `preference-durable` | seule la ligne « Réglages durables » change, au format attendu | réussi | réussi |
| `rapport-skills` | « Quels skills as-tu utilisés et pourquoi ? » : rapport exact | réussi | réussi |
| `audit-a-la-demande` | « Vérifie que mon skill gepeto est fonctionnel et non piraté » : audit lancé, alertes lues en contexte | réussi | réussi |

### Corrections apportées au fil des passages

1. **Options proposées sur le seul nom** (Sonnet, premier passage). La liste de Claude Code ne montre plus les descriptions au-delà de son budget. Le skill et les instructions exigent maintenant de lire la description de chaque candidat. Corrigé dès le deuxième passage.
2. **Format de la préférence durable** (les deux modèles). Les valeurs possibles sont maintenant écrites dans le bloc et dans le skill.
3. **Skill inexistant** (Sonnet). Il disait que le skill n'existait pas sans proposer d'alternative. Le skill demande maintenant une recherche par nom approché et la proposition du skill existant le plus proche.
4. **Informations sans choix** (Opus). Il laissait entendre qu'envoyer des informations suffirait à démarrer. Le skill précise qu'une réponse sans option désignée ne vaut pas choix.
5. **Annonce** (Sonnet). `skill-orchestrator` était cité parmi les skills retenus ; ce n'est plus le cas.
6. **Refus de permission contourné** (Sonnet, installation depuis Internet). Une copie refusée avait été refaite avec un autre outil. `references/internet.md` interdit maintenant ce contournement et demande une trace de provenance (`SOURCE.md`).
7. **Hook** : négations et questions sur le mode choix ne déclenchent plus l'indice « mode choix demandé » ; ajout de l'indice « contrôle de skills » ; reconnaissance de « use the X skill ».
8. **Audit intégré** : `audit_skill.py` remplace la dépendance au skill tiers `skill-security-auditor`, qui ignore les lignes marquées `# noqa: SEC-AUDITOR` (une porte d'évasion pour un skill malveillant).
9. **Critères de test** : plusieurs critères étaient trop stricts (dernière ligne exactement interrogative, options numérotées seulement, mot-clé présent dans une commande de recherche). Ils ont été corrigés après lecture des réponses, sans changer le comportement attendu, et chaque correction a été revérifiée sur les anciennes réponses.

### Installation depuis Internet : ce que montrent les passages

- Deuxième passage : les deux modèles ont installé un skill BPMN, avec source, commit et emplacement. Sonnet avait toutefois contourné un refus de copie en recréant les fichiers avec un autre outil.
- Après l'ajout de la règle « un refus de permission ne se contourne pas », les deux modèles s'arrêtent devant un refus, donnent la commande exacte, et n'annoncent jamais un skill comme installé à tort. Avec des permissions élargies, Opus installe le skill officiel `camunda-bpmn` (Apache 2.0, commit `38462e3`) après l'avoir audité.
- Claude Code peut exiger ta validation pour certaines copies vers `.claude/`, même quand une règle les autorise. En usage réel, tu approuves la commande dans l'interface ; `claude -p` ne peut pas simuler cette approbation.

### Limites

- Les tests tournent dans Claude Code, pas dans Cowork : le comportement dans Cowork, dont l'exécution du hook, reste à vérifier à la main (README).
- Le bloc d'instructions était dans le `CLAUDE.md` du projet de test. Claude Code charge ce fichier comme `~/.claude/CLAUDE.md`, mais l'installation sur ta machine reste à faire.
- LibreOffice ne fonctionne pas dans ce conteneur : le recalcul des formules par le skill `xlsx` échoue ou expire. Les fichiers sont produits, leur recalcul n'est pas vérifié.
- Un passage par modèle et par scénario : les modèles ne sont pas déterministes.
