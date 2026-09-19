# pl-equation-input

This repository develops and publishes a PrairieLearn element for entering and grading one symbolic equation or inequality.

## Instructors

Vendor the standalone element from the generated `release` branch:

```sh
git clone --branch release https://github.com/SybelBlue/pl-equation-input.git elements/pl-equation-input
```

The release branch contains only the files needed under `elements/pl-equation-input`. See the [element documentation](elements/pl-equation-input/README.md) for attributes, grading behavior, and examples.

## Developers

### Prerequisites

- Python 3.13 or newer
- [uv](https://docs.astral.sh/uv/)
- [pnpm](https://pnpm.io/) 11.19 or newer
- GNU Make
- Docker (optional, for running PrairieLearn in a container)

Install dependencies and run the full local validation suite:

```sh
make deps
make ci-dryrun
```

Start the demo course locally:

```sh
make dev
```

The `main` branch is a complete PrairieLearn development course. Each push to `main` rebuilds `release` from `elements/pl-equation-input`, places the element README at the release root, and excludes the surrounding demo and development tooling.

### Useful commands

| Command | Description |
| --- | --- |
| `make test` | Run element and maintenance-script tests |
| `make typecheck` | Type-check project-owned Python code |
| `make check-format` | Check Python formatting |
| `make check-pl-schemas` | Verify downloaded PrairieLearn schemas |
| `make check-prairielearn-pin` | Verify that the vendored symbolic input, Python source, and lockfile use one upstream commit |
| `make update-prairielearn-pin [PL_REF=<ref>]` | Refresh the PrairieLearn pin; defaults to `master` |
| `make ci-dryrun` | Run the checks used by CI |
| `make dev` | Launch the demo course with the PrairieLearn runner |
| `make docker` | Launch the demo course with the official PrairieLearn image |

The element vendors PrairieLearn's `pl-symbolic-input`. Its exact source commit and source path are recorded in `elements/pl-equation-input/prairielearn-source.json`; the upstream license is included in the vendored snapshot.
