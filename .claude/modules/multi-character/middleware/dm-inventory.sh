#!/bin/bash
# multi-character middleware for dm-inventory.sh
# Resolves character name to file path and passes --character-file to InventoryManager.
# Falls through to CORE (exit 1) when campaign uses single-character format.

MODULE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_ROOT="$(cd "$MODULE_DIR/../../.." && pwd)"

source "$PROJECT_ROOT/tools/common.sh"

if [ "$1" = "--help" ]; then
    echo ""
    echo "  Multi-Character: inventory commands use --character-file to target specific characters"
    exit 1
fi

CAMPAIGN_DIR=$(get_campaign_dir)
if [ -z "$CAMPAIGN_DIR" ]; then
    exit 1
fi

# If not multi-character, fall through to CORE
if [ ! -d "$CAMPAIGN_DIR/characters" ]; then
    exit 1
fi

# Extract the subcommand and character name
SUBCMD="${1:-}"
CHAR_NAME="${2:-}"

if [ -z "$CHAR_NAME" ]; then
    exit 1  # No character specified, let CORE handle
fi

# Resolve character name to file path (user input passed via sys.argv, not interpolated)
CHAR_FILE=$(uv run python -c "
import sys
sys.path.insert(0, sys.argv[1])
from multi_character import find_character_file
from pathlib import Path
try:
    path = find_character_file(Path(sys.argv[2]), sys.argv[3])
    print(path.relative_to(Path(sys.argv[2])))
except FileNotFoundError as e:
    print(str(e), file=sys.stderr)
    sys.exit(1)
" "$MODULE_DIR/lib" "$CAMPAIGN_DIR" "$CHAR_NAME" 2>&1)

rc=$?
if [ $rc -ne 0 ]; then
    echo "$CHAR_FILE" >&2  # Print the error message
    exit $rc
fi

# Forward to the inventory-system module's tool with --character-file injected
INVENTORY_MODULE="$PROJECT_ROOT/.claude/modules/inventory-system"
exec uv run python "$INVENTORY_MODULE/lib/inventory_manager.py" --character-file "$CHAR_FILE" "$@"
