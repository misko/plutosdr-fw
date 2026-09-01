#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
guard="$script_dir/check_firmware_merge_guard.sh"
fixture=$(mktemp -d)
trap 'rm -rf -- "$fixture"' EXIT
repository="$fixture/repository"
mkdir -p "$repository"
git -C "$repository" init -q -b main
git -C "$repository" config user.name 'merge guard fixture'
git -C "$repository" config user.email 'merge-guard-fixture@example.invalid'

git_commit() {
  local message=$1
  git -C "$repository" add -A
  if [[ -n ${fixture_component_oid:-} ]]; then
    git -C "$repository" update-index --add --cacheinfo \
      "160000,$fixture_component_oid,component"
  fi
  git -C "$repository" commit -q -m "$message"
  git -C "$repository" rev-parse HEAD
}

new_candidate_from() {
  local starting_point=$1
  candidate_number=$((candidate_number + 1))
  git -C "$repository" switch -q --detach "$starting_point"
  git -C "$repository" switch -q -c "fixture-$candidate_number"
}

new_candidate() {
  new_candidate_from "$base_sha"
}

expect_pass() {
  local label=$1
  local ref=$2
  local base=$3
  local head=$4
  if ! "$guard" "$ref" "$repository" "$base" "$head" >"$fixture/output" 2>&1; then
    printf 'expected PASS for %s:\n' "$label" >&2
    sed -n '1,20p' "$fixture/output" >&2
    exit 1
  fi
}

expect_reject() {
  local label=$1
  local expected=$2
  local ref=$3
  local base=$4
  local head=$5
  if "$guard" "$ref" "$repository" "$base" "$head" >"$fixture/output" 2>&1; then
    printf 'guard accepted forbidden fixture: %s\n' "$label" >&2
    exit 1
  fi
  if ! grep -Fq -- "$expected" "$fixture/output"; then
    printf 'guard rejected %s for the wrong reason; expected %s:\n' \
      "$label" "$expected" >&2
    sed -n '1,20p' "$fixture/output" >&2
    exit 1
  fi
}

mkdir -p "$repository/manifests" "$repository/rtl"
printf 'schema: ordinary\n' >"$repository/manifests/ordinary-source.yaml"
printf 'module ordinary; endmodule\n' >"$repository/rtl/ordinary.v"
seed_sha=$(git_commit 'fixture seed')

git -C "$repository" switch -q -c known-experimental-lineage
printf 'module known_experiment; endmodule\n' >"$repository/rtl/known-experiment.v"
denied_sha=$(git_commit 'known experimental lineage root')
printf 'module known_experiment_v2; endmodule\n' \
  >"$repository/rtl/known-experiment-v2.v"
second_denied_sha=$(git_commit 'second known experimental component pin')
git -C "$repository" tag fixture-dnm-v1-source/firmware-root-v1 "$denied_sha"
git -C "$repository" remote add origin "$repository"

git -C "$repository" switch -q main
mkdir -p "$repository/.github/workflows" "$repository/scripts"
printf '/.github/CODEOWNERS @fixture-owner\n' >"$repository/.github/CODEOWNERS"
printf 'name: protected fixture workflow\n' \
  >"$repository/.github/workflows/experimental-firmware-merge-guard.yml"
printf '#!/usr/bin/env bash\nexit 0\n' \
  >"$repository/scripts/check_firmware_merge_guard.sh"
printf '#!/usr/bin/env bash\nexit 0\n' \
  >"$repository/scripts/test_firmware_merge_guard.sh"
chmod 755 "$repository/scripts/check_firmware_merge_guard.sh" \
  "$repository/scripts/test_firmware_merge_guard.sh"
printf '# fixture denylist\n%s refs/tags/fixture-dnm-v1-source/firmware-root-v1 known-experiment\n' \
  "$denied_sha" \
  >"$repository/.github/experimental-firmware-lineages.txt"
printf '# fixture denied gitlinks\ncomponent %s known-experimental-component\n' \
  "$denied_sha" \
  >"$repository/.github/experimental-firmware-gitlinks.txt"
printf 'component %s second-known-experimental-component\n' \
  "$second_denied_sha" \
  >>"$repository/.github/experimental-firmware-gitlinks.txt"
printf 'hdl d53ac844e1206fa37fb858c30c1301a831c11843 starlink-pss15-raw-hdl-v1\n' \
  >>"$repository/.github/experimental-firmware-gitlinks.txt"
fixture_component_oid=$seed_sha
base_sha=$(git_commit 'install protected fixture policy')
candidate_number=0

git -C "$repository" switch -q --detach "$base_sha"
git -C "$repository" switch -q -c appendable-experimental-lineage
printf 'module appendable_experiment; endmodule\n' \
  >"$repository/rtl/appendable-experiment.v"
appendable_lineage_sha=$(git_commit 'appendable experimental lineage root')
git -C "$repository" tag fixture-dnm-v2-source/firmware-root-v1 \
  "$appendable_lineage_sha"

new_candidate
mkdir -p "$repository/docs"
printf 'ordinary firmware change\n' >"$repository/docs/ordinary.md"
ordinary_sha=$(git_commit 'ordinary candidate')
expect_pass 'ordinary candidate' codex/ordinary-firmware-change "$base_sha" "$ordinary_sha"

new_candidate
printf '%s refs/tags/fixture-dnm-v2-source/firmware-root-v1 appended-lineage\n' \
  "$appendable_lineage_sha" \
  >>"$repository/.github/experimental-firmware-lineages.txt"
printf 'component %s appended-component-pin\n' "$appendable_lineage_sha" \
  >>"$repository/.github/experimental-firmware-gitlinks.txt"
safe_policy_append_sha=$(git_commit 'append valid experimental policy entries')
expect_pass 'safe append-only policy extension' codex/append-policy-entry \
  "$base_sha" "$safe_policy_append_sha"

new_candidate
printf 'component %s same-pr-component-pin\n' "$appendable_lineage_sha" \
  >>"$repository/.github/experimental-firmware-gitlinks.txt"
fixture_component_oid=$appendable_lineage_sha
same_pr_gitlink_sha=$(git_commit 'append and select denied component pin')
fixture_component_oid=$seed_sha
expect_reject 'new gitlink entry enforced in same PR' \
  'selects denied experimental gitlink' \
  codex/append-and-select-component "$base_sha" "$same_pr_gitlink_sha"

new_candidate_from "$appendable_lineage_sha"
printf '%s refs/tags/fixture-dnm-v2-source/firmware-root-v1 same-pr-lineage\n' \
  "$appendable_lineage_sha" \
  >>"$repository/.github/experimental-firmware-lineages.txt"
same_pr_lineage_sha=$(git_commit 'append merged lineage root to policy')
expect_reject 'new lineage entry enforced in same PR' \
  'descends from denied experimental lineage' \
  codex/append-merged-lineage "$base_sha" "$same_pr_lineage_sha"

expect_reject 'uppercase DNM ref' 'experimental branch name' \
  codex/DNM "$base_sha" "$ordinary_sha"
expect_reject 'path-segment DNM ref' 'experimental branch name' \
  codex/dnm/candidate "$base_sha" "$ordinary_sha"
expect_reject 'mixed-separator marker ref' 'experimental branch name' \
  codex/do--not_merge/candidate "$base_sha" "$ordinary_sha"
expect_reject 'nonstandard-boundary DNM ref' 'experimental branch name' \
  'codex/foo=dnm+candidate' "$base_sha" "$ordinary_sha"
expect_reject 'invalid ref' 'not a valid branch ref' \
  'codex/bad ref' "$base_sha" "$ordinary_sha"

new_candidate
printf '# stop\n' >"$repository/STARLINK_RX_ONLY_EXPERIMENT_DO_NOT_MERGE.md"
marker_sha=$(git_commit 'add uppercase marker path')
expect_reject 'uppercase marker path' 'candidate tree contains experimental path' \
  codex/renamed-experiment "$base_sha" "$marker_sha"

new_candidate
mkdir -p "$repository/docs"
printf '# stop\n' >"$repository/docs/do-not_merge-this.md"
mixed_marker_sha=$(git_commit 'add mixed-separator marker path')
expect_reject 'mixed-separator marker path' 'candidate tree contains experimental path' \
  codex/renamed-experiment "$base_sha" "$mixed_marker_sha"

new_candidate
mkdir -p "$repository/docs"
printf '# stop\n' >"$repository/docs/review do + not=merge.txt"
spaced_marker_sha=$(git_commit 'add spaced mixed-separator marker path')
expect_reject 'spaced mixed-separator marker path' \
  'candidate tree contains experimental path' \
  codex/renamed-experiment "$base_sha" "$spaced_marker_sha"

new_candidate
mkdir -p "$repository/docs"
printf '# STOP: DO NOT MERGE OR DEPLOY\n' >"$repository/docs/innocent-name.md"
content_sha=$(git_commit 'hide marker in ordinary path')
expect_reject 'content marker' 'experimental content marker' \
  codex/renamed-experiment "$base_sha" "$content_sha"

new_candidate
mkdir -p "$repository/docs"
printf '# STOP: do not merge or cherry-pick this branch\n' \
  >"$repository/docs/innocent-root-marker.md"
root_marker_content_sha=$(git_commit 'hide root marker in ordinary path')
expect_reject 'root marker content' 'experimental content marker' \
  codex/renamed-experiment "$base_sha" "$root_marker_content_sha"

new_candidate
mkdir -p "$repository/docs"
printf 'branch = codex/starlink-rx-only-do-not-merge\n' \
  >"$repository/docs/ordinary-module-config"
ref_content_sha=$(git_commit 'hide forbidden branch in ordinary configuration')
expect_reject 'hyphenated ref in content' 'experimental content marker' \
  codex/renamed-experiment "$base_sha" "$ref_content_sha"

new_candidate
mkdir -p "$repository/docs"
printf '\0DO NOT MERGE OR DEPLOY\n' >"$repository/docs/binary-fixture.bin"
binary_content_sha=$(git_commit 'hide marker in binary-classified content')
expect_reject 'binary content marker' 'experimental content marker' \
  codex/renamed-experiment "$base_sha" "$binary_content_sha"

new_candidate
mkdir -p "$repository/docs"
printf 'DO NOT MERGE OR DEPLOY\n' >"$repository/docs/temporary-warning.md"
git_commit 'temporarily add content marker' >/dev/null
printf 'ordinary replacement\n' >"$repository/docs/temporary-warning.md"
historical_content_sha=$(git_commit 'replace marker before review')
expect_reject 'replaced historical content marker' 'candidate history commit' \
  codex/renamed-experiment "$base_sha" "$historical_content_sha"

new_candidate
ln -s ordinary-source.yaml "$repository/manifests/example-dnm-v1-source.yaml"
symlink_sha=$(git_commit 'use symlink experimental manifest')
expect_reject 'symlink manifest' 'candidate tree contains experimental path' \
  codex/renamed-experiment "$base_sha" "$symlink_sha"

new_candidate
printf 'stop\n' >"$repository/DO_NOT_MERGE_INTO_FIRMWARE_MAIN"
git_commit 'temporarily add marker' >/dev/null
rm "$repository/DO_NOT_MERGE_INTO_FIRMWARE_MAIN"
history_sha=$(git_commit 'remove marker before review')
expect_reject 'deleted historical marker' 'pull-request history contains experimental path' \
  codex/renamed-experiment "$base_sha" "$history_sha"

new_candidate
fixture_component_oid=$denied_sha
denied_gitlink_sha=$(git_commit 'select denied experimental component pin')
fixture_component_oid=$seed_sha
expect_reject 'denied experimental gitlink' 'selects denied experimental gitlink' \
  codex/ordinary-firmware-change "$base_sha" "$denied_gitlink_sha"

new_candidate
fixture_component_oid=$second_denied_sha
second_denied_gitlink_sha=$(git_commit 'select second denied component pin')
fixture_component_oid=$seed_sha
expect_reject 'second denied experimental gitlink' \
  'selects denied experimental gitlink' \
  codex/ordinary-firmware-change "$base_sha" "$second_denied_gitlink_sha"

new_candidate
fixture_component_oid=d53ac844e1206fa37fb858c30c1301a831c11843
protected_evidence_gitlink_sha=$(git_commit 'select protected PSS15 HDL evidence pin')
fixture_component_oid=$seed_sha
expect_reject 'protected PSS15 HDL evidence gitlink' \
  'starlink-pss15-raw-hdl-v1' \
  codex/ordinary-firmware-change "$base_sha" "$protected_evidence_gitlink_sha"

new_candidate
git -C "$repository" update-index --add --cacheinfo \
  "160000,$denied_sha,vendor-component"
git -C "$repository" commit -q -m 'relocate denied component pin'
relocated_gitlink_sha=$(git -C "$repository" rev-parse HEAD)
expect_reject 'relocated denied experimental gitlink' \
  'selects denied experimental gitlink' \
  codex/ordinary-firmware-change "$base_sha" "$relocated_gitlink_sha"

new_candidate
fixture_component_oid=$denied_sha
git_commit 'temporarily select denied component pin' >/dev/null
fixture_component_oid=$seed_sha
historical_gitlink_sha=$(git_commit 'restore ordinary component pin')
expect_reject 'historical denied experimental gitlink' 'selects denied experimental gitlink' \
  codex/ordinary-firmware-change "$base_sha" "$historical_gitlink_sha"

new_candidate
printf '# fixture denylist\n%s refs/tags/fixture-dnm-v1-source/firmware-root-v1 mutated-lineage-name\n' \
  "$denied_sha" \
  >"$repository/.github/experimental-firmware-lineages.txt"
mutated_policy_sha=$(git_commit 'mutate an existing lineage entry')
expect_reject 'mutated append-only entry' 'does not preserve the exact base-byte prefix' \
  codex/mutate-policy "$base_sha" "$mutated_policy_sha"

new_candidate
git -C "$repository" rm -q .github/experimental-firmware-lineages.txt
removed_policy_sha=$(git_commit 'remove append-only lineage policy')
expect_reject 'removed append-only policy' 'candidate append-only policy' \
  codex/remove-policy "$base_sha" "$removed_policy_sha"

new_candidate
printf '# fixture denied gitlinks\n' \
  >"$repository/.github/experimental-firmware-gitlinks.txt"
printf 'component %s second-known-experimental-component\n' "$second_denied_sha" \
  >>"$repository/.github/experimental-firmware-gitlinks.txt"
printf 'component %s known-experimental-component\n' "$denied_sha" \
  >>"$repository/.github/experimental-firmware-gitlinks.txt"
printf 'hdl d53ac844e1206fa37fb858c30c1301a831c11843 starlink-pss15-raw-hdl-v1\n' \
  >>"$repository/.github/experimental-firmware-gitlinks.txt"
reordered_policy_sha=$(git_commit 'reorder append-only gitlink policy')
expect_reject 'reordered append-only entries' \
  'does not preserve the exact base-byte prefix' \
  codex/reorder-policy "$base_sha" "$reordered_policy_sha"

new_candidate
printf 'malformed appended policy entry\n' \
  >>"$repository/.github/experimental-firmware-lineages.txt"
malformed_policy_sha=$(git_commit 'append malformed lineage entry')
expect_reject 'malformed appended entry' 'has a malformed entry' \
  codex/malformed-policy "$base_sha" "$malformed_policy_sha"

new_candidate
printf '# binary\0comment\ncomponent %s binary-policy-component\n' \
  "$appendable_lineage_sha" \
  >>"$repository/.github/experimental-firmware-gitlinks.txt"
binary_policy_sha=$(git_commit 'append binary policy bytes')
expect_reject 'binary append-only policy' 'contains a non-text or control byte' \
  codex/binary-policy "$base_sha" "$binary_policy_sha"

new_candidate
printf '%s refs/tags/fixture-dnm-v1-source/firmware-root-v1 known-experiment\n' \
  "$denied_sha" \
  >>"$repository/.github/experimental-firmware-lineages.txt"
duplicate_policy_sha=$(git_commit 'append duplicate lineage entry')
expect_reject 'duplicate appended entry' 'repeats lineage object' \
  codex/duplicate-policy "$base_sha" "$duplicate_policy_sha"

new_candidate
printf '../component %s unsafe-appended-component\n' "$appendable_lineage_sha" \
  >>"$repository/.github/experimental-firmware-gitlinks.txt"
unsafe_policy_sha=$(git_commit 'append unsafe gitlink path')
expect_reject 'unsafe appended entry' 'has an unsafe path' \
  codex/unsafe-policy "$base_sha" "$unsafe_policy_sha"

new_candidate
printf '# comment without an entry\n' \
  >>"$repository/.github/experimental-firmware-gitlinks.txt"
comment_only_policy_sha=$(git_commit 'append only a policy comment')
expect_reject 'comment-only append' 'without adding a validated entry' \
  codex/comment-only-policy "$base_sha" "$comment_only_policy_sha"

new_candidate
chmod 755 "$repository/.github/experimental-firmware-lineages.txt"
executable_policy_sha=$(git_commit 'make append-only policy executable')
expect_reject 'executable append-only policy' \
  'is not one regular non-executable 100644 blob' \
  codex/executable-policy "$base_sha" "$executable_policy_sha"

new_candidate
git -C "$repository" rm -q .github/experimental-firmware-lineages.txt
ln -s experimental-firmware-gitlinks.txt \
  "$repository/.github/experimental-firmware-lineages.txt"
symlink_policy_sha=$(git_commit 'replace append-only policy with symlink')
expect_reject 'symlink append-only policy' \
  'is not one regular non-executable 100644 blob' \
  codex/symlink-policy "$base_sha" "$symlink_policy_sha"

new_candidate
head -c 33000 /dev/zero | tr '\0' x \
  >>"$repository/.github/experimental-firmware-gitlinks.txt"
printf '\n' >>"$repository/.github/experimental-firmware-gitlinks.txt"
oversized_policy_sha=$(git_commit 'exceed append-only policy byte bound')
expect_reject 'oversized append-only policy' 'exceeds the 32768-byte bound' \
  codex/oversized-policy "$base_sha" "$oversized_policy_sha"

new_candidate
for ((bulk_index = 1; bulk_index <= 255; bulk_index += 1)); do
  printf -v bulk_oid '%040x' "$bulk_index"
  printf 'component %s bulk-component-%s\n' "$bulk_oid" "$bulk_index" \
    >>"$repository/.github/experimental-firmware-gitlinks.txt"
done
too_many_policy_entries_sha=$(git_commit 'exceed append-only policy entry bound')
expect_reject 'too many append-only entries' 'exceeds the 256-entry bound' \
  codex/too-many-policy-entries "$base_sha" "$too_many_policy_entries_sha"

new_candidate
printf '# fixture denylist\n%s refs/tags/fixture-dnm-v1-source/firmware-root-v1 temporary-mutation\n' \
  "$denied_sha" \
  >"$repository/.github/experimental-firmware-lineages.txt"
git_commit 'temporarily mutate append-only policy' >/dev/null
git -C "$repository" restore --source="$base_sha" \
  .github/experimental-firmware-lineages.txt
restored_mutation_sha=$(git_commit 'restore mutated append-only policy')
expect_reject 'hidden append-only mutation' \
  'does not preserve the exact base-byte prefix' \
  codex/hidden-policy-mutation "$base_sha" "$restored_mutation_sha"

new_candidate
printf 'component %s temporary-appended-component\n' "$appendable_lineage_sha" \
  >>"$repository/.github/experimental-firmware-gitlinks.txt"
git_commit 'temporarily append policy entry' >/dev/null
git -C "$repository" restore --source="$base_sha" \
  .github/experimental-firmware-gitlinks.txt
restored_append_sha=$(git_commit 'remove previously appended policy entry')
expect_reject 'hidden append-only removal' 'removes or truncates protected base bytes' \
  codex/hidden-policy-removal "$base_sha" "$restored_append_sha"

for protected_path in \
  .github/CODEOWNERS \
  .github/workflows/experimental-firmware-merge-guard.yml \
  scripts/check_firmware_merge_guard.sh \
  scripts/test_firmware_merge_guard.sh; do
  new_candidate
  printf '\n# planted policy bypass\n' >>"$repository/$protected_path"
  policy_sha=$(git_commit "modify protected policy $protected_path")
  expect_reject "modified $protected_path" 'changes immutable base policy' \
    codex/ordinary-firmware-change "$base_sha" "$policy_sha"
done

new_candidate
printf '\n# temporary policy bypass\n' \
  >>"$repository/.github/workflows/experimental-firmware-merge-guard.yml"
git_commit 'temporarily modify protected workflow' >/dev/null
git -C "$repository" restore \
  --source="$base_sha" .github/workflows/experimental-firmware-merge-guard.yml
reverted_policy_sha=$(git_commit 'hide protected workflow change by reverting it')
expect_reject 'modify then revert guard' 'history changes immutable base policy' \
  codex/ordinary-firmware-change "$base_sha" "$reverted_policy_sha"

new_candidate
ordinary_branch=$(git -C "$repository" branch --show-current)
git -C "$repository" switch -q --orphan unrelated-policy-root
git -C "$repository" rm -qrf --ignore-unmatch .
mkdir -p "$repository/scripts"
printf '#!/usr/bin/env bash\nexit 0\n' \
  >"$repository/scripts/check_firmware_merge_guard.sh"
git -C "$repository" add -A
git -C "$repository" commit -q -m 'unrelated root plants protected policy'
git -C "$repository" switch -q "$ordinary_branch"
git -C "$repository" merge -q --allow-unrelated-histories -s ours \
  unrelated-policy-root -m 'merge unrelated root without its tree'
unrelated_history_sha=$(git -C "$repository" rev-parse HEAD)
expect_reject 'protected path in merged unrelated root' \
  'history changes immutable base policy' \
  codex/ordinary-firmware-change "$base_sha" "$unrelated_history_sha"

new_candidate
git -C "$repository" rm -q scripts/check_firmware_merge_guard.sh
deleted_policy_sha=$(git_commit 'delete protected guard')
expect_reject 'deleted guard' 'changes immutable base policy' \
  codex/ordinary-firmware-change "$base_sha" "$deleted_policy_sha"

new_candidate
git -C "$repository" rm -qr manifests
ln -s missing-manifests "$repository/manifests"
bad_manifests_sha=$(git_commit 'replace manifests tree with symlink')
expect_reject 'symlink manifests directory' 'manifests path is not a Git tree' \
  codex/ordinary-firmware-change "$base_sha" "$bad_manifests_sha"

expect_reject 'malformed base SHA' 'base SHA is not one lowercase full commit ID' \
  codex/ordinary-firmware-change BAD "$ordinary_sha"
expect_reject 'malformed head SHA' 'head SHA is not one lowercase full commit ID' \
  codex/ordinary-firmware-change "$base_sha" BAD

git -C "$repository" tag -f fixture-dnm-v1-source/firmware-root-v1 "$seed_sha" \
  >/dev/null
expect_reject 'trusted lineage ref lost root' 'no longer retains lineage root' \
  codex/ordinary-firmware-change "$base_sha" "$ordinary_sha"

printf 'PASS firmware-main merge guard adversarial fixtures\n'
