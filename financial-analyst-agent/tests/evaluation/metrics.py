"""Evaluation metrics for the financial analyst RAG system.

Computes:
  - MRR  (Mean Reciprocal Rank)  — retrieval quality
  - Source Hit Rate               — whether expected source was retrieved at all
  - Answer Correctness            — Groq judge score averaged across questions
  - Pass Rate                     — fraction of questions scored >= 0.7 by the judge
  - Per-type breakdowns           — narrative / quantitative / adversarial slices
"""

from __future__ import annotations

from collections import defaultdict

from tests.evaluation.evaluator import PASS_THRESHOLD


def _reciprocal_rank(expected_sources: list[str], actual_sources: list[str]) -> float:
    """Return 1/rank of the first expected source found in actual_sources.

    Rank is 1-indexed.  Returns 0.0 if none of the expected sources appear.
    """
    for rank, source in enumerate(actual_sources, start=1):
        if source in expected_sources:
            return 1.0 / rank
    return 0.0


def compute_metrics(eval_results: list[dict]) -> dict:
    """Compute all evaluation metrics from a list of per-question result dicts.

    Each result dict is expected to have:
        question_id       str
        question_type     str   ("narrative", "quantitative", "adversarial")
        is_refusal_expected bool
        expected_sources  list[str]
        actual_sources    list[str]   — returned by the /chat endpoint
        judge_score       float       — 0.0 to 1.0 from GroqEvaluator
        judge_verdict     str         — "PASS" or "FAIL"

    Returns a dict with overall and per-type metric dicts.
    """
    # --- Retrieval metrics (exclude adversarial; they have no expected source) ---
    retrieval_results = [r for r in eval_results if not r.get("is_refusal_expected")]

    rr_values = [
        _reciprocal_rank(r["expected_sources"], r.get("actual_sources", []))
        for r in retrieval_results
    ]
    mrr = sum(rr_values) / len(rr_values) if rr_values else 0.0

    hit_rate = (
        sum(1 for rr in rr_values if rr > 0) / len(rr_values)
        if rr_values
        else 0.0
    )

    # --- Answer quality metrics (all questions) ---------------------------------
    scores = [r.get("judge_score", 0.0) for r in eval_results]
    avg_score = sum(scores) / len(scores) if scores else 0.0
    pass_rate = (
        sum(1 for r in eval_results if r.get("judge_score", 0.0) >= PASS_THRESHOLD)
        / len(eval_results)
        if eval_results
        else 0.0
    )

    # --- Per-type breakdown ------------------------------------------------------
    by_type: dict[str, list[dict]] = defaultdict(list)
    for r in eval_results:
        by_type[r.get("question_type", "unknown")].append(r)

    type_metrics: dict[str, dict] = {}
    for q_type, group in by_type.items():
        grp_scores = [r.get("judge_score", 0.0) for r in group]
        grp_passes = sum(1 for r in group if r.get("judge_score", 0.0) >= PASS_THRESHOLD)
        retrieval_group = [r for r in group if not r.get("is_refusal_expected")]
        grp_rr = [
            _reciprocal_rank(r["expected_sources"], r.get("actual_sources", []))
            for r in retrieval_group
        ]
        type_metrics[q_type] = {
            "count": len(group),
            "avg_score": round(sum(grp_scores) / len(grp_scores), 4) if grp_scores else 0.0,
            "pass_rate": round(grp_passes / len(group), 4) if group else 0.0,
            "mrr": round(sum(grp_rr) / len(grp_rr), 4) if grp_rr else None,
        }

    return {
        "total_questions": len(eval_results),
        "mrr": round(mrr, 4),
        "source_hit_rate": round(hit_rate, 4),
        "avg_judge_score": round(avg_score, 4),
        "pass_rate": round(pass_rate, 4),
        "by_type": type_metrics,
    }


def format_report(metrics: dict, eval_results: list[dict]) -> str:
    """Render a human-readable evaluation report."""
    lines: list[str] = []

    lines.append("=" * 65)
    lines.append("  LEDGERMIND — RAG EVALUATION REPORT")
    lines.append("=" * 65)
    lines.append(f"  Total questions evaluated : {metrics['total_questions']}")
    lines.append(f"  Mean Reciprocal Rank (MRR): {metrics['mrr']:.4f}")
    lines.append(f"  Source Hit Rate           : {metrics['source_hit_rate']:.2%}")
    lines.append(f"  Avg Groq Judge Score      : {metrics['avg_judge_score']:.4f} / 1.0")
    lines.append(f"  Pass Rate (score >= 0.7)  : {metrics['pass_rate']:.2%}")
    lines.append("")

    lines.append("  ── Per-type Breakdown ──────────────────────────────────")
    for q_type, m in metrics["by_type"].items():
        mrr_str = f"{m['mrr']:.4f}" if m["mrr"] is not None else "N/A"
        lines.append(
            f"  {q_type:<14}  n={m['count']}  "
            f"score={m['avg_score']:.2f}  "
            f"pass={m['pass_rate']:.0%}  "
            f"mrr={mrr_str}"
        )
    lines.append("")

    lines.append("  ── Per-question Detail ─────────────────────────────────")
    for r in eval_results:
        verdict_icon = "✓" if r.get("judge_verdict") == "PASS" else "✗"
        rr = (
            _reciprocal_rank(r["expected_sources"], r.get("actual_sources", []))
            if not r.get("is_refusal_expected")
            else None
        )
        rr_str = f"rr={rr:.2f}" if rr is not None else "rr=N/A"
        lines.append(
            f"  {verdict_icon} [{r['question_id']:<35}]  "
            f"score={r.get('judge_score', 0.0):.2f}  {rr_str}"
        )
        if r.get("judge_reasoning"):
            lines.append(f"      {r['judge_reasoning']}")
    lines.append("=" * 65)

    return "\n".join(lines)
