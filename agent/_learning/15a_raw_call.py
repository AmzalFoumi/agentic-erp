"""Gate 15a - a raw call to the Gemini API. No tools, no framework, no loop.

TEACHING ARTIFACT - not the real agent. Kept forever at agent/_learning/, per
docs/AGENT-PLAN.md's Gate 15, and imported by nothing that runs.

### What "deliberately under-abstracted" means here, precisely

The *agent logic* is flat: one file, top to bottom, no helper layer, no
wrapper class, nothing to jump to in order to follow the flow. Read it like a
recipe.

The *infrastructure* is real. Settings come from `agent/config.py` - the same
`BaseSettings` object that `conversation.py`, `store.py` and `app.py` will use
from Gate 17 onward - not from a one-off `os.environ` read. That is the point:
`_learning/` is the same system with fewer layers, not a different system. If
the config mechanism changed after the teaching gate, the loop you learned
would stop being the loop that runs, and this directory's whole value (being
worth re-reading in six months when the framework misbehaves) would go with
it.

So the rule is: **flatten the thinking, not the plumbing.**

### The lesson in this file

One request, one response. A "turn" at its very simplest - before tools exist,
before there is anything to loop over. 15b adds a tool declaration, 15c adds
the MCP client, 15d joins them into the loop.

Run it (from agent/, with the venv active):
    python _learning/15a_raw_call.py
"""

import sys
from pathlib import Path

from google import genai

# agent/ is not an installed package yet - that lands at Gate 17, when there
# are real modules to import between. Until then this script is run directly
# from a subdirectory, so agent/ is not on the import path and `import config`
# would fail. Adding the parent directory by hand is the honest fix for a
# standalone script.
#
# This is scaffolding for the teaching scripts only. Nothing in the real agent
# will need it, because by then agent/ is a package and these two lines are
# replaced by `from agent.config import settings`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings  # noqa: E402  (must follow the sys.path line above)

# Importing `settings` is what validates the key. If GEMINI_API_KEY is missing
# from agent/.env, the process has already died by this line with a pydantic
# error naming the field - not with a 401 from Google three seconds into a
# request. Fail loudly at the boundary; the rest of the file can then assume
# it has a key.
client = genai.Client(api_key=settings.gemini_api_key)

# The simplest possible call: a model name and a string.
#
# `contents` is a string here, which is the SDK being generous - underneath it
# becomes a list of Content objects, each with a role and a list of parts.
# That structure looks like pointless ceremony right up until 15b, where a
# tool-use response arrives as a *part* alongside the text, and 15d, where the
# entire conversation so far is resent as a list of those Contents on every
# single call. Worth knowing the shape is there before you need it.
response = client.models.generate_content(
    model=settings.gemini_model,
    contents="In one sentence, what does a supermarket inventory system do?",
)

# Print the whole response object before reaching for the convenience
# property. `response.text` is what real code uses, but seeing what it is
# shorthand FOR is the entire reason this script exists - note the candidates
# list, the parts inside each one, the finish_reason, and the token counts in
# usage_metadata. Every one of those becomes load-bearing in a later gate.
print("=== the raw response object ===")
print(response)

print()
print("=== response.text (the shortcut real code uses) ===")
print(response.text)
