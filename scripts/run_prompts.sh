set -euo pipefail

# The prompt files must be committed so every worktree can see them.
# git add scripts/prompts
# git commit -m "Add publication-readiness agent prompts"

base_dir="/private/tmp/pl-big-operator-agents-$$"

git worktree add -b audit/test-inventory \
  "$base_dir/test-inventory" HEAD
git worktree add -b audit/core-python \
  "$base_dir/core-python" HEAD
git worktree add -b audit/parser-migration \
  "$base_dir/parser-migration" HEAD

codex exec -C "$base_dir/test-inventory" \
  -s workspace-write \
  - < "$base_dir/test-inventory/scripts/prompts/01-test-inventory.md" \
  > "$base_dir/test-inventory.log" 2>&1 &
pid_tests=$!

codex exec -C "$base_dir/core-python" \
  -s workspace-write \
  - < "$base_dir/core-python/scripts/prompts/02-core-python-audit.md" \
  > "$base_dir/core-python.log" 2>&1 &
pid_core=$!

codex exec -C "$base_dir/parser-migration" \
  -s workspace-write \
  - < "$base_dir/parser-migration/scripts/prompts/03-parser-migration.md" \
  > "$base_dir/parser-migration.log" 2>&1 &
pid_parser=$!

wait "$pid_tests"
wait "$pid_core"
wait "$pid_parser"

git -C "$base_dir/test-inventory" add scripts/prompts/output
git -C "$base_dir/test-inventory" commit \
  -m "Add test inventory and suite proposal"

git -C "$base_dir/core-python" add scripts/prompts/output
git -C "$base_dir/core-python" commit \
  -m "Add core Python audit"

git -C "$base_dir/parser-migration" add scripts/prompts/output
git -C "$base_dir/parser-migration" commit \
  -m "Add parser migration analysis"

git merge --no-ff audit/test-inventory \
  -m "Merge test inventory audit"
git merge --no-ff audit/core-python \
  -m "Merge core Python audit"
git merge --no-ff audit/parser-migration \
  -m "Merge parser migration audit"

git worktree remove "$base_dir/test-inventory"
git worktree remove "$base_dir/core-python"
git worktree remove "$base_dir/parser-migration"

printf 'Merged all three audits. Agent logs remain in %s\n' "$base_dir"