
"""Extract text from lab reports and parse supported laboratory results."""

import os
import re

try:
    import pymupdf as fitz
except ImportError:
    try:
        import fitz
    except ImportError:
        fitz = None

try:
    import pytesseract
    from PIL import Image, ImageOps, ImageEnhance, ImageFilter
except ImportError:
    pytesseract = None
    Image = None
    ImageOps = None
    ImageEnhance = None
    ImageFilter = None


SUPPORTED_TYPES = {
    "pdf", "jpg", "jpeg", "png", "bmp", "tif", "tiff", "webp"
}

IMAGE_TYPES = {
    "jpg", "jpeg", "png", "bmp", "tif", "tiff", "webp"
}


# Supports examples such as:
# RDW 12.00 Normal 11.60 - 14.00 %
# Neutrophils 60 Normal 50 - 62 %
# Hemoglobin 13.5 g/dL 12.0 - 15.5
# Glucose 110 mg/dL 70 - 100


LINE = re.compile(
    r"^\s*"
    r"([A-Za-z][A-Za-z0-9 ,()/%µμ^.+_-]{0,59}?)"
    r"\s+([-+]?\d+(?:\.\d+)?)"
    r"(?:\s+(?:Normal|High|Low|Borderline|Abnormal|H|L|N))?"
    r"\s+"
    r"(?:(%|[A-Za-z0-9µμ][A-Za-z0-9µμ/^.-]*)\s+)?"
    r"([-+]?\d+(?:\.\d+)?)"
    r"\s*(?:-|–|—|to)\s*"
    r"([-+]?\d+(?:\.\d+)?)"
    r"(?:\s*(%|[A-Za-z0-9µμ][A-Za-z0-9µμ/^.-]*))?"
    r"\s*$",
    re.IGNORECASE,
)




def ocr_available():
    """Return True if Tesseract OCR is installed and accessible."""
    if pytesseract is None or Image is None:
        return False

    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def _ocr(image):
    """Extract text from an image using improved OCR preprocessing."""
    if not ocr_available():
        raise RuntimeError(
            "Tesseract OCR is unavailable. Install Tesseract and pytesseract."
        )

    image = ImageOps.exif_transpose(image).convert("RGB")

    width, height = image.size
    if width < 1800:
        scale = 1800 / width
        image = image.resize(
            (1800, int(height * scale)),
            Image.Resampling.LANCZOS,
        )

    image = ImageOps.grayscale(image)
    image = ImageOps.autocontrast(image)
    image = ImageEnhance.Contrast(image).enhance(1.5)
    image = image.filter(ImageFilter.SHARPEN)

    return pytesseract.image_to_string(
        image,
        config="--oem 3 --psm 6",
    )


def extract_text(file_path, kind="pdf"):
    """Extract text from a PDF or supported image."""
    warnings = []

    kind = (kind or "").lower().strip().lstrip(".")
    extension = os.path.splitext(file_path)[1].lower().lstrip(".")
    file_type = kind if kind in SUPPORTED_TYPES else extension

    if file_type in IMAGE_TYPES:
        if not ocr_available():
            return "", [
                "Image text could not be extracted because OCR is unavailable."
            ]

        try:
            with Image.open(file_path) as image:
                text = _ocr(image)

            warnings.append(
                "OCR was used. Verify extracted values against the original report."
            )
            return text, warnings

        except Exception as exc:
            return "", [f"Could not read the image: {exc}"]

    if file_type == "pdf":
        if fitz is None:
            return "", [
                "PDF extraction is unavailable because PyMuPDF is not installed."
            ]

        try:
            with fitz.open(file_path) as document:
                text = "\n".join(
                    page.get_text("text") for page in document
                ).strip()

                if text:
                    return text, warnings

                if not ocr_available():
                    return "", [
                        "This PDF appears to be scanned, but OCR is unavailable."
                    ]

                ocr_pages = []

                for page in document:
                    pixmap = page.get_pixmap(
                        matrix=fitz.Matrix(2, 2),
                        alpha=False,
                    )

                    image = Image.frombytes(
                        "RGB",
                        (pixmap.width, pixmap.height),
                        pixmap.samples,
                    )

                    ocr_pages.append(_ocr(image))

                warnings.append(
                    "OCR was used. Verify extracted values against the original report."
                )

                return "\n".join(ocr_pages), warnings

        except Exception as exc:
            return "", [f"Could not read the PDF: {exc}"]

    return "", [
        f"Unsupported file type ({file_type or 'unknown'}). "
        "Please upload a PDF or a supported image."
    ]


def parse_results(text):
    """Parse supported numeric results and recognised blood-group results."""
    results = []
    skipped = 0
    lines = (text or "").splitlines()
    processed = set()

    blood_patterns = [
        (
            re.compile(
                r"^\s*(ABO\s+Group|Blood\s+Group)"
                r"\s*[:\-]?\s*(A\s*B|AB|A|B|O)\s*$",
                re.IGNORECASE,
            ),
            "group",
        ),
        (
            re.compile(
                r"^\s*(Rh\s+Factor|Rhesus\s+Factor)"
                r"\s*[:\-]?\s*"
                r"(Positive\s*\(\s*\+\s*\)|"
                r"Negative\s*\(\s*-\s*\)|"
                r"Positive|Negative|\+|-)\s*$",
                re.IGNORECASE,
            ),
            "rh",
        ),
    ]

    def add_text_result(name, value):
        results.append({
            "name": name,
            "value": None,
            "text_value": re.sub(r"\s+", " ", value).strip(),
            "unit": "",
            "low": None,
            "high": None,
            "flag": "normal",
        })

    for i, raw_line in enumerate(lines):
        line = raw_line.strip()

        if not line or i in processed:
            continue

        # Handle reports where the ABO label and result are on separate lines.
        if re.fullmatch(r"ABO\s+Group", line, re.IGNORECASE):
            for j in range(i + 1, min(i + 5, len(lines))):
                candidate = lines[j].strip()

                if re.fullmatch(r"A\s*B|AB|A|B|O", candidate, re.IGNORECASE):
                    add_text_result("ABO Group", candidate.upper())
                    processed.add(j)
                    break

            continue

        # Handle reports where the Rh label and result are on separate lines.
        if re.fullmatch(
            r"(Rh|Rhesus)\s+Factor", line, re.IGNORECASE
        ):
            for j in range(i + 1, min(i + 5, len(lines))):
                candidate = lines[j].strip()

                if re.fullmatch(
                    r"Positive\s*\(\s*\+\s*\)|"
                    r"Negative\s*\(\s*-\s*\)|"
                    r"Positive|Negative|\+|-",
                    candidate,
                    re.IGNORECASE,
                ):
                    add_text_result("Rh Factor", candidate)
                    processed.add(j)
                    break

            continue

        # Handle blood-group results written on a single line.
        found_blood = False

        for pattern, result_type in blood_patterns:
            match = pattern.match(line)

            if not match:
                continue

            if result_type == "group":
                label = (
                    "ABO Group"
                    if match.group(1).lower().startswith("abo")
                    else "Blood Group"
                )
            else:
                label = "Rh Factor"

            add_text_result(label, match.group(2))
            found_blood = True
            break

        if found_blood:
            continue

        # Handle numeric results with reference ranges.
        match = LINE.match(line)

        if not match:
            if re.search(r"\d", line) and len(line) > 8:
                skipped += 1
            continue

        name, value, unit_before, low, high, unit_after = match.groups()
        unit = unit_before or unit_after or ""

        try:
            value = float(value)
            low = float(low)
            high = float(high)
        except (ValueError, TypeError):
            skipped += 1
            continue

        if low > high:
            skipped += 1
            continue

        if value < low:
            flag = "low"
        elif value > high:
            flag = "high"
        else:
            flag = "normal"

        results.append({
            "name": name.strip(),
            "value": value,
            "text_value": None,
            "unit": unit.strip(),
            "low": low,
            "high": high,
            "flag": flag,
        })

    warnings = []

    if skipped:
        warnings.append(
            f"{skipped} line(s) could not be confidently read. "
            "Check the original report."
        )

    if not results:
        warnings.append(
            "No supported results were recognised. Check the original report "
            "or try a clearer image."
        )

    return results, warnings
