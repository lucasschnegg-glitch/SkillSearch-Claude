---
name: orchestrer
description: Commande de l'utilisateur pour activer l'orchestration des skills sur la mission en cours, sans question de départ. Arguments facultatifs : choix, internet.
argument-hint: "[choix] [internet]"
disable-model-invocation: true
---

# Activer l'orchestration des skills

L'utilisateur active lui-même l'orchestration des skills pour la mission en cours. Ne pose pas la question de départ : sa réponse est « oui ».

Arguments reçus : $ARGUMENTS

Lis-les ainsi (s'ils n'ont pas été remplacés ci-dessus, lis-les dans le message de l'utilisateur, après le nom de la commande) :

- aucun argument : mode automatique ;
- « choix » : mode choix ;
- « internet » : option Internet activée pour cette mission, en plus du mode indiqué.

Puis, dans cet ordre :

1. Charge en entier le skill `skill-orchestrator` (outil Skill, ou lecture complète de son `SKILL.md`) et applique sa procédure à la mission en cours, avec le mode ci-dessus.
2. Si aucune mission n'est encore décrite dans la conversation, demande en une phrase quelle est la mission, puis applique la procédure dès la réponse.
3. Ce réglage vaut jusqu'à la fin de la mission ; il ne modifie pas la ligne « Réglages durables ».
