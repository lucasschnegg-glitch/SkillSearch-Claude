#!/usr/bin/env bash
# Lance les scénarios de tests/cases.json avec claude -p, chacun dans une session neuve
# et un projet temporaire qui contient :
#   - CLAUDE.md = le bloc instructions/claude-code-CLAUDE.md (instructions persistantes) ;
#   - un dossier .claude/skills vide (pour tester l'ajout d'un skill en cours de session).
# Le plugin est chargé pour la session seulement avec --plugin-dir : rien n'est installé.
#
#   tests/run-tests.sh                    tous les cas
#   tests/run-tests.sh simple-sans-skill  un ou plusieurs cas
#   MODEL=claude-sonnet-5-5 tests/run-tests.sh
#
# Résultats : tests/results/<cas>.jsonl (flux stream-json), puis vérification automatique.
set -euo pipefail

repo=$(cd "$(dirname "$0")/.." && pwd)
out=${OUT_DIR:-$repo/tests/results}
model=${MODEL:-claude-opus-5-5}
work_root=${WORK_ROOT:-$(mktemp -d)}
mkdir -p "$out" "$work_root"

field() { python3 -c 'import json,sys; c=[c for c in json.load(open(sys.argv[1]))["cases"] if c["id"]==sys.argv[2]][0]; print(c.get(sys.argv[3], ""))' "$repo/tests/cases.json" "$1" "$2"; }

if [ $# -gt 0 ]; then
  ids="$*"
else
  ids=$(python3 -c 'import json,sys; print(" ".join(c["id"] for c in json.load(open(sys.argv[1]))["cases"]))' "$repo/tests/cases.json")
fi

for id in $ids; do
  (
    work="$work_root/$id/projet"
    rm -rf "$work_root/$id"
    mkdir -p "$work/.claude/skills"
    cp "$repo/instructions/claude-code-CLAUDE.md" "$work/CLAUDE.md"
    prompt=$(field "$id" prompt)
    turns=$(field "$id" max_turns)
    perm=$(field "$id" permission_mode)
    read -r -a tools <<< "$(field "$id" allowed_tools)"
    session=$(python3 -c 'import uuid; print(uuid.uuid4())')
    cd "$work"
    # --session-id : une session neuve et distincte pour chaque cas.
    timeout 1200 claude -p "$prompt" \
      --session-id "$session" \
      --model "$model" \
      --max-turns "$turns" \
      --permission-mode "$perm" \
      --allowedTools "${tools[@]}" \
      --plugin-dir "$repo/plugins/skill-orchestrator" \
      --output-format stream-json --verbose --include-hook-events \
      > "$out/$id.jsonl" 2> "$out/$id.stderr" || echo "[$id] code de sortie $?" >> "$out/$id.stderr"
    # Deuxième message facultatif, dans la même session (champ « followup »).
    followup=$(field "$id" followup 2>/dev/null || true)
    if [ -n "$followup" ]; then
      timeout 1200 claude -p "$followup" \
        --resume "$session" \
        --model "$model" \
        --max-turns "$turns" \
        --permission-mode "$perm" \
        --allowedTools "${tools[@]}" \
        --plugin-dir "$repo/plugins/skill-orchestrator" \
        --output-format stream-json --verbose --include-hook-events \
        >> "$out/$id.jsonl" 2>> "$out/$id.stderr" || echo "[$id] relance : code de sortie $?" >> "$out/$id.stderr"
    fi
    cp "$work/CLAUDE.md" "$out/$id.claude.md"
    (cd "$work" && find . -type f ! -name CLAUDE.md | sort) > "$out/$id.files"
    echo "[$id] terminé"
  ) &
done
wait

python3 "$repo/tests/check_results.py" "$out" $ids
