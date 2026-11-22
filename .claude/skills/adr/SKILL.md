---
name: adr
description: Record a design decision as docs/adr/NNNN-slug.md from docs/templates/adr.md. Use when choosing a library, storage, routing rule, or dropping/changing a plan item.
---

1. Next number = highest in `docs/adr/` + 1, zero-padded to 4.
2. Copy `docs/templates/adr.md`, fill Context (with numbers), Decision, Consequences (what we will measure).
3. Superseding an ADR: set the old one's status to `superseded by ADR-NNNN`.
4. Mention the ADR in the commit body and the next HANDOFF entry.
