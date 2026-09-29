"""Versioned prompt templates, one module per operation and version (docs/AI.md §9).

A prompt is never edited in place once it has been used: change it by adding `<name>_v2` and
switching the caller, so the `prompt_version` stored with generated content (spec §73) always
identifies the exact text that produced it.
"""
