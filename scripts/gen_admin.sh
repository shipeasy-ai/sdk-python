#!/usr/bin/env bash
#
# Regenerate the OPTIONAL Admin API client (`shipeasy.admin.generated`) from the
# vendored OpenAPI spec. The generated client is a raw, 1:1 projection of
# `admin/openapi.json` (id-based, basis-points, snake_case) — no name->id or
# percent->bp ergonomics. The hand-written `shipeasy/admin/__init__.py` /
# `_client.py` shim (the `AdminClient` entry point) sits on top and is NEVER
# touched by this script: only `shipeasy/admin/generated/` is replaced.
#
# Usage:
#   1. Refresh the vendored spec when the contract changes:
#        cp <monorepo>/marketplace/openapi/openapi.json admin/openapi.json
#   2. Regenerate:
#        bash scripts/gen_admin.sh
#   3. Commit `admin/openapi.json` + `shipeasy/admin/generated/`.
#
# Requires Java (for openapi-generator) and npx. The generator version is pinned
# in `openapitools.json` (7.23.0).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SPEC="admin/openapi.json"
PKG="shipeasy.admin.generated"
DEST="shipeasy/admin/generated"
BUILD="$(mktemp -d)"
trap 'rm -rf "$BUILD"' EXIT

if [[ ! -f "$SPEC" ]]; then
  echo "error: missing vendored spec at $SPEC — copy it from the monorepo's marketplace/openapi/openapi.json" >&2
  exit 1
fi

# OpenAPI version-compat shim. The pinned openapi-generator (openapitools.json)
# bundles a swagger-parser that cannot parse OpenAPI >= 3.2 (it NPEs before
# codegen). The canonical admin spec is emitted as 3.2.x, but its *content* is
# 3.1-compatible — only the version label is ahead of the parser. Pin the label
# down to 3.1.0 (byte-preserving: only the version token changes) so the vendored
# spec is consumable. Harmless no-op when the spec is already <= 3.1.
perl -0pi -e 's/("openapi"\s*:\s*")3\.[2-9]\.\d+(")/${1}3.1.0${2}/' "$SPEC"

echo "Generating $PKG from $SPEC ..."
# --skip-validate-spec: the leniently-parsed 3.2-labelled spec trips the strict
# validator (spurious "unexpected"/"missing" errors); the codegen model builder
# handles the 3.1-expressible surface correctly, so skip validation.
npx --yes @openapitools/openapi-generator-cli generate \
  -i "$SPEC" \
  -g python \
  --skip-validate-spec \
  --package-name "$PKG" \
  --additional-properties=library=urllib3,projectName=shipeasy-admin \
  -o "$BUILD" >/dev/null

GENERATED="$BUILD/shipeasy/admin/generated"
if [[ ! -d "$GENERATED" ]]; then
  echo "error: generator did not produce $GENERATED" >&2
  exit 1
fi

# Replace ONLY the generated subpackage. The shim (__init__.py / _client.py) and
# the rest of the `shipeasy` package are left intact.
rm -rf "$DEST"
mkdir -p "$DEST"
cp -R "$GENERATED/." "$DEST/"

echo "Wrote $(find "$DEST" -name '*.py' | wc -l | tr -d ' ') Python files to $DEST"
echo "Done. Review the diff and commit admin/openapi.json + $DEST."
