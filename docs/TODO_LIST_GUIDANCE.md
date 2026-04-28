# TODO List Guidance

TODO lists for new features or tasks live in `docs/requirements/` as markdown files.

## File naming

Filename format: `<YYYYMMDD>_TODO_<PROJECT_NAME>.md`, all caps with underscores between words. For camel-cased project names without acronyms (like `API`), split at word boundaries.

Example: `20260418_TODO_NEWS_NEXUS_12.md`

## Structure

Tasks are checklist items grouped into phases. Each phase is a discrete, testable unit of work.

## Per-phase workflow

After completing a phase:

1. Run the project's tests. Skip if the project has no test suite.
2. For typed projects (TypeScript, etc.), run the type-check or build step and confirm it succeeds.
3. Check off the phase's completed tasks once all applicable checks pass.
4. Commit. The commit message should reference the TODO file and the phase completed.

## Python projects

Every machine has a `python` alias pointing to the version intended for use. Do not use the system Python — verify with `which python` and `python --version` before running Python commands.
