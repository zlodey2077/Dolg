"""Learning drafts generated from ingested engineering artifacts."""

from __future__ import annotations

from typing import Any

from .artifact_ingestion import learning_tasks_from_artifact


def learning_suggestions_from_artifacts(artifact_reports: list[dict[str, Any]] | None, *, limit: int = 6) -> list[dict[str, Any]]:
    suggestions = []
    for report in artifact_reports or []:
        for task in learning_tasks_from_artifact(report, limit=limit):
            suggestions.append(task)
            if len(suggestions) >= limit:
                return suggestions
    return suggestions


def artifact_training_summary(artifact_reports: list[dict[str, Any]] | None) -> dict[str, Any]:
    reports = artifact_reports or []
    check_findings = 0
    fault_cases = 0
    parsers = {}
    for report in reports:
        parser = report.get('parser') or 'unknown'
        parsers[parser] = parsers.get(parser, 0) + 1
        facts = report.get('facts') or {}
        check_report = facts.get('check_report') or {}
        check_findings += len(check_report.get('findings') or [])
        fault_cases += len(facts.get('fault_cases') or [])
    return {
        'artifact_count': len(reports),
        'parsers': parsers,
        'check_findings': check_findings,
        'fault_cases': fault_cases,
        'safe_learning_mode': 'batch_curated',
    }
