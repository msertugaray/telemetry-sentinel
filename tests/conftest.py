import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.parser import Fleet  # noqa: E402


@pytest.fixture
def fleet():
    """Testlerdeki varsayılan filo: B1, B2, B3; her otobüste S1, S2, S3."""
    return Fleet(buses=("B1", "B2", "B3"), sensors=("S1", "S2", "S3"))


def make_csv(*rows):
    """('B1', 'S1', '00:00:02', '00:00:09') gibi satırlardan CSV metni üretir."""
    lines = ["otobus,sensor,baslangic,bitis"]
    lines += [",".join(row) for row in rows]
    return "\n".join(lines) + "\n"


def t(seconds):
    """Kısaltma: t(5) -> '00:00:05'."""
    return f"00:00:{seconds:02d}"
