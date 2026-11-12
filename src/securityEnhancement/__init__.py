"""Security-enhancement methods used by the benchmark.

The package groups the three independent security-enhancement schemes:

- ``AgentGuard``: action-level allow/deny guard on tool calls.
- ``QuittingAgents``: the paper's Specified Quit condition.
- ``TargetedReminder``: prompt-only targeted safety reminder.

Each subpackage remains self-contained; nothing here re-exports their APIs.
"""
