"""Lab 10: Automating Workflows & Controlling Costs (Gemini Router + Antigravity SDK).

Demonstrates:
1. A smart Gemini Cost & Model Router (`select_optimal_gemini_model` &
   `estimate_workload_cost`) that routes tasks between `gemini-3.1-flash-lite`,
   `gemini-3-flash-preview`, and `gemini-3.1-pro-preview`, and calculates savings from
   Gemini Context Caching and the Gemini Batch API (50% discount).
2. A programmatic Release Readiness & Git Diff Reviewer built around the
   `google-antigravity` Python SDK (`Agent`, `LocalAgentConfig`, `CapabilitiesConfig`),
   including an offline-compatible adapter so tests run deterministically anywhere.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Literal

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# 1. Smart Gemini Model Router & Token Cost Calculator
# ---------------------------------------------------------------------------

ModelTier = Literal["gemini-3.1-flash-lite", "gemini-3-flash-preview", "gemini-3.1-pro-preview"]


class ModelPricingSpec(BaseModel):
    """Per-1M-token pricing in USD (illustrative standard tiers for comparison)."""

    model_config = ConfigDict(extra="forbid")

    model_id: ModelTier
    input_per_1m_usd: float = Field(ge=0.0)
    output_per_1m_usd: float = Field(ge=0.0)
    cached_input_per_1m_usd: float = Field(ge=0.0)


PRICING_TABLE: dict[ModelTier, ModelPricingSpec] = {
    "gemini-3.1-flash-lite": ModelPricingSpec(
        model_id="gemini-3.1-flash-lite",
        input_per_1m_usd=0.075,
        output_per_1m_usd=0.30,
        cached_input_per_1m_usd=0.01875,
    ),
    "gemini-3-flash-preview": ModelPricingSpec(
        model_id="gemini-3-flash-preview",
        input_per_1m_usd=0.15,
        output_per_1m_usd=0.60,
        cached_input_per_1m_usd=0.0375,
    ),
    "gemini-3.1-pro-preview": ModelPricingSpec(
        model_id="gemini-3.1-pro-preview",
        input_per_1m_usd=1.25,
        output_per_1m_usd=5.00,
        cached_input_per_1m_usd=0.3125,
    ),
}


class RoutingDecision(BaseModel):
    """Explains which Gemini model was selected for a task and why."""

    model_config = ConfigDict(extra="forbid")

    selected_model: ModelTier
    task_category: Literal["classification_or_extraction", "general_agent_or_chat", "deep_reasoning"]
    reason: str


class CostComparisonReport(BaseModel):
    """Compares standard on-demand cost vs. Context Caching and Batch API savings."""

    model_config = ConfigDict(extra="forbid")

    model_id: ModelTier
    standard_cost_usd: float
    cached_cost_usd: float
    batch_cost_usd: float
    cache_savings_percent: float
    batch_savings_percent: float


def select_optimal_gemini_model(
    prompt: str,
    requires_multi_file_architecture: bool = False,
    is_high_volume_classification: bool = False,
) -> RoutingDecision:
    """Route a prompt to the most cost-effective Gemini 3 model that fits the task.

    Routing rules:
    1. High-volume classification, sentiment tagging, or simple field extraction
       -> `gemini-3.1-flash-lite`.
    2. Complex multi-file architecture debugging, deep root-cause analysis, or
       long-horizon math/planning -> `gemini-3.1-pro-preview`.
    3. Everyday customer chat, structured JSON generation, and tool-calling
       agents -> `gemini-3-flash-preview`.
    """
    lowered = prompt.lower()

    if requires_multi_file_architecture or any(
        phrase in lowered
        for phrase in (
            "architectural tradeoff",
            "multi-file refactor",
            "root-cause analysis",
            "prove mathematically",
        )
    ):
        return RoutingDecision(
            selected_model="gemini-3.1-pro-preview",
            task_category="deep_reasoning",
            reason="Task requires deep multi-step reasoning or cross-file architectural analysis.",
        )

    if is_high_volume_classification or any(
        phrase in lowered
        for phrase in (
            "classify",
            "sentiment",
            "yes or no",
            "extract category",
            "label ticket",
        )
    ):
        return RoutingDecision(
            selected_model="gemini-3.1-flash-lite",
            task_category="classification_or_extraction",
            reason="Fast classification/extraction task fits gemini-3.1-flash-lite at lowest cost.",
        )

    return RoutingDecision(
        selected_model="gemini-3-flash-preview",
        task_category="general_agent_or_chat",
        reason="General structured output or tool-calling task fits gemini-3-flash-preview.",
    )


def estimate_workload_cost(
    model_id: ModelTier,
    num_requests: int,
    shared_system_tokens: int,
    unique_user_tokens_per_req: int,
    output_tokens_per_req: int,
) -> CostComparisonReport:
    """Calculate USD cost for a workload and show Context Cache & Batch API savings.

     Notice why output tokens matter: across every tier, 1M output tokens cost 4x
    as much as 1M input tokens!
    """
    spec = PRICING_TABLE[model_id]

    total_input_tokens = num_requests * (shared_system_tokens + unique_user_tokens_per_req)
    total_output_tokens = num_requests * output_tokens_per_req

    standard_input_cost = (total_input_tokens / 1_000_000.0) * spec.input_per_1m_usd
    standard_output_cost = (total_output_tokens / 1_000_000.0) * spec.output_per_1m_usd
    standard_total = standard_input_cost + standard_output_cost

    # With Context Caching: shared_system_tokens are billed once at standard input rate,
    # and reused across (num_requests - 1) requests at the 75%-discounted cached rate.
    if num_requests > 1 and shared_system_tokens > 0:
        first_Load_tokens = shared_system_tokens + unique_user_tokens_per_req
        repeated_cached_tokens = (num_requests - 1) * shared_system_tokens
        repeated_unique_tokens = (num_requests - 1) * unique_user_tokens_per_req

        cached_input_cost = (
            ((first_Load_tokens + repeated_unique_tokens) / 1_000_000.0) * spec.input_per_1m_usd
            + (repeated_cached_tokens / 1_000_000.0) * spec.cached_input_per_1m_usd
        )
    else:
        cached_input_cost = standard_input_cost

    cached_total = cached_input_cost + standard_output_cost

    # Gemini Batch API provides a flat 50% discount for non-urgent asynchronous jobs
    batch_total = standard_total * 0.50

    cache_savings_pct = (
        ((standard_total - cached_total) / standard_total) * 100.0
        if standard_total > 0
        else 0.0
    )
    return CostComparisonReport(
        model_id=model_id,
        standard_cost_usd=round(standard_total, 4),
        cached_cost_usd=round(cached_total, 4),
        batch_cost_usd=round(batch_total, 4),
        cache_savings_percent=round(cache_savings_pct, 2),
        batch_savings_percent=50.0,
    )


# ---------------------------------------------------------------------------
# 2. `google-antigravity` Python SDK Pattern & Release Diff Reviewer
# ---------------------------------------------------------------------------


@dataclass
class ToolCallEvent:
    """Strongly-typed tool execution event streamed from `response.tool_calls`."""

    name: str
    args: dict[str, Any]


@dataclass
class CapabilitiesConfig:
    """Mirrors `google.antigravity.CapabilitiesConfig` for enabling agent capabilities."""

    enable_write_tools: bool = False


@dataclass
class LocalAgentConfig:
    """Mirrors `google.antigravity.LocalAgentConfig` for configuring the local agent."""

    system_instructions: str = "You are a helpful coding and security review agent."
    capabilities: CapabilitiesConfig = field(default_factory=CapabilitiesConfig)


class StreamingAgentResponse:
    """Mirrors the streaming response returned by `await agent.chat(prompt)`.

    Supports:
    - `async for token in response:` (streaming text tokens)
    - `async for thought in response.thoughts:` (streaming internal reasoning)
    - `async for call in response.tool_calls:` (streaming tool invocations)
    """

    def __init__(
        self,
        tokens: list[str],
        thoughts: list[str],
        tool_calls: list[ToolCallEvent],
    ) -> None:
        self._tokens = tokens
        self._thoughts = thoughts
        self._tool_calls = tool_calls

    def __aiter__(self) -> AsyncIterator[str]:
        return self._iterate_items(self._tokens)

    @property
    def thoughts(self) -> AsyncIterator[str]:
        return self._iterate_items(self._thoughts)

    @property
    def tool_calls(self) -> AsyncIterator[ToolCallEvent]:
        return self._iterate_items(self._tool_calls)

    @staticmethod
    async def _iterate_items(items: list[Any]) -> AsyncIterator[Any]:
        for item in items:
            await asyncio.sleep(0)
            yield item


class LocalAntigravityAgentAdapter:
    """Compatible local implementation of `google.antigravity.Agent` for deterministic testing."""

    def __init__(self, config: LocalAgentConfig) -> None:
        self.config = config

    async def __aenter__(self) -> LocalAntigravityAgentAdapter:
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None

    async def chat(self, prompt: str) -> StreamingAgentResponse:
        findings = inspect_git_diff_for_risks(prompt)
        thoughts = [
            "Scanning git diff for hardcoded secrets, wildcard binds, and raw SQL strings...",
            f"Identified {len(findings)} potential release-blocking issue(s).",
        ]
        tool_calls = [
            ToolCallEvent(
                name="static_diff_security_check",
                args={"lines_scanned": len(prompt.splitlines())},
            )
        ]
        if not findings:
            summary_text = "STATUS: APPROVED\nNo security or reliability issues detected in diff."
        else:
            joined = "\n".join(f"- [{item.rule_id}] {item.message}" for item in findings)
            summary_text = f"STATUS: BLOCKED\nFound {len(findings)} issue(s):\n{joined}"

        tokens = [word + " " for word in summary_text.split(" ")]
        return StreamingAgentResponse(
            tokens=tokens,
            thoughts=thoughts,
            tool_calls=tool_calls,
        )


class DiffFinding(BaseModel):
    """Single security or reliability issue discovered in a git diff."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str
    severity: Literal["HIGH", "MEDIUM"]
    message: str


class AutomatedReviewResult(BaseModel):
    """Structured output from the automated Antigravity SDK release reviewer."""

    model_config = ConfigDict(extra="forbid")

    approved: bool
    findings: list[DiffFinding]
    thoughts_log: list[str]
    tools_invoked: list[str]
    final_summary: str


def inspect_git_diff_for_risks(diff_text: str) -> list[DiffFinding]:
    """Check added lines in a git diff for common security regressions."""
    findings: list[DiffFinding] = []
    added_lines = [
        line[1:]
        for line in diff_text.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]
    combined = "\n".join(added_lines)

    # 1. Check for hardcoded API keys or literal fallback secrets in os.environ.get
    if re.search(r"AIza[0-9A-Za-z\-_]{10,}", combined) or re.search(
        r"os\.(?:environ\.get|getenv)\(\s*['\"][A-Z0-9_]*SECRET[A-Z0-9_]*['\"]\s*,\s*['\"][^'\"]+['\"]\s*\)",
        combined,
    ):
        findings.append(
            DiffFinding(
                rule_id="SEC-001-HARDCODED-SECRET",
                severity="HIGH",
                message="Hardcoded API key or literal fallback secret detected in diff.",
            )
        )

    # 2. Check for f-string or concatenated SQL queries
    if re.search(r"execute\(\s*f['\"].*?(?:SELECT|INSERT|UPDATE|DELETE)\b", combined, re.IGNORECASE):
        findings.append(
            DiffFinding(
                rule_id="SEC-002-SQL-INJECTION",
                severity="HIGH",
                message="Unparameterized f-string SQL query detected; use '?' placeholders.",
            )
        )

    # 3. Check for 0.0.0.0 bind in local test runner
    if re.search(r"uvicorn\.run\([^)]*host\s*=\s*['\"]0\.0\.0\.0['\"]", combined):
        findings.append(
            DiffFinding(
                rule_id="SEC-003-WILDCARD-BIND",
                severity="MEDIUM",
                message="Local uvicorn.run binds to 0.0.0.0; bind to 127.0.0.1 for local testing.",
            )
        )

    return findings


async def run_automated_diff_review(diff_text: str) -> AutomatedReviewResult:
    """Run an automated pre-release diff review using the Antigravity SDK pattern."""
    config = LocalAgentConfig(
        system_instructions=(
            "You are a pre-release security reviewer. Block any diff that introduces "
            "hardcoded secrets, unparameterized SQL, or insecure local server binds."
        ),
        capabilities=CapabilitiesConfig(enable_write_tools=False),
    )

    async with LocalAntigravityAgentAdapter(config) as agent:
        response = await agent.chat(diff_text)

        thoughts_log: list[str] = []
        async for thought in response.thoughts:
            thoughts_log.append(thought)

        tools_invoked: list[str] = []
        async for call in response.tool_calls:
            tools_invoked.append(call.name)

        chunks: list[str] = []
        async for token in response:
            chunks.append(token)

        final_summary = "".join(chunks).strip()

    findings = inspect_git_diff_for_risks(diff_text)
    return AutomatedReviewResult(
        approved=(len(findings) == 0),
        findings=findings,
        thoughts_log=thoughts_log,
        tools_invoked=tools_invoked,
        final_summary=final_summary,
    )


if __name__ == "__main__":
    sample_report = estimate_workload_cost(
        model_id="gemini-3-flash-preview",
        num_requests=1000,
        shared_system_tokens=20_000,
        unique_user_tokens_per_req=500,
        output_tokens_per_req=250,
    )
    print(
        f"Workload Cost ({sample_report.model_id}): "
        f"Standard=${sample_report.standard_cost_usd:.2f} | "
        f"With Context Cache=${sample_report.cached_cost_usd:.2f} "
        f"({sample_report.cache_savings_percent:.1f}% saved) | "
        f"With Batch API=${sample_report.batch_cost_usd:.2f} (50% saved)"
    )
