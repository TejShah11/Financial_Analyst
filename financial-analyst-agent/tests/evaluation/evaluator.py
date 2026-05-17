"""Groq-based LLM judge for evaluating chatbot answers against the golden dataset.

The judge receives the question, the expected answer summary, a list of key facts
that MUST appear in the answer, and the actual answer produced by the chatbot.
It returns a structured verdict: a numeric score (0.0–1.0), a pass/fail label,
and the reasoning behind it.

For adversarial (refusal-expected) questions the logic is inverted: a correct
answer is one that says "I don't have data", not one that produces numbers.
"""

from __future__ import annotations

import json
import logging
import os
import re

from groq import Groq

logger = logging.getLogger(__name__)

GROQ_MODEL = "llama-3.3-70b-versatile"

_FACTUAL_JUDGE_PROMPT = """You are a strict financial analyst evaluator. Your job is to judge whether an AI chatbot's answer is CORRECT and COMPLETE relative to the expected facts.

QUESTION:
{question}

EXPECTED ANSWER SUMMARY:
{expected_summary}

KEY FACTS that must appear in the answer (exact numbers/phrases):
{key_facts}

ACTUAL ANSWER FROM CHATBOT:
{actual_answer}

Your evaluation task:
1. Check whether EACH key fact appears (or is clearly referenced) in the actual answer.
2. Score the answer from 0.0 to 1.0:
   - 1.0: All key facts present and answer is accurate
   - 0.7-0.9: Most key facts present, minor omissions
   - 0.4-0.6: Some key facts present but significant gaps or inaccuracies
   - 0.0-0.3: Most key facts missing or answer is wrong/hallucinated
3. Verdict: PASS if score >= 0.7, else FAIL.

Respond in valid JSON only (no markdown, no code fences):
{{
  "score": <float 0.0 to 1.0>,
  "verdict": "<PASS or FAIL>",
  "found_facts": ["<fact found>", ...],
  "missing_facts": ["<fact missing>", ...],
  "reasoning": "<one sentence explaining your verdict>"
}}"""

_REFUSAL_JUDGE_PROMPT = """You are a strict financial analyst evaluator. The correct behavior for this question is for the chatbot to REFUSE to answer and say it does not have the data.

QUESTION:
{question}

ACTUAL ANSWER FROM CHATBOT:
{actual_answer}

Evaluate whether the chatbot correctly refused to answer (i.e., it explicitly stated it does not have the data or the question is outside the scope of its documents).

Score:
- 1.0: Chatbot clearly stated it does not have the data / question is out of scope
- 0.5: Chatbot expressed uncertainty but still provided a partial guess
- 0.0: Chatbot hallucinated a confident answer without any data

Verdict: PASS if score >= 0.7, else FAIL.

Respond in valid JSON only (no markdown, no code fences):
{{
  "score": <float 0.0 to 1.0>,
  "verdict": "<PASS or FAIL>",
  "reasoning": "<one sentence explaining your verdict>"
}}"""


class GroqEvaluator:
    """LLM-as-judge using Groq's free-tier Llama model."""

    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or os.getenv("GROQ_API_KEY")
        if not key:
            raise ValueError(
                "GROQ_API_KEY not found. Set it in .env or pass api_key= to GroqEvaluator."
            )
        self._client = Groq(api_key=key)

    def _call(self, prompt: str) -> str:
        """Send a prompt to Groq and return the response text."""
        response = self._client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=512,
        )
        return response.choices[0].message.content.strip()

    def _parse_json(self, raw: str) -> dict:
        """Extract JSON from the model's response (strips any surrounding prose)."""
        # Try direct parse first.
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        # Extract the first {...} block if the model wrapped it in prose.
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        # Fallback: return a failure result so the run continues.
        logger.warning("Could not parse Groq judge response: %r", raw[:200])
        return {
            "score": 0.0,
            "verdict": "FAIL",
            "reasoning": f"Judge response could not be parsed: {raw[:100]}",
        }

    def evaluate(
        self,
        question: str,
        expected_summary: str,
        key_facts: list[str],
        actual_answer: str,
        is_refusal_expected: bool = False,
    ) -> dict:
        """Score one chatbot answer.

        Args:
            question: The original question asked.
            expected_summary: Short description of the correct answer.
            key_facts: Specific numbers/phrases that must appear for a pass.
            actual_answer: The chatbot's generated answer text.
            is_refusal_expected: True for out-of-scope questions where the
                correct response is to say "I don't have data."

        Returns:
            dict with keys: score (float), verdict (str), reasoning (str),
            found_facts (list, factual only), missing_facts (list, factual only).
        """
        if is_refusal_expected:
            prompt = _REFUSAL_JUDGE_PROMPT.format(
                question=question,
                actual_answer=actual_answer,
            )
        else:
            facts_block = "\n".join(f"  - {f}" for f in key_facts) or "  (none specified)"
            prompt = _FACTUAL_JUDGE_PROMPT.format(
                question=question,
                expected_summary=expected_summary,
                key_facts=facts_block,
                actual_answer=actual_answer,
            )

        raw = self._call(prompt)
        result = self._parse_json(raw)

        # Normalise to a consistent shape.
        return {
            "score": float(result.get("score", 0.0)),
            "verdict": str(result.get("verdict", "FAIL")).upper(),
            "found_facts": result.get("found_facts", []),
            "missing_facts": result.get("missing_facts", []),
            "reasoning": result.get("reasoning", ""),
        }
