# 0003. Grounded generation, citations and abstention

Status: accepted

## Context

The failure that loses user trust is a fluent answer that the documents don't
support. A second risk is ingested text that tries to instruct the model.

## Decision

1. **Abstain before generation.** If the best vector similarity is below
   `RAGDESK_MIN_SIMILARITY`, return `grounded: false` without calling a model.
2. **Cite or abstain.** The generator receives numbered passages and must cite
   them as `[n]`. Citations are mapped back to chunk IDs server-side, so the
   client never trusts indices the model invented.
3. **Documents are data.** Passages are wrapped in `<document index="n" title="...">`
   tags with HTML-escaped titles. The system prompt says the content is reference
   material, not instructions.
4. **Two generators behind one port.** `ExtractiveGenerator` quotes the top
   passages and needs no API key; it is the default and what tests use.
   `ClaudeGenerator` calls the Claude API with low effort, server-side fallbacks
   enabled, and treats a `refusal` stop reason as an abstention.

## Consequences

- Questions outside the corpus cost nothing at the model provider.
- The floor trades recall against false answers. It is tuned with the eval
  suite, never by feel, and changes to it go through review.
- The audit log stores chunk IDs per question, so any answer can be traced back
  to the exact passages it was given.
