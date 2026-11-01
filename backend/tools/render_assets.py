"""Pre-render static image assets (onboarding infographic RU/UZ) into assets/.

    python tools/render_assets.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chat_helper.media.infographic import save_assets  # noqa: E402

if __name__ == "__main__":
    for p in save_assets():
        print(p, p.stat().st_size, "bytes")
