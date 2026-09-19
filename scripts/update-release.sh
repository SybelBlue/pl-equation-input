#!/usr/bin/env bash

set -euo pipefail

source_branch="main"
target_branch="release"
push=false

usage() {
  cat <<'EOF'
Usage: scripts/update-release.sh [--push]

Rebuild release from the contents and history of
main:elements/pl-equation-input. The files under
elements/pl-equation-input become the root of release, alongside
main:.gitignore. Its README.md replaces the top-level README.md; nothing else
from main is kept.

Options:
  --push  Force-push the rebuilt branch to origin using --force-with-lease.
  -h, --help  Show this help.
EOF
}

while (($#)); do
  case "$1" in
    --push)
      push=true
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

repo_root=$(git rev-parse --show-toplevel)
cd "$repo_root"

git rev-parse --verify --quiet "${source_branch}^{commit}" >/dev/null || {
  printf 'Branch %s does not exist.\n' "$source_branch" >&2
  exit 1
}

git cat-file -e "${source_branch}:elements/pl-equation-input" || {
  printf '%s does not contain elements/pl-equation-input.\n' \
    "$source_branch" >&2
  exit 1
}

git cat-file -e "${source_branch}:elements/pl-equation-input/README.md" || {
  printf '%s does not contain elements/pl-equation-input/README.md.\n' \
    "$source_branch" >&2
  exit 1
}

git cat-file -e "${source_branch}:.gitignore" || {
  printf '%s does not contain .gitignore.\n' "$source_branch" >&2
  exit 1
}

if git worktree list --porcelain | grep -Fxq "branch refs/heads/${target_branch}"; then
  printf 'Branch %s is checked out in a worktree; switch that worktree to another branch first.\n' \
    "$target_branch" >&2
  exit 1
fi

old_target=$(git rev-parse --verify --quiet "refs/heads/${target_branch}" ||
  git rev-parse --verify --quiet "refs/remotes/origin/${target_branch}" || true)
split_commit=$(git subtree split --prefix=elements/pl-equation-input \
  "$source_branch")

temporary_directory=$(mktemp -d)
trap 'rm -rf "$temporary_directory"' EXIT
temporary_index="${temporary_directory}/index"

GIT_INDEX_FILE="$temporary_index" git read-tree "${split_commit}^{tree}"
gitignore_blob=$(git rev-parse "${source_branch}:.gitignore")
GIT_INDEX_FILE="$temporary_index" git update-index \
  --add --cacheinfo "100644,${gitignore_blob},.gitignore"
readme_blob=$(git rev-parse \
  "${source_branch}:elements/pl-equation-input/README.md")
GIT_INDEX_FILE="$temporary_index" git update-index \
  --add --cacheinfo "100644,${readme_blob},README.md"
target_tree=$(GIT_INDEX_FILE="$temporary_index" git write-tree)

if [[ -n "$old_target" ]] &&
  [[ "$(git rev-parse "${old_target}^{tree}")" == "$target_tree" ]]; then
  generated_commit=$old_target
else
  generated_commit=$(printf 'Prepare %s release tree\n' "$target_branch" |
    GIT_AUTHOR_NAME="$(git show -s --format=%an "$source_branch")" \
      GIT_AUTHOR_EMAIL="$(git show -s --format=%ae "$source_branch")" \
      GIT_AUTHOR_DATE="$(git show -s --format=%aI "$source_branch")" \
      GIT_COMMITTER_NAME="$(git show -s --format=%cn "$source_branch")" \
      GIT_COMMITTER_EMAIL="$(git show -s --format=%ce "$source_branch")" \
      GIT_COMMITTER_DATE="$(git show -s --format=%cI "$source_branch")" \
      git commit-tree "$target_tree" -p "$split_commit")
fi

old_local_target=$(git rev-parse --verify --quiet "refs/heads/${target_branch}" || true)
if [[ -n "$old_local_target" ]]; then
  git update-ref "refs/heads/${target_branch}" "$generated_commit" "$old_local_target"
else
  git update-ref "refs/heads/${target_branch}" "$generated_commit"
fi

actual_target_tree=$(git rev-parse "${target_branch}^{tree}")
if [[ "$target_tree" != "$actual_target_tree" ]]; then
  printf 'Refusing to continue: generated tree does not match %s.\n' \
    "$target_branch" >&2
  exit 1
fi

printf 'Updated %s to %s from %s:elements/pl-equation-input.\n' \
  "$target_branch" "$generated_commit" "$source_branch"

if [[ "$push" == true ]]; then
  git push --force-with-lease "origin" "${target_branch}:${target_branch}"
fi
