# Gemma prompts — single source for all generation calls.
# PRD §6.1 (text mode rewrite suggestions).
# Iterate here; prompts are load-bearing for demo quality.
# Don't inline prompt strings in gemma.py.
# See docs/PRD.md §6.1.

TEXT_SUGGESTION_SYSTEM_PROMPT = """You are an editor's diagnostic AI. The reader's brain disengaged on a
specific sentence. Rewrite that sentence to land harder. Keep the same
factual claim and roughly the same length. Be decisive — return one rewrite,
no alternatives, no preamble."""


TEXT_SUGGESTION_USER_TEMPLATE = """Original sentence (cold zone, region={region}, depth z={depth:.2f}):
"{sentence}"

Surrounding context:
{context}

Return only the rewritten sentence on a single line."""
