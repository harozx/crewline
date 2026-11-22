from __future__ import annotations

import json
from pathlib import Path

import typer

app = typer.Typer(no_args_is_help=True, help="Crewline: ticket -> context -> location -> crew -> PR.")
evals_app = typer.Typer(no_args_is_help=True, help="Benchmarks.")
crew_app = typer.Typer(no_args_is_help=True, help="Run the local CLI agents.")
app.add_typer(evals_app, name="eval")
app.add_typer(crew_app, name="crew")


@evals_app.command("build-kafka")
def build_kafka() -> None:
    """Fetch Kafka Jira tickets and link them to fix commits."""
    from crewline.evals import kafka
    typer.echo(json.dumps(kafka.build(), indent=2))


@evals_app.command("locate")
def locate(limit: int = typer.Option(None, help="Only the first N tickets."),
           split: str = typer.Option("eval", help="eval (report) | dev (tune)"),
           tag: str = typer.Option("p1", help="Label for the result file.")) -> None:
    """Score file localisation methods (recall@k)."""
    from crewline.evals import kafka
    typer.echo(json.dumps(kafka.evaluate(limit, split, tag), indent=2))


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
