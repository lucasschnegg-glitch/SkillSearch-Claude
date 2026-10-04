#!/usr/bin/env bash
# Lance les scénarios de tests/cases.json avec claude -p, chacun dans une session neuve
# et un projet temporaire qui contient :
#   - CLAUDE.md = le bloc instructions/claude-code-CLAUDE.md (instructions persistantes) ;
#   - un dossier .claude/skills vide (pour tester l'ajout d'un skill en cours de session) ;
#   - les fichiers d'entrée du cas (champ « files »).
# Le plugin est chargé pour la session seulement avec --plugin-dir : rien n'est installé.
# Les messages suivants (champ « followup », texte ou liste) sont envoyés dans la même
# session avec --resume.
#
#   tests/run-tests.sh                    tous les cas
#   tests/run-tests.sh simple-sans-skill  un ou plusieurs cas
#   MODEL=claude-sonnet-5-5 tests/run-tests.sh
#   MAX_JOBS=4 tests/run-tests.sh         nombre de sessions en parallèle (défaut 6)
#
# Résultats : tests/results/<cas>.jsonl (flux stream-json), puis vérification automatique.
set -euo pipefail

repo=$(cd "$(dirname "$0")/.." && pwd)
cases="$repo/tests/cases.json"
out=${OUT_DIR:-$repo/tests/results}
model=${MODEL:-claude-opus-5-5}
max_jobs=${MAX_JOBS:-6}
work_root=${WORK_ROOT:-$(mktemp -d)}
mkdir -p "$out" "$work_root"

# Lit un champ d'un cas. Les listes sont rendues une valeur par ligne.
field() {
  python3 - "$cases" "$1" "$2" <<'EOF'
import json, sys
case = next(c for c in json.load(open(sys.argv[1], encoding="utf-8"))["cases"] if c["id"] == sys.argv[2])
value = case.get(sys.argv[3], "")
if isinstance(value, list):
    print("\n".join(value))
elif isinstance(value, dict):
    print(json.dumps(value, ensure_ascii=False))
else:
    print(value)
EOF
}

if [ $# -gt 0 ]; then
  ids="$*"
else
  ids=$(python3 -c 'import json,sys; print(" ".join(c["id"] for c in json.load(open(sys.argv[1]))["cases"]))' "$cases")
fi

run_case() {
  local id=$1
  local work="$work_root/$id/projet"
  rm -rf "$work_root/$id"
  mkdir -p "$work/.claude/skills"
  cp "$repo/instructions/claude-code-CLAUDE.md" "$work/CLAUDE.md"
  # Fichiers d'entrée : {"nom": "contenu"}.
  python3 - "$cases" "$id" "$work" <<'EOF'
import json, sys, pathlib
case = next(c for c in json.load(open(sys.argv[1], encoding="utf-8"))["cases"] if c["id"] == sys.argv[2])
for name, content in case.get("files", {}).items():
    path = pathlib.Path(sys.argv[3]) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
EOF
  local prompt turns perm session
  prompt=$(field "$id" prompt)
  turns=$(field "$id" max_turns)
  perm=$(field "$id" permission_mode)
  mapfile -t tools < <(field "$id" allowed_tools | tr ' ' '\n' | grep -v '^$' || true)
  # Une liste JSON garde les règles qui contiennent des espaces.
  if python3 -c 'import json,sys; c=next(c for c in json.load(open(sys.argv[1]))["cases"] if c["id"]==sys.argv[2]); sys.exit(0 if isinstance(c.get("allowed_tools"), list) else 1)' "$cases" "$id"; then
    mapfile -t tools < <(field "$id" allowed_tools)
  fi
  session=$(python3 -c 'import uuid; print(uuid.uuid4())')
  # Dossiers supplémentaires accessibles (champ « add_dirs », {repo} = racine du dépôt).
  local extra=()
  while IFS= read -r dir; do
    [ -n "$dir" ] && extra+=(--add-dir "${dir//\{repo\}/$repo}")
  done < <(field "$id" add_dirs)
  local common=(--model "$model" --max-turns "$turns" --permission-mode "$perm"
    --allowedTools "${tools[@]}" --plugin-dir "$repo/plugins/skill-orchestrator"
    "${extra[@]}" --output-format stream-json --verbose --include-hook-events)
  cd "$work"
  # --session-id : une session neuve et distincte pour chaque cas.
  timeout 1500 claude -p "$prompt" --session-id "$session" "${common[@]}" \
    > "$out/$id.jsonl" 2> "$out/$id.stderr" || echo "[$id] code de sortie $?" >> "$out/$id.stderr"
  local followup
  while IFS= read -r followup; do
    [ -n "$followup" ] || continue
    timeout 1500 claude -p "$followup" --resume "$session" "${common[@]}" \
      >> "$out/$id.jsonl" 2>> "$out/$id.stderr" || echo "[$id] relance : code de sortie $?" >> "$out/$id.stderr"
  done < <(field "$id" followup)
  cp "$work/CLAUDE.md" "$out/$id.claude.md"
  (cd "$work" && find . -type f ! -name CLAUDE.md | sort) > "$out/$id.files"
  echo "[$id] terminé"
}

for id in $ids; do
  while [ "$(jobs -rp | wc -l)" -ge "$max_jobs" ]; do wait -n || true; done
  run_case "$id" &
done
wait

python3 "$repo/tests/check_results.py" "$out" $ids
