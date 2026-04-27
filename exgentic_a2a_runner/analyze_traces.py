#!/usr/bin/env python3
"""Analyze Phoenix agent traces from JSON input.

Reads the raw GraphQL response (JSON) from stdin or a file,
extracts Agent.Session spans and their child spans,
and prints a grouped timing report.

Usage:
    echo "$JSON" | python3 analyze_traces.py
    python3 analyze_traces.py traces.json
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class TraceRecord:
    """Aggregated data for a single Agent.Session trace."""

    session_id: str
    agent_name: str
    benchmark_name: str
    model: str
    num_parallel: int
    status: str
    total_latency_s: float
    evaluation_result: bool | None = None

    # Timing from child spans (seconds)
    session_creation_s: float = 0.0
    agent_call_s: float = 0.0
    evaluation_s: float = 0.0
    llm_total_s: float = 0.0
    tool_total_s: float = 0.0
    time_to_first_obs_s: float = 0.0
    llm_count: int = 0
    tool_count: int = 0
    llm_input_tokens: int = 0
    llm_output_tokens: int = 0


def parse_attrs(node: dict) -> dict:
    """Parse span attributes, handling JSON string or dict."""
    attrs = node.get("attributes", {})
    if isinstance(attrs, str):
        try:
            return json.loads(attrs)
        except (json.JSONDecodeError, TypeError):
            return {}
    return attrs


def parse_traces(data: dict) -> list[TraceRecord]:
    """Parse the full traces response into TraceRecords."""
    traces_data = data.get("traces", [])
    records = []

    for trace in traces_data:
        spans = trace.get("spans", [])
        if not spans:
            continue

        # Find the Agent.Session root span
        root = None
        children = []
        for s in spans:
            if s.get("name") == "Agent.Session":
                root = s
            else:
                children.append(s)

        if root is None:
            continue

        root_attrs = parse_attrs(root)
        meta = root_attrs.get("metadata", {})
        meta_data = root_attrs.get("meta_data", {})

        # Extract grouping fields
        agent_name = meta.get("agent_name", "unknown")
        benchmark_name = meta.get("benchmark_name", "unknown")
        num_parallel = int(meta.get("num_parallel_tasks", 0))
        session_id = meta.get("session_id", "unknown")
        status = root.get("statusCode", "UNSET")
        evaluation_result = meta.get("evaluation_result")

        # Model from the invoke_agent child span or root metadata
        model = "unknown"
        for s in children:
            if s.get("name", "").startswith("invoke_agent"):
                child_attrs = parse_attrs(s)
                model = (
                    child_attrs.get("gen_ai", {}).get("request", {}).get("model")
                    or child_attrs.get("llm", {}).get("model_name")
                    or "unknown"
                )
                break

        record = TraceRecord(
            session_id=session_id,
            agent_name=agent_name,
            benchmark_name=benchmark_name,
            model=model,
            num_parallel=num_parallel,
            status=status,
            total_latency_s=(root.get("latencyMs") or 0) / 1000.0,
            evaluation_result=evaluation_result,
        )

        # Extract timing from child spans
        invoke_start = None
        initial_obs_start = None

        root_span_id = root.get("context", {}).get("spanId")
        for s in children:
            name = s.get("name", "")
            latency_s = (s.get("latencyMs") or 0) / 1000.0

            if name == "MCP.CreateSession":
                record.session_creation_s = latency_s
            elif name == "Agent.Call":
                record.agent_call_s = latency_s
            elif name == "Evaluator.Evaluate":
                record.evaluation_s = latency_s
            elif name.startswith("chat "):
                record.llm_total_s += latency_s
                record.llm_count += 1
                child_attrs = parse_attrs(s)
                token_count = child_attrs.get("llm", {}).get("token_count", {})
                record.llm_input_tokens += int(token_count.get("prompt", 0) or 0)
                record.llm_output_tokens += int(token_count.get("completion", 0) or 0)
            elif name == "execute_tool initial_observation":
                initial_obs_start = s.get("startTime")
            elif name.startswith("execute_tool "):
                record.tool_total_s += latency_s
                record.tool_count += 1

            if name.startswith("invoke_agent"):
                invoke_start = s.get("startTime")

        # Time to first observation: invoke_agent start → initial_observation start
        if invoke_start and initial_obs_start:
            try:
                t_invoke = datetime.fromisoformat(invoke_start.replace("Z", "+00:00"))
                t_obs = datetime.fromisoformat(initial_obs_start.replace("Z", "+00:00"))
                record.time_to_first_obs_s = max((t_obs - t_invoke).total_seconds(), 0.0)
            except (ValueError, TypeError):
                pass

        # Fall back to metadata durations if child spans not found
        if record.agent_call_s == 0:
            record.agent_call_s = float(meta_data.get("agent_call_duration_seconds", 0))
        if record.evaluation_s == 0:
            record.evaluation_s = float(meta.get("evaluation_duration_seconds", 0))

        records.append(record)

    return records


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = min(int(len(s) * p), len(s) - 1)
    return s[idx]


def avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def format_time(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, AttributeError):
        return iso[:19].replace("T", " ") if iso else ""


def print_report(records: list[TraceRecord]) -> None:
    if not records:
        print("No Agent.Session traces found.")
        return

    # Group by (agent_name, benchmark_name, model, num_parallel)
    groups: dict[tuple, list[TraceRecord]] = defaultdict(list)
    for r in records:
        key = (r.agent_name, r.benchmark_name, r.model, r.num_parallel)
        groups[key].append(r)

    for key, traces in sorted(groups.items()):
        agent, benchmark, model, num_parallel = key
        n = len(traces)
        errors = sum(1 for t in traces if t.status == "ERROR")
        eval_success = sum(1 for t in traces if t.evaluation_result is True)

        print("=" * 90)
        print(f"Agent: {agent}  |  Benchmark: {benchmark}  |  Model: {model}  |  Parallel: {num_parallel}")
        print("=" * 90)
        print()

        # Counts
        print(f"  Traces:              {n}")
        print(f"  Errors:              {errors}")
        print(f"  Eval Success:        {eval_success}/{n} ({eval_success / n * 100:.0f}%)")
        print()

        # Timing breakdown
        creation_times = [t.session_creation_s for t in traces]
        agent_times = [t.agent_call_s for t in traces]
        eval_times = [t.evaluation_s for t in traces]
        llm_times = [t.llm_total_s for t in traces]
        tool_times = [t.tool_total_s for t in traces]
        ttfo_times = [t.time_to_first_obs_s for t in traces]
        total_times = [t.total_latency_s for t in traces]
        llm_counts = [t.llm_count for t in traces]
        tool_counts = [t.tool_count for t in traces]

        print(f"  {'Timing':<30s} {'Avg':>9s} {'P50':>9s} {'P95':>9s} {'Min':>9s} {'Max':>9s}")
        print(f"  {'-' * 30} {'-' * 9} {'-' * 9} {'-' * 9} {'-' * 9} {'-' * 9}")

        def row(label: str, values: list[float]) -> None:
            if not values or all(v == 0 for v in values):
                print(f"  {label:<30s} {'n/a':>9s}")
                return
            print(
                f"  {label:<30s} {avg(values):>9.2f} {percentile(values, 0.5):>9.2f} "
                f"{percentile(values, 0.95):>9.2f} {min(values):>9.2f} {max(values):>9.2f}"
            )

        row("Total (s)", total_times)
        row("Session Creation (s)", creation_times)
        row("Agent Call (s)", agent_times)
        row("  Time to 1st Obs (s)", ttfo_times)
        row("  LLM Calls (s)", llm_times)
        row("  Tool Calls (s)", tool_times)
        row("Evaluation (s)", eval_times)

        print()
        print(f"  Avg LLM calls/session:     {avg(llm_counts):.1f}")
        print(f"  Avg Tool calls/session:    {avg(tool_counts):.1f}")
        if any(llm_times):
            print(f"  Avg LLM call latency:      {avg([t.llm_total_s / t.llm_count for t in traces if t.llm_count > 0]):.2f}s")
        
        # Calculate percentage of agent call time spent on LLM vs Tool
        llm_pcts = [(t.llm_total_s / t.agent_call_s * 100) if t.agent_call_s > 0 else 0 for t in traces]
        tool_pcts = [(t.tool_total_s / t.agent_call_s * 100) if t.agent_call_s > 0 else 0 for t in traces]
        if any(llm_pcts):
            print(f"  Avg % time on LLM calls:   {avg(llm_pcts):.1f}%")
        if any(tool_pcts):
            print(f"  Avg % time on Tool calls:  {avg(tool_pcts):.1f}%")
        
        input_tokens = [t.llm_input_tokens for t in traces]
        output_tokens = [t.llm_output_tokens for t in traces]
        if any(input_tokens):
            print(f"  Avg LLM input tokens:      {avg(input_tokens):.0f}")
        if any(output_tokens):
            print(f"  Avg LLM output tokens:     {avg(output_tokens):.0f}")
        if any(input_tokens) or any(output_tokens):
            print(f"  Avg LLM total tokens:      {avg([i + o for i, o in zip(input_tokens, output_tokens)]):.0f}")
        print()

    # Individual traces
    print("=" * 140)
    print("Individual Traces")
    print("=" * 140)
    print()
    header = (
        f"{'Agent':<20s} {'Benchmark':<15s} {'Model':<30s} {'Par':>3s} "
        f"{'Session ID':<38s} {'Stat':<5s} {'Eval':<4s} "
        f"{'Total':>6s} {'Crt':>5s} {'Agt':>6s} {'TTFO':>5s} "
        f"{'LLM':>6s} {'LLM%':>5s} {'Tool':>6s} {'Tool%':>5s} {'Eval':>5s}"
    )
    print(header)
    print("-" * len(header))

    for r in records:
        eval_str = "pass" if r.evaluation_result is True else "fail" if r.evaluation_result is False else "?"
        llm_pct = (r.llm_total_s / r.agent_call_s * 100) if r.agent_call_s > 0 else 0
        tool_pct = (r.tool_total_s / r.agent_call_s * 100) if r.agent_call_s > 0 else 0
        print(
            f"{r.agent_name:<20s} {r.benchmark_name:<15s} {r.model:<30s} {r.num_parallel:>3d} "
            f"{r.session_id:<38s} {r.status:<5s} {eval_str:<4s} "
            f"{r.total_latency_s:>6.1f} {r.session_creation_s:>5.1f} {r.agent_call_s:>6.1f} {r.time_to_first_obs_s:>5.1f} "
            f"{r.llm_total_s:>6.1f} {llm_pct:>5.1f} {r.tool_total_s:>6.1f} {tool_pct:>5.1f} {r.evaluation_s:>5.1f}"
        )

    print()
    print("All times in seconds. LLM% and Tool% show percentage of Agent call time.")


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] != "-":
        with open(sys.argv[1]) as f:
            raw = json.load(f)
    else:
        raw = json.load(sys.stdin)

    records = parse_traces(raw)
    print_report(records)
    return 0


if __name__ == "__main__":
    sys.exit(main())
