#!/usr/bin/env bash
# Decide whether (and what) to release. Used by .github/workflows/release.yml.
#
# Inputs (env): GITHUB_EVENT_NAME GITHUB_REF GITHUB_REF_NAME GITHUB_SHA
#               INPUT_TAG (workflow_dispatch only, optional)
# Outputs (to $GITHUB_OUTPUT): release=true|false  tag=vX.Y.Z  ref=<sha-or-tag>
#
#  - tag push                 -> release that tag
#  - push to main             -> release v<VERSION> unless that tag already exists
#  - workflow_dispatch        -> release INPUT_TAG (default v<VERSION>); re-runs allowed
set -euo pipefail

VERSION=$(grep -Po '^VERSION\s*=\s*"\K[^"]+' sven/constants.py)
OUT="${GITHUB_OUTPUT:-/dev/stdout}"

tag_exists() { git ls-remote --exit-code --tags origin "refs/tags/$1" >/dev/null 2>&1; }

RELEASE=true
REF="$GITHUB_SHA"

case "$GITHUB_EVENT_NAME" in
  push)
    if [[ "$GITHUB_REF" == refs/tags/* ]]; then
      TAG="$GITHUB_REF_NAME"
    else
      TAG="v$VERSION"
      if tag_exists "$TAG"; then
        echo "::notice::$TAG already released; nothing to do (bump VERSION in sven/constants.py to release)"
        RELEASE=false
      fi
    fi
    ;;
  workflow_dispatch)
    TAG="${INPUT_TAG:-v$VERSION}"
    if tag_exists "$TAG"; then REF="$TAG"; fi   # rebuild exactly what was tagged
    ;;
  *)
    echo "::error::unsupported event $GITHUB_EVENT_NAME"; exit 1 ;;
esac

if ! [[ "$TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.]+)?$ ]]; then
  echo "::error::'$TAG' is not a valid release tag (expected vX.Y.Z)"; exit 1
fi

echo "plan: release=$RELEASE tag=$TAG ref=$REF"
{ echo "release=$RELEASE"; echo "tag=$TAG"; echo "ref=$REF"; } >> "$OUT"
