# Security

Crewline reads Jira, GitHub and git with the token you put in your own environment (`JIRA_TOKEN`, `gh` login).
It never writes to those systems and never stores tokens. Ticket text, indexes and maps are cached locally in
`$CREWLINE_DATA`; treat that folder like the source it came from. Map pages are self-contained HTML that embed
ticket titles and people's names: share them only with people who can see the tickets.

To report a vulnerability, open a private security advisory on GitHub (Security → Report a vulnerability)
rather than a public issue.
