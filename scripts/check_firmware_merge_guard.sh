#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C

readonly LINEAGE_DENYLIST_PATH=.github/experimental-firmware-lineages.txt
readonly GITLINK_DENYLIST_PATH=.github/experimental-firmware-gitlinks.txt
readonly MAX_PR_COMMITS=256
readonly MAX_POLICY_BYTES=32768
readonly MAX_POLICY_LINE_BYTES=512
readonly MAX_LINEAGE_ENTRIES=32
readonly MAX_GITLINK_ENTRIES=256
readonly -a IMMUTABLE_POLICY_PATHS=(
  .github/CODEOWNERS
  .github/workflows/experimental-firmware-merge-guard.yml
  scripts/check_firmware_merge_guard.sh
  scripts/test_firmware_merge_guard.sh
)
readonly -a APPEND_ONLY_POLICY_PATHS=(
  .github/experimental-firmware-gitlinks.txt
  .github/experimental-firmware-lineages.txt
)
readonly -a ALL_POLICY_PATHS=(
  "${IMMUTABLE_POLICY_PATHS[@]}"
  "${APPEND_ONLY_POLICY_PATHS[@]}"
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

is_immutable_policy_path() {
  local candidate=$1
  local protected
  for protected in "${IMMUTABLE_POLICY_PATHS[@]}"; do
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

# Sets POLICY_PRESENT, POLICY_OID, and POLICY_SIZE. Candidate-controlled objects
# are never checked out or executed; only exact Git tree/blob objects are read.
inspect_policy_blob() {
  local commit=$1
  local policy_path=$2
  local description=$3
  local required=$4
  local entry
  local metadata
  local entry_path
  local mode
  local object_type
  local oid
  local size
  local extra

  POLICY_PRESENT=false
  POLICY_OID=
  POLICY_SIZE=0
  entry=$(git_repo ls-tree "$commit" -- "$policy_path") ||
    fail "cannot inspect $description"
  if [[ -z "$entry" ]]; then
    [[ "$required" == false ]] || fail "$description is absent"
    return 0
  fi
  [[ "$entry" == *$'\t'* ]] || fail "$description has a malformed tree entry"
  metadata=${entry%%$'\t'*}
  entry_path=${entry#*$'\t'}
  read -r mode object_type oid extra <<<"$metadata"
  [[ "$entry_path" == "$policy_path" && -z ${extra:-} &&
     "$mode" == 100644 && "$object_type" == blob &&
     "$oid" =~ ^[0-9a-f]{40}$ ]] ||
    fail "$description is not one regular non-executable 100644 blob"
  size=$(git_repo cat-file -s "$oid" 2>/dev/null) ||
    fail "cannot size $description"
  [[ "$size" =~ ^[0-9]+$ ]] || fail "$description has a malformed blob size"
  (( size <= MAX_POLICY_BYTES )) ||
    fail "$description exceeds the ${MAX_POLICY_BYTES}-byte bound"
  POLICY_PRESENT=true
  POLICY_OID=$oid
  POLICY_SIZE=$size
}

materialize_policy_blob() {
  local oid=$1
  local expected_size=$2
  local destination=$3
  local description=$4
  local actual_size
  local last_byte

  git_repo cat-file blob "$oid" >"$destination" || fail "cannot read $description"
  actual_size=$(stat -c %s -- "$destination") || fail "cannot size materialized $description"
  [[ "$actual_size" =~ ^[0-9]+$ && "$actual_size" == "$expected_size" ]] ||
    fail "$description changed size while being read"
  (( actual_size > 0 )) || fail "$description is empty"
  last_byte=$(tail -c 1 -- "$destination" | od -An -tu1 | tr -d '[:space:]')
  [[ "$last_byte" == 10 ]] || fail "$description does not end with one complete line"
  if grep -a -q $'[^[:print:]\t]' -- "$destination"; then
    fail "$description contains a non-text or control byte"
  fi
}

require_exact_prefix() {
  local prefix=$1
  local candidate=$2
  local description=$3
  local prefix_size
  local candidate_size

  prefix_size=$(stat -c %s -- "$prefix") || fail "cannot size base $description"
  candidate_size=$(stat -c %s -- "$candidate") || fail "cannot size candidate $description"
  (( candidate_size >= prefix_size )) ||
    fail "$description removes or truncates protected base bytes"
  if (( prefix_size > 0 )) && ! cmp -s -n "$prefix_size" -- "$prefix" "$candidate"; then
    fail "$description does not preserve the exact base-byte prefix"
  fi
}

# Sets VALIDATED_ENTRY_COUNT. With populate=true, also fills the effective
# candidate gitlink map used for this same pull request.
validate_gitlink_policy() {
  local input=$1
  local description=$2
  local populate=$3
  local line
  local line_number=0
  local entry_count=0
  local gitlink_path
  local gitlink_oid
  local gitlink_name
  local -A seen_oids=()
  local -A seen_names=()

  while IFS= read -r line || [[ -n "$line" ]]; do
    ((line_number += 1))
    (( ${#line} <= MAX_POLICY_LINE_BYTES )) ||
      fail "$description line $line_number exceeds the ${MAX_POLICY_LINE_BYTES}-byte bound"
    [[ -z "$line" || "$line" == \#* ]] && continue
    if [[ ! "$line" =~ ^([^[:space:]]+)[[:space:]]+([0-9a-f]{40})[[:space:]]+([a-z0-9][a-z0-9._-]*)$ ]]; then
      fail "$description has a malformed entry on line $line_number"
    fi
    gitlink_path=${BASH_REMATCH[1]}
    gitlink_oid=${BASH_REMATCH[2]}
    gitlink_name=${BASH_REMATCH[3]}
    [[ "$gitlink_path" != /* && "$gitlink_path" != */ &&
       "$gitlink_path" != . && "$gitlink_path" != .. &&
       "$gitlink_path" != ./* && "$gitlink_path" != */./* &&
       "$gitlink_path" != */. && "$gitlink_path" != ../* &&
       "$gitlink_path" != */../* && "$gitlink_path" != */.. &&
       "$gitlink_path" != *//* &&
       "$gitlink_path" =~ ^[a-zA-Z0-9._/-]+$ ]] ||
      fail "$description entry $gitlink_name has an unsafe path"
    [[ -z ${seen_oids[$gitlink_oid]+present} ]] ||
      fail "$description repeats gitlink object $gitlink_oid"
    [[ -z ${seen_names[$gitlink_name]+present} ]] ||
      fail "$description repeats stable label $gitlink_name"
    seen_oids[$gitlink_oid]=$gitlink_name
    seen_names[$gitlink_name]=$gitlink_oid
    ((entry_count += 1))
    (( entry_count <= MAX_GITLINK_ENTRIES )) ||
      fail "$description exceeds the ${MAX_GITLINK_ENTRIES}-entry bound"
    if [[ "$populate" == true ]]; then
      denied_gitlink_oids[$gitlink_oid]="$gitlink_name (listed at $gitlink_path)"
    fi
  done <"$input"
  (( entry_count > 0 )) || fail "$description has no entries"
  VALIDATED_ENTRY_COUNT=$entry_count
}

# Sets VALIDATED_ENTRY_COUNT. With populate=true, fills the effective candidate
# lineage arrays used for this same pull request.
validate_lineage_policy() {
  local input=$1
  local description=$2
  local populate=$3
  local line
  local line_number=0
  local entry_count=0
  local lineage_oid
  local lineage_ref
  local lineage_name
  local -A seen_oids=()
  local -A seen_names=()

  while IFS= read -r line || [[ -n "$line" ]]; do
    ((line_number += 1))
    (( ${#line} <= MAX_POLICY_LINE_BYTES )) ||
      fail "$description line $line_number exceeds the ${MAX_POLICY_LINE_BYTES}-byte bound"
    [[ -z "$line" || "$line" == \#* ]] && continue
    if [[ ! "$line" =~ ^([0-9a-f]{40})[[:space:]]+([^[:space:]]+)[[:space:]]+([a-z0-9][a-z0-9._-]*)$ ]]; then
      fail "$description has a malformed entry on line $line_number"
    fi
    lineage_oid=${BASH_REMATCH[1]}
    lineage_ref=${BASH_REMATCH[2]}
    lineage_name=${BASH_REMATCH[3]}
    [[ "$lineage_ref" == refs/heads/* || "$lineage_ref" == refs/tags/* ]] ||
      fail "$description entry $lineage_name does not use a trusted heads/tags ref"
    git check-ref-format "$lineage_ref" >/dev/null 2>&1 ||
      fail "$description entry $lineage_name has an invalid source ref"
    [[ -z ${seen_oids[$lineage_oid]+present} ]] ||
      fail "$description repeats lineage object $lineage_oid"
    [[ -z ${seen_names[$lineage_name]+present} ]] ||
      fail "$description repeats stable label $lineage_name"
    seen_oids[$lineage_oid]=$lineage_name
    seen_names[$lineage_name]=$lineage_oid
    ((entry_count += 1))
    (( entry_count <= MAX_LINEAGE_ENTRIES )) ||
      fail "$description exceeds the ${MAX_LINEAGE_ENTRIES}-entry bound"
    if [[ "$populate" == true ]]; then
      lineage_oids+=("$lineage_oid")
      lineage_refs+=("$lineage_ref")
      lineage_names+=("$lineage_name")
    fi
  done <"$input"
  (( entry_count > 0 )) || fail "$description has no entries"
  VALIDATED_ENTRY_COUNT=$entry_count
}

validate_policy_syntax() {
  local policy_path=$1
  local input=$2
  local description=$3
  local populate=$4
  case "$policy_path" in
    "$GITLINK_DENYLIST_PATH")
      validate_gitlink_policy "$input" "$description" "$populate"
      ;;
    "$LINEAGE_DENYLIST_PATH")
      validate_lineage_policy "$input" "$description" "$populate"
      ;;
    *)
      fail "internal error: unknown append-only policy path $policy_path"
      ;;
  esac
}

declare -A denied_gitlink_oids=()
declare -a lineage_oids=()
declare -a lineage_refs=()
declare -a lineage_names=()
declare -a base_policy_files=()
declare -a base_policy_counts=()

for policy_index in "${!APPEND_ONLY_POLICY_PATHS[@]}"; do
  policy_path=${APPEND_ONLY_POLICY_PATHS[$policy_index]}
  policy_label="append-only policy $policy_path"
  base_policy_file="$scratch/base-policy-$policy_index"
  candidate_policy_file="$scratch/candidate-policy-$policy_index"

  inspect_policy_blob "$base_sha" "$policy_path" "base $policy_label" true
  base_policy_oid=$POLICY_OID
  base_policy_size=$POLICY_SIZE
  materialize_policy_blob "$base_policy_oid" "$base_policy_size" \
    "$base_policy_file" "base $policy_label"

  inspect_policy_blob "$head_sha" "$policy_path" "candidate $policy_label" true
  candidate_policy_oid=$POLICY_OID
  candidate_policy_size=$POLICY_SIZE
  materialize_policy_blob "$candidate_policy_oid" "$candidate_policy_size" \
    "$candidate_policy_file" "candidate $policy_label"

  require_exact_prefix "$base_policy_file" "$candidate_policy_file" "$policy_label"
  validate_policy_syntax "$policy_path" "$base_policy_file" "base $policy_label" false
  base_policy_count=$VALIDATED_ENTRY_COUNT
  validate_policy_syntax "$policy_path" "$candidate_policy_file" \
    "candidate $policy_label" true
  candidate_policy_count=$VALIDATED_ENTRY_COUNT
  if (( candidate_policy_size > base_policy_size )); then
    (( candidate_policy_count > base_policy_count )) ||
      fail "$policy_label appends bytes without adding a validated entry"
  else
    (( candidate_policy_count == base_policy_count )) ||
      fail "$policy_label entry count changed without a byte extension"
  fi

  base_policy_files[$policy_index]=$base_policy_file
  base_policy_counts[$policy_index]=$base_policy_count
done

history_commits=$scratch/history-commits
git_repo rev-list --reverse "$merge_base..$head_sha" >"$history_commits" ||
  fail 'cannot enumerate pull-request commit history'
if (( commit_count == 0 )); then
  printf '%s\n' "$head_sha" >"$history_commits"
fi

validate_append_only_history() {
  local commit=$1
  local ancestry
  local -a commit_and_parents
  local -a parents
  local policy_index
  local policy_path
  local child_present
  local child_oid
  local child_size
  local child_file
  local child_count
  local child_validated
  local parent
  local parent_present
  local parent_oid
  local parent_size
  local parent_file
  local parent_count

  ancestry=$(git_repo rev-list --parents -n 1 "$commit") ||
    fail "cannot enumerate parents for candidate history commit $commit"
  read -r -a commit_and_parents <<<"$ancestry"
  [[ ${commit_and_parents[0]:-} == "$commit" ]] ||
    fail "candidate history commit $commit has malformed parent metadata"
  parents=("${commit_and_parents[@]:1}")

  for policy_index in "${!APPEND_ONLY_POLICY_PATHS[@]}"; do
    policy_path=${APPEND_ONLY_POLICY_PATHS[$policy_index]}
    inspect_policy_blob "$commit" "$policy_path" \
      "append-only policy $policy_path at candidate history commit $commit" false
    child_present=$POLICY_PRESENT
    child_oid=$POLICY_OID
    child_size=$POLICY_SIZE
    child_file="$scratch/history-$commit-$policy_index-child"
    child_validated=false

    if (( ${#parents[@]} == 0 )); then
      [[ "$child_present" == true ]] || continue
      materialize_policy_blob "$child_oid" "$child_size" "$child_file" \
        "append-only policy $policy_path at candidate root commit $commit"
      validate_policy_syntax "$policy_path" "$child_file" \
        "append-only policy $policy_path at candidate root commit $commit" false
      child_count=$VALIDATED_ENTRY_COUNT
      require_exact_prefix "${base_policy_files[$policy_index]}" "$child_file" \
        "append-only policy $policy_path at candidate root commit $commit"
      (( child_count > base_policy_counts[$policy_index] )) ||
        fail "append-only policy $policy_path at candidate root commit $commit does not extend the protected base list"
      continue
    fi

    for parent in "${parents[@]}"; do
      [[ "$parent" =~ ^[0-9a-f]{40}$ ]] ||
        fail "candidate history commit $commit has a malformed parent ID"
      inspect_policy_blob "$parent" "$policy_path" \
        "append-only policy $policy_path at parent $parent" false
      parent_present=$POLICY_PRESENT
      parent_oid=$POLICY_OID
      parent_size=$POLICY_SIZE
      if [[ "$child_present" == "$parent_present" &&
            "$child_present" == false ]]; then
        continue
      fi
      if [[ "$child_present" == true && "$parent_present" == true &&
            "$child_oid" == "$parent_oid" ]]; then
        continue
      fi
      [[ "$child_present" == true ]] ||
        fail "append-only policy $policy_path is removed at candidate history commit $commit"

      if [[ "$child_validated" == false ]]; then
        materialize_policy_blob "$child_oid" "$child_size" "$child_file" \
          "append-only policy $policy_path at candidate history commit $commit"
        validate_policy_syntax "$policy_path" "$child_file" \
          "append-only policy $policy_path at candidate history commit $commit" false
        child_count=$VALIDATED_ENTRY_COUNT
        child_validated=true
      fi

      if [[ "$parent_present" == true ]]; then
        parent_file="$scratch/history-$commit-$policy_index-parent-$parent"
        materialize_policy_blob "$parent_oid" "$parent_size" "$parent_file" \
          "append-only policy $policy_path at parent $parent"
        validate_policy_syntax "$policy_path" "$parent_file" \
          "append-only policy $policy_path at parent $parent" false
        parent_count=$VALIDATED_ENTRY_COUNT
        require_exact_prefix "$parent_file" "$child_file" \
          "append-only policy $policy_path at candidate history commit $commit"
      else
        parent_count=0
      fi
      (( child_count > parent_count )) ||
        fail "append-only policy $policy_path at candidate history commit $commit changes bytes without appending an entry"
    done
  done
}

while IFS= read -r commit; do
  [[ "$commit" =~ ^[0-9a-f]{40}$ ]] ||
    fail 'candidate history contains a malformed commit ID'
  validate_append_only_history "$commit"
done <"$history_commits"

changed_paths=$scratch/changed-paths
git_repo diff --no-renames --name-only -z "$merge_base" "$head_sha" -- >"$changed_paths" ||
  fail 'cannot enumerate pull-request paths'
while IFS= read -r -d '' path; do
  if is_immutable_policy_path "$path"; then
    fail "pull request changes immutable base policy: $path"
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
  if is_immutable_policy_path "$path"; then
    fail "pull-request history changes immutable base policy: $path"
  fi
  if contains_experimental_token "$path"; then
    fail "pull-request history contains experimental path: $path"
  fi
done <"$history_paths"

readonly CONTENT_PATTERN='do[^[:alnum:][:space:]]+not[^[:alnum:][:space:]]+merge|(^|[^[:alnum:]])dnm([^[:alnum:]]|$)|do[ _.-]+not[ _.-]+merge([ _.-]+into[ _.-]+firmware[ _.-]+main|[ _.-]+or[ _.-]+deploy|,[[:space:]]+release)'
content_pathspecs=(.)
for protected_path in "${ALL_POLICY_PATHS[@]}"; do
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
  local extra
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

while IFS= read -r commit; do
  scan_content_at_commit "$commit"
  scan_gitlinks_at_commit "$commit"
done <"$history_commits"

for lineage_index in "${!lineage_oids[@]}"; do
  lineage_oid=${lineage_oids[$lineage_index]}
  lineage_ref=${lineage_refs[$lineage_index]}
  lineage_name=${lineage_names[$lineage_index]}
  fetched_ref="refs/remotes/experimental-guard/lineage-$((lineage_index + 1))"
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
done

printf 'PASS firmware-main merge guard for %s (%s..%s)\n' \
  "$head_ref" "$merge_base" "$head_sha"
