"""Classify feedback and produce candidate memories."""

from app.memory.extractor import extract_memory_from_feedback


def execute(**kwargs):
    return extract_memory_from_feedback(**kwargs)
