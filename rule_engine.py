"""Rule engine implementing EPD risk checks.

Step 1: EPD existence -> if no url => Red
Step 2: URL accessibility -> if relative path => Yellow
Step 3: Validity verifiability -> add advisory note (manual verification)

Final label consolidation prefers highest risk of triggered checks.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple


def _is_absolute_url(url: str) -> bool:
    lowered = url.strip().lower()
    return lowered.startswith("http://") or lowered.startswith("https://")


def evaluate_product(product: Dict[str, Any]) -> Tuple[str, List[str], List[str]]:
    """Evaluate a single product and return (risk_level, reasons, advisories).

    Product is expected to have optional keys: 'epd_url', 'epd_issue_date'.
    Missing keys are treated as None.
    """
    reasons: List[str] = []
    advisories: List[str] = []

    epd_url = product.get("epd_url") or None
    epd_issue_date = product.get("epd_issue_date") or None

    # Step 1: EPD existence
    if not epd_url or (isinstance(epd_url, str) and not epd_url.strip()):
        reasons.append("Missing EPD file link")
        risk_level = "Red"
        # Still advise manual verification generally
        advisories.append("Please manually verify the validity period of all EPDs")
    else:
        is_abs = _is_absolute_url(epd_url)
        has_issue_date = bool(epd_issue_date and str(epd_issue_date).strip())

        if not is_abs and not has_issue_date:
            risk_level = "Yellow"
            reasons.append("EPD link is relative and issue date is missing")
        elif not is_abs:
            risk_level = "Yellow"
            reasons.append("EPD link is a relative path and may be inaccessible")
        elif not has_issue_date:
            risk_level = "Yellow"
            reasons.append("EPD issue date is missing; validity cannot be verified")
        else:
            risk_level = "Green"
            reasons.append(
                "EPD link is accessible; please verify the issue date manually"
            )

        advisories.append("Please manually verify the validity period of all EPDs")

    # Future extension (commented):
    # If epd_issue_date exists and >5 years, escalate to Red.
    # if epd_issue_date:
    #     try:
    #         issue_dt = datetime.fromisoformat(epd_issue_date[:10])
    #         if datetime.utcnow() - issue_dt > timedelta(days=5*365):
    #             reasons.append("EPD issue date is older than 5 years: may be expired")
    #             risk_level = "Red"
    #     except Exception:
    #         advisories.append("Unable to parse epd_issue_date; please verify validity manually")

    return risk_level, reasons, advisories
