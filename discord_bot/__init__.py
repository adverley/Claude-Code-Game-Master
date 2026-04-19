"""discord_bot package.

Importing this package installs the sys.path entries that commands need to reach
into `lib/` and `.claude/modules/*/lib` (see `_bootstrap`).
"""

from discord_bot import _bootstrap  # noqa: F401 — side effect: installs sys.path
