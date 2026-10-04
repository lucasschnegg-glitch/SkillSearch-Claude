#!/bin/sh
# Hook UserPromptSubmit du plugin skill-orchestrator : lanceur.
#
# La logique est dans skill_reminder.py (lecture JSON fiable, accents et casse quelle
# que soit la langue du système). Sans Python utilisable, le lanceur écrit seulement le
# rappel court, sans indices. Aucun accès réseau, aucune écriture de fichier.
#
# SKILL_ORCHESTRATOR_HOOK : on (défaut) = rappel + indices ; hints = indices seulement ;
# off = rien. SKILL_ORCHESTRATOR_PYTHON : interpréteur à utiliser (défaut python3).

mode="${SKILL_ORCHESTRATOR_HOOK:-on}"
[ "$mode" = "off" ] && exit 0

here=$(dirname "$0")
py="${SKILL_ORCHESTRATOR_PYTHON:-python3}"
input=$(cat 2>/dev/null)

usable=no
if command -v "$py" >/dev/null 2>&1; then
  usable=yes
  # macOS sans outils de développement : /usr/bin/python3 ouvrirait une fenêtre d'installation.
  if [ "$(command -v "$py")" = /usr/bin/python3 ] && [ "$(uname)" = Darwin ] \
     && ! xcode-select -p >/dev/null 2>&1; then
    usable=no
  fi
fi

if [ "$usable" = yes ]; then
  if out=$(printf '%s' "$input" | "$py" "$here/skill_reminder.py" 2>/dev/null); then
    [ -n "$out" ] && printf '%s\n' "$out"
    exit 0
  fi
fi

[ "$mode" = "hints" ] && exit 0
printf '%s\n' '{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":"[Orchestration des skills] Demande simple : réponds directement, sans skill. Début de mission : suis la ligne « Réglages durables » (question de départ, procédure directe ou mode choix). Orchestration retenue : lis d’abord le skill skill-orchestrator, puis applique sa procédure."}}'
exit 0
