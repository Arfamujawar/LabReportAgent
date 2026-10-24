
"""Educational explanations for laboratory results using Groq with fallback."""

import os
import json
from groq import Groq

MODE = "Groq AI with rule-based fallback"

DISCLAIMER = (
    "Educational information only. This is not a diagnosis or medical advice. "
    "Discuss your results with a qualified healthcare professional."
)

INFO = {
    "hemoglobin": (
        "Hemoglobin is the protein in red blood cells that carries oxygen.",
        "Commonly ordered in a complete blood count to check overall blood health.",
        "Hydration, altitude, pregnancy, iron intake, and the lab's method.",
    ),
    "glucose": (
        "Glucose is the main sugar in your blood and a primary energy source.",
        "Commonly ordered to check blood sugar regulation.",
        "Recent meals, fasting status, stress, illness, and some medicines.",
    ),
    "cholesterol": (
        "Cholesterol is a fatty substance carried in the blood.",
        "Commonly ordered as part of a lipid panel.",
        "Diet, fasting status, activity, genetics, and some medicines.",
    ),
    "creatinine": (
        "Creatinine is a waste product from muscle that the kidneys filter.",
        "Commonly ordered to look at kidney function.",
        "Muscle mass, hydration, diet, and some medicines.",
    ),
}


def _rule_based_explain(r):
    """Provide a local explanation if AI is unavailable."""

    text_value = getattr(r, "text_value", None)

    if text_value:
        return {
            "comparison": f"Reported result: {text_value}.",
            "what": f"{r.name} is a text-based laboratory result.",
            "why": "This result records information reported by the laboratory.",
            "factors": "Check the original report to confirm the extracted result.",
            "questions": [
                "Can you explain this result and its significance to me?",
                "Is any follow-up needed for this result?",
            ],
        }

    key = next((k for k in INFO if k in r.name.lower()), None)

    what, why, factors = INFO.get(
        key,
        (
            f"{r.name} is a laboratory measurement. "
            "A built-in explanation is not available for it yet.",
            "Your clinician orders tests based on your individual situation.",
            "Timing, hydration, medicines, and laboratory methods may influence results.",
        ),
    )

    unit = f" {r.unit}" if r.unit else ""
    low, high, value = r.low, r.high, r.value

    if value is not None and low is not None and high is not None:
        where = {
            "low": "below",
            "high": "above",
            "normal": "within",
        }.get(r.flag, "compared with")

        comparison = (
            f"Your value ({value:g}{unit}) is {where} the range printed "
            f"on your report ({low:g}-{high:g}{unit})."
        )
    else:
        comparison = "A complete numeric result or reference range is unavailable."

    questions = [
        "What does this result mean for me, given my history?",
        "Should this test be repeated, and when?",
    ]

    if r.flag in ("low", "high"):
        questions.append("Is this result something I should follow up on soon?")

    return {
        "comparison": comparison,
        "what": what,
        "why": why,
        "factors": factors,
        "questions": questions,
    }


def explain(r):
    """Generate an educational explanation, falling back safely if needed."""

    fallback = _rule_based_explain(r)
    api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        return fallback

    # Preserve text-only results without sending them to an external service.
    if getattr(r, "text_value", None):
        return fallback

    try:
        client = Groq(api_key=api_key, timeout=15.0, max_retries=0)

        # Send only the test details needed for an educational explanation.
        # Do not send patient names, account details, or the original report.
        lab_details = {
            "test_name": str(r.name),
            "value": r.value,
            "unit": str(r.unit or ""),
            "reference_low": r.low,
            "reference_high": r.high,
            "reported_flag": str(r.flag or "unknown"),
        }

        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You explain laboratory tests in plain, simple language "
                        "for patient visit preparation. This is education only, "
                        "not diagnosis or medical advice. Never diagnose, prescribe "
                        "treatment, or change the supplied result, flag, or range. "
                        "Do not infer missing information. Explain uncertainty and "
                        "encourage discussion with a qualified clinician. "
                        "Return only valid JSON with these keys: what, why, factors, "
                        "questions. what, why, and factors must be short strings. "
                        "questions must be a list of two or three short questions. "
                        "Do not include a comparison or alter the numerical result."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(lab_details),
                },
            ],
            temperature=0.2,
            max_completion_tokens=700,
        )

        content = response.choices[0].message.content
        if not content:
            return fallback

        # Extract JSON even if the model surrounds it with code fences.
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1]
            if content.endswith("```"):
                content = content[:-3].strip()

        ai = json.loads(content)

        # Keep the comparison calculated locally from the report.
        for field in ("what", "why", "factors"):
            if not isinstance(ai.get(field), str) or not ai[field].strip():
                return fallback

        questions = ai.get("questions")
        if (
            not isinstance(questions, list)
            or not 2 <= len(questions) <= 3
            or not all(isinstance(q, str) and q.strip() for q in questions)
        ):
            return fallback

        return {
            "comparison": fallback["comparison"],
            "what": ai["what"].strip(),
            "why": ai["why"].strip(),
            "factors": ai["factors"].strip(),
            "questions": [q.strip() for q in questions],
        }

    except Exception:
        # Keep the report usable even if the API fails.
        return fallback
