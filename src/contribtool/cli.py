from __future__ import annotations

from datetime import date
from pathlib import Path
import signal
import typer

from .calendar import stats
from .config import ToolConfig
from .formats import dump_schedule, load_mapping, load_schedule
from .gitops import validate_repo
from .models import Schedule
from .patterns import PATTERNS, generate
from .persistence import Lock, append_activity, completed_sequences, dirs, journal, load_state, save_state
from .preview import render
from .errors import ContribToolError


app = typer.Typer(help="Safe, reproducible Git contribution schedules", no_args_is_help=True)


def repo_path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def resolve_schedule(value: Path, repo: Path) -> Path:
    if value.exists():
        return value
    candidate = repo / ".contribution-tool" / "plans" / f"{value}.json"
    if candidate.exists():
        return candidate
    raise typer.BadParameter(f"schedule file not found: {value}")


def parse_range(start: str | None, end: str | None, year: int | None) -> tuple[date, date]:
    if year is not None:
        if year < 1970 or year > 9999:
            raise typer.BadParameter("year must be between 1970 and 9999")
        return date(year, 1, 1), date(year, 12, 31)
    if not start or not end:
        raise typer.BadParameter("provide --year or both --start and --end")
    try:
        first, last = date.fromisoformat(start), date.fromisoformat(end)
    except ValueError as exc:
        raise typer.BadParameter("dates must use YYYY-MM-DD") from exc
    if first > last:
        raise typer.BadParameter("--start must not be after --end")
    return first, last


def _summary(schedule: Schedule) -> str:
    active = sum(day.commits > 0 for day in schedule.days)
    inactive = len(schedule.days) - active
    timestamps = [slot.timestamp for day in schedule.days for slot in day.slots]
    return (
        f"Repository schedule\n"
        f"Schedule ID  : {schedule.schedule_id}\n"
        f"Branch       : {schedule.branch}\n"
        f"Pattern      : {schedule.pattern}\n"
        f"Range        : {schedule.start} -> {schedule.end}\n"
        f"Active days  : {active}\n"
        f"Inactive days: {inactive}\n"
        f"Earliest     : {min(timestamps).isoformat() if timestamps else '(none)'}\n"
        f"Latest       : {max(timestamps).isoformat() if timestamps else '(none)'}\n"
        f"Total commits: {schedule.total_commits}"
    )


@app.command("generate")
def generate_cmd(
    repo: str = typer.Option(".", "--repo"),
    start: str | None = typer.Option(None, "--start"),
    end: str | None = typer.Option(None, "--end"),
    year: int | None = typer.Option(None, "--year"),
    pattern: str = typer.Option("natural", "--pattern"),
    min_commits: int = typer.Option(0, "--min-commits"),
    max_commits: int = typer.Option(4, "--max-commits"),
    seed: int | None = typer.Option(None, "--seed"),
    timezone: str | None = typer.Option(None, "--timezone"),
    branch: str | None = typer.Option(None, "--branch"),
    output: Path | None = typer.Option(None, "--output"),
    config_path: Path | None = typer.Option(None, "--config"),
    custom_file: Path | None = typer.Option(None, "--custom-file", help="JSON/TOML/YAML date mapping for custom pattern"),
    text: str | None = typer.Option(None, "--text", help="Text for the pixel-art pattern"),
):
    """Generate a validated schedule file without changing Git history."""
    if min_commits < 0 or max_commits < min_commits:
        raise typer.BadParameter("commit bounds are invalid")
    root = repo_path(repo)
    config = ToolConfig.load(config_path or (root / ".contribution-tool" / "config.toml"))
    first, last = parse_range(start, end, year)
    if pattern not in PATTERNS:
        raise typer.BadParameter(f"pattern must be one of {', '.join(PATTERNS)}")
    pattern_options = {}
    if custom_file:
        if pattern != "custom":
            raise typer.BadParameter("--custom-file requires --pattern custom")
        source = load_mapping(custom_file)
        pattern_options = source.get("dates", source)
        if not isinstance(pattern_options, dict):
            raise typer.BadParameter("custom file must map dates to commit counts")
    if text is not None:
        if pattern != "text":
            raise typer.BadParameter("--text requires --pattern text")
        pattern_options = {"text": text}
    schedule = generate(
        first, last, pattern, timezone or config.timezone, branch or config.branch,
        min_commits, max_commits, seed if seed is not None else config.seed,
        options={"dates": pattern_options} if pattern == "custom" else pattern_options,
        work_start=config.work_start, work_end=config.work_end,
        intensity_mapping={int(config.intensity.get(name, threshold)): level for name, threshold, level in (
            ("low", 1, 1), ("medium", 3, 2), ("high", 6, 3), ("very_high", 10, 4)
        ) if int(config.intensity.get(name, threshold)) > 0},
    )
    destination = output or root / ".contribution-tool" / "plans" / f"{schedule.schedule_id}.json"
    dump_schedule(schedule, destination)
    typer.echo(f"Schedule {schedule.schedule_id} written to {destination}")


@app.command("preview")
def preview_cmd(schedule: Path, ascii_only: bool = typer.Option(False, "--ascii", help="Use ASCII symbols only")):
    """Render a schedule as a terminal contribution calendar."""
    typer.echo(render(load_schedule(schedule), ascii_only=ascii_only))


@app.command("stats")
def stats_cmd(schedule: Path):
    """Show schedule statistics."""
    values = stats(load_schedule(schedule))
    for key, value in values.items():
        typer.echo(f"{key}: {value}")


@app.command("patterns")
def patterns_cmd():
    """List available patterns."""
    typer.echo("\n".join(PATTERNS))


@app.command("interactive")
def interactive_cmd(repo: str = typer.Option(".", "--repo")):
    """Run a small guided workflow for interactive terminals."""
    root = repo_path(repo)
    typer.echo("Git Contribution Tool")
    typer.echo(f"Repository: {root}")
    choice = typer.prompt("Choose: [1] inspect  [2] patterns  [3] validate  [4] generate  [5] preview  [6] apply  [7] push  [q] quit", default="q")
    if choice == "1":
        inspect_cmd(str(root))
    elif choice == "2":
        patterns_cmd()
    elif choice == "3":
        validate_cmd(str(root))
    elif choice == "4":
        year = typer.prompt("Year", default= date.today().year, type=int)
        pattern = typer.prompt("Pattern", default="natural")
        seed = typer.prompt("Seed (blank for none)", default="")
        output = typer.prompt("Output path (blank for default)", default="")
        generate_cmd(str(root), None, None, year, pattern, 0, 4, int(seed) if seed else None, None, None, Path(output) if output else None)
    elif choice == "5":
        path = Path(typer.prompt("Schedule path"))
        preview_cmd(path)
    elif choice == "6":
        path = Path(typer.prompt("Schedule path"))
        apply_cmd(path, str(root), False, False, None)
    elif choice == "7":
        push_cmd(str(root), False)
    elif choice.lower() != "q":
        raise typer.BadParameter("unknown interactive choice")


@app.command("validate")
def validate_cmd(repo: str = typer.Option(".", "--repo"), branch: str | None = typer.Option(None, "--branch")):
    """Validate repository safety prerequisites."""
    repository = validate_repo(repo_path(repo), branch)
    name, email = repository.identity()
    typer.echo(f"Repository: {repository.root}")
    typer.echo(f"Branch: {repository.branch()}")
    typer.echo(f"Remote: {repository.remote() or '(none)'}")
    typer.echo(f"Git identity: {name} <{email}>")
    typer.echo("Worktree: clean")


@app.command("inspect")
def inspect_cmd(repo: str = typer.Option(".", "--repo")):
    """Show local repository and tool diagnostics without modifying anything."""
    repository = validate_repo(repo_path(repo), allow_dirty=True)
    name, email = repository.identity()
    config_path = repository.root / ".contribution-tool" / "config.toml"
    typer.echo(f"Repository: {repository.root}")
    typer.echo(f"HEAD: {repository.head()}")
    typer.echo(f"Branch: {repository.branch() or '(detached)'}")
    typer.echo(f"Remote: {repository.remote() or '(none)'}")
    typer.echo(f"Identity: {name} <{email}>")
    typer.echo(f"Dirty: {'yes' if repository.status() else 'no'}")
    typer.echo(f"Config: {config_path if config_path.exists() else '(default)'}")
    typer.echo("Git executable: available")


def _apply(schedule: Schedule, root: Path, dry_run: bool, yes: bool, resume_mode: bool = False, config_path: Path | None = None) -> None:
    config = ToolConfig.load(config_path or (root / ".contribution-tool" / "config.toml"))
    repository = validate_repo(root, schedule.branch, config.allow_dirty)
    state_root = root / ".contribution-tool"
    state = load_state(state_root, schedule.schedule_id) if state_root.exists() else None
    completed = completed_sequences(state_root, schedule.schedule_id) if state_root.exists() else set()
    completed |= repository.schedule_sequences(schedule.schedule_id)
    if state and state.get("status") == "complete":
        raise typer.BadParameter("schedule already completed")
    if dry_run:
        typer.echo(_summary(schedule))
        typer.echo(f"Already completed: {len(completed)}")
        return
    if not yes and not typer.confirm("This operation will create Git commits. Continue?", default=False):
        raise typer.Abort()
    dirs(state_root)
    base_head = state.get("base_head") if state else repository.head()
    state = state or {
        "schedule_id": schedule.schedule_id,
        "repository": str(repository.root),
        "branch": schedule.branch,
        "base_head": base_head,
        "total": schedule.total_commits,
        "completed": len(completed),
        "status": "running",
        "failures": [],
    }
    if state.get("repository") and Path(state["repository"]).resolve() != repository.root:
        raise typer.BadParameter("checkpoint belongs to a different repository")
    if state.get("branch") and state["branch"] != repository.branch():
        raise typer.BadParameter("checkpoint belongs to a different branch")
    if state.get("total") is not None and int(state["total"]) != schedule.total_commits:
        raise typer.BadParameter("checkpoint total does not match schedule")
    stop = False

    def request_stop(_signum, _frame):
        nonlocal stop
        stop = True

    previous_int = signal.signal(signal.SIGINT, request_stop)
    previous_term = signal.signal(signal.SIGTERM, request_stop)
    sequence = 0
    try:
        with Lock(state_root / "locks" / f"{schedule.schedule_id}.lock", schedule.schedule_id, str(repository.root)):
            for day in schedule.days:
                for slot in day.slots:
                    sequence += 1
                    if sequence in completed:
                        continue
                    if stop:
                        state["status"] = "interrupted"
                        save_state(state_root, schedule.schedule_id, state)
                        typer.echo(f"Interrupted after {state['completed']} / {state['total']} commits")
                        return
                    expected_head = state.get("last_commit") or state.get("base_head")
                    if expected_head and repository.head() != expected_head:
                        raise typer.BadParameter("repository HEAD changed during execution; inspect before resuming")
                    activity_path = root / ".contribution-history" / "activity.jsonl"
                    previous_size = activity_path.stat().st_size if activity_path.exists() else 0
                    append_activity(root, schedule, day.date, sequence, slot.timestamp)
                    message = config.message_template.format(date=day.date.isoformat(), index=slot.index)
                    message += f"\n\nContrib-Schedule-Id: {schedule.schedule_id}\nContrib-Sequence: {sequence}"
                    try:
                        sha = repository.commit(message, slot.timestamp.isoformat(), [".contribution-history/activity.jsonl"])
                    except Exception as exc:
                        if activity_path.exists():
                            if previous_size == 0:
                                activity_path.unlink()
                            else:
                                with activity_path.open("r+b") as stream:
                                    stream.truncate(previous_size)
                        repository.run("restore", "--staged", "--", ".contribution-history/activity.jsonl", check=False)
                        state["failures"].append({"sequence": sequence, "error": str(exc)})
                        state["status"] = "failed"
                        save_state(state_root, schedule.schedule_id, state)
                        raise
                    state["completed"] = int(state.get("completed", 0)) + 1
                    state["last_commit"] = sha
                    state["current_date"] = day.date.isoformat()
                    journal(state_root, schedule.schedule_id, {"sequence": sequence, "date": day.date.isoformat(), "sha": sha, "status": "success"})
                    save_state(state_root, schedule.schedule_id, state)
            state["status"] = "complete"
            save_state(state_root, schedule.schedule_id, state)
            typer.echo(f"Execution complete: {state['completed']} commits")
    finally:
        signal.signal(signal.SIGINT, previous_int)
        signal.signal(signal.SIGTERM, previous_term)


@app.command("apply")
def apply_cmd(schedule: Path, repo: str = typer.Option(".", "--repo"), dry_run: bool = typer.Option(False, "--dry-run"), yes: bool = typer.Option(False, "--yes"), config_path: Path | None = typer.Option(None, "--config")):
    """Apply a schedule, or show a no-write dry run."""
    _apply(load_schedule(schedule), repo_path(repo), dry_run, yes, config_path=config_path)


@app.command("resume")
def resume_cmd(schedule: Path, repo: str = typer.Option(".", "--repo"), yes: bool = typer.Option(False, "--yes"), config_path: Path | None = typer.Option(None, "--config")):
    """Resume an interrupted or failed schedule."""
    root = repo_path(repo)
    _apply(load_schedule(resolve_schedule(schedule, root)), root, False, yes, True, config_path)


@app.command("config")
def config_cmd(repo: str = typer.Option(".", "--repo")):
    """Show effective project configuration."""
    typer.echo(ToolConfig.load(repo_path(repo) / ".contribution-tool" / "config.toml"))


@app.command("analyze")
def analyze_cmd(repo: str = typer.Option(".", "--repo")):
    """Analyze existing local history without modifying the repository."""
    repository = validate_repo(repo_path(repo), allow_dirty=True)
    dates = [line for line in repository.run("log", "--all", "--format=%ad", "--date=short").stdout.splitlines() if line]
    per_day = {}
    for item in dates:
        per_day[item] = per_day.get(item, 0) + 1
    typer.echo(f"Repository: {repository.root}\nHistory analysis is read-only.")
    typer.echo(f"Commit count: {len(dates)}")
    typer.echo(f"Active days: {len(per_day)}")
    if per_day:
        busiest = max(per_day, key=per_day.get)
        typer.echo(f"Busiest day: {busiest} ({per_day[busiest]} commits)")


@app.command("diff")
def diff_cmd(old: Path, new: Path):
    """Compare two schedules by date and total commits."""
    first, second = load_schedule(old), load_schedule(new)
    changes = sum(a.commits != b.commits for a, b in zip(first.days, second.days))
    typer.echo(f"Old {first.schedule_id}: {first.total_commits} commits")
    typer.echo(f"New {second.schedule_id}: {second.total_commits} commits")
    typer.echo(f"Changed dates: {changes}")


@app.command("push")
def push_cmd(repo: str = typer.Option(".", "--repo"), yes: bool = typer.Option(False, "--yes")):
    """Push the current branch explicitly; never force-pushes."""
    repository = validate_repo(repo_path(repo))
    remote = repository.remote()
    if not remote:
        raise typer.BadParameter("origin remote is not configured")
    if not yes and not typer.confirm(f"Push {repository.branch()} to {remote}?", default=False):
        raise typer.Abort()
    repository.run("push", "origin", repository.branch())
    typer.echo("Push complete")


def main() -> None:
    try:
        app()
    except (ContribToolError, ValueError, RuntimeError, OSError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    main()
