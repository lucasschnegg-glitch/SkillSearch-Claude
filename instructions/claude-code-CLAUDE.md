<!-- skill-orchestrator:start v1 -->
## Orchestration des skills

Réglages durables : sélection = automatique ; recherche Internet = désactivée ; explications = courtes.
Valeurs possibles de cette ligne : sélection = automatique ou choix ; recherche Internet = désactivée ou activée ; explications = courtes ou détaillées.

À chaque nouvelle demande, avant de travailler :

1. Si la demande est simple (question courte, calcul, conversation, suite immédiate d'une tâche déjà cadrée), réponds directement, sans skill ni annonce.
2. Sinon, identifie l'objectif, le livrable et les contraintes, puis examine les noms et descriptions des skills disponibles. Si la liste est tronquée ou sans descriptions, recherche les skills par mots-clés : ne juge jamais un skill sur son seul nom.
3. Retiens le plus petit ensemble de skills qui améliore concrètement le résultat (exactitude, méthode, qualité rédactionnelle, présentation, vérification, efficacité), jamais sur une simple correspondance de mot-clé. Lis leurs instructions complètes avant de les appliquer.
4. Annonce les skills retenus en une ligne, puis poursuis sans demander de validation. Réévalue la sélection à chaque changement d'étape ou besoin nouveau, sans relire tout le catalogue à chaque action.

La procédure détaillée est dans le skill `skill-orchestrator` : lis-le à la première tâche qui le justifie et dès que je pilote les skills. S'il n'est pas disponible, applique ces règles telles quelles.

- « Mode choix », « Propose-moi plusieurs skills », « Je veux choisir les skills » : présente au plus trois options dont tu as lu la description (apport, avantages, limites, différences), recommande, puis attends mon choix. Mon silence ne vaut pas accord.
- Option Internet (« Cherche un skill sur Internet si nécessaire », « Trouve et installe un skill adapté ») : désactivée par défaut. Sans activation, aucune recherche ni installation de skill externe.
- Autres pilotages : « Mode automatique », « Désactive la recherche Internet », « Utilise uniquement mes skills installés », « Utilise le skill [nom] », « N'utilise aucun skill », « Quels skills as-tu utilisés et pourquoi ? ».

Un réglage demandé pour une tâche ne vaut que pour cette tâche. Modifie la ligne « Réglages durables » seulement si je demande explicitement d'enregistrer une préférence. Mes demandes explicites, les règles de l'environnement et les restrictions d'invocation des skills priment sur cette procédure.
<!-- skill-orchestrator:end -->
