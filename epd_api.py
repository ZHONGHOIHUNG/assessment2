"""EPD Screener API blueprint.

Endpoints:
 - POST /api/epd/scan (multipart CSV or JSON ids)
 - GET  /api/epd/scan/<scan_id>
 - GET  /api/epd/export/<scan_id>?format=csv
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any, Dict, List

from flask import Blueprint, jsonify, request, current_app, Response

from db import db
from models import Scan, ScanResult
from rule_engine import evaluate_product


epd_bp = Blueprint("epd", __name__, url_prefix="/api/epd")


def _is_http_url(s: str) -> bool:
    return isinstance(s, str) and s.lower().startswith(("http://", "https://"))


def _is_image_url(s: str) -> bool:
    if not isinstance(s, str):
        return False
    lowered = s.lower()
    return lowered.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg"))


def _extract_first_image_url(product: Dict[str, Any]) -> str | None:
    """Try to find a representative image URL or a relative path in product."""
    if not product:
        return None

    candidates: list[str] = []

    def push(val: Any):
        if isinstance(val, str) and val.strip():
            candidates.append(val.strip())

    def extract_from_array(arr: Any):
        if not arr:
            return
        if isinstance(arr, list):
            for x in arr:
                if isinstance(x, str):
                    push(x)
                elif isinstance(x, dict):
                    for k in ("url", "href", "src", "file", "image"):
                        v = x.get(k)
                        push(v)

    # Common single fields
    for key in (
        "image",
        "image_url",
        "product_image",
        "main_image",
        "thumbnail",
        "photo",
    ):
        push(product.get(key))

    # Common arrays and nested arrays
    for key in (
        "images",
        "product_images",
        "gallery",
        "photos",
    ):
        extract_from_array(product.get(key))

    media = product.get("media") or {}
    extract_from_array(media.get("images"))
    assets = product.get("assets") or {}
    extract_from_array(assets.get("images"))
    extract_from_array(product.get("attachments"))

    # Pick the first usable candidate
    for url in candidates:
        if _is_http_url(url) and _is_image_url(url):
            return url
        # Relative S3-style product path
        if isinstance(url, str) and url.startswith(("/products/", "products/", "/media/products/", "media/products/")) and _is_image_url(url):
            rel = url if url.startswith("/") else f"/{url}"
            return f"/api/proxy-image?path={rel}"

    return None


def _text_contains_any(text: str, keywords: list[str]) -> bool:
    t = (text or "").lower()
    return any(k in t for k in keywords)


def _detect_cert_state(product: Dict[str, Any]) -> tuple[bool, bool]:
    """Heuristically detect certificate presence and EPD certificate.

    Returns: (has_any_certificate, has_epd_certificate)
    """
    if not product:
        return False, False

    # 1) Direct boolean flag
    has_flag = bool(product.get("has_certifications"))

    # 2) Array of certifications
    certs = product.get("certifications") or []
    has_array = bool(certs)

    # 3) Known URL fields indicating certificates
    url_fields = [
        "certificate_url",
        "certification_url",
        "green_tag_url",
        "greentag_url",
        "hpd_url",
    ]
    has_url = any(bool(product.get(f)) for f in url_fields)

    # 4) Textual keyword search across likely text fields
    text_fields = [
        "product_name",
        "product_description",
        "long_description",
        "description",
        "title",
        "certifications_text",
        "notes",
    ]
    combined_text = " ".join(str(product.get(f) or "") for f in text_fields)

    general_keywords = [
        "greentag",
        "green tag",
        "geca",
        "greenguard",
        "bifma",
        "afrdi",
        "cradle to cradle",
        "c2c",
        "declare",
        "hpd",
        "health product declaration",
        "fsc",
        "pefc",
        "responsible wood",
        "responsible steel",
        "oeko-tex",
        "scs indoor advantage",
        "certificate",
        "certified",
        "certification",
        "ecolabel",
        "green rate",
        "health rate",
        "lca rate",
    ]
    epd_keywords = [
        "epd",
        "environmental product declaration",
        "iso 14025",
        "en 15804",
        "ibu",
        "epd australasia",
        "epd international",
        "environdec",
    ]

    # From certifications array names
    cert_names = []
    for c in certs:
        name = c.get("certification") or c.get("name") or ""
        cert_names.append(str(name))
    names_text = " ".join(cert_names)

    has_general_by_text = _text_contains_any(
        combined_text, general_keywords
    ) or _text_contains_any(names_text, general_keywords)
    has_epd_by_text = _text_contains_any(
        combined_text, epd_keywords
    ) or _text_contains_any(names_text, epd_keywords)

    has_any = has_flag or has_array or has_url or has_general_by_text

    # EPD-specific also treat explicit epd_url as evidence
    epd_url = product.get("epd_url")
    has_epd = bool(epd_url) or has_epd_by_text

    return bool(has_any), bool(has_epd)


def _normalize_ids_from_csv(file_storage) -> List[str]:
    """Parse CSV and extract product ids. Accepts columns: product_id, id, or first column."""
    content = file_storage.read()
    # Reset stream for safety (not strictly needed after read())
    stream = io.StringIO(content.decode("utf-8", errors="ignore"))
    reader = csv.DictReader(stream)
    ids: List[str] = []
    if reader.fieldnames:
        fieldnames_lower = [f.lower() for f in reader.fieldnames]
        for row in reader:
            # Prefer explicit id columns
            val = None
            for key in ("product_id", "id"):
                if key in fieldnames_lower:
                    # Find actual cased key
                    k = reader.fieldnames[fieldnames_lower.index(key)]
                    val = (row.get(k) or "").strip()
                    break
            if val is None:
                # Fallback: take first column value
                first_key = reader.fieldnames[0]
                val = (row.get(first_key) or "").strip()
            if val:
                ids.append(val)
    else:
        # No header: read simple lines
        stream.seek(0)
        for line in stream:
            line = line.strip()
            if line:
                ids.append(line)
    return ids


def _find_product_by_id(product_id: str) -> Dict[str, Any] | None:
    """Lookup product by multiple possible id fields."""
    # Access the global indexer from app module
    try:
        from app import indexer as global_indexer  # type: ignore
    except Exception:
        global_indexer = None
    if not global_indexer or not getattr(global_indexer, "products", None):
        return None

    target = str(product_id)
    # Accept numeric or string id, and alternate keys
    candidate_keys = ["id", "product_id", "sku", "code"]
    for p in global_indexer.products:
        for k in candidate_keys:
            if k in p and str(p.get(k)) == target:
                return p
    return None


@epd_bp.post("/scan")
def create_scan():
    """Create a new scan from uploaded CSV or JSON list of ids.

    Accepts:
    - multipart/form-data with file field name 'file' (CSV)
    - application/json: { "product_ids": ["..."] }
    """
    product_ids: List[str] = []

    # Ensure index and products are loaded
    try:
        from app import init_search_system  # type: ignore
        init_search_system()
    except Exception:
        pass

    if request.content_type and request.content_type.startswith("multipart/form-data"):
        if "file" not in request.files:
            return jsonify({"error": "Missing file field 'file'"}), 400
        try:
            product_ids = _normalize_ids_from_csv(request.files["file"])[:5000]
        except Exception as e:
            return jsonify({"error": f"CSV parse failed: {e}"}), 400
    else:
        data = request.get_json(silent=True) or {}
        product_ids = [
            str(x).strip() for x in data.get("product_ids", []) if str(x).strip()
        ][:5000]
        if not product_ids:
            return (
                jsonify({"error": "Missing product IDs (CSV or JSON: product_ids)"}),
                400,
            )

    # Create Scan record
    scan = Scan(source="local_index", input_count=len(product_ids))
    db.session.add(scan)
    db.session.flush()

    high = med = low = 0
    results_payload: List[dict] = []

    for pid in product_ids:
        product = _find_product_by_id(pid) or {}
        epd_url = product.get("epd_url")
        epd_issue_date = product.get("epd_issue_date")
        has_certs, has_epd_cert = _detect_cert_state(product)
        # Collect certificate names (if present)
        certs = product.get("certifications") or []
        cert_names = []
        for c in certs:
            nm = c.get("certification") or c.get("name")
            if nm:
                cert_names.append(str(nm))
        # Collect possible certificate URLs
        certificate_urls: list[str] = []
        known_url_fields = [
            "certificate_url",
            "certification_url",
            "green_tag_url",
            "greentag_url",
            "hpd_url",
            "hpd_certificate_url",
        ]
        for f in known_url_fields:
            v = product.get(f)
            if v and str(v).strip():
                certificate_urls.append(str(v).strip())
        for c in certs:
            for k in ("url", "link", "certificate_url"):
                v = c.get(k)
                if v and str(v).strip():
                    certificate_urls.append(str(v).strip())
        # Collect category/type names
        cats = product.get("product_categories") or []
        cat_names = []
        for cat in cats:
            cn = cat.get("category_name") or cat.get("name")
            if cn:
                cat_names.append(str(cn))
        # Thumbnail image candidate
        thumb = _extract_first_image_url(product)

        base_risk, reasons, advisories = evaluate_product(product)
        # Certificate-based risk buckets:
        # - Green (Low): has EPD certificate
        # - Yellow (Medium): has certificates but not EPD
        # - Red (High): no certificates
        if has_epd_cert:
            risk_for_display = "Green"
            low += 1
        elif has_certs:
            risk_for_display = "Yellow"
            med += 1
        else:
            risk_for_display = "Red"
            high += 1

        # Prefer robust fallbacks for names
        product_name = product.get("product_name") or product.get("name")
        manufacturer_name = product.get("manufacturer_name") or product.get("manufacturer")

        sr = ScanResult(
            scan_id=scan.id,
            input_product_id=str(pid),
            product_name=product_name,
            manufacturer_name=manufacturer_name,
            epd_url=epd_url,
            epd_issue_date=epd_issue_date,
            risk_level=risk_for_display,
            reasons=json.dumps(reasons, ensure_ascii=False),
            advisories=json.dumps(advisories, ensure_ascii=False),
        )
        db.session.add(sr)
        results_payload.append(
            {
                "input_product_id": sr.input_product_id,
                "product_name": product_name,
                "manufacturer_name": manufacturer_name,
                "epd_url": epd_url,
                "epd_issue_date": epd_issue_date,
                "risk_level": risk_for_display,
                "has_epd": bool(epd_url and str(epd_url).strip()),
                "has_certifications": has_certs,
                "has_epd_certificate": has_epd_cert,
                "certifications": cert_names,
                "certificate_urls": certificate_urls,
                "categories": cat_names,
                "thumbnail_url": thumb,
                "reasons": reasons,
                "advisories": advisories,
            }
        )

    scan.high_risk_count = high
    scan.medium_risk_count = med
    scan.low_risk_count = low
    db.session.commit()

    summary = {
        "scan_id": scan.id,
        "created_at": scan.created_at.isoformat(),
        "counts": {
            "high": high,
            "medium": med,
            "low": low,
            "total": len(product_ids),
        },
        "advisory": "Due to missing issue dates (epd_issue_date) in the source data, please manually verify the validity periods of all EPDs.",
    }

    return jsonify(
        {
            "success": True,
            "summary": summary,
            "results": results_payload,
        }
    )


@epd_bp.get("/scan/<int:scan_id>")
def get_scan(scan_id: int):
    scan = db.session.get(Scan, scan_id)
    if not scan:
        return jsonify({"error": "Scan not found"}), 404

    results = (
        db.session.query(ScanResult)
        .filter(ScanResult.scan_id == scan.id)
        .order_by(ScanResult.id.asc())
        .all()
    )

    def parse_json_list(txt: str | None) -> List[str]:
        if not txt:
            return []
        try:
            return json.loads(txt)
        except Exception:
            return []

    payload = {
        "scan_id": scan.id,
        "created_at": scan.created_at.isoformat(),
        "source": scan.source,
        "counts": {
            "high": scan.high_risk_count,
            "medium": scan.medium_risk_count,
            "low": scan.low_risk_count,
            "total": scan.input_count,
        },
        "results": [
            {
                "input_product_id": r.input_product_id,
                "product_name": r.product_name,
                "manufacturer_name": r.manufacturer_name,
                "epd_url": r.epd_url,
                "epd_issue_date": r.epd_issue_date,
                "risk_level": r.risk_level,
                "reasons": parse_json_list(r.reasons),
                "advisories": parse_json_list(r.advisories),
            }
            for r in results
        ],
    }
    return jsonify(payload)


@epd_bp.get("/export/<int:scan_id>")
def export_scan(scan_id: int):
    fmt = (request.args.get("format") or "csv").lower()
    scan = db.session.get(Scan, scan_id)
    if not scan:
        return jsonify({"error": "Scan not found"}), 404

    results = (
        db.session.query(ScanResult)
        .filter(ScanResult.scan_id == scan.id)
        .order_by(ScanResult.id.asc())
        .all()
    )

    if fmt == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "input_product_id",
                "product_name",
                "manufacturer_name",
                "epd_url",
                "epd_issue_date",
                "risk_level",
                "reasons",
                "advisories",
            ]
        )
        for r in results:
            writer.writerow(
                [
                    r.input_product_id,
                    r.product_name or "",
                    r.manufacturer_name or "",
                    r.epd_url or "",
                    r.epd_issue_date or "",
                    r.risk_level,
                    r.reasons or "[]",
                    r.advisories or "[]",
                ]
            )
        csv_bytes = output.getvalue().encode("utf-8-sig")
        return Response(
            csv_bytes,
            headers={
                "Content-Type": "text/csv; charset=utf-8",
                "Content-Disposition": f"attachment; filename=epd_scan_{scan.id}.csv",
            },
        )

    return jsonify({"error": f"Unsupported format: {fmt}"}), 400
