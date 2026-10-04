#!/bin/sh
# Hook UserPromptSubmit du plugin skill-orchestrator.
#
# Lit le JSON de l'événement sur l'entrée standard et écrit un court rappel sur la
# sortie standard. Pour cet événement, Claude Code ajoute la sortie standard au
# contexte du message. Le script ne fait aucun accès réseau et n'écrit aucun fichier.
#
# Les « indices » détectés par mots-clés ne sont que des signaux : Claude vérifie
# l'intention réelle dans le message.
#
# Désactivation rapide sans désinstaller : variable SKILL_ORCHESTRATOR_HOOK=off.

[ "${SKILL_ORCHESTRATOR_HOOK:-on}" = "off" ] && exit 0

input=$(cat 2>/dev/null)

# On retire les champs techniques (chemins, identifiants) pour ne chercher les
# formulations que dans le texte du message, puis on passe en minuscules.
text=$(printf '%s' "$input" \
  | sed -e 's/"transcript_path"[[:space:]]*:[[:space:]]*"[^"]*"//' \
        -e 's/"cwd"[[:space:]]*:[[:space:]]*"[^"]*"//' \
        -e 's/"session_id"[[:space:]]*:[[:space:]]*"[^"]*"//' \
        -e 's/"prompt_id"[[:space:]]*:[[:space:]]*"[^"]*"//' \
  | tr '[:upper:]' '[:lower:]')

has() {
  printf '%s' "$text" | grep -E -q "$1"
}

printf '%s\n' "[Orchestration des skills] Si la demande est simple, réponds directement, sans skill ni annonce. Sinon : identifie objectif, livrable et contraintes ; retiens le plus petit ensemble de skills disponibles qui améliore concrètement le résultat ; lis-les en entier avant de les appliquer ; annonce-les en une ligne ; réévalue à chaque changement d'étape. Réglages : ceux déjà fixés pour la tâche en cours, sinon les réglages durables (par défaut : mode automatique, recherche Internet désactivée, explications courtes). Procédure complète : skill skill-orchestrator."

hints=""
add_hint() {
  hints="${hints}
- $1"
}

if has "mode choix|propose[r]?[- ]moi (plusieurs|des|quelques) skills|je (veux|voudrais|souhaite) choisir (les |mes |le )?skills?|laisse[- ]moi choisir|choice mode|let me choose"; then
  add_hint "mode choix demandé pour cette tâche : présente au plus trois options, recommande, puis attends le choix explicite."
elif has "mode auto(matique)?"; then
  add_hint "retour au mode automatique pour cette tâche."
fi

if has "d(e|é)sactive[rz]? (la )?recherche (sur )?internet|sans (recherche )?internet|(uniquement|seulement) (avec )?(mes|les) skills install|only (my )?installed skills|no internet"; then
  add_hint "option Internet désactivée : aucune recherche ni installation de skill externe."
elif has "(cherche|trouve|recherche)[^.?!]{0,50}skills?[^.?!]{0,50}(internet|en ligne|sur le web)|(^|[^a-z])active[rz]? la recherche internet|avec recherche internet|(trouve|cherche)[^.?!]{0,20} et installe|installe[rz]?[^.?!]{0,30}skills?[^.?!]{0,30}(internet|en ligne|adapt)|(search|look) (the )?(web|internet|online) for (a )?skill|find and install"; then
  add_hint "option Internet activée pour cette tâche : suis references/internet.md du skill skill-orchestrator."
fi

if has "n('|’|e )?utilise (aucun|pas de) skills?|sans (aucun )?skills?([^a-z]|$)|don'?t use (any )?skills?"; then
  add_hint "aucun skill pour cette tâche."
elif has "utilise (le|les|uniquement le) skills? [a-z0-9]"; then
  add_hint "skill demandé explicitement : utilise-le s'il existe et peut être invoqué."
fi

if has "quels? skills? (as[- ]tu|avez[- ]vous|tu as) (utilis|employ)|which skills (did|have) you use"; then
  add_hint "rapport demandé : liste les skills réellement chargés, leur étape et leur apport."
fi

if has "(enregistre|m(é|e)morise|garde|retiens)[^.?!]{0,40}(r(é|e)glage|pr(é|e)f(é|e)rence|par d(é|e)faut)|par d(é|e)faut d(é|e)sormais|d(é|e)sormais par d(é|e)faut"; then
  add_hint "préférence durable possible : modifie seulement la ligne « Réglages durables » si la demande est explicite."
fi

if [ -n "$hints" ]; then
  printf '%s%s\n' "Indices détectés dans le message (vérifie l'intention réelle) :" "$hints"
fi

exit 0
