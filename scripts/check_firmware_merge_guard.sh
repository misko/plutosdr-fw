#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C

readonly DENYLIST_PATH=.github/experimental-firmware-lineages.txt
readonly GITLINK_DENYLIST_PATH=.github/experimental-firmware-gitlinks.txt
readonly MAX_PR_COMMITS=256
readonly -a PROTECTED_POLICY_PATHS=(
  .github/CODEOWNERS
  .github/experimental-firmware-gitlinks.txt
  .github/experimental-firmware-lineages.txt
  .github/workflows/experimental-firmware-merge-guard.yml
  scripts/check_firmware_merge_guard.sh
  scripts/test_firmware_merge_guard.sh
)

fail() {
  printf 'FAIL experimental firmware merge guard: %s\n' "$*" >&2
  exit 1
}

usage() {
  fail 'usage: check_firmware_merge_guard.sh HEAD_REF ABSOLUTE_REPOSITORY BASE_SHA HEAD_SHA'
}

[[ $# == 4 ]] || usage
head_ref=$1
repository=$2
base_sha=$3
head_sha=$4

[[ "$repository" == /* ]] || fail 'repository path must be absolute'
[[ -e "$repository/.git" ]] || fail 'repository path is not a Git worktree'
repository=$(cd -- "$repository" && pwd -P)

git_repo() {
  git --no-replace-objects -c core.hooksPath=/dev/null -C "$repository" "$@"
}

validate_commit() {
  local label=$1
  local oid=$2
  local resolved
  [[ "$oid" =~ ^[0-9a-f]{40}$ ]] || fail "$label is not one lowercase full commit ID"
  resolved=$(git_repo rev-parse --verify "$oid^{commit}" 2>/dev/null) ||
    fail "$label commit is unavailable"
  [[ "$resolved" == "$oid" ]] || fail "$label does not resolve to the exact commit"
}

contains_experimental_token() {
  local value=${1,,}
  [[ "$value" =~ do[^[:alnum:]]+not[^[:alnum:]]+merge ||
     "$value" =~ (^|[^[:alnum:]])dnm([^[:alnum:]]|$) ]]
}

is_protected_policy_path() {
  local candidate=$1
  local protected
  for protected in "${PROTECTED_POLICY_PATHS[@]}"; do
    [[ "$candidate" == "$protected" ]] && return 0
  done
  return 1
}

git check-ref-format "refs/heads/$head_ref" >/dev/null 2>&1 ||
  fail 'pull-request head ref is not a valid branch ref'
validate_commit 'base SHA' "$base_sha"
validate_commit 'head SHA' "$head_sha"

merge_base=$(git_repo merge-base "$base_sha" "$head_sha" 2>/dev/null) ||
  fail 'base and head do not have a common ancestor'
validate_commit 'merge-base SHA' "$merge_base"

if contains_experimental_token "$head_ref"; then
  fail "experimental branch name is forbidden: $head_ref"
fi

commit_count=$(git_repo rev-list --count "$merge_base..$head_sha") ||
  fail 'cannot enumerate pull-request commits'
[[ "$commit_count" =~ ^[0-9]+$ ]] || fail 'pull-request commit count is malformed'
(( commit_count <= MAX_PR_COMMITS )) ||
  fail "pull request exceeds the ${MAX_PR_COMMITS}-commit inspection bound"

scratch=$(mktemp -d)
trap 'rm -rf -- "$scratch"' EXIT

read_base_policy_blob() {
  local policy_path=$1
  local destination=$2
  local description=$3
  local policy_entry
  policy_entry=$(git_repo ls-tree "$base_sha" -- "$policy_path") ||
    fail "cannot inspect the base-owned $description"
  [[ "$policy_entry" =~ ^100644[[:space:]]blob[[:space:]][0-9a-f]{40}[[:space:]] ]] ||
    fail "base-owned $description is absent or not one regular non-executable blob"
  git_repo show "$base_sha:$policy_path" >"$destination" ||
    fail "cannot read the base-owned $description"
}

denylist=$scratch/denylist
read_base_policy_blob "$DENYLIST_PATH" "$denylist" 'lineage denylist'

gitlink_denylist=$scratch/gitlink-denylist
read_base_policy_blob "$GITLINK_DENYLIST_PATH" "$gitlink_denylist" \
  'gitlink denylist'

declare -A denied_gitlink_oids=()
gitlink_count=0
while IFS= read -r line || [[ -n "$line" ]]; do
  [[ -z "$line" || "$line" == \#* ]] && continue
  if [[ ! "$line" =~ ^([^[:space:]]+)[[:space:]]+([0-9a-f]{40})[[:space:]]+([a-z0-9][a-z0-9._-]*)$ ]]; then
    fail 'base-owned gitlink denylist has a malformed entry'
  fi
  gitlink_path=${BASH_REMATCH[1]}
  gitlink_oid=${BASH_REMATCH[2]}
  gitlink_name=${BASH_REMATCH[3]}
  [[ "$gitlink_path" != /* && "$gitlink_path" != */ &&
     "$gitlink_path" != . && "$gitlink_path" != .. &&
     "$gitlink_path" != ./* && "$gitlink_path" != */./* &&
     "$gitlink_path" != */. && "$gitlink_path" != ../* &&
     "$gitlink_path" != */../* && "$gitlink_path" != */.. &&
     "$gitlink_path" != *//* ]] ||
    fail "gitlink denylist entry $gitlink_name has an unsafe path"
  [[ "$gitlink_path" =~ ^[a-zA-Z0-9._/-]+$ ]] ||
    fail "gitlink denylist entry $gitlink_name has an unsafe path"
  [[ -z ${denied_gitlink_oids[$gitlink_oid]+present} ]] ||
    fail "base-owned gitlink denylist repeats $gitlink_oid"
  denied_gitlink_oids[$gitlink_oid]="$gitlink_name (listed at $gitlink_path)"
  ((gitlink_count += 1))
done <"$gitlink_denylist"
(( gitlink_count > 0 )) || fail 'base-owned gitlink denylist is empty'

changed_paths=$scratch/changed-paths
git_repo diff --no-renames --name-only -z "$merge_base" "$head_sha" -- >"$changed_paths" ||
  fail 'cannot enumerate pull-request paths'
while IFS= read -r -d '' path; do
  if is_protected_policy_path "$path"; then
    fail "pull request changes protected base policy: $path"
  fi
done <"$changed_paths"

manifest_type=$(git_repo cat-file -t "$head_sha:manifests" 2>/dev/null) ||
  fail 'candidate tree has no manifests directory'
[[ "$manifest_type" == tree ]] || fail 'candidate manifests path is not a Git tree'

final_paths=$scratch/final-paths
git_repo ls-tree -r -z --name-only "$head_sha" >"$final_paths" ||
  fail 'cannot enumerate candidate tree'
while IFS= read -r -d '' path; do
  if contains_experimental_token "$path"; then
    fail "candidate tree contains experimental path: $path"
  fi
done <"$final_paths"

history_paths=$scratch/history-paths
git_repo log --format= --name-only -z --root --no-renames --diff-merges=separate \
  "$merge_base..$head_sha" -- >"$history_paths" ||
  fail 'cannot enumerate pull-request path history'
while IFS= read -r -d '' path; do
  [[ -z "$path" ]] && continue
  if is_protected_policy_path "$path"; then
    fail "pull-request history changes protected base policy: $path"
  fi
  if contains_experimental_token "$path"; then
    fail "pull-request history contains experimental path: $path"
  fi
done <"$history_paths"

readonly CONTENT_PATTERN='do[^[:alnum:][:space:]]+not[^[:alnum:][:space:]]+merge|(^|[^[:alnum:]])dnm([^[:alnum:]]|$)|do[ _.-]+not[ _.-]+merge([ _.-]+into[ _.-]+firmware[ _.-]+main|[ _.-]+or[ _.-]+deploy|,[[:space:]]+release)'
content_pathspecs=(.)
for protected_path in "${PROTECTED_POLICY_PATHS[@]}"; do
  content_pathspecs+=(":(exclude)$protected_path")
done

scan_content_at_commit() {
  local commit=$1
  local output="$scratch/content-$commit"
  local grep_status
  local match
  set +e
  git_repo grep -a -i -l -z -E "$CONTENT_PATTERN" \
    "$commit" -- "${content_pathspecs[@]}" >"$output"
  grep_status=$?
  set -e
  if (( grep_status == 0 )); then
    IFS= read -r -d '' match <"$output" || true
    fail "candidate history commit $commit contains an experimental content marker: ${match:-unknown path}"
  elif (( grep_status != 1 )); then
    fail "cannot scan content markers at candidate history commit $commit"
  fi
}

scan_gitlinks_at_commit() {
  local commit=$1
  local output="$scratch/gitlinks-$commit"
  local entry
  local metadata
  local path
  local mode
  local object_type
  local oid
  git_repo ls-tree -r -z "$commit" >"$output" ||
    fail "cannot inspect guarded gitlinks at candidate history commit $commit"
  while IFS= read -r -d '' entry; do
    [[ "$entry" == *$'\t'* ]] ||
      fail "candidate history commit $commit has a malformed tree entry"
    metadata=${entry%%$'\t'*}
    path=${entry#*$'\t'}
    read -r mode object_type oid extra <<<"$metadata"
    [[ -z ${extra:-} && "$mode" =~ ^[0-7]{6}$ &&
       "$object_type" =~ ^[a-z]+$ && "$oid" =~ ^[0-9a-f]{40}$ ]] ||
      fail "candidate history commit $commit has a malformed tree entry for $path"
    [[ "$mode" == 160000 && "$object_type" == commit ]] || continue
    if [[ -n ${denied_gitlink_oids[$oid]+present} ]]; then
      fail "candidate history commit $commit selects denied experimental gitlink ${denied_gitlink_oids[$oid]} at $path ($oid)"
    fi
  done <"$output"
}

history_commits=$scratch/history-commits
git_repo rev-list --reverse "$merge_base..$head_sha" >"$history_commits" ||
  fail 'cannot enumerate pull-request commit history'
if (( commit_count == 0 )); then
  printf '%s\n' "$head_sha" >"$history_commits"
fi
while IFS= read -r commit; do
  [[ "$commit" =~ ^[0-9a-f]{40}$ ]] || fail 'candidate history contains a malformed commit ID'
  scan_content_at_commit "$commit"
  scan_gitlinks_at_commit "$commit"
done <"$history_commits"

declare -A seen_lineages=()
lineage_count=0
while IFS= read -r line || [[ -n "$line" ]]; do
  [[ -z "$line" || "$line" == \#* ]] && continue
  if [[ ! "$line" =~ ^([0-9a-f]{40})[[:space:]]+([^[:space:]]+)[[:space:]]+([a-z0-9][a-z0-9._-]*)$ ]]; then
    fail 'base-owned lineage denylist has a malformed entry'
  fi
  lineage_oid=${BASH_REMATCH[1]}
  lineage_ref=${BASH_REMATCH[2]}
  lineage_name=${BASH_REMATCH[3]}
  [[ "$lineage_ref" == refs/heads/* || "$lineage_ref" == refs/tags/* ]] ||
    fail "denylisted lineage $lineage_name does not use a trusted heads/tags ref"
  git check-ref-format "$lineage_ref" >/dev/null 2>&1 ||
    fail "denylisted lineage $lineage_name has an invalid source ref"
  [[ -z ${seen_lineages[$lineage_oid]+present} ]] ||
    fail "base-owned lineage denylist repeats $lineage_oid"
  seen_lineages[$lineage_oid]=$lineage_name
  ((lineage_count += 1))
  fetched_ref="refs/remotes/experimental-guard/lineage-$lineage_count"
  git_repo fetch --no-tags --force origin "+$lineage_ref:$fetched_ref" >/dev/null 2>&1 ||
    fail "cannot fetch trusted source ref for lineage $lineage_name"
  validate_commit "denylisted lineage $lineage_name" "$lineage_oid"
  fetched_tip=$(git_repo rev-parse --verify "$fetched_ref^{commit}" 2>/dev/null) ||
    fail "trusted source ref for lineage $lineage_name is not a commit"
  if git_repo merge-base --is-ancestor "$lineage_oid" "$fetched_tip"; then
    :
  else
    ancestry_status=$?
    (( ancestry_status == 1 )) || fail "cannot verify source ref for lineage $lineage_name"
    fail "trusted source ref no longer retains lineage root $lineage_name"
  fi
  if git_repo merge-base --is-ancestor "$lineage_oid" "$base_sha"; then
    fail "denylisted lineage $lineage_name is already an ancestor of protected base"
  else
    ancestry_status=$?
    (( ancestry_status == 1 )) || fail "cannot compare base to lineage $lineage_name"
  fi
  if git_repo merge-base --is-ancestor "$lineage_oid" "$head_sha"; then
    fail "pull request descends from denied experimental lineage: $lineage_name"
  else
    ancestry_status=$?
    (( ancestry_status == 1 )) || fail "cannot compare head to lineage $lineage_name"
  fi
done <"$denylist"
(( lineage_count > 0 )) || fail 'base-owned lineage denylist is empty'

printf 'PASS firmware-main merge guard for %s (%s..%s)\n' \
  "$head_ref" "$merge_base" "$head_sha"
