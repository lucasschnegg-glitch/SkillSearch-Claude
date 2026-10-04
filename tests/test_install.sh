#!/bin/sh
# Tests du script install/install-claude-code.sh dans un dossier de configuration temporaire.
#   sh tests/test_install.sh
set -u

repo=$(cd "$(dirname "$0")/.." && pwd)
installer="$repo/install/install-claude-code.sh"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
export CLAUDE_CONFIG_DIR="$tmp/config"
mkdir -p "$CLAUDE_CONFIG_DIR"
target="$CLAUDE_CONFIG_DIR/CLAUDE.md"
fails=0

check() {
  if eval "$2"; then echo "ok   $1"; else echo "KO   $1"; fails=$((fails + 1)); fi
}

printf '# Mes règles\n\nNe jamais utiliser de tiret cadratin.\n' > "$target"
cp "$target" "$tmp/original.md"

sh "$installer" > /dev/null
check "le bloc est ajouté" '[ "$(grep -c "skill-orchestrator:start" "$target")" = 1 ]'
check "le contenu existant est conservé" 'grep -q "Ne jamais utiliser de tiret cadratin." "$target"'
check "une sauvegarde est créée" '[ "$(ls "$CLAUDE_CONFIG_DIR" | grep -c "CLAUDE.md.bak-")" -ge 1 ]'

sh "$installer" > /dev/null
check "réinstallation sans doublon" '[ "$(grep -c "skill-orchestrator:start" "$target")" = 1 ]'

sed -i.tmp 's/^Réglages durables : sélection = demander/Réglages durables : sélection = choix/' "$target" && rm -f "$target.tmp"
sh "$installer" > /dev/null
check "la préférence durable survit à la mise à jour" 'grep -q "^Réglages durables : sélection = choix" "$target"'

sh "$installer" --uninstall > /dev/null
check "la désinstallation restitue le fichier d'origine" 'cmp -s "$tmp/original.md" "$target"'

printf '<!-- skill-orchestrator:start v1 -->\nincomplet\n' >> "$target"
cp "$target" "$tmp/broken.md"
sh "$installer" > /dev/null 2>&1
code=$?
check "marqueurs incomplets : refus" '[ "$code" -ne 0 ]'
check "marqueurs incomplets : fichier intact" 'cmp -s "$tmp/broken.md" "$target"'

rm -f "$target"
sh "$installer" --uninstall > /dev/null
check "désinstallation sans fichier : rien n'est créé" '[ ! -f "$target" ]'

check "aucune trace hors du dossier temporaire" '[ -z "$(find "$tmp" -newer "$tmp/original.md" -path "$HOME/*" 2>/dev/null)" ]'

[ "$fails" -eq 0 ] && echo "Tous les tests du script d'installation réussissent." || { echo "$fails échec(s)."; exit 1; }
