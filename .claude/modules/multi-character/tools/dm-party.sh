#!/usr/bin/env bash
# dm-party.sh — Party roster management CLI
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODULE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$MODULE_ROOT/../../.." && pwd)"

source "$PROJECT_ROOT/tools/common.sh"
require_active_campaign

ACTION="${1:-}"
shift 2>/dev/null || true

CAMPAIGN_DIR=$(get_campaign_dir)

case "$ACTION" in
    list)
        uv run python -c "
import sys, json
sys.path.insert(0, sys.argv[1])
from party import get_party_characters
from pathlib import Path
chars = get_party_characters(Path(sys.argv[2]))
if not chars:
    print('[INFO] No characters in party')
    sys.exit(0)
print('Party Members:')
print('-' * 60)
for c in chars:
    hp = c.get('hp', {})
    gold = c.get('gold', 0)
    print(f\"  {c.get('name', '?')} - {c.get('race', '?')} {c.get('class', '?')} Lv{c.get('level', 1)} (HP: {hp.get('current', 0)}/{hp.get('max', 0)}, Gold: {gold})\")
print(f'\nTotal: {len(chars)} character(s)')
" "$MODULE_ROOT/lib" "$CAMPAIGN_DIR"
        ;;

    add)
        if [ -z "${1:-}" ]; then
            echo "Usage: dm-party.sh add <character-name>"
            exit 1
        fi
        uv run python -c "
import sys
sys.path.insert(0, sys.argv[1])
from multi_character import find_character_file, load_character
from party import add_to_party
from pathlib import Path

campaign_dir = Path(sys.argv[2])
name = sys.argv[3]
try:
    find_character_file(campaign_dir, name)
except FileNotFoundError as e:
    print(f'[ERROR] {e}', file=sys.stderr)
    sys.exit(1)

char = load_character(campaign_dir, name)
char_id = char.get('id', name.lower().replace(' ', '-'))
add_to_party(campaign_dir, char_id)
print(f'[SUCCESS] Added {char.get(\"name\", name)} to party')
" "$MODULE_ROOT/lib" "$CAMPAIGN_DIR" "$1"
        ;;

    remove)
        if [ -z "${1:-}" ]; then
            echo "Usage: dm-party.sh remove <character-name>"
            exit 1
        fi
        uv run python -c "
import sys
sys.path.insert(0, sys.argv[1])
from party import remove_from_party
from pathlib import Path

campaign_dir = Path(sys.argv[2])
char_id = sys.argv[3].lower().replace(' ', '-').replace(\"'\", '').replace('\"', '')
remove_from_party(campaign_dir, char_id)
print(f'[SUCCESS] Removed {char_id} from party')
" "$MODULE_ROOT/lib" "$CAMPAIGN_DIR" "$1"
        ;;

    migrate)
        uv run python -c "
import sys
sys.path.insert(0, sys.argv[1])
from multi_character import migrate_to_multi, is_multi_character
from pathlib import Path

campaign_dir = Path(sys.argv[2])
if is_multi_character(campaign_dir) and not (campaign_dir / 'character.json').exists():
    print('[INFO] Campaign already uses multi-character format')
    sys.exit(0)
migrate_to_multi(campaign_dir)
print('[SUCCESS] Migrated to multi-character format')
" "$MODULE_ROOT/lib" "$CAMPAIGN_DIR"
        ;;

    *)
        echo "D&D Party Management"
        echo "Usage: dm-party.sh <action> [args]"
        echo ""
        echo "Actions:"
        echo "  list              Show all PCs in party with stats"
        echo "  add <name>        Add character to party roster"
        echo "  remove <name>     Remove character from party roster"
        echo "  migrate           Manually migrate to multi-character format"
        ;;
esac
