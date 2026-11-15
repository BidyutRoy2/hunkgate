"""Errors for hunkgate."""

from __future__ import annotations


class HunkgateError(Exception):
    """Base error; the CLI prints the message and exits non-zero."""


class DiffParseError(HunkgateError):
    """The input is not a parseable unified diff."""


class StoreError(HunkgateError):
    """The review store (.hunkgate/) is missing or unreadable."""


class ItemNotFoundError(HunkgateError):
    """No review item with that id exists in the store."""


class DecisionError(HunkgateError):
    """A decision (approve/reject) is refused — see the message."""
