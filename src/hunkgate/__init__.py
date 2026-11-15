"""hunkgate — the human gate for agent-written code.

Review a diff hunk by hunk, approve what you trust, apply only that,
and send the rest back to the agent as a structured prompt.

Zero dependencies. Python 3.9+. Local-first: all state lives in
``.hunkgate/`` inside the repo you are reviewing.
"""

__version__ = "0.1.0"
__all__ = ["__version__"]
