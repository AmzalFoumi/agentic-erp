"""Gate 33: the toolset hands the model structured output when the server sent it.

Before gate 33 `call_tool` did `"\\n".join(block.text ...)` over the *unstructured*
content blocks and dropped `structured_content` entirely - which is why a list
tool arrived at the browser as `}\\n{`-concatenated JSON text instead of an array.
`_tool_output` is that logic, pulled out so it can be tested without a live MCP
server (the same move `tool_kind` made for the approval rule)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp_client import _tool_output  # noqa: E402
from pydantic_ai import ModelRetry  # noqa: E402


class _Block:
    def __init__(self, text):
        self.text = text


class _Result:
    def __init__(self, *, content=(), is_error=False, structured_content=None):
        self.content = list(content)
        self.is_error = is_error
        self.structured_content = structured_content


def test_structured_content_is_returned_verbatim_when_present():
    payload = {"products": [{"sku": "RICE-1KG"}], "total": 1}
    result = _Result(content=[_Block('{"products": [...]}')], structured_content=payload)
    assert _tool_output(result) is payload


def test_falls_back_to_joined_text_when_no_structured_content():
    result = _Result(content=[_Block("line one"), _Block("line two")])
    assert _tool_output(result) == "line one\nline two"


def test_an_error_result_raises_model_retry_with_the_text():
    result = _Result(content=[_Block("no product has that SKU")], is_error=True)
    with pytest.raises(ModelRetry, match="no product has that SKU"):
        _tool_output(result)


def test_an_error_result_with_no_text_still_raises():
    result = _Result(is_error=True)
    with pytest.raises(ModelRetry):
        _tool_output(result)
