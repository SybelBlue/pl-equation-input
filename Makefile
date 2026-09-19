SHELL := /bin/bash
.SHELLFLAGS := -euo pipefail -c

.DEFAULT_GOAL := test

UV_CACHE_DIR ?= /private/tmp/learnvia_uv_cache
PL_REF ?= master

LIB_TEST_PATHS := elements/**/tests
SCRIPT_TEST_PATHS := scripts/tests
PYTHON_FORMAT_PATHS := elements questions scripts src

export UV_CACHE_DIR

DOCKER_JOBS_DIR ?= $(shell mktemp -d /tmp/pl-docker-jobs.XXXXXX)

export DOCKER_JOBS_DIR

.PHONY: clean deps venv test test-smoke test-regression test-unit test-publication typecheck format-py format-json format-html format check-format check-pl-schemas update-prairielearn-pin check-prairielearn-pin ci-dryrun fetch-pl-schemas dev docker

# install deps, RUN ME FIRST
# requires pnpm and uv to be installed on the commandline
deps: fetch-pl-schemas
	pnpm install
	uv sync

venv: deps
	uv venv --refresh

fetch-pl-schemas:
	uv run --active scripts/pull_down_prairielearn_schemas.py --write


# testing and validation
test:
	uv run --active pytest $(LIB_TEST_PATHS) $(SCRIPT_TEST_PATHS) $(PYTEST_ARGS)

test-smoke:
	uv run --active pytest -m smoke $(LIB_TEST_PATHS) $(PYTEST_ARGS)

test-regression:
	uv run --active pytest -m regression $(LIB_TEST_PATHS) $(PYTEST_ARGS)

test-unit:
	uv run --active pytest -m unit $(LIB_TEST_PATHS) $(SCRIPT_TEST_PATHS) $(PYTEST_ARGS)

test-publication: test typecheck check-format check-pl-schemas
	git diff --check

typecheck:
	uv run --active pyright

check-format:
	uv run --active ruff format --check $(PYTHON_FORMAT_PATHS)

check-pl-schemas:
	uv run --active scripts/pull_down_prairielearn_schemas.py

update-prairielearn-pin:
	uv run --active scripts/update_prairielearn_pin.py --ref "$(PL_REF)"

check-prairielearn-pin:
	uv run --active scripts/update_prairielearn_pin.py --check

ci-dryrun: test typecheck check-format check-pl-schemas check-prairielearn-pin


# format source
format: format-py format-json format-html

format-py:
	uv run --active ruff format $(PYTHON_FORMAT_PATHS)

format-json:
	pnpm dlx prettier --write "{.vscode,courseInstances,elements,questions}/**/*.{json,jsonc}"

format-html:
	pnpm dlx prettier --write "{elements,questions}/**/*.{html,mustache,mu}"


# launch prairielearn
dev:
	pnpm dlx @sybelblue/prairielearn-runner@latest

docker:
	docker run -it --rm --pull=always \
		-p 3000:3000 \
		-v ".:/course" \
		-v "$(DOCKER_JOBS_DIR):/jobs" \
		-e HOST_JOBS_DIR="$(DOCKER_JOBS_DIR)" \
		-v /var/run/docker.sock:/var/run/docker.sock \
		--add-host=host.docker.internal:172.17.0.1 \
		prairielearn/prairielearn:us-prod-live

# Remove project-local caches, build outputs, and installed dependencies.
clean:
	rm -rf .venv node_modules build dist htmlcov .prairielearn/schemas .pnpm-store
	find . -type d \( \
		-name __pycache__ -o \
		-name .pytest_cache -o \
		-name .ruff_cache -o \
		-name .mypy_cache -o \
		-name '*.egg-info' \
	\) -prune -exec rm -rf {} +
	find . -type f \( \
		-name '*.py[co]' -o \
		-name .coverage -o \
		-name 'coverage.*' \
	\) -delete
