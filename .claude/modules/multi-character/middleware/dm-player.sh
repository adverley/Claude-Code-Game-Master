#!/bin/bash
# multi-character middleware for dm-player.sh
# Routes character commands to characters/<id>.json when in multi-character mode.
# Falls through to CORE (exit 1) when campaign uses single-character format.

MODULE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_ROOT="$(cd "$MODULE_DIR/../../.." && pwd)"

source "$PROJECT_ROOT/tools/common.sh"

if [ "$1" = "--help" ]; then
    echo ""
    echo "  Multi-Character Commands:"
    echo "    show-all                     Show all party members"
    echo "    (All commands require explicit character name in multi-character mode)"
    exit 1
fi

ACTION="$1"
shift

# Check if this campaign uses multi-character format
CAMPAIGN_DIR=$(get_campaign_dir)
if [ -z "$CAMPAIGN_DIR" ]; then
    exit 1  # No campaign, let CORE handle the error
fi

# If characters/ directory doesn't exist, fall through to CORE
if [ ! -d "$CAMPAIGN_DIR/characters" ]; then
    exit 1
fi

# In multi-character mode, route commands to the correct character file
case "$ACTION" in
    show)
        if [ -z "$1" ]; then
            # show without name: show all party members
            exec uv run python -c "
import sys, json
sys.path.insert(0, '$MODULE_DIR/lib')
from party import get_party_characters
from pathlib import Path
chars = get_party_characters(Path('$CAMPAIGN_DIR'))
if not chars:
    print('[INFO] No characters in party')
    sys.exit(0)
for c in chars:
    hp = c.get('hp', {})
    gold = c.get('gold', 0)
    conds = c.get('conditions', [])
    line = f\"{c.get('name', '?')} - {c.get('race', '?')} {c.get('class', '?')} Level {c.get('level', 1)} (HP: {hp.get('current', 0)}/{hp.get('max', 0)}, Gold: {gold})\"
    if conds:
        line += f' | Conditions: {\", \".join(conds)}'
    print(line)
"
        else
            # show <name>: show specific character
            exec $PYTHON_CMD "$LIB_DIR/player_manager.py" show "$1"
        fi
        ;;

    show-all)
        exec uv run python -c "
import sys, json
sys.path.insert(0, '$MODULE_DIR/lib')
from party import get_party_characters
from pathlib import Path
chars = get_party_characters(Path('$CAMPAIGN_DIR'))
if not chars:
    print('[INFO] No characters in party')
    sys.exit(0)
for c in chars:
    hp = c.get('hp', {})
    gold = c.get('gold', 0)
    conds = c.get('conditions', [])
    line = f\"{c.get('name', '?')} - {c.get('race', '?')} {c.get('class', '?')} Level {c.get('level', 1)} (HP: {hp.get('current', 0)}/{hp.get('max', 0)}, Gold: {gold})\"
    if conds:
        line += f' | Conditions: {\", \".join(conds)}'
    print(line)
"
        ;;

    save-json)
        # Route save to characters/<id>.json and add to party
        exec uv run python -c "
import sys, json
sys.path.insert(0, '$MODULE_DIR/lib')
from multi_character import save_character, is_multi_character, migrate_to_multi
from party import add_to_party
from pathlib import Path

campaign_dir = Path('$CAMPAIGN_DIR')
char_json = ' '.join(sys.argv[1:])
char_data = json.loads(char_json)
char_id = char_data.get('id') or char_data['name'].lower().replace(' ', '-').replace(\"'\", '').replace('\"', '')
char_data['id'] = char_id

# If character.json exists (single-char), migrate first
single_file = campaign_dir / 'character.json'
if single_file.exists() and not is_multi_character(campaign_dir):
    migrate_to_multi(campaign_dir)

path = save_character(campaign_dir, char_data)
add_to_party(campaign_dir, char_id)
result = {'success': True, 'character_id': char_id, 'file_path': str(path)}
print(json.dumps(result, indent=2, ensure_ascii=False))
" "$@"
        ;;

    get|hp|xp|gold|inventory|condition|loot|level-check)
        # These commands require a character name — pass through to CORE
        # CORE's PlayerManager already supports characters/ directory (legacy format)
        exit 1
        ;;

    list)
        # List all character IDs from characters/ directory
        exec uv run python -c "
import sys
sys.path.insert(0, '$MODULE_DIR/lib')
from multi_character import list_characters
from pathlib import Path
chars = list_characters(Path('$CAMPAIGN_DIR'))
for c in chars:
    cid = c.get('id', 'unknown')
    print(cid)
"
        ;;

    *)
        exit 1  # Unknown action, let CORE handle
        ;;
esac
