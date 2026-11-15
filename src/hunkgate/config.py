"""Config: ``.hunkgate.toml`` — a small, documented TOML subset.

Supported (everything optional)::

    reviewer = "ada"
    auto_approve = ["docs-only", "tests-only"]
    block_on_undecided = true

    [rules.SEC-01]
    enabled = false          # disable a built-in rule by id

    [[custom_rule]]
    id = "ACME-01"
    severity = "high"        # critical | high | medium | low
    pattern = "TODO\\(acme\\)"
    message = "ACME TODO left in code"
    fix = "Resolve the TODO or file a ticket and link it."
    direction = "add"        # add | del | path

Python 3.11+ has ``tomllib``; for 3.9/3.10 this module parses the same
subset by hand, so the file works everywhere hunkgate runs. Anything
outside the subset is refused with a clear error instead of silently
ignored — a config that does not do what it says is worse than no
config.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .errors import HunkgateError
from .rules import Rule

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - 3.9/3.10 fallback
    tomllib = None


@dataclass
class CustomRule:
    rule_id: str
    severity: str
    pattern: str
    message: str
    fix: str
    direction: str = "add"

    def to_rule(self) -> Rule:
        """Compile this custom rule into the engine's Rule shape."""
        compiled = re.compile(self.pattern)
        if self.direction == "path":
            return Rule(self.rule_id, self.severity, self.message, self.fix,
                        path_patterns=[compiled], direction="path")
        return Rule(self.rule_id, self.severity, self.message, self.fix,
                    patterns=[compiled], direction=self.direction)


@dataclass
class Config:
    reviewer: str = ""
    auto_approve: list[str] = field(default_factory=list)
    block_on_undecided: bool = True
    disabled_rules: set[str] = field(default_factory=set)
    custom_rules: list[CustomRule] = field(default_factory=list)

    @classmethod
    def defaults(cls) -> "Config":
        return cls()


def _subset_parse(text: str) -> dict:
    """Parse the documented TOML subset (sections, scalars, string lists)."""
    data: dict = {}
    current: dict = data
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[[") and line.endswith("]]"):
            name = line[2:-2].strip()
            data.setdefault(name, []).append({})
            current = data[name][-1]
            continue
        if line.startswith("[") and line.endswith("]"):
            name = line[1:-1].strip()
            parts = name.split(".")
            current = data
            for part in parts:
                current = current.setdefault(part, {})
            continue
        m = re.match(r"^([A-Za-z0-9_-]+)\s*=\s*(.+)$", line)
        if not m:
            raise HunkgateError(f"cannot parse config line: {raw!r}")
        key, value = m.group(1), m.group(2).strip()
        current[key] = _parse_value(value)
    return data


def _parse_value(value: str):
    if value in ("true", "false"):
        return value == "true"
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if value.startswith('"') and value.endswith('"'):
        return bytes(value[1:-1], "utf-8").decode("unicode_escape")
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_value(item.strip()) for item in inner.split(",")]
    raise HunkgateError(f"unsupported config value: {value!r}")


def load_config(path: str) -> Config:
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError as exc:
        raise HunkgateError(f"cannot read config {path}: {exc}") from exc
    if tomllib is not None:
        try:
            data = tomllib.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise HunkgateError(f"invalid TOML in {path}: {exc}") from exc
    else:
        data = _subset_parse(raw.decode("utf-8"))
    return _from_dict(data)


def _from_dict(data: dict) -> Config:
    config = Config()
    if not isinstance(data, dict):
        raise HunkgateError("config must be a TOML document (table at top level)")
    config.reviewer = str(data.get("reviewer", ""))
    auto = data.get("auto_approve", [])
    if isinstance(auto, str):
        auto = [auto]
    if not isinstance(auto, list) or any(not isinstance(x, str) for x in auto):
        raise HunkgateError("auto_approve must be a list of strings")
    for policy in auto:
        if policy not in ("docs-only", "tests-only"):
            raise HunkgateError(
                f"unknown auto_approve policy {policy!r} "
                "(allowed: docs-only, tests-only)")
        config.auto_approve.append(policy)
    config.block_on_undecided = bool(data.get("block_on_undecided", True))
    rules = data.get("rules", {})
    if not isinstance(rules, dict):
        raise HunkgateError("[rules] must be a table of rule ids")
    for rule_id, rule_cfg in rules.items():
        if isinstance(rule_cfg, dict) and rule_cfg.get("enabled") is False:
            config.disabled_rules.add(rule_id)
    custom = data.get("custom_rule", [])
    if isinstance(custom, dict):
        custom = [custom]
    for entry in custom:
        if not isinstance(entry, dict):
            raise HunkgateError("[[custom_rule]] entries must be tables")
        for field_name in ("id", "severity", "pattern", "message", "fix"):
            if field_name not in entry:
                raise HunkgateError(
                    f"[[custom_rule]] is missing required field {field_name!r}")
        if entry["severity"] not in ("critical", "high", "medium", "low"):
            raise HunkgateError(
                f"custom rule {entry['id']}: bad severity {entry['severity']!r}")
        if str(entry.get("direction", "add")) not in ("add", "del", "path"):
            raise HunkgateError(
                f"custom rule {entry['id']}: direction must be add, del or path")
        try:
            re.compile(entry["pattern"])
        except re.error as exc:
            raise HunkgateError(
                f"custom rule {entry['id']}: bad regex: {exc}") from exc
        config.custom_rules.append(CustomRule(
            rule_id=str(entry["id"]), severity=str(entry["severity"]),
            pattern=str(entry["pattern"]), message=str(entry["message"]),
            fix=str(entry["fix"]),
            direction=str(entry.get("direction", "add"))))
    return config
