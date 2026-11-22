from __future__ import annotations

import json
from pathlib import Path

import typer

app = typer.Typer(no_args_is_help=True, help="Crewline: ticket -> context -> location -> crew -> PR.")
evals_app = typer.Typer(no_args_is_help=True, help="Benchmarks.")
crew_app = typer.Typer(no_args_is_help=True, help="Run the local CLI agents.")
app.add_typer(evals_app, name="eval")
app.add_typer(crew_app, name="crew")


@evals_app.command("build")
def build(project: str = typer.Option("kafka", help="kafka | flink | hbase | hive")) -> None:
    """Fetch an Apache project's Jira tickets and link them to fix commits (repo cloned in <data>/repos)."""
    from crewline.evals import apache
    typer.echo(json.dumps(apache.build(project), indent=2))


@evals_app.command("memory")
def eval_memory(n: int = typer.Option(60, help="Number of review comments to test.")) -> None:
    """Review with vs without team memory: how often the agent raises the human reviewer's point."""
    from crewline.evals import memory
    typer.echo(json.dumps(memory.run(n), indent=2))


@evals_app.command("locate")
def locate(project: str = typer.Option("kafka", help="kafka | flink | hbase | hive"),
           limit: int = typer.Option(None, help="Only the first N tickets."),
           split: str = typer.Option("eval", help="eval (report) | dev (tune)"),
           tag: str = typer.Option("p1", help="Label for the result file.")) -> None:
    """Score file localisation methods (recall@k)."""
    from crewline.evals import apache
    typer.echo(json.dumps(apache.evaluate(project, limit, split, tag), indent=2))


@evals_app.command("rerank")
def eval_rerank(project: str = typer.Option("kafka", help="kafka | flink | hbase | hive"),
                split: str = typer.Option("eval", help="eval (report) | dev (tune)"),
                limit: int = typer.Option(None, help="Only the first N tickets."),
                cli: str = typer.Option("codex", help="Agent CLI: claude | codex | agy"),
                model: str = typer.Option("gpt-5.6-luna", help="Model for the re-ranker."),
                pool: int = typer.Option(60, help="Fused candidates passed to the re-ranker.")) -> None:
    """Score agent re-ranking of the fused candidates (recall@k)."""
    from crewline.evals import apache
    typer.echo(json.dumps(apache.rerank_eval(project, split, limit, cli, model, pool), indent=2))


@app.command("brief")
def brief(key: str, jira: str = typer.Option("https://issues.apache.org/jira", help="Jira base URL."),
          out: Path = typer.Option(None, help="Output folder (default <data>/briefs/<KEY>)."),
          vision: bool = typer.Option(True, help="Describe images with a light vision model.")) -> None:
    """Build a ticket brief: markdown with images described in place, attachments downloaded."""
    from crewline.config import data_dir
    from crewline.reader import brief as b
    from crewline.sources.jira import Jira
    path = b.build(Jira(jira), key, out or data_dir() / "briefs" / key, vision=vision)
    typer.echo(str(path))


@app.command("locate")
def locate_cmd(ticket: str = typer.Argument(..., help="Ticket text, or a path to brief.md."),
               repo: Path = typer.Option(Path("."), help="Git repository to search."),
               top: int = typer.Option(10, help="How many files to return."),
               agent: bool = typer.Option(True, help="Let an agent re-rank the top 60."),
               as_json: bool = typer.Option(False, "--json", help="JSON instead of a markdown table.")) -> None:
    """Rank the files a ticket most likely needs changed, with the evidence for each."""
    from crewline.locate import engine
    hits = engine.locate(repo, engine.ticket_text(ticket), top=top, use_agent=agent)
    typer.echo(engine.to_json(hits) if as_json else engine.to_markdown(hits))


@crew_app.command("run")
def crew_run(prompt: str, tier: str = typer.Option("light", help="light | medium | heavy"),
             cwd: Path = typer.Option(Path("."), help="Working directory for the agent."),
             write: bool = typer.Option(False, help="Allow the agent to edit files."),
             purpose: str = typer.Option("", help="Short label for the ledger.")) -> None:
    """One agent turn routed by tier, with fallback and escalation."""
    from crewline.crew.router import ask
    res = ask(prompt, cwd, tier, purpose=purpose, write=write)  # type: ignore[arg-type]
    typer.echo(f"[{res.choice.cli}:{res.choice.model} ok={res.ok} {res.seconds:.0f}s]")
    typer.echo(res.text)


@crew_app.command("solve")
def crew_solve(brief: Path = typer.Argument(..., help="brief.md describing the change."),
               repo: Path = typer.Option(Path("."), help="Git repository to change."),
               gate: str = typer.Option(None, help="Shell command that must pass, e.g. 'uv run pytest -q'."),
               solo: str = typer.Option(None, help="Baseline: one agent 'cli:model' instead of the crew."),
               review: bool = typer.Option(True, help="Cross-vendor review of each task."),
               keep: bool = typer.Option(False, help="Keep worktrees for inspection.")) -> None:
    """Run the crew (or a solo baseline) on a brief. Result lands on a local branch; nothing is pushed."""
    from dataclasses import asdict

    from crewline.crew import team
    from crewline.crew.models import Choice
    if solo:
        cli, model = solo.split(":", 1)
        report = team.solo(repo, brief, gate, Choice(cli, model))  # type: ignore[arg-type]
    else:
        crew = team.Crew(repo, brief, gate)
        report = crew.run(review=review)
        if not keep:
            crew.cleanup()
    typer.echo(json.dumps(asdict(report), indent=2))
