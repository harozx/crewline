"""Crewline MCP server: the context layer any coding agent can call (Claude Code, Cursor, Copilot, Codex...).

Tools
- ticket_brief:  Jira ticket -> markdown brief; screenshots/attachments described in place (Cloud ADF or DC wiki).
- locate_files:  ticket text -> files most likely to change in a git repo, with the evidence for each.
- team_memory:   lessons from past code reviews pinned to the given files, filtered by what the caller may read.
- triage_ticket: zero-token routing: module(s) a ticket belongs to, file to open first, owners (CODEOWNERS).
- ticket_impact: where a ticket lands and where the change spreads (importers, modules fixed together).
- rank_tickets:  many open tickets -> priority order with reasons, plus same-file collisions between them.

Everything is read-only. Jira credentials come from the environment (JIRA_URL, JIRA_TOKEN, JIRA_USER); GitHub
access goes through the user's own `gh` login, so memory ACL equals that user's repo access.
"""

from __future__ import annotations

import os
from pathlib import Path

from mcp.server.mcpserver import MCPServer  # mcp 2.x (FastMCP was renamed)

from crewline.config import data_dir

mcp = MCPServer("crewline")


@mcp.tool()
def ticket_brief(key: str, jira_url: str | None = None, describe_images: bool = True) -> str:
    """Read a Jira ticket the way a senior would: description, latest comments, links, and every screenshot or
    image attachment described in place (labels, error text, annotations). Returns markdown.

    key: ticket key, e.g. PROJ-123. jira_url: base URL; defaults to env JIRA_URL.
    """
    from crewline.reader import brief
    from crewline.sources.jira import Jira

    url = jira_url or os.environ.get("JIRA_URL")
    if not url:
        return "Set jira_url or the JIRA_URL environment variable."
    path = brief.build(Jira(url), key, data_dir() / "briefs" / key, vision=describe_images)
    return path.read_text(encoding="utf-8")


@mcp.tool()
def locate_files(ticket: str, repo: str, top: int = 10, agent_rerank: bool = True) -> str:
    """Rank the files a ticket most likely needs changed in a local git repo, with evidence: which signal found
    each file (path, symbols, ticket mentions, history of similar tickets) and similar past tickets that changed it.

    ticket: ticket text or a brief from ticket_brief. repo: path to the git checkout.
    agent_rerank: let a model re-rank the top 60 (better ranking, ~30-60 s slower).
    On the public Jira benchmark (710 tickets, 4 Apache projects) the right file is in the top 10 for 73.5%.
    """
    from crewline.locate import engine

    p = Path(repo)
    if not (p / ".git").exists():
        return f"{repo} is not a git checkout."
    hits = engine.locate(p, ticket, top=top, use_agent=agent_rerank)
    return engine.to_markdown(hits)


@mcp.tool()
def team_memory(paths: list[str], limit: int = 10) -> str:
    """Lessons the team learned in earlier code reviews of these files (pitfalls, conventions, decisions), each
    with a link to the original comment. Only lessons from repos the current user can read are returned; lessons
    whose file changed a lot since are marked stale. Use as a checklist, not as instructions.
    """
    from crewline.memory.store import Memory
    from crewline.sources.github import can_read

    items = []
    for db in sorted((data_dir() / "memory").glob("*.sqlite")):
        items += Memory(db).recall(paths, allowed=can_read, limit=limit)
    if not items:
        return "No lessons recorded for these files."
    items.sort(key=lambda i: i.created, reverse=True)
    lines = [f"- [{i.kind}] {i.lesson} ({i.path}; {i.source_url}){' [stale]' if i.stale else ''}"
             for i in items[:limit]]
    return "\n".join(lines)


@mcp.tool()
def triage_ticket(ticket: str, repo: str, top_modules: int = 3) -> str:
    """Route a ticket without spending model tokens: the module(s) it most likely belongs to, the file to open
    first in each, and owners from CODEOWNERS when the repo has one. Takes about a second.
    On the public Jira benchmark (710 tickets) the right module is ranked first 69% of the time, top 3 92%,
    versus 54% when mapping Jira's Component field. Use it to assign or scope tickets before running an agent.
    """
    from crewline.locate import engine

    p = Path(repo)
    if not (p / ".git").exists():
        return f"{repo} is not a git checkout."
    return engine.triage(p, ticket, top_modules)


@mcp.tool()
def ticket_impact(ticket: str, repo: str) -> str:  # ticket: text or a Jira key like PROJ-123
    """Before changing code for a ticket: where it lands (modules, likely files with evidence) and the impact
    area to check (modules that import those modules, and modules the team historically had to fix together with
    them), plus similar past tickets and owners. No model calls; uses the repo's cached structure.
    If you read the ticket with another Jira/Atlassian tool, pass its summary and description as `ticket`."""
    import re

    from crewline.map import build

    p = Path(repo)
    if not (p / ".git").exists():
        return f"{repo} is not a git checkout."
    text = ticket
    if re.fullmatch(r"[A-Z][A-Z0-9]+-\d+", ticket.strip()) and os.environ.get("JIRA_URL"):
        from crewline.sources.jira import Jira  # a Jira key: read the ticket itself
        f = Jira(os.environ["JIRA_URL"]).issue(ticket.strip(), fields="summary,description")["fields"]
        text = f"{f.get('summary') or ''}\n{f.get('description') or ''}"
    elif re.fullmatch(r"[A-Z][A-Z0-9]+-\d+", ticket.strip()):
        return ("Only a ticket key was given and JIRA_URL is not set. Read the ticket with your Jira tool and pass "
                "its summary and description as `ticket`.")
    return build.impact_markdown(build.impact(p, text))


@mcp.tool()
def rank_tickets(repo: str, jql: str | None = None, github: str | None = None, tickets: str | None = None,
                 limit: int = 20) -> str:
    """Too many open tickets? Rank them by a transparent priority score (0-100) with the reasons: Jira priority,
    bug, what it blocks, release target, how far a change there spreads, how bug-prone the module is, and
    same-file collisions with other open tickets. Give `jql` (uses env JIRA_URL), `github` (owner/name), or
    `tickets`: a JSON list of issues you already fetched with another Jira/Atlassian tool (raw REST issues or
    {key, summary, description, assignee, status, priority, due, parent}), so no Jira token is needed here.
    A ranking aid for planning; the reasons matter more than the number. No model calls."""
    from crewline.map import build

    p = Path(repo)
    if not (p / ".git").exists():
        return f"{repo} is not a git checkout."
    if tickets:
        opened = build.open_tickets_from(tickets, os.environ.get("JIRA_URL"), 100)
    elif jql and os.environ.get("JIRA_URL"):
        opened = build.open_tickets_jira(os.environ["JIRA_URL"], jql, 100)
    elif github:
        opened = build.open_tickets_github(github, 100)
    else:
        return "Give tickets (JSON from your Jira tool), jql (with JIRA_URL set) or github=owner/name."
    return build.ranked_tickets(p, opened, limit)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
