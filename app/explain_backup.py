
"""Rule-based educational explanations for laboratory results."""

MODE = "Demo mode: rule-based educational text. No AI model was called."

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


def explain(r):
    """Return a plain-language explanation for one result."""

    # Handle text results, such as blood group and Rh factor.
    text_value = getattr(r, "text_value", None)

    if text_value:
        return {
            "comparison": f"Reported result: {text_value}.",
            "what": f"{r.name} is a text-based laboratory result.",
            "why": "This result records information reported by the laboratory.",
            "factors": (
                "Check the original report to confirm the extracted result."
            ),
            "questions": [
                "Can you explain this result and its significance to me?",
                "Is any follow-up needed for this result?",
            ],
        }

    # Handle numeric results.
    key = next(
        (k for k in INFO if k in r.name.lower()),
        None,
    )

    what, why, factors = INFO.get(
        key,
        (
            f"{r.name} is a laboratory measurement. "
            "A built-in explanation is not available for it yet.",
            "Your clinician orders tests based on your individual situation.",
            "Many factors can influence results, including timing, hydration, "
            "medicines, and laboratory methods.",
        ),
    )

    unit = f" {r.unit}" if r.unit else ""
    low = r.low
    high = r.high
    value = r.value

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
        comparison = (
            "A complete numeric result or reference range is unavailable."
        )

    questions = [
        "What does this result mean for me, given my history?",
        "Should this test be repeated, and when?",
    ]

    if r.flag in ("low", "high"):
        questions.append(
            "Is this result something I should follow up on soon?"
        )

    return {
        "comparison": comparison,
        "what": what,
        "why": why,
        "factors": factors,
        "questions": questions,
    }
