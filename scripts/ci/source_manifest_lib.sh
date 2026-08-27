#!/usr/bin/env bash

# Shared, side-effect-free helpers for source-manifest validation.  Callers
# intentionally decide whether a mismatch is a warning or a hard failure.

source_manifest_value() {
    local manifest=$1 key=$2 value
    value="$(sed -n "s/^${key}:[[:space:]]*//p" "$manifest" | head -1)"
    printf '%s' "${value%"${value##*[![:space:]]}"}"
}

source_manifest_ref_commit() {
    local repo=$1 ref=$2 advertised direct peeled

    # Annotated tags advertise both the tag object and a peeled ^{} commit.
    # Source manifests always pin commits, so prefer the peeled value.  A plain
    # ls-remote query silently returns the tag-object SHA and made valid
    # annotated release tags look mismatched.
    advertised="$(git ls-remote "$repo" "$ref" "${ref}^{}")" || return
    direct="$(awk -v ref="$ref" '$2 == ref {print $1; exit}' <<<"$advertised")"
    peeled="$(awk -v ref="${ref}^{}" '$2 == ref {print $1; exit}' <<<"$advertised")"
    printf '%s\n' "${peeled:-$direct}"
}

source_manifest_tag_identity() {
    local ref=$1

    [[ "$ref" == refs/tags/* ]] || return 1
    printf '%s\n' "${ref#refs/tags/}"
}
