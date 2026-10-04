#!/bin/sh
# Enveloppe de compatibilité : la logique est dans tests/run_evals.py (Python 3.9+, macOS et Linux,
# sans mapfile, wait -n ni timeout). Les arguments sont transmis tels quels.
#
#   tests/run-tests.sh                                  cas « dev », bras full, modèle claude-opus-5-5
#   tests/run-tests.sh simple-sans-skill rapport-skills un ou plusieurs cas
#   MODEL=claude-sonnet-5-5 MAX_JOBS=4 tests/run-tests.sh
#   tests/run-tests.sh --arm all --split all --repeat 5 --dry-run
#
# Résultats : tests/results/<modèle>/<bras>/run<i>/ (voir tests/README.md).
repo=$(cd "$(dirname "$0")/.." && pwd)
exec "${PYTHON:-python3}" "$repo/tests/run_evals.py" "$@"
