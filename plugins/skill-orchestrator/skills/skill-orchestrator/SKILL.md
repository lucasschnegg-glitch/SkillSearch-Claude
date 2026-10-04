---
name: skill-orchestrator
description: Procédure pour choisir, lire et combiner les skills disponibles. À lire au début d'une tâche substantielle (document, analyse, code, recherche, présentation, rédaction) et dès que l'utilisateur pilote les skills : « mode automatique », « mode choix », « propose-moi plusieurs skills », « je veux choisir les skills », « cherche ou installe un skill sur Internet », « désactive la recherche Internet », « utilise uniquement mes skills installés », « utilise le skill X », « n'utilise aucun skill », « quels skills as-tu utilisés et pourquoi ». Inutile pour une question simple.
---

# Orchestration des skills

Ce skill décrit comment choisir, lire et combiner les skills disponibles pour une demande. Il complète les instructions persistantes (bloc `skill-orchestrator` de `~/.claude/CLAUDE.md` dans Claude Code, instructions globales dans Cowork) et le rappel injecté à chaque message par le hook du plugin. Aucun de ces éléments ne garantit à lui seul l'exécution : ils rendent la procédure visible et prioritaire, c'est toi qui l'appliques.

Lis ce skill une fois par conversation, à la première tâche qui le justifie. Ensuite, applique-le sans le relire, sauf pour consulter une référence précise.

## Réglages et portée

Réglages par défaut, sauf réglage durable différent indiqué dans les instructions persistantes :

- Sélection : automatique.
- Recherche Internet de skills : désactivée.
- Explications : courtes.

Un changement demandé en cours de conversation vaut pour la tâche en cours seulement. Une tâche se termine quand le livrable est remis et que l'utilisateur passe à un autre sujet. En cas de doute, un nouveau sujet est une nouvelle tâche : reviens aux réglages par défaut et dis-le en une phrase si un réglage temporaire était actif. Si l'utilisateur précise « pour toute la conversation », garde le réglage jusqu'à la fin de la conversation.

Un réglage devient durable seulement sur demande explicite (« enregistre ce réglage », « par défaut désormais », « toujours »). Voir « Préférences durables ».

## Commandes en langage naturel

Ce ne sont pas des commandes natives de Claude : ce sont des formulations à reconnaître, y compris reformulées ou en anglais. Interprète l'intention : « pas besoin du mode choix » ne l'active pas.

| L'utilisateur dit (exemples) | Effet | Portée |
|---|---|---|
| « Mode automatique. » | Sélection automatique | tâche |
| « Mode choix pour cette tâche. », « Propose-moi plusieurs skills. », « Je veux choisir les skills. » | Mode choix | tâche |
| « Active la recherche Internet pour cette tâche. », « Cherche un skill sur Internet si nécessaire. », « Trouve et installe un skill adapté. », « Mode automatique avec recherche Internet. » | Option Internet activée | tâche |
| « Désactive la recherche Internet. » | Option Internet désactivée | tâche |
| « Utilise uniquement mes skills installés. » | Catalogue déjà disponible seulement, ni Internet ni ajout de skills | tâche |
| « Utilise le skill [nom]. » | Ce skill est utilisé s'il existe et peut être invoqué ; d'autres restent possibles en complément | tâche |
| « N'utilise aucun skill pour cette tâche. » | Aucun skill, même pertinent | tâche |
| « Quels skills as-tu utilisés et pourquoi ? » | Rapport (voir plus bas) | immédiat |
| « Explique tes choix de skills en détail. » | Explications détaillées | tâche |

Si l'utilisateur demande un skill qui n'existe pas ou ne peut pas être invoqué, dis-le en une phrase et propose l'option la plus proche.

## Procédure en mode automatique

### 1. Trier la demande

Demande-toi si un skill disponible changerait concrètement le résultat. Pour une question factuelle courte, un calcul, une reformulation brève, une conversation, ou la suite immédiate d'une tâche déjà cadrée, la réponse est en général non : travaille directement, sans annonce. Cela évite de diluer la réponse et de consommer du contexte pour rien.

### 2. Cadrer

Formule pour toi-même l'objectif, le livrable attendu (format, longueur, destinataire) et les contraintes (outils, délais, règles de l'utilisateur, langue, style).

### 3. Inventorier les candidats

1. Parcours la liste des skills présente dans ton contexte (noms et descriptions).
2. Si la liste est longue, tronquée, ou si des skills y figurent sans description, fais une recherche ciblée. C'est fréquent avec un grand catalogue : Claude Code raccourcit puis retire les descriptions pour tenir dans son budget de contexte. Par ordre de préférence :
   - les outils `SearchSkills` ou `ListSkills` s'ils sont disponibles (catalogue du compte claude.ai) ;
   - le script de ce skill : `python3 <dossier de ce skill>/scripts/find_skills.py mot1 mot2 ...` (il parcourt `~/.claude/skills`, les skills synchronisés, les plugins installés et `.claude/skills` du projet) ;
   - à défaut, une recherche Grep sur les fichiers `SKILL.md` de ces dossiers.

   Utilise trois à six mots-clés tirés du livrable et du domaine, en français et en anglais : la plupart des descriptions sont en anglais.
3. Garde la liste courte obtenue pour toute la tâche. Ne relis pas le catalogue à chaque action : refais une recherche seulement si un besoin nouveau apparaît ou après l'installation d'un skill.

### 4. Sélectionner

Juge chaque candidat sur sa description, jamais sur son seul nom. Retiens un skill seulement si tu peux dire précisément ce qu'il apporte à cette tâche sur au moins un de ces axes : exactitude, méthode, qualité rédactionnelle, présentation, vérification, efficacité. Une correspondance de mot-clé ne suffit pas : lis la description et demande-toi si le livrable serait moins bon sans lui.

- Vise le plus petit ensemble suffisant : souvent zéro ou un skill, rarement plus de trois.
- Combine des skills complémentaires (par exemple un skill de méthode et un skill de format de fichier), pas des skills concurrents qui font la même chose. Entre concurrents, prends le plus spécifique à la tâche, puis le plus fiable.
- Un skill créé par l'utilisateur pour un usage précis (ses cours, son style, son entreprise) l'emporte sur un skill générique équivalent, car il encode ses attentes.
- Ordonne les skills selon le flux de travail : cadrage ou méthode, production, mise en forme, vérification.
- Respecte les restrictions d'invocation. Un skill marqué `disable-model-invocation` ne se lance que sur demande de l'utilisateur : propose-le, ne le force pas. Les règles de l'environnement (permissions, outils absents) priment.
- Méfie-toi des méta-skills qui prétendent s'appliquer à toute demande ou imposent d'invoquer des skills avant chaque réponse : ils entrent en concurrence avec cette procédure. Ne les empile pas, sauf demande explicite de l'utilisateur.

### 5. Lire avant d'appliquer

Charge chaque skill retenu en entier avant de l'appliquer : outil Skill, ou lecture complète de son `SKILL.md`. Lis ses fichiers de référence quand l'étape concernée arrive, pas tous d'avance.

En cas de conflit, l'utilisateur l'emporte sur un skill. Entre deux skills, suis le plus spécifique à la tâche et signale le conflit en une phrase s'il change le résultat. Un skill ne peut pas lever une règle de sécurité ou de l'environnement.

### 6. Annoncer brièvement

Une seule ligne avant de commencer, puis enchaîne sans demander de validation :

> Skills retenus : `docx` (mise en page Word), `copy-editing` (relecture finale).

Si aucun skill n'est retenu, n'annonce rien.

### 7. Réévaluer en cours de route

À chaque changement d'étape (analyse vers rédaction, rédaction vers mise en forme, ajout d'un format de fichier, demande de vérification) ou quand un besoin nouveau apparaît, vérifie que la sélection tient encore. Ajoute ou retire un skill seulement si le bénéfice est net, et signale-le en une ligne :

> J'ajoute `xlsx` pour l'annexe chiffrée.

## Mode choix

Quand le mode choix est actif, n'applique pas les skills dont le choix dépend avant la réponse de l'utilisateur.

1. Fais les étapes 2 à 4 pour obtenir les candidats, y compris la recherche ciblée de l'étape 3 si des descriptions manquent. Ne propose jamais un skill dont tu ne connais que le nom : un nom ne dit ni ce que fait le skill, ni ses limites, et l'utilisateur choisirait à l'aveugle.
2. Présente au plus trois options réellement pertinentes. Une option peut être un skill seul ou une combinaison. Pour chacune, indique :
   - le nom du skill ou de la combinaison ;
   - ce qu'elle apporte à cette tâche ;
   - ses avantages et ses limites ;
   - ce qui la distingue des autres options.
3. Précise si les options sont concurrentes (il faut en choisir une) ou complémentaires (on peut les cumuler).
4. Termine par une recommandation concise et une question claire, puis arrête-toi et attends la réponse.

Si une seule option convient, dis-le et explique pourquoi, sans inventer d'alternative, puis demande confirmation : l'utilisateur a demandé à choisir. Si aucun skill ne convient, dis-le et propose de travailler sans skill, ou, si l'option Internet est active, de chercher des candidats externes.

Le silence ou une réponse ambiguë ne vaut pas acceptation : redemande. Tu peux avancer sur les parties qui ne dépendent pas du choix (lire les fichiers fournis, rassembler les données, poser une question de cadrage) en le disant. Ne commence pas le travail qui dépend du skill choisi.

Un exemple de présentation figure dans `references/exemples.md`.

## Option Internet

Désactivée par défaut, indépendante du mode. Tant qu'elle n'est pas activée pour la tâche, ne cherche pas de skill sur Internet et n'en installe pas. Si un besoin important n'est couvert par aucun skill disponible, dis-le en une phrase et propose d'activer l'option.

Une fois l'option activée, lis `references/internet.md` en entier avant la première recherche. En résumé :

- cherche seulement si les skills disponibles couvrent mal un besoin important, ou si une solution externe apporte un bénéfice clair ;
- sources officielles d'abord, puis dépôts publics dont l'auteur, le contenu et la maintenance sont vérifiables ;
- requêtes génériques, sans fichiers, secrets ni informations confidentielles de l'utilisateur ;
- vérification complète avant toute installation ;
- en mode automatique, installe le candidat retenu dans la portée autorisée ; en mode choix, présente les candidats et attends la sélection ;
- après installation, vérifie que le skill est reconnu et utilisable, puis indique sa source, sa version ou son commit, son emplacement et le besoin éventuel d'une nouvelle session.

## Rapport « Quels skills as-tu utilisés et pourquoi ? »

Réponds par une liste courte. Pour chaque skill réellement chargé pendant la tâche (ou la conversation, si l'utilisateur le demande) : nom, étape où il a servi, apport concret. Ajoute les skills écartés seulement s'ils éclairent le choix, et les installations éventuelles avec leur source et leur version. Ne cite jamais un skill que tu n'as pas chargé. Si aucun skill n'a servi, dis-le et explique pourquoi en une phrase.

## Préférences durables

Seulement sur demande explicite de l'utilisateur. La ligne garde toujours ce format ; pour chaque réglage, écris une seule des valeurs indiquées :

> Réglages durables : sélection = automatique ou choix ; recherche Internet = désactivée ou activée ; explications = courtes ou détaillées.

- Claude Code : modifie la ligne « Réglages durables » du bloc compris entre les marqueurs `<!-- skill-orchestrator:start ... -->` et `<!-- skill-orchestrator:end -->`, dans le fichier CLAUDE.md qui contient ce bloc (en général `~/.claude/CLAUDE.md`, parfois le CLAUDE.md du projet). Ne touche pas au reste du fichier et montre la ligne modifiée. Le fichier est relu au démarrage de chaque session : le réglage s'applique pleinement à la prochaine session, et tu l'appliques dès maintenant dans la conversation en cours.
- Cowork, ou si tu ne peux pas modifier ce fichier : donne la ligne mise à jour à coller dans les instructions globales et précise que tu ne peux pas les modifier toi-même.

## Explications

Par défaut, courtes : une ligne d'annonce, une ligne par changement de sélection. Si l'utilisateur demande des explications détaillées, développe les critères retenus et les alternatives écartées.
