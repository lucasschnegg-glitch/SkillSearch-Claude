# skill-orchestrator

Capacité persistante d'orchestration des skills pour **Claude Code** et **Cowork** (application desktop Claude).

À chaque demande, Claude identifie les skills disponibles qui améliorent concrètement le travail, les lit, puis les applique selon le mode choisi :

- **mode automatique** (par défaut) : sélection du plus petit ensemble utile, annoncée en une ligne ;
- **mode choix** (sur demande) : jusqu'à trois options, une recommandation, puis attente de ton choix ;
- **option Internet** (désactivée par défaut, indépendante du mode) : recherche, vérification et installation d'un skill externe.

## Architecture

| Élément | Rôle | Claude Code | Cowork |
|---|---|---|---|
| Instructions persistantes | Imposent l'analyse des skills à chaque demande et fixent les réglages durables | Bloc dans `~/.claude/CLAUDE.md` | Texte dans les instructions globales |
| Skill `skill-orchestrator` | Procédure détaillée : sélection, mode choix, option Internet, rapport | Via le plugin | Via le plugin |
| Hook `UserPromptSubmit` | Ajoute un rappel court à chaque message et repère les commandes en langage naturel | Via le plugin | Via le plugin (exécution à confirmer, voir « État ») |

Le skill et le hook forment un seul plugin (`plugins/skill-orchestrator`). Un plugin ajouté à ton compte dans l'application est synchronisé vers Claude Code. Une seule installation couvre donc les deux applications.

Aucun de ces éléments ne garantit à lui seul l'exécution à chaque message. Le hook garantit seulement que le rappel est injecté. Les instructions sont chargées à chaque session, mais c'est Claude qui applique la procédure.

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

Ne téléverse pas en plus `dist/skill-orchestrator-skill.zip` : le skill apparaîtrait en double. Cette archive sert uniquement si ton organisation bloque l'ajout de plugins. Dans ce cas, utilise **Personnaliser > Skills > + > Create skill > Upload a skill**, sans hook. Une page d'aide mentionne une limite de 200 caractères pour la description d'un skill téléversé, une autre 1 024. La description actuelle en compte 576 : si l'import la refuse, raccourcis-la dans `SKILL.md` puis relance `python3 install/build-dist.py`.

### 2. Instructions persistantes dans Cowork

**Paramètres > Cowork > Instructions globales > Modifier**. Avec la nouvelle interface qui fusionne Chat et Cowork, c'est **Paramètres > Général > Instructions pour Claude**.

Colle **à la suite de ton texte actuel** le contenu de `instructions/cowork-instructions-globales.md`, puis enregistre. Ne remplace pas tes préférences existantes.

### 3. Instructions persistantes dans Claude Code (terminal, onglet Code de l'application)

Depuis une copie du dépôt sur ta machine :

```sh
sh install/install-claude-code.sh                # ajoute ou met à jour le bloc dans ~/.claude/CLAUDE.md
sh install/install-claude-code.sh --with-plugin  # idem, puis installe le plugin depuis le dépôt local
```

Le script ne touche qu'au bloc compris entre les marqueurs `skill-orchestrator`, crée une sauvegarde horodatée et conserve ta ligne « Réglages durables » lors d'une mise à jour. Tu peux aussi copier `instructions/claude-code-CLAUDE.md` à la main à la fin de `~/.claude/CLAUDE.md`.

### 4. Vérifier

- Claude Code : `/plugin` (onglet Installed) liste `skill-orchestrator` ; `/hooks` montre le hook `UserPromptSubmit` ; `/memory` montre le bloc dans `~/.claude/CLAUDE.md`. Dans une session déjà ouverte, lance `/reload-plugins`.
- Cowork : ouvre une nouvelle tâche et envoie : « Combien font 17 × 23 ? » (réponse directe, sans skill), puis « Mode choix pour cette tâche : prépare une présentation de 5 diapositives sur un sujet de ton choix. » (options, puis attente). Pour savoir si le hook s'exécute dans Cowork, demande : « As-tu reçu un rappel "[Orchestration des skills]" avec mon message ? ».

## Utilisation

Rien à faire par défaut : le mode automatique s'applique. Pour piloter en langage naturel (ce ne sont pas des commandes natives) :

| Tu dis | Effet | Portée |
|---|---|---|
| « Mode automatique. » | sélection automatique | tâche |
| « Mode choix pour cette tâche. », « Propose-moi plusieurs skills. », « Je veux choisir les skills. » | options puis attente de ton choix | tâche |
| « Active la recherche Internet pour cette tâche. », « Cherche un skill sur Internet si nécessaire. », « Trouve et installe un skill adapté. », « Mode automatique avec recherche Internet. » | option Internet activée | tâche |
| « Désactive la recherche Internet. » | option Internet désactivée | tâche |
| « Utilise uniquement mes skills installés. » | catalogue existant seulement | tâche |
| « Utilise le skill [nom]. » | ce skill est utilisé | tâche |
| « N'utilise aucun skill pour cette tâche. » | aucun skill | tâche |
| « Quels skills as-tu utilisés et pourquoi ? » | rapport | immédiat |
| « Enregistre [réglage] par défaut. » | préférence durable (Claude Code : modifie la ligne « Réglages durables » ; Cowork : te donne la ligne à coller) | durable |

Réglages initiaux : sélection automatique, recherche Internet désactivée, explications courtes.

Exemples détaillés pour les deux modes, avec et sans Internet : `plugins/skill-orchestrator/skills/skill-orchestrator/references/exemples.md`.

## Désactivation

| Pour | Claude Code | Cowork |
|---|---|---|
| Une tâche | « N'utilise aucun skill pour cette tâche. » | idem |
| Le rappel à chaque message seulement | `"env": {"SKILL_ORCHESTRATOR_HOOK": "off"}` dans `~/.claude/settings.json` | désactiver le plugin |
| Le plugin | `/plugin` > Installed > Disable (ou `claude plugin disable skill-orchestrator@skillsearch`) ; s'il vient du compte, le désactiver dans l'application | Personnaliser > Plugins > désactiver ou supprimer |
| Les instructions persistantes | `sh install/install-claude-code.sh --uninstall` | supprimer le bloc entre `[Orchestration des skills...]` et `[Fin orchestration des skills]` |

## État au 4 octobre 2026

| Élément | État |
|---|---|
| Fichiers du plugin, du skill, du hook, des instructions et des scripts | **Créés** dans ce dépôt. Manifeste du plugin et de la marketplace validés par `claude plugin validate --strict`. |
| Plugin chargé dans Claude Code (dossier, archive .zip et installation depuis GitHub), skill reconnu, hook exécuté | **Testé** dans une session Claude Code 2.1.289 (voir `tests/RESULTATS.md`). |
| Comportements (sélection pertinente, demande simple, mode choix, « aucun skill », Internet désactivé, mode choix avec Internet, nouveau skill reconnu, nouvelle session, préférence durable, rapport) | **Testés** avec `claude -p` sur Opus 5.5 et Sonnet 5.5 : 11 scénarios sur 11 réussis par modèle. Résultats et limites dans `tests/RESULTATS.md`. |
| Installation sur ton compte (Cowork) et instructions globales | **À activer par toi** : ces réglages se font dans l'interface, je n'y ai pas accès. |
| Bloc dans ton `~/.claude/CLAUDE.md` local | **À activer par toi** avec le script : cette session tourne dans un conteneur cloud, pas sur ta machine. |
| Exécution du hook `UserPromptSubmit` dans Cowork | **À vérifier** : la documentation indique que les hooks des plugins se chargent dans Cowork, sans préciser les événements. Les instructions globales couvrent le cas où le hook ne s'exécute pas. |
| Synchronisation du plugin vers l'onglet Code de l'application | **À vérifier** avec `/plugin` après l'installation. Elle est documentée pour Claude Code 2.1.273 et plus récent. |

## Points d'attention

- **Catalogue très large.** Ton compte synchronise environ 530 skills. Claude Code réserve environ 1 % du contexte à la liste des skills : au-delà, il raccourcit puis retire les descriptions. C'est pourquoi la procédure prévoit une recherche par mots-clés (`SearchSkills`, `ListSkills` ou `scripts/find_skills.py`). Tu peux augmenter ce budget avec le réglage `skillListingBudgetFraction`, ou masquer des skills inutiles avec `skillOverrides`, au prix de plus de contexte consommé à chaque message.
- **Skill concurrent.** Ton catalogue contient `using-superpowers`, qui impose d'invoquer des skills avant toute réponse. Il contredit la règle du plus petit ensemble suffisant. La procédure demande de ne pas l'empiler, mais le désactiver éviterait des signaux contradictoires. Je ne l'ai pas modifié.
- **Indices du hook.** Le hook repère les commandes par mots-clés. Ce ne sont que des indices : Claude vérifie l'intention dans ton message.
- **Windows.** Le hook est un script `sh`. Il nécessite Git Bash, qu'utilise normalement Claude Code sous Windows.

## Branche

Le travail est sur la branche `claude/wizardly-fermi-zudpk1`. Comme le dépôt était vide, GitHub en a fait la branche par défaut : l'ajout de marketplace fonctionne donc tel quel. Si tu choisis plus tard une autre branche par défaut (par exemple `main`), fusionnes-y d'abord ces fichiers, ou ajoute `#claude/wizardly-fermi-zudpk1` à la commande dans Claude Code. Le téléversement de l'archive .zip ne dépend pas de la branche.

## Contenu du dépôt

```
.claude-plugin/marketplace.json         marketplace « skillsearch »
plugins/skill-orchestrator/             le plugin (skill + hook)
  .claude-plugin/plugin.json
  hooks/hooks.json                      hook UserPromptSubmit
  scripts/skill-reminder.sh             rappel et détection des commandes
  skills/skill-orchestrator/
    SKILL.md                            procédure
    references/internet.md              option Internet : sources, vérifications, installation
    references/exemples.md              exemples des deux modes, avec et sans Internet
    scripts/find_skills.py              recherche locale dans le catalogue de skills
instructions/claude-code-CLAUDE.md      bloc pour ~/.claude/CLAUDE.md
instructions/cowork-instructions-globales.md   texte pour Cowork
install/install-claude-code.sh          installe, met à jour ou retire le bloc CLAUDE.md
install/build-dist.py                   reconstruit les archives de dist/
dist/                                   archives à téléverser dans l'application
tests/                                  scénarios, lanceur, vérificateur, résultats
```

## Sources officielles consultées

- Skills dans Claude Code, budget de la liste, skills synchronisés : https://code.claude.com/docs/en/skills
- Hooks, `UserPromptSubmit`, sortie ajoutée au contexte : https://code.claude.com/docs/en/hooks
- Mémoire `CLAUDE.md` : https://code.claude.com/docs/en/memory
- Installation des plugins et synchronisation depuis claude.ai : https://code.claude.com/docs/en/discover-plugins
- Composants pris en charge par Chat, Cowork et Claude Code : https://claude.com/docs/plugins/platform-support
- Instructions globales de Cowork : https://support.claude.com/en/articles/13345190
- Skills dans l'application : https://support.claude.com/en/articles/12512180
