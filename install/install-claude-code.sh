#!/bin/sh
# Installe, met à jour ou retire le bloc d'instructions « skill-orchestrator »
# dans ~/.claude/CLAUDE.md (instructions persistantes de Claude Code).
#
#   sh install/install-claude-code.sh                 installe ou met à jour le bloc
#   sh install/install-claude-code.sh --with-plugin   idem, puis installe le plugin depuis ce dépôt
#   sh install/install-claude-code.sh --uninstall     retire le bloc (le reste du fichier est conservé)
#   sh install/install-claude-code.sh --dry-run       affiche le résultat sans rien écrire
#
# Le reste de CLAUDE.md n'est jamais modifié. Une copie de sauvegarde est créée avant
# toute écriture. Lors d'une mise à jour, la ligne « Réglages durables » existante est
# conservée, pour ne pas effacer tes préférences.

set -eu

here=$(cd "$(dirname "$0")/.." && pwd)
block_file="$here/instructions/claude-code-CLAUDE.md"
config_dir="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
target="$config_dir/CLAUDE.md"
start='<!-- skill-orchestrator:start'
end='<!-- skill-orchestrator:end -->'

mode=install
with_plugin=no
for arg in "$@"; do
  case "$arg" in
    --uninstall) mode=uninstall ;;
    --dry-run) mode=dry-run ;;
    --with-plugin) with_plugin=yes ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "Option inconnue : $arg" >&2; exit 2 ;;
  esac
done

[ -f "$block_file" ] || { echo "Bloc introuvable : $block_file" >&2; exit 1; }
if [ ! -f "$target" ]; then
  if [ "$mode" = "uninstall" ]; then
    echo "Rien à retirer : $target n'existe pas."
    exit 0
  fi
  mkdir -p "$config_dir"
  : > "$target"
fi

starts=$(grep -c -F "$start" "$target" || true)
ends=$(grep -c -F "$end" "$target" || true)
if [ "$starts" != "$ends" ] || [ "$starts" -gt 1 ]; then
  echo "Marqueurs skill-orchestrator incomplets ou en double dans $target : corrige-les à la main, rien n'a été modifié." >&2
  exit 1
fi

tmp=$(mktemp)
trap 'rm -f "$tmp" "$tmp.trim"' EXIT

# Ligne de réglages durables déjà présente (si le bloc existe), à conserver.
kept=$(awk -v s="$start" -v e="$end" '
  index($0, s) == 1 { inside = 1; next }
  index($0, e) == 1 { inside = 0; next }
  inside && /^Réglages durables :/ { print; exit }
' "$target")

# Copie du fichier sans l'ancien bloc.
awk -v s="$start" -v e="$end" '
  index($0, s) == 1 { inside = 1; next }
  inside && index($0, e) == 1 { inside = 0; next }
  !inside { print }
' "$target" > "$tmp"

# Retire les lignes vides finales laissées par l'ancien bloc.
awk '{ lines[NR] = $0 } END { n = NR; while (n > 0 && lines[n] ~ /^[[:space:]]*$/) n--; for (i = 1; i <= n; i++) print lines[i] }' "$tmp" > "$tmp.trim"
mv "$tmp.trim" "$tmp"

if [ "$mode" != "uninstall" ]; then
  # Une ligne vide de séparation, puis le nouveau bloc.
  [ -s "$tmp" ] && printf '\n' >> "$tmp"
  if [ -n "$kept" ]; then
    awk -v kept="$kept" '/^Réglages durables :/ { print kept; next } { print }' "$block_file" >> "$tmp"
  else
    cat "$block_file" >> "$tmp"
  fi
fi

if [ "$mode" = "dry-run" ]; then
  cat "$tmp"
  exit 0
fi

if cmp -s "$tmp" "$target"; then
  echo "Aucun changement : $target est déjà à jour."
else
  backup="$target.bak-$(date +%Y%m%d-%H%M%S)-$$"
  cp "$target" "$backup"
  cp "$tmp" "$target"
  if [ "$mode" = "uninstall" ]; then
    echo "Bloc skill-orchestrator retiré de $target (sauvegarde : $backup)."
  else
    echo "Bloc skill-orchestrator installé dans $target (sauvegarde : $backup)."
    [ -n "$kept" ] && echo "Réglages durables conservés : $kept"
  fi
fi

if [ "$with_plugin" = "yes" ] && [ "$mode" = "install" ]; then
  if command -v claude >/dev/null 2>&1; then
    claude plugin marketplace add "$here"
    claude plugin install skill-orchestrator@skillsearch
    echo "Plugin installé. Dans une session déjà ouverte, lance /reload-plugins."
  else
    echo "Commande claude introuvable : installe le plugin depuis une session avec"
    echo "  /plugin marketplace add $here"
    echo "  /plugin install skill-orchestrator@skillsearch"
  fi
fi
