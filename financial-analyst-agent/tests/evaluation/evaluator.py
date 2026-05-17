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

# Score threshold above which an answer is considered a PASS.
# Determined in Python — we never rely on the LLM to emit the verdict itself
# because it is inconsistent (e.g. it may output score=0.70 but verdict=FAIL).
PASS_THRESHOLD = 0.6

_FACTUAL_JUDGE_PROMPT = """You are a financial fact-checker. Your ONLY job is to check whether the chatbot's answer contains the correct core facts.

QUESTION:
{question}

CORE FACTS TO VERIFY (the answer must contain these values):
{key_facts}

CHATBOT'S ANSWER:
{actual_answer}

RULES — read carefully before scoring:
1. Focus ONLY on whether each core fact is present and numerically correct.
2. Ignore everything else: markdown, citations, footnotes, extra context, caveats, or verbose phrasing.
3. Number formats are EQUIVALENT — treat all of these as the same value:
   - "5,076 million" = "5,076" = "5.1 billion" = "$5.1 bn" = "approximately 5 billion"
   - "20.8%" = "20.82%" = "~21%" = "around 20.8 percent"
   - "1,251.20" = "1251.20" = "₹1,251" = "Rs 1,251.20"
4. If a fact is stated correctly in the answer (even with a different format), count it as FOUND.
5. Only mark a fact as MISSING if the answer completely omits it OR states a clearly wrong value.

Scoring guide:
- 1.0 : All core facts found and correct
- 0.8 : All core facts found, minor format difference only
- 0.6 : Most core facts found; one secondary fact missing but the primary answer is right
- 0.3 : Primary fact is missing or clearly wrong
- 0.0 : Answer is completely off-topic or hallucinated

Return ONLY valid JSON (no markdown, no code fences):
{{
  "score": <float 0.0 to 1.0>,
  "found_facts": ["<fact>", ...],
  "missing_facts": ["<fact>", ...],
  "reasoning": "<one sentence: what was correct and what, if anything, was wrong>"
}}"""

_REFUSAL_JUDGE_PROMPT = """You are evaluating whether a financial chatbot correctly declined to answer an out-of-scope question.

QUESTION (out of scope — the correct response is to say "I don't have this data"):
{question}

CHATBOT'S ANSWER:
{actual_answer}

Check: Did the chatbot explicitly state it does not have the data / the question is outside its documents?

Scoring:
- 1.0 : Chatbot clearly said it does not have the data and did not guess
- 0.6 : Chatbot expressed uncertainty but gave a cautious partial answer
- 0.0 : Chatbot confidently hallucinated an answer with no disclaimer

Return ONLY valid JSON (no markdown, no code fences):
{{
  "score": <float 0.0 to 1.0>,
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

        score = float(result.get("score", 0.0))
        # Derive PASS/FAIL in Python so the verdict is deterministic regardless
        # of what the LLM chooses to emit (it is sometimes inconsistent).
        verdict = "PASS" if score >= PASS_THRESHOLD else "FAIL"

        return {
            "score": score,
            "verdict": verdict,
            "found_facts": result.get("found_facts", []),
            "missing_facts": result.get("missing_facts", []),
            "reasoning": result.get("reasoning", ""),
        }
