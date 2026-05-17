"""Main evaluation runner for the LedgerMind financial analyst chatbot.

Workflow:
  1. Load the golden dataset (tests/evaluation/golden_dataset.json).
  2. For each question, call the FastAPI /chat endpoint to get an answer.
  3. Pass each answer to the Groq judge (GroqEvaluator) for scoring.
  4. Compute MRR, hit rate, pass rate, and per-type breakdowns.
  5. Print a formatted report and save full results as JSON.

Prerequisites:
  - FastAPI backend must be running: `uv run uvicorn backend.api.main:app --reload`
  - GROQ_API_KEY must be set in the project's .env file (or as an env var).

Usage:
  uv run python -m tests.evaluation.run_eval
  uv run python -m tests.evaluation.run_eval --dataset tests/evaluation/golden_dataset.json
  uv run python -m tests.evaluation.run_eval --output results/my_run.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

from tests.evaluation.evaluator import GroqEvaluator
from tests.evaluation.metrics import compute_metrics, format_report

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger("eval.runner")

BACKEND_URL = "http://localhost:8000"
CHAT_ENDPOINT = f"{BACKEND_URL}/chat"
REQUEST_TIMEOUT = 180


def _call_chatbot(question: str) -> dict:
    """Send one question to the FastAPI /chat endpoint.

    Each question gets a fresh session_id so no conversation history bleeds
    across questions.

    Returns a dict with keys: answer, intent, sources, verified, file_url,
    plus error (str) if the call failed.
    """
    session_id = uuid.uuid4().hex
    try:
        response = requests.post(
            CHAT_ENDPOINT,
            json={"query": question, "session_id": session_id},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        return {
            "answer": "",
            "intent": "",
            "sources": [],
            "verified": False,
            "error": f"Cannot connect to {BACKEND_URL}. Is the FastAPI server running?",
        }
    except requests.exceptions.Timeout:
        return {
            "answer": "",
            "intent": "",
            "sources": [],
            "verified": False,
            "error": "Request timed out after 180 seconds.",
        }
    except requests.exceptions.RequestException as exc:
        return {
            "answer": "",
            "intent": "",
            "sources": [],
            "verified": False,
            "error": str(exc),
        }


def run_evaluation(
    dataset_path: str = "tests/evaluation/golden_dataset.json",
    output_path: str | None = None,
    groq_api_key: str | None = None,
) -> dict:
    """Run the full evaluation pipeline.

    Args:
        dataset_path: Path to the golden dataset JSON.
        output_path: Where to save results JSON. Auto-generated if None.
        groq_api_key: Groq API key. Falls back to GROQ_API_KEY env var.

    Returns:
        The metrics dict.
    """
    # --- Load dataset -----------------------------------------------------------
    dataset_file = Path(dataset_path)
    if not dataset_file.exists():
        logger.error("Golden dataset not found: %s", dataset_file)
        sys.exit(1)

    with dataset_file.open(encoding="utf-8") as f:
        golden_dataset: list[dict] = json.load(f)

    logger.info("Loaded %d questions from %s.", len(golden_dataset), dataset_file)

    # --- Init Groq judge --------------------------------------------------------
    try:
        evaluator = GroqEvaluator(api_key=groq_api_key)
        logger.info("Groq evaluator ready.")
    except ValueError as exc:
        logger.error("%s", exc)
        sys.exit(1)

    # --- Run evaluation ---------------------------------------------------------
    eval_results: list[dict] = []
    total = len(golden_dataset)

    for i, sample in enumerate(golden_dataset, start=1):
        q_id = sample["id"]
        question = sample["question"]
        logger.info("[%d/%d] Evaluating: %s", i, total, q_id)

        # Step 1: Call the chatbot.
        chatbot_response = _call_chatbot(question)

        if chatbot_response.get("error"):
            logger.error("Chatbot error for %s: %s", q_id, chatbot_response["error"])
            eval_results.append(
                {
                    "question_id": q_id,
                    "question_type": sample["question_type"],
                    "is_refusal_expected": sample["is_refusal_expected"],
                    "expected_sources": sample["expected_sources"],
                    "actual_sources": [],
                    "actual_answer": "",
                    "chatbot_intent": "",
                    "chatbot_verified": False,
                    "judge_score": 0.0,
                    "judge_verdict": "FAIL",
                    "judge_reasoning": f"Chatbot call failed: {chatbot_response['error']}",
                    "found_facts": [],
                    "missing_facts": sample["key_facts"],
                    "error": chatbot_response["error"],
                }
            )
            continue

        actual_answer = chatbot_response.get("answer", "")
        actual_sources = chatbot_response.get("sources", [])

        # Step 2: Judge the answer.
        judgement = evaluator.evaluate(
            question=question,
            expected_summary=sample["expected_answer_summary"],
            key_facts=sample["key_facts"],
            actual_answer=actual_answer,
            is_refusal_expected=sample["is_refusal_expected"],
        )

        eval_results.append(
            {
                "question_id": q_id,
                "question_type": sample["question_type"],
                "difficulty": sample["difficulty"],
                "is_refusal_expected": sample["is_refusal_expected"],
                "expected_sources": sample["expected_sources"],
                "actual_sources": actual_sources,
                "actual_answer": actual_answer,
                "chatbot_intent": chatbot_response.get("intent", ""),
                "chatbot_verified": chatbot_response.get("verified", True),
                "judge_score": judgement["score"],
                "judge_verdict": judgement["verdict"],
                "judge_reasoning": judgement["reasoning"],
                "found_facts": judgement.get("found_facts", []),
                "missing_facts": judgement.get("missing_facts", []),
            }
        )

        logger.info(
            "  → verdict=%s  score=%.2f  sources=%s",
            judgement["verdict"],
            judgement["score"],
            actual_sources,
        )

    # --- Compute metrics --------------------------------------------------------
    metrics = compute_metrics(eval_results)
    report = format_report(metrics, eval_results)
    print("\n" + report)

    # --- Save results -----------------------------------------------------------
    if output_path is None:
        results_dir = Path("tests/evaluation/results")
        results_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = str(results_dir / f"eval_{timestamp}.json")

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "run_timestamp": datetime.now().isoformat(),
                "dataset": str(dataset_file),
                "metrics": metrics,
                "results": eval_results,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    logger.info("Full results saved to: %s", output_file)
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Run LedgerMind golden dataset evaluation.")
    parser.add_argument(
        "--dataset",
        default="tests/evaluation/golden_dataset.json",
        help="Path to the golden dataset JSON file.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Path to save results JSON. Defaults to tests/evaluation/results/eval_<ts>.json.",
    )
    parser.add_argument(
        "--groq-api-key",
        default=None,
        help="Groq API key. Falls back to GROQ_API_KEY environment variable.",
    )
    args = parser.parse_args()

    run_evaluation(
        dataset_path=args.dataset,
        output_path=args.output,
        groq_api_key=args.groq_api_key,
    )


if __name__ == "__main__":
    main()
