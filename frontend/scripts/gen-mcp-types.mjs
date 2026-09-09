// Generates src/lib/api/mcp-types.d.ts from src/lib/api/mcp-schema.json.
//
// Why a script and not the `json2ts` CLI: json-schema-to-typescript v16's CLI
// forwards `--style.singleQuote false` to Prettier as the string "false", which
// Prettier rejects. Calling compileFromFile directly passes real booleans and is
// stable across versions. Run via `npm run mcp:types`; do not hand-edit the output.
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { compile } from "json-schema-to-typescript";

const here = dirname(fileURLToPath(import.meta.url));
const input = resolve(here, "../src/lib/api/mcp-schema.json");
const output = resolve(here, "../src/lib/api/mcp-types.d.ts");

const schema = JSON.parse(readFileSync(input, "utf8"));

// Drop the per-property `title` fields Pydantic emits ("Cost Price", "Id", ...).
// json-schema-to-typescript turns every one of those into a standalone exported
// alias, which buries the real interfaces. Titles that name a model (the `$defs`
// entries and the root) are kept so the interfaces stay named.
function stripPropertyTitles(node) {
  if (!node || typeof node !== "object") return;
  if (node.properties && typeof node.properties === "object") {
    for (const prop of Object.values(node.properties)) {
      if (prop && typeof prop === "object") delete prop.title;
    }
  }
  for (const value of Object.values(node)) {
    if (Array.isArray(value)) value.forEach(stripPropertyTitles);
    else if (value && typeof value === "object") stripPropertyTitles(value);
  }
}
stripPropertyTitles(schema);

const ts = await compile(schema, "MCPToolOutputs", {
  additionalProperties: false,
  style: { singleQuote: false },
  bannerComment:
    "/**\n * This file was automatically generated from src/lib/api/mcp-schema.json.\n * DO NOT MODIFY IT BY HAND. Instead, run `npm run mcp:types` to regenerate this file.\n */",
});

writeFileSync(output, ts);
