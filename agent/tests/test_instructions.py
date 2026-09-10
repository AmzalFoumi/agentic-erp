"""Gate 34: the agent is told not to re-type tool list rows the UI already shows."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conversation import INSTRUCTIONS  # noqa: E402


def test_instructions_tell_the_model_not_to_retype_list_rows():
    lowered = INSTRUCTIONS.lower()
    assert "re-type" in lowered or "retype" in lowered or "repeat every" in lowered
    # The point of the line: a one-sentence summary is enough because the
    # interface renders the detail.
    assert "summar" in lowered
