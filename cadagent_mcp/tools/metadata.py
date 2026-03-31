"""Helpers for richer MCP tool descriptions and contracts."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional


def tool_contract(
    *,
    summary: str,
    when_to_use: str,
    when_not_to_use: str,
    authoritative_result: str,
    follow_up: str,
    failure_handling: str,
    input_field_semantics: Optional[Dict[str, str]] = None,
    output_field_semantics: Optional[Dict[str, str]] = None,
    follow_up_tools: Optional[List[str]] = None,
    common_failures: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    description_lines = [
        summary,
        f"Use when: {when_to_use}",
        f"Do not use when: {when_not_to_use}",
        f"Authoritative result fields: {authoritative_result}",
        f"Typical next step: {follow_up}",
        f"Failure handling: {failure_handling}",
    ]

    if common_failures:
        failure_summaries = "; ".join(
            f"{item['code']}: {item['recovery']}" for item in common_failures if item.get("code") and item.get("recovery")
        )
        if failure_summaries:
            description_lines.append(f"Common failures: {failure_summaries}")

    contract: Dict[str, Any] = {
        "whenToUse": when_to_use,
        "whenNotToUse": when_not_to_use,
        "authoritativeResult": authoritative_result,
        "followUpExpectation": follow_up,
        "failureHandling": failure_handling,
    }
    if input_field_semantics:
        contract["inputFieldSemantics"] = deepcopy(input_field_semantics)
    if output_field_semantics:
        contract["outputFieldSemantics"] = deepcopy(output_field_semantics)
    if follow_up_tools:
        contract["followUpTools"] = list(follow_up_tools)
    if common_failures:
        contract["commonFailures"] = deepcopy(common_failures)

    return {
        "description": "\n".join(description_lines),
        "x-cadagent-contract": contract,
    }


__all__ = ["tool_contract"]
