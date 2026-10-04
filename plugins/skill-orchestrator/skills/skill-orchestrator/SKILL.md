---
name: skill-orchestrator
description: Skill-selection procedure. Not for simple questions. Read once orchestration is accepted (oui, mode choix, /orchestrer) or when the user steers skills (« aucun skill », « vérifie mes skills »).
---

# Orchestration des skills

Procédure pour choisir, lire et combiner les skills disponibles. Elle complète le bloc `skill-orchestrator` des instructions persistantes (`~/.claude/CLAUDE.md` dans Claude Code, instructions globales dans Cowork), qui contient les réglages durables, la question de départ et les définitions de « demande simple », « mission » et « changement d'étape ». Lis ce skill en entier dès que l'orchestration est retenue pour une mission ; ensuite, applique-le sans le relire et ouvre une référence seulement quand son étape arrive.

## Réglages

Par défaut : sélection = demander (question de départ à chaque mission), recherche Internet de skills désactivée, explications courtes. Les réglages durables des instructions persistantes priment sur ces valeurs. Un réglage demandé en cours de conversation vaut pour la mission en cours ; « pour toute la conversation » le prolonge jusqu'à la fin de la conversation. Quand un nouveau sujet met fin à un réglage temporaire, dis-le en une phrase.

## Question de départ

Avec sélection = demander, ta première réponse à une nouvelle mission est seulement cette question, avant toute lecture de skill, recherche ou production :

> Mission : j'utilise l'orchestration des skills ? **Oui** / **Non** / **Mode choix**. Je recommande « oui » : le livrable est un document Word, `docx` et une relecture l'amélioreraient.

- **Oui** : procédure en mode automatique (plus bas).
- **Mode choix** : lis `references/mode-choix.md` et présente les options.
- **Non** : travail normal, sans recherche de catalogue ni annonce ; un skill évident pour le format demandé (par exemple `docx` pour un fichier .docx) reste permis.
- Réponse ambiguë ou absente : redemande, sans commencer.

La réponse vaut pour toute la mission : ne repose pas la question pour ses suites. Ne la pose pas non plus pour une demande simple, quand le message règle déjà la question (« mode choix », « n'utilise aucun skill », « utilise le skill X », « orchestre cette mission », commande `/orchestrer`), ni quand une autre instruction permanente de l'utilisateur désigne déjà un skill pour ce type de demande : applique-la directement. Avec sélection = automatique, passe directement à la procédure ; avec sélection = choix, directement au mode choix.

## Commandes en langage naturel

Ce sont des formulations à reconnaître, reformulées ou en anglais, pas des commandes natives. Interprète l'intention : une négation (« pas besoin du mode choix »), une question (« comment marche le mode choix ? ») ou un autre sens du mot (« soft skills ») n'active rien. Les indices du hook ne sont que des repères.

| L'utilisateur dit (exemples) | Effet | Portée |
|---|---|---|
| `/orchestrer` (commande), « Orchestre cette mission. » | orchestration activée sans question, mode automatique | mission |
| `/orchestrer choix`, `/orchestrer internet` | idem, en mode choix ou avec l'option Internet | mission |
| « Mode automatique. » | sélection automatique | mission |
| « Mode choix pour cette mission. », « Propose-moi plusieurs skills. » | mode choix : lis `references/mode-choix.md` | mission |
| « Cherche un skill sur Internet si nécessaire. », « Trouve et installe un skill adapté. » | option Internet activée : lis `references/internet.md` | mission |
| « Désactive la recherche Internet. », « Utilise uniquement mes skills installés. » | catalogue installé seulement | mission |
| « Utilise le skill [nom]. » | ce skill est utilisé s'il existe et peut être invoqué, d'autres restent possibles | mission |
| « N'utilise aucun skill pour cette mission. » | aucun skill, même pertinent | mission |
| « Quels skills as-tu utilisés et pourquoi ? » | rapport (plus bas) | immédiat |
| « Explique tes choix de skills en détail. » | explications détaillées | mission |
| « Vérifie mes skills. », « Ce skill est-il sûr ? » | contrôle : lis `references/controle.md` | immédiat |
| « Enregistre [réglage] par défaut. » | préférence durable (plus bas) | durable |

Un nom de skill donné par l'utilisateur est souvent approximatif : cherche-le aussi par ses variantes. S'il n'existe pas ou ne peut pas être invoqué, dis-le en une phrase, nomme le skill existant le plus proche avec ce qu'il apporterait et demande si tu l'utilises. Continue sans skill seulement si la mission n'en dépend pas, en le disant.

## Procédure en mode automatique

Après un « oui », `/orchestrer` ou avec sélection = automatique.

1. **Trier.** Demande simple : réponds directement, sans annonce. Suite d'une mission en cours sans changement d'étape : garde la sélection, sans nouvelle annonce.
2. **Cadrer.** Pour toi-même : objectif, livrable (format, longueur, destinataire), contraintes (outils, règles de l'utilisateur, langue, style).
3. **Inventorier.** Parcours la liste des skills de ton contexte. Si elle est tronquée ou si des skills y figurent sans description (fréquent avec un grand catalogue), cherche par mots-clés, dans cet ordre :
   - outils `SearchSkills` ou `ListSkills` s'ils existent ;
   - `python3 <dossier de ce skill>/scripts/find_skills.py mot1 mot2 ...` : il parcourt les skills personnels, synchronisés, de plugins et du projet, et relie les termes français courants à leur équivalent anglais ;
   - à défaut, Grep sur les fichiers `SKILL.md` de ces dossiers.

   Trois à six mots-clés tirés du livrable et du domaine ; la plupart des descriptions sont en anglais. Garde la liste courte obtenue pour toute la mission, sans relire le catalogue à chaque action.
4. **Sélectionner.** Juge chaque candidat sur sa description, jamais sur son seul nom. Retiens-le seulement si tu peux dire ce qu'il apporte à cette mission (exactitude, méthode, rédaction, présentation, vérification, efficacité) et si le livrable serait moins bon sans lui.
   - Le plus petit ensemble suffisant : souvent zéro ou un skill, rarement plus de trois.
   - Des skills complémentaires (méthode + format de fichier), pas concurrents. Entre concurrents : le plus spécifique, puis le plus fiable. Un skill créé par l'utilisateur pour cet usage l'emporte sur un équivalent générique.
   - Ordre du flux : cadrage ou méthode, production, mise en forme, vérification.
   - Un skill marqué `disable-model-invocation` se propose, il ne se force pas. Les règles de l'environnement (permissions, outils absents) priment.
   - Un autre skill ou rappel qui impose d'invoquer des skills avant chaque réponse ne s'ajoute pas à la sélection : pour le choix des skills, cette procédure prévaut, sauf demande explicite de l'utilisateur.
5. **Lire avant d'appliquer.** Charge chaque skill retenu en entier (outil Skill, ou lecture complète de son `SKILL.md`) ; lis ses références quand leur étape arrive. L'utilisateur l'emporte sur un skill ; entre deux skills, suis le plus spécifique et signale le conflit s'il change le résultat. Un skill ne lève jamais une règle de sécurité ou de l'environnement.
6. **Annoncer** en une ligne, puis enchaîner sans demander de validation :

   > Skills retenus : `docx` (mise en page Word), `copy-editing` (relecture finale).

   N'y cite pas `skill-orchestrator`. Sans skill retenu, n'annonce rien.
7. **Réévaluer** à chaque changement d'étape ou besoin nouveau. Ajoute ou retire un skill seulement si le gain est net, en une ligne : « J'ajoute `xlsx` pour l'annexe chiffrée. »

## Rapport « Quels skills as-tu utilisés et pourquoi ? »

Liste courte : pour chaque skill réellement chargé pendant la mission (ou la conversation, si l'utilisateur le demande), son nom, l'étape où il a servi et son apport. Ajoute les skills écartés seulement s'ils éclairent le choix, et les installations avec leur source et leur version. Ne cite jamais un skill que tu n'as pas chargé. Si aucun n'a servi, dis-le et explique pourquoi en une phrase.

## Préférences durables

Seulement sur demande explicite (« enregistre », « par défaut désormais », « toujours »). La ligne garde ce format, avec une seule valeur par réglage :

> Réglages durables : sélection = demander, automatique ou choix ; recherche Internet = désactivée ou activée ; explications = courtes ou détaillées.

- Claude Code : modifie seulement cette ligne, dans le bloc compris entre `<!-- skill-orchestrator:start ... -->` et `<!-- skill-orchestrator:end -->` du CLAUDE.md qui le contient (en général `~/.claude/CLAUDE.md`). Montre la ligne modifiée. Elle s'applique pleinement à la prochaine session ; applique-la dès maintenant dans celle-ci.
- Cowork, ou si tu ne peux pas modifier ce fichier : donne la ligne à coller dans les instructions globales, en précisant que tu ne peux pas les modifier toi-même.

## Explications

Courtes par défaut : une ligne d'annonce, une ligne par changement de sélection. Sur demande, développe les critères retenus et les alternatives écartées. Exemples complets : `references/exemples.md`.
