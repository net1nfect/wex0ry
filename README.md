# contribtool

`contribtool` is a modular Python CLI for planning and safely applying
date-based Git commits in repositories you own or control. It separates pattern
generation from Git execution, produces a reviewable calendar, and records an
append-only activity log instead of touching project source files.

## Requirements and installation

- Python 3.11 or newer
- Git 2.30 or newer
- A configured local `user.name` and `user.email`

```bash
python -m pip install -e '.[dev]'
# Optional YAML input/output support:
python -m pip install -e '.[yaml]'
```

## Workflow

Always review before applying:

```bash
contribtool generate --repo . --year 2026 --pattern natural --seed 1337 \
  --output .contribution-tool/plans/2026-natural.json
contribtool preview .contribution-tool/plans/2026-natural.json
contribtool apply .contribution-tool/plans/2026-natural.json --dry-run
contribtool apply .contribution-tool/plans/2026-natural.json --yes
contribtool validate --repo .
contribtool push --repo .
```

`apply` requires a clean worktree, validates the active branch, and never
checks out, resets, rebases, rewrites history, changes Git identity, or force
pushes. If a generated plan is stored inside the repository, commit that plan
first or store it outside the repository; this keeps the dirty-worktree guard
unambiguous.

## Commands

`generate`, `preview`, `apply`, `validate`, `config`, `patterns`, `inspect`,
`stats`, `resume`, `push`, `analyze`, and `diff` are available. Run
`python -m contribtool --help` or `<command> --help` for options.

For a guided terminal flow use `contribtool interactive --repo .`.

Custom date mappings can be supplied with `--pattern custom --custom-file
mapping.json`; text mode uses `--pattern text --text WEX0RY` and requires a
range large enough for the bitmap.

Supported patterns: `full`, `random`, `natural`, `gradient`, `wave`,
`checkerboard`, `weekdays`, `weekends`, `custom`, and `text`.

Date ranges use `--start YYYY-MM-DD --end YYYY-MM-DD` or `--year YYYY`.
Random patterns are reproducible with `--seed`. Times are generated in the
configured timezone and working hours and are stored in the schedule.

## Schedule and configuration

Schedules are JSON documents containing every date, its commit count,
intensity, and exact timezone-aware commit slots. The schedule ID is a stable
SHA-256 prefix of canonical content. JSON is the default exchange format;
TOML is accepted for input and YAML is optional.

Project settings live in `.contribution-tool/config.toml`:

```toml
timezone = "Asia/Jakarta"
branch = "main"

[commit]
message_template = "chore(contrib): activity {date} #{index}"

[intensity]
low = 1
medium = 3
high = 6
very_high = 10

[working_hours]
start = 9
end = 20
```

Runtime state is stored in `.contribution-tool/state`, `journals`, and
`locks`; these paths are ignored. Plans and configuration can be committed
for reproducibility. The only intentional tracked file changed by execution
is `.contribution-history/activity.jsonl`.

## Resume and recovery

Each successful commit is recorded in a JSONL journal and checkpointed. If an
execution is interrupted, run:

```bash
contribtool resume .contribution-tool/plans/<schedule-id>.json --yes
```

The journal and commit trailers (`Contrib-Schedule-Id` and
`Contrib-Sequence`) prevent duplicate work. A lock prevents concurrent
executions for the same schedule.

## GitHub attribution

The tool verifies local Git facts only. GitHub attribution still depends on
the commit email being connected to your account, commits being on the
repository default branch, repository permissions/visibility, pushing the
commits, and GitHub's processing delay. A successful local commit is never
presented as a guarantee of a green contribution graph.

## Testing and development

```bash
pytest
python -m compileall src
```

Integration tests create temporary Git repositories and verify author and
committer dates with `git log --format=fuller`; the real project repository is
never used as a destructive test target.
