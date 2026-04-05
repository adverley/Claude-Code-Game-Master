import sys
from pathlib import Path

# Add project root to import path so 'discord_bot' package is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
