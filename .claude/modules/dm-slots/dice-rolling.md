## Dice Rolling

**YOU roll ALL dice.** Players NEVER roll during gameplay. When a player action
requires a check, attack, save, or damage — you roll it yourself. Never say
"roll a perception check" or "make a saving throw" — just roll and narrate the result.

Players have `!roll` for casual/fun rolls, but all mechanical rolls are yours.

**HOW TO ROLL**: Always use `uv run python lib/dice.py "[notation]"`

**NEVER** write inline Python for dice rolls.

```bash
# Standard roll
uv run python lib/dice.py "1d20+5"

# Advantage (roll 2, keep highest)
uv run python lib/dice.py "2d20kh1+5"

# Disadvantage (roll 2, keep lowest)
uv run python lib/dice.py "2d20kl1+5"

# Multiple dice
uv run python lib/dice.py "3d6"
```

**Roll each check separately** - do NOT batch multiple rolls into one command.

---
