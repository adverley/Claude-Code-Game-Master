# Multi-Character Campaign Support

**Date:** 2026-04-06
**Status:** Approved

## Summary

Add support for tracking multiple playable characters within a single campaign. Currently each campaign stores one `character.json` — this design introduces a `characters/` directory holding one JSON file per PC, a party roster in campaign overview, and a new module to manage it all.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Spatial model | Party-based (shared location) | Matches existing `move_party()`, simplest model, standard D&D |
| Storage format | `characters/<id>.json` directory | One file per character avoids merge conflicts, clean separation |
| Character creation | Additive, no cap | DM manages party size narratively |
| Migration strategy | On demand | No disruption to single-character campaigns; migrates when second PC is added |
| Command targeting | Explicit name required | No ambiguous "active character" state; clear in multiplayer sessions |
| Architecture | Module-based (`.claude/modules/multi-character/`) | Follows project convention — no changes to `lib/` core |

## Storage & Data Model

### Character files

Each PC is stored as `<campaign>/characters/<character-id>.json`. The character JSON schema is unchanged — same fields as the current `character.json`.

Example layout after migration:
```
world-state/campaigns/the-pot-of-trammeloeren/
├── campaign-overview.json
├── characters/
│   ├── theron-oakshade.json
│   └── lyra-moonwhisper.json
├── npcs.json
├── locations/
└── session-log.md
```

### Campaign overview changes

Add a `party` array to `campaign-overview.json` listing active character IDs:

```json
{
  "campaign_name": "The Pot of Trammeloeren",
  "party": ["theron-oakshade", "lyra-moonwhisper"],
  "player_position": {
    "current_location": "Trammeloeren Village"
  }
}
```

The `player_position.current_location` remains shared across all party members (party-based movement).

The existing `current_character` field is unused by this design and can be ignored.

### Migration (on demand)

When a second character is created in a campaign that uses the old `character.json` format:

1. Read existing `character.json`
2. Create `characters/` directory
3. Write character data to `characters/<id>.json` (ID derived from character's `id` field)
4. Delete old `character.json`
5. Add the character's ID to the new `party` array in campaign overview
6. Save the new character to `characters/<new-id>.json`
7. Add the new character's ID to the `party` array

Single-character campaigns that never add a second PC continue using `character.json` with no changes. The module's middleware transparently handles both formats.

## Module Structure

```
.claude/modules/multi-character/
├── module.json
├── middleware/
│   └── dm-player.sh
├── lib/
│   ├── multi_character.py
│   └── party.py
└── tools/
    └── dm-party.sh
```

### module.json

```json
{
  "name": "multi-character",
  "description": "Multi-character campaign support with party roster management",
  "version": "1.0.0",
  "middleware": ["dm-player.sh"],
  "tools": ["dm-party.sh"]
}
```

### middleware/dm-player.sh

Intercepts all `dm-player.sh` calls. Behavior:

- All character-targeting commands (`show`, `modify-hp`, `modify-gold`, `modify-inventory`, `award-xp`, `modify-condition`, `apply-loot`) require an explicit character name parameter.
- Middleware resolves the character name to `characters/<id>.json` file path.
- If the campaign uses single-character format (`character.json` exists, no `characters/` directory), passes through to core `PlayerManager` unchanged.
- On `save-json`: if `characters/` directory exists, routes the save to the correct file based on the character's `id` field.
- On `show-all`: iterates all files in `characters/` and displays each.
- Supports `--help` flag per module convention.

### lib/multi_character.py

Core multi-character operations:

- `list_characters(campaign_dir)` — returns list of character data from `characters/*.json`
- `load_character(campaign_dir, name)` — loads a specific character by name/ID from `characters/`
- `save_character(campaign_dir, character_data)` — saves character data to `characters/<id>.json`
- `migrate_to_multi(campaign_dir)` — migrates `character.json` to `characters/<id>.json` format
- `is_multi_character(campaign_dir)` — returns True if `characters/` directory exists
- `find_character_file(campaign_dir, name)` — resolves a character name to its file path. Searches by `id` first (exact match on filename), then falls back to matching the `name` field inside each JSON file (case-insensitive). Returns the first match or raises an error listing available characters.

### lib/party.py

Party roster management:

- `get_party(campaign_dir)` — returns the `party` array from campaign overview
- `add_to_party(campaign_dir, character_id)` — adds a character ID to the party array
- `remove_from_party(campaign_dir, character_id)` — removes a character ID from the party array (does not delete the character file)
- `get_party_characters(campaign_dir)` — loads full character data for all party members

### tools/dm-party.sh

New CLI tool for party management:

- `dm-party.sh list` — shows all PCs in the party with summary stats (name, race, class, level, HP)
- `dm-party.sh add <name>` — adds an existing character to the party roster
- `dm-party.sh remove <name>` — removes a character from the party roster (file preserved)
- `dm-party.sh migrate` — manually triggers single-to-multi character migration

## Integration Points

### Character creation (`/create-character` skill)

The module middleware intercepts the `dm-player.sh save-json` call:

- If `characters/` directory exists: saves directly to `characters/<id>.json`
- If `character.json` exists and this is a new character (different ID): triggers migration first, then saves the new character
- If no character exists at all: creates `characters/` directory, saves to `characters/<id>.json`
- In all cases: adds the new character's ID to the `party` array in campaign overview

### Discord bot

No changes needed to the Discord bot:

- `PlayerMap` already maps Discord user IDs to character names
- `!join <character>` works as-is since character names map to file names
- `!status` and `!inventory` pass the character name from `PlayerMap` through to CLI commands, which the middleware routes to the correct file
- `claude_bridge.py` session start passes all player mappings — Claude sees the full party

### Session management

- `start_session()` — world summary includes all party members' stats by iterating the `party` array and loading each character
- `move_party()` — unchanged, moves the whole party as a unit
- `end_session()` — session log can reference all PCs involved in the session

### Existing modules

No changes needed to other modules:

- `custom-stats/` — already takes a character name parameter
- `inventory-system/` — same, character name is passed through
- `firearms-combat/` — combat resolution already accepts character names

All existing modules receive character names via the middleware layer and operate on whichever character is specified.

### show_all_players()

Currently loads the single `character.json`. The module middleware overrides this to iterate `characters/*.json` and display all party members. Used by session start and world summary.

## Testing Strategy

### Unit tests

**multi_character.py:**
- `list_characters` returns all characters from `characters/` directory
- `load_character` finds character by name and by ID
- `save_character` writes to correct path with correct filename
- `migrate_to_multi` moves `character.json` to `characters/<id>.json`, preserves all data, removes old file
- `is_multi_character` correctly detects both formats
- `find_character_file` resolves names case-insensitively

**party.py:**
- `add_to_party` appends ID to party array, creates array if missing
- `remove_from_party` removes ID, handles ID not in list
- `get_party_characters` loads all party member data
- Party array stays in sync with `characters/` directory

### Integration tests

- Create first character in empty campaign: `characters/` created, party array contains one entry
- Create second character with existing `character.json`: migration occurs, both characters in `characters/`, party has two entries
- All `dm-player.sh` commands with explicit name target correct character file
- `dm-party.sh list` displays all party members with stats
- Single-character campaign with no second PC: `character.json` format works unchanged
- `dm-party.sh remove` then `dm-party.sh add` round-trips correctly

### Edge cases

- Character name doesn't match any file: clear error message with available names listed
- Duplicate character IDs on creation: rejected with error
- Empty party (all members removed): handled gracefully, no crashes
- Migration when `characters/` directory already exists: skips directory creation, only moves file
- Character with no `id` field: falls back to generating ID from `name` field (slugified)
