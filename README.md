# skill-orchestrator

Capacité persistante d'orchestration des skills pour **Claude Code** et **Cowork** (application desktop Claude).

À chaque demande, Claude identifie les skills disponibles qui améliorent concrètement le travail, les lit, puis les applique selon le mode choisi :

- **question de départ** (par défaut) : au début de chaque mission (une demande qui produit un livrable ou compte plusieurs étapes), Claude demande d'abord « j'utilise l'orchestration des skills ? Oui / Non / Mode choix », avec sa recommandation ; ta réponse vaut pour toute la mission ;
- **mode automatique** (« oui », commande `/orchestrer`, ou réglage durable) : Claude lit la procédure, sélectionne le plus petit ensemble utile et l'annonce en une ligne ;
- **mode choix** (« mode choix », ou `/orchestrer choix`) : jusqu'à trois options, une recommandation, puis attente de ton choix ;
- **non** : travail normal, sans recherche ni annonce ; un skill évident pour le format demandé reste permis ;
- **option Internet** (désactivée par défaut, indépendante du mode) : recherche, vérification et installation d'un skill externe ;
- **contrôle des skills** (sur demande) : audit de fonctionnement et de sécurité d'un skill ou de tout le catalogue.

## Architecture

| Élément | Rôle | Claude Code | Cowork |
|---|---|---|---|
| Instructions persistantes | Imposent l'analyse des skills à chaque demande et fixent les réglages durables | Bloc dans `~/.claude/CLAUDE.md` | Texte dans les instructions globales |
| Skill `skill-orchestrator` | Procédure détaillée : question de départ, sélection, mode choix, option Internet, rapport | Via le plugin | Via le plugin |
| Skill `orchestrer` | Commande que toi seul peux lancer (`disable-model-invocation`) : active l'orchestration sur la mission en cours, sans question | `/skill-orchestrator:orchestrer` (tape `/orch`) | Via le plugin |
| Hook `UserPromptSubmit` | Ajoute un rappel court (environ 60 tokens) à chaque message et signale, sans rien décider, les formulations de pilotage repérées | Via le plugin | Via le plugin (exécution à confirmer, voir « État ») |
| `find_skills.py` | Recherche dans le catalogue local : BM25 sur le nom et la description, mots vides, dictionnaire français-anglais | Via le plugin | Via le plugin |
| `audit_skill.py` | Audit statique d'un skill : structure, fichiers cités, syntaxe des scripts, outils accordés, signaux de compromission | Via le plugin | Via le plugin |
| `compare_upstream.py` | Vérifie l'origine d'un skill en le comparant à son dépôt source et à tout son historique | Via le plugin | Via le plugin |
| `install_skill.py` | Installe un skill téléchargé à l'identique de ce qui a été audité et écrit sa provenance (`SOURCE.json`) | Via le plugin | Préparation de l'archive |

Le skill et le hook forment un seul plugin (`plugins/skill-orchestrator`). Un plugin ajouté à ton compte dans l'application est synchronisé vers Claude Code. Une seule installation couvre donc les deux applications.

Aucun de ces éléments ne garantit à lui seul l'exécution à chaque message. Le hook garantit seulement que le rappel est injecté. Les instructions sont chargées à chaque session, mais c'est Claude qui applique la procédure.

Répartition du contexte : le bloc d'instructions (environ 1 000 tokens par session) porte les réglages durables et les définitions communes (« demande simple », « tâche », « changement d'étape ») ; le hook ajoute environ 80 tokens par message, et environ 70 de plus quand le message ressemble au début d'une mission ; `SKILL.md` (environ 2 500 tokens) est lu après un « oui », `/orchestrer` ou le mode choix, une fois par mission ; le mode choix, l'option Internet et le contrôle des skills sont dans des références lues seulement quand leur étape arrive.

## Installation

### 1. Plugin, une seule fois pour Cowork et Claude Code

1. Télécharge `dist/skill-orchestrator-plugin.zip`.
2. Dans l'application Claude : **Personnaliser > Plugins > Ajouter > Upload plugin**, puis choisis l'archive. Les libellés peuvent varier selon la version de l'application.
3. Vérifie que le plugin est activé.

Autre possibilité dans l'application, qui facilite les mises à jour : **Personnaliser > Plugins > Ajouter > Add marketplace**, avec `lucasschnegg-glitch/SkillSearch-Claude`. Le dépôt est public. L'application lit sa branche par défaut (voir « Branche » plus bas).

Variante pour Claude Code seul :

```
/plugin marketplace add lucasschnegg-glitch/SkillSearch-Claude
/plugin install skill-orchestrator@skillsearch
```

Depuis une copie locale, utilise `/plugin marketplace add ./SkillSearch-Claude`. Si le plugin vient aussi de ton compte, la version installée localement est prioritaire : il n'y a pas de doublon.

Ne téléverse pas en plus `dist/skill-orchestrator-skill.zip` ni `dist/orchestrer-skill.zip` : les skills apparaîtraient en double. Ces archives servent uniquement si ton organisation bloque l'ajout de plugins. Dans ce cas, utilise **Personnaliser > Skills > + > Create skill > Upload a skill**, sans hook. La description du skill compte 182 caractères, sous la plus stricte des deux limites citées par l'aide (200 et 1 024).

### 2. Instructions persistantes dans Cowork

**Paramètres > Cowork > Instructions globales > Modifier**. Avec la nouvelle interface qui fusionne Chat et Cowork, c'est **Paramètres > Général > Instructions pour Claude**.

Colle **à la suite de ton texte actuel** le contenu de `instructions/cowork-instructions-globales.md`, puis enregistre. Ne remplace pas tes préférences existantes.

### 3. Instructions persistantes dans Claude Code (terminal, onglet Code de l'application)

Depuis une copie du dépôt sur ta machine :

```sh
sh install/install-claude-code.sh                # ajoute ou met à jour le bloc dans ~/.claude/CLAUDE.md
sh install/install-claude-code.sh --with-plugin  # idem, puis installe le plugin depuis le dépôt local
```

Le script ne touche qu'au bloc compris entre les marqueurs `skill-orchestrator`, crée une sauvegarde horodatée et conserve ta ligne « Réglages durables » lors d'une mise à jour (de la v1 vers la v2 comprise). Tu peux aussi copier `instructions/claude-code-CLAUDE.md` à la main à la fin de `~/.claude/CLAUDE.md`.

### 4. Vérifier

- Intégrité des fichiers téléchargés : `python3 install/verify-integrity.py` (ou `sha256sum -c SHA256SUMS`). Le script compare chaque fichier du plugin et le contenu des archives aux empreintes de `SHA256SUMS`. Pour vérifier un plugin déjà installé : `python3 install/verify-integrity.py --installed <dossier du plugin>`. Ces empreintes sont dans le même dépôt : elles détectent une corruption ou une modification locale, pas une modification du dépôt lui-même. Compare aussi le commit (`git rev-parse HEAD`) à celui qui t'a été communiqué.
- Claude Code : `/plugin` (onglet Installed) liste `skill-orchestrator` ; `/hooks` montre le hook `UserPromptSubmit` ; `/memory` montre le bloc dans `~/.claude/CLAUDE.md`. Dans une session déjà ouverte, lance `/reload-plugins`.
- Cowork : ouvre une nouvelle tâche et envoie : « Combien font 17 × 23 ? » (réponse directe, sans skill), puis « Mode choix pour cette tâche : prépare une présentation de 5 diapositives sur un sujet de ton choix. » (options, puis attente). Pour savoir si le hook s'exécute dans Cowork, demande : « As-tu reçu un rappel "[Orchestration des skills]" avec mon message ? ».

## Utilisation

Rien à faire par défaut : le mode automatique s'applique. Pour piloter en langage naturel (ce ne sont pas des commandes natives ; Claude interprète l'intention, négations et questions comprises) :

| Tu dis | Effet | Portée |
|---|---|---|
| Réponse à la question de départ : « Oui », « Non », « Mode choix » | orchestration complète, travail normal ou options | mission |
| `/orchestrer` (Claude Code : `/skill-orchestrator:orchestrer`), « Orchestre cette mission. » | orchestration lancée sans question, mode automatique | mission |
| `/orchestrer choix`, `/orchestrer internet` | idem, en mode choix ou avec l'option Internet | mission |
| « Mode automatique. » | sélection automatique | mission |
| « Mode choix pour cette tâche. », « Propose-moi plusieurs skills. », « Je veux choisir les skills. » | options puis attente de ton choix | mission |
| « Active la recherche Internet pour cette tâche. », « Cherche un skill sur Internet si nécessaire. », « Trouve et installe un skill adapté. », « Mode automatique avec recherche Internet. » | option Internet activée | mission |
| « Désactive la recherche Internet. » | option Internet désactivée | mission |
| « Utilise uniquement mes skills installés. » | catalogue existant seulement | mission |
| « Utilise le skill [nom]. » | ce skill est utilisé | mission |
| « N'utilise aucun skill pour cette tâche. » | aucun skill | mission |
| « Quels skills as-tu utilisés et pourquoi ? » | rapport | immédiat |
| « Vérifie mes skills. », « Audite le skill [nom]. » | audit de fonctionnement et de sécurité, alertes lues en contexte | immédiat |
| « Enregistre [réglage] par défaut. » | préférence durable (Claude Code : modifie la ligne « Réglages durables » ; Cowork : te donne la ligne à coller) | durable |

Réglages initiaux : sélection = demander (question de départ), recherche Internet désactivée, explications courtes. Pour ne plus être interrogé : « Enregistre sélection = automatique par défaut. » ; pour choisir toujours toi-même : « Enregistre le mode choix par défaut. »

Exemples détaillés pour les deux modes, avec et sans Internet : `plugins/skill-orchestrator/skills/skill-orchestrator/references/exemples.md`.

## Désactivation

| Pour | Claude Code | Cowork |
|---|---|---|
| Une tâche | « N'utilise aucun skill pour cette tâche. » | idem |
| Le rappel à chaque message, en gardant les indices | `"env": {"SKILL_ORCHESTRATOR_HOOK": "hints"}` dans `~/.claude/settings.json` | désactiver le plugin |
| Le hook entier | `"env": {"SKILL_ORCHESTRATOR_HOOK": "off"}` dans `~/.claude/settings.json` | désactiver le plugin |
| Le plugin | `/plugin` > Installed > Disable (ou `claude plugin disable skill-orchestrator@skillsearch`) ; s'il vient du compte, le désactiver dans l'application | Personnaliser > Plugins > désactiver ou supprimer |
| Les instructions persistantes | `sh install/install-claude-code.sh --uninstall` | supprimer le bloc entre `[Orchestration des skills...]` et `[Fin orchestration des skills]` |

## État au 5 octobre 2026 (version 1.3.1)

| Élément | État |
|---|---|
| Plugin, skill, hook, instructions et scripts | **Créés** dans ce dépôt. Manifestes validés par `claude plugin validate --strict`. Empreintes dans `SHA256SUMS`. |
| Tests unitaires (sans modèle) : hook (43 messages, négations, échappements JSON, locale C, repli sans Python), recherche de skills, audit, vérification d'origine, installation vérifiée, banc d'essai, script d'installation, intégrité | **Réussis** sous Python 3.9 et 3.14 (`sh tests/run-unit-tests.sh`). |
| Hook v1.2.0 lancé par Claude Code 2.1.281 sous macOS | **Vérifié** : exécuté, sortie JSON acceptée (`hook_response` réussi). Sa prise en compte par le modèle sera confirmée au premier passage de comportement. |
| Recherche de skills sur ton catalogue (1 423 skills) | **Mesurée** sur 24 requêtes étiquetées avant réglage (voir « Évaluation »). |
| Comportements avec la version 1.3.0 | **Essai ciblé réussi** sur ton Mac (Sonnet 5.5, 7 scénarios sur 7 : question de départ, « oui », « non », suite de mission, `/orchestrer`, demande simple, mode automatique). L'A/B complet avec répétitions reste à lancer (`tests/RESULTATS.md`). |
| Installation sur ton compte (Cowork) et instructions globales | **À activer par toi** dans l'interface. |
| Bloc dans ton `~/.claude/CLAUDE.md` local | **À activer par toi** avec `sh install/install-claude-code.sh`. |
| Exécution du hook `UserPromptSubmit` dans Cowork | **À vérifier** : la documentation indique que les hooks des plugins se chargent dans Cowork, sans préciser les événements. Les instructions globales couvrent le cas où le hook ne s'exécute pas. |
| Synchronisation du plugin vers l'onglet Code de l'application | **À vérifier** avec `/plugin` après l'installation. |

## Évaluation

Trois niveaux, du moins cher au plus cher. Détail : `tests/README.md`.

1. **Tests unitaires**, sans modèle, en quelques secondes : `sh tests/run-unit-tests.sh`.
2. **Classement de la recherche de skills** sur ton propre catalogue : `python3 tests/eval_find_skills.py --split all`. Les étiquettes ont été écrites avant tout réglage ; la partie `test` n'a servi qu'à la mesure finale.

   | Partie (12 requêtes) | Classement | MRR@10 | P@5 | R@5 |
   |---|---|---|---|---|
   | dev | ancien (sous-chaînes) | 0,70 | 0,27 | 0,42 |
   | dev | nouveau (BM25 + dictionnaire) | 1,00 | 0,48 | 0,82 |
   | test | ancien | 0,54 | 0,15 | 0,32 |
   | test | nouveau | 0,77 | 0,45 | 0,59 |

   Les requêtes et le dictionnaire ont le même auteur : la partie `test` protège contre un réglage trop fin des poids, pas contre un biais de vocabulaire. Ajoute ton vocabulaire de cours dans `SYNONYMES_PERSONNELS` (`find_skills.py`).
3. **Scénarios de comportement** avec `claude -p`, par bras : `full` (bloc + plugin), `claude-md`, `plugin`, `baseline` (ni l'un ni l'autre). Le bras `baseline` mesure ce que Claude fait déjà sans le plugin : l'apport réel est l'écart `full − baseline`, avec son intervalle. Huit scénarios `heldout`, écrits avant tout passage, ne servent jamais à régler le skill. Chaque session de test est facturée : `--dry-run` affiche le nombre d'appels avant de dépenser quoi que ce soit, et `--max-budget-usd` plafonne chaque appel.

## Points d'attention

- **Catalogue très large.** Environ 1 400 skills sur ta machine. Claude Code réserve environ 1 % du contexte à la liste des skills : au-delà, il retire les descriptions, et seuls les noms restent visibles. La procédure s'appuie donc sur la recherche par mots-clés (`SearchSkills`, `ListSkills` ou `scripts/find_skills.py`). Tu peux augmenter ce budget avec `skillListingBudgetFraction`, ou masquer des skills inutiles avec `skillOverrides`, au prix de plus de contexte à chaque message.
- **Audit de ton catalogue (4 octobre 2026).** Aucun skill malveillant ou piraté n'a été trouvé, et 410 skills sur 527 ont une origine vérifiée. Après la correction de l'audit (une auto-déclaration « outil de sécurité » ne réduit plus aucune gravité), les 1 425 verdicts locaux sont inchangés : aucun échec, 129 alertes à lire. Le rapport détaillé t'a été remis à part ; il n'est pas versionné, car le dépôt est public.
- **Skill concurrent.** `using-superpowers` (plugin `superpowers`) impose d'invoquer des skills avant toute réponse, ce qui contredit la règle du plus petit ensemble suffisant. Le bloc v2 dit explicitement que, pour le choix des skills, cette procédure prévaut ; `using-superpowers` reconnaît lui-même la priorité des instructions de `CLAUDE.md`. Le désactiver reste la solution la plus nette ; je ne l'ai pas modifié.
- **Indices du hook.** Le hook ne décide rien : il signale les formulations de pilotage repérées (« mode choix », « recherche Internet »…) et marque « négation possible » quand une négation les précède. Claude interprète l'intention.
- **Limites de l'audit.** `audit_skill.py` est une analyse statique : une alerte est un point à lire, « OK » ne prouve pas l'absence de risque. Ce qu'un skill dit de lui-même ne réduit aucune gravité ; seul `--trust`, que tu donnes après relecture, le fait. La comparaison à la source (`compare_upstream.py`) est la vérification la plus forte quand la source publique est connue ; un champ ajouté au frontmatter y compte désormais comme un écart.
- **Installation depuis Internet.** `install_skill.py` installe exactement l'instantané audité et écrit lui-même `SOURCE.json` ; un fichier de provenance fourni par le dépôt est ignoré. Un skill en cours d'examen n'est jamais chargé avec l'outil Skill.
- **Réglages de permissions.** Avec `bypassPermissions` ou des règles `allow` très larges dans `~/.claude/settings.json`, les garde-fous fondés sur les refus de permission (ne pas contourner un refus) ne se déclenchent jamais. Le banc d'essai le signale.
- **Windows.** Le lanceur du hook est un script `sh` (Git Bash, qu'utilise normalement Claude Code sous Windows). Sans Python, il n'ajoute que le rappel, sans indices.

## Branche

Le travail initial est sur la branche `claude/wizardly-fermi-zudpk1`, devenue branche par défaut parce que le dépôt était vide. Pour un nom stable, crée `main` à partir d'elle et choisis-la comme branche par défaut dans les réglages GitHub ; l'ajout de marketplace (`lucasschnegg-glitch/SkillSearch-Claude`) suivra la nouvelle branche par défaut. Le téléversement de l'archive .zip ne dépend pas de la branche.

## Contenu du dépôt

```
.claude-plugin/marketplace.json         marketplace « skillsearch »
plugins/skill-orchestrator/             le plugin (skill + hook)
  .claude-plugin/plugin.json
  hooks/hooks.json                      hook UserPromptSubmit
  scripts/skill-reminder.sh             lanceur du hook (repli sans Python)
  scripts/skill_reminder.py             rappel court et repérage neutre des formulations
  skills/orchestrer/SKILL.md            commande /orchestrer (lancée par toi seul)
  skills/skill-orchestrator/
    SKILL.md                            procédure (cœur, question de départ)
    references/mode-choix.md            mode choix
    references/internet.md              option Internet : sources, vérifications, installation
    references/controle.md              contrôle des skills : audit, origine, compte rendu
    references/exemples.md              exemples des deux modes, avec et sans Internet
    scripts/find_skills.py              recherche locale (BM25, dictionnaire français-anglais)
    scripts/audit_skill.py              audit statique (fonctionnement et sécurité)
    scripts/compare_upstream.py         vérification d'origine par comparaison aux dépôts sources
    scripts/install_skill.py            installation à l'identique de l'instantané audité
instructions/claude-code-CLAUDE.md      bloc pour ~/.claude/CLAUDE.md
instructions/cowork-instructions-globales.md   texte pour Cowork
install/install-claude-code.sh          installe, met à jour ou retire le bloc CLAUDE.md
install/build-dist.py                   reconstruit les archives de dist/ et SHA256SUMS
install/verify-integrity.py             vérifie les fichiers et les archives avec SHA256SUMS
SHA256SUMS                              empreintes du plugin et des archives
dist/                                   archives à téléverser dans l'application
tests/                                  tests unitaires, mesure de la recherche, banc d'essai de comportement, résultats
```

## Changements de la version 1.3.1

- **Instructions permanentes respectées** : pas de question de départ quand une autre instruction permanente désigne déjà un skill pour ce type de demande (par exemple un skill imposé pour les résumés de cours) ; Claude l'applique directement. Repéré lors d'un essai réel : la question passait avant une telle règle.

## Changements de la version 1.3.0

- **Question de départ** (nouveau réglage par défaut, sélection = demander) : au début de chaque mission, Claude demande « Oui / Non / Mode choix » avec sa recommandation, avant toute lecture de skill, recherche ou production. Après « oui », la lecture complète de la procédure est obligatoire, au lieu d'être laissée à l'appréciation de Claude.
- **Commande `/orchestrer`** (skill `orchestrer`, que seul l'utilisateur peut lancer) : orchestration immédiate, sans question ; arguments `choix` et `internet`.
- **Hook** : repère le début possible d'une mission (verbe de production et livrable) et le rappelle neutrement ; repère « orchestre » / « sans orchestration ».
- **Mise à jour depuis une version antérieure** : le script d'installation conserve ta ligne « Réglages durables ». Si elle dit encore « sélection = automatique », tu garderas l'ancien comportement : dis « Enregistre sélection = demander par défaut » pour passer au nouveau.
- **Banc d'essai** : réglages durables propres à chaque scénario (`reglages`) ; les scénarios écrits pour le mode automatique le gardent ; cinq scénarios couvrent la question de départ, « oui », « non », la suite de mission et `/orchestrer`.

## Changements de la version 1.2.0

- **Sécurité** : l'audit ne réduit plus aucune gravité sur la foi de ce qu'un skill dit de lui-même (option `--trust` à la place) ; la vérification d'origine voit les champs ajoutés au frontmatter et compare les deux copies dans le bon ordre ; contrôle des liens symboliques par composants de chemin ; signalement des `allowed-tools` qui donnent réseau ou shell sans confirmation ; installation vérifiée (`install_skill.py`) ; un skill examiné n'est jamais chargé.
- **Hook** : logique en Python (JSON, accents, casse, locale C), indices neutres avec repérage des négations au lieu de verdicts, rappel ramené de 161 à environ 60 tokens par message, sans réglages par défaut qui contrediraient une préférence enregistrée, sortie `additionalContext`, mode `hints`.
- **Consignes** : définitions communes de « demande simple », « tâche » et « changement d'étape » dans le bloc persistant ; `SKILL.md` réduit de moitié (environ 2 100 tokens), détails dans des références lues à la demande ; description de 182 caractères ; règle d'arrêt du mode choix sans contradiction ; priorité explicite sur les méta-skills qui imposent d'invoquer des skills.
- **Recherche** : BM25, mots vides, racines, dictionnaire français-anglais, bonus du nom, égalités départagées ; correction de la lecture des descriptions écrites à la ligne, des dossiers cachés et des copies rangées dans un autre skill.
- **Évaluation** : banc d'essai exécutable sous macOS, bras de comparaison, répétitions, intervalles de Wilson et de Newcombe, erreurs d'infrastructure séparées des échecs, critères qui passaient quoi qu'il arrive corrigés, huit scénarios réservés.

## Sources officielles consultées

- Skills dans Claude Code, budget de la liste, skills synchronisés : https://code.claude.com/docs/en/skills
- Hooks, `UserPromptSubmit`, sortie ajoutée au contexte : https://code.claude.com/docs/en/hooks
- Mémoire `CLAUDE.md` : https://code.claude.com/docs/en/memory
- Installation des plugins et synchronisation depuis claude.ai : https://code.claude.com/docs/en/discover-plugins
- Composants pris en charge par Chat, Cowork et Claude Code : https://claude.com/docs/plugins/platform-support
- Instructions globales de Cowork : https://support.claude.com/en/articles/13345190
- Skills dans l'application : https://support.claude.com/en/articles/12512180
