#!/bin/sh
# Tests rapides, sans modèle : hook, recherche de skills, audit, installation, intégrité, manifestes.
#   sh tests/run-unit-tests.sh
set -u
repo=$(cd "$(dirname "$0")/.." && pwd)
cd "$repo" || exit 1
fails=0
run() {
  printf '\n== %s\n' "$1"
  shift
  if "$@"; then :; else fails=$((fails + 1)); fi
}
run "hook" python3 tests/test_hook.py
run "find_skills" python3 tests/test_find_skills.py
run "audit_skill" python3 tests/test_audit_skill.py
run "installation" sh tests/test_install.sh
run "intégrité" python3 install/verify-integrity.py
if command -v claude > /dev/null 2>&1; then
  run "manifeste du plugin" claude plugin validate plugins/skill-orchestrator --strict
  run "manifeste de la marketplace" claude plugin validate . --strict
fi
printf '\n'
[ "$fails" -eq 0 ] && echo "Tous les tests unitaires réussissent." || { echo "$fails série(s) en échec."; exit 1; }
