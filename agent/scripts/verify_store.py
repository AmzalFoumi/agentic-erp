"""Gate 18's verification: prove conversations/messages actually round-trip
through Postgres, not just through in-memory state within one process.

Two invocations, not one function call: `--write` creates a conversation and
appends messages (one with fake provider_data bytes, to prove that column
round-trips too), printing the conversation id. `--read <id>` is a SEPARATE
process invocation that loads that id back and prints what it found. Running
these as two separate `python` calls - not two functions in one script - is
what makes this a real test of "did Postgres actually keep it", since a bug
that only worked by accident of shared process memory would still pass a
single-process version of this check.

Usage:

    python scripts/verify_store.py --write
        # prints: conversation id: <n>

    python scripts/verify_store.py --read <n>
        # prints each message's role, content, and whether provider_data is set
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conversation import Message  # noqa: E402
from store import append_message, load_history, start_conversation  # noqa: E402


def _write() -> None:
    conversation_id = start_conversation(title="gate 18 verification")
    append_message(conversation_id, Message(role="user", content="hello"))
    append_message(
        conversation_id,
        Message(role="assistant", content="hi there", provider_data=b'{"fake": "signature bytes"}'),
    )
    print(f"conversation id: {conversation_id}")


def _read(conversation_id: int) -> None:
    history = load_history(conversation_id)
    if not history:
        print(f"no messages found for conversation {conversation_id}")
        return
    for message in history:
        has_provider_data = message.provider_data is not None
        print(f"{message.role}: {message.content!r} (provider_data set: {has_provider_data})")


def main() -> None:
    if sys.argv[1:2] == ["--write"]:
        _write()
    elif sys.argv[1:2] == ["--read"] and len(sys.argv) == 3:
        _read(int(sys.argv[2]))
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
