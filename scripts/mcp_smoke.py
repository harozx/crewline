"""Call every Crewline MCP tool through a real stdio client. Run: uv run python scripts/mcp_smoke.py"""

import asyncio

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

KAFKA = "D:/crewline-data/repos/kafka"
GMM = "group-coordinator/src/main/java/org/apache/kafka/coordinator/group/GroupMetadataManager.java"
CALLS = [
    ("team_memory", {"paths": [GMM], "limit": 3}),
    ("locate_files", {"ticket": "PartitionChangeBuilder#toString doesn't cover all fields", "repo": KAFKA,
                      "top": 5, "agent_rerank": False}),
    ("ticket_brief", {"key": "KAFKA-21597", "jira_url": "https://issues.apache.org/jira",
                      "describe_images": False}),
]


async def main() -> None:
    params = StdioServerParameters(command="uv", args=["--directory", "D:/crewline", "run", "crewline", "mcp"])
    async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
        await s.initialize()
        print("tools:", [t.name for t in (await s.list_tools()).tools])
        for name, args in CALLS:
            res = await s.call_tool(name, args)
            print(f"--- {name}\n{res.content[0].text[:600]}")


asyncio.run(main())
