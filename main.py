import os
import re
import datetime
from typing import List, Optional

import requests
from fastapi import FastAPI
from pydantic import BaseModel
from openai import OpenAI

# ========= ENV VARS =========
COMPANIES_HOUSE_API_KEY = os.environ.get("COMPANIES_HOUSE_API_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
GOOGLE_CUSTOM_SEARCH_API_KEY = os.environ.get("GOOGLE_CUSTOM_SEARCH_API_KEY")  # optional
GOOGLE_CUSTOM_SEARCH_ENGINE_ID = os.environ.get("GOOGLE_CUSTOM_SEARCH_ENGINE_ID")  # optional

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

app = FastAPI(title="Dealer Qualifier API")


# ========= MODELS =========
class DealerRequest(BaseModel):
    dealer_name: str
    postcode: Optional[str] = None
    website_url: Optional[str] = None


class DealerResponse(BaseModel):
    company_status: str
    company_age: int
    companies_house_url: Optional[str]
    fca_status: str  # "yes" / "no" / "unknown"
    fca_register_url: Optional[str]
    google_rating: Optional[float]
    inventory_estimate: Optional[int]
    decision: str      # "PASS" / "REJECT"
    reasons: List[str]


# ========= HEALTH =========
@app.get("/")
def root():
    return {"status": "ok", "message": "Dealer-qualifier backend is running."}


@app.get("/health")
def health():
    return {"status": "healthy"}


# ========= HELPERS =========

def normalize_postcode(pc: Optional[str]) -> str:
    if not pc:
        return ""
    return pc.replace(" ", "").upper()


def get_companies_house_best_match(name: str, postcode: Optional[str]) -> Optional[dict]:
    """
    Call Companies House search API and pick the best match
    using a heuristic (name similarity + postcode proximity).
    """
    if not COMPANIES_HOUSE_API_KEY:
        return None

    search_terms = [
        name,
        re.sub(r"(MOTORS|CARS|AUTOS|AUTOMOTIVE|VEHICLES?)", "", name, flags=re.I).strip(),
        re.sub(r"(LIMITED|LTD|PLC)", "", name, flags=re.I).strip(),
    ]

    target_name = name.lower()
    target_pc = normalize_postcode(postcode)

    best_match = None
    best_score = 0

    for term in search_terms:
        if not term or len(term) < 2:
            continue

        url = f"https://api.company-information.service.gov.uk/search/companies?q={term}&items_per_page=25"
        resp = requests.get(url, auth=(COMPANIES_HOUSE_API_KEY, ""), timeout=10)
        if resp.status_code != 200:
            continue

        data = resp.json()
        items = data.get("items", [])
        for company in items:
            title = (company.get("title") or "").lower()
            status = company.get("company_status", "unknown")
            address = company.get("address", {})
            pc = address.get("postal_code", "") or ""
            pc_norm = normalize_postcode(pc)

            score = 0

            # name similarity
            if title == target_name:
                score += 100
            elif target_name in title or title in target_name:
                score += 60

            # postcode match
            if target_pc and pc_norm:
                if pc_norm == target_pc:
                    score += 80
                elif target_pc in pc_norm or pc_norm in target_pc:
                    score += 30

            # active bonus
            if status == "active":
                score += 10

            if score > best_score:
                best_score = score
                best_match = company

    if not best_match or best_score < 40:  # threshold
        return None

    creation_date_str = best_match.get("date_of_creation")
    if creation_date_str:
        y, m, d = map(int, creation_date_str.split("-"))
        creation = datetime.date(y, m, d)
        today = datetime.date.today()
        age = today.year - creation.year - ((today.month, today.day) < (creation.month, creation.day))
    else:
        age = 0

    # extract postcode robustly
    address = best_match.get("address", {})
    pc = address.get("postal_code") or ""
    if not pc and best_match.get("address_snippet"):
        m = re.search(r"[A-Z]{1,2}\d[A-Z0-9]?\s?\d[A-Z]{2}", best_match["address_snippet"], re.I)
        if m:
            pc = m.group(0)

    return {
        "company_name": best_match["title"],
        "status": best_match.get("company_status", "unknown"),
        "company_number": best_match.get("company_number"),
        "company_age": age,
        "postcode": pc,
        "url": f"https://find-and-update.company-information.service.gov.uk/company/{best_match.get('company_number')}",
    }


def check_fca_authorisation(company_name: str, postcode: Optional[str]) -> tuple[str, Optional[str]]:
    """
    Check FCA register by name + postcode (no more CH company number nonsense).
    Returns ("yes"/"no"/"unknown", url_if_any).
    """
    base_url = "https://register.fca.org.uk/s/search"
    cleaned_name = re.sub(r"(LIMITED|LTD|PLC|UK|\.)", "", company_name, flags=re.I).strip()
    pc_norm = normalize_postcode(postcode)

    queries = []
    if cleaned_name and pc_norm:
        queries.append(f"{cleaned_name} {pc_norm}")
    if cleaned_name:
        queries.append(cleaned_name)

    patterns = [
        re.compile(r"Status:\s*Authorised", re.I),
        re.compile(r"Authorised and regulated", re.I),
        re.compile(r"Authorised\s+by\s+the\s+Financial\s+Conduct\s+Authority", re.I),
        re.compile(r"regulated\s+by\s+the\s+Financial\s+Conduct\s+Authority", re.I),
        re.compile(r"Firm Reference Number", re.I),
    ]

    for q in queries:
        params = {"q": q}
        try:
            resp = requests.get(
                base_url,
                params=params,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
                timeout=10,
            )
        except Exception:
            continue

        if resp.status_code != 200:
            continue

        html = resp.text

        # basic pattern detection
        for pat in patterns:
            if pat.search(html):
                return "yes", resp.url

        # best-effort heuristic: if FCA search shows firm details section
        if "Firm reference number" in html or "firm-details" in html:
            return "yes", resp.url

    # if we tried and found nothing, it's "no", but we distinguish from "unknown" only if we did at least one query
    if queries:
        return "no", None
    return "unknown", None


def fetch_website_content(url: Optional[str]) -> str:
    if not url:
        return ""
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.text[:15000]  # cap length
    except Exception:
        return ""
    return ""


def ai_estimate_rating_and_inventory(dealer_name: str, website_html: str) -> tuple[Optional[float], Optional[int]]:
    """
    Use OpenAI to guess rating (1-5) and inventory size based on website HTML.
    If OPENAI_API_KEY is not set, returns (None, None).
    """
    if not client or not website_html:
        return None, None

    prompt = f"""
You are analysing a UK used car dealership website.

Dealership name: {dealer_name}

HTML content (truncated):
\"\"\"{website_html}\"\"\"

Tasks:
1. Estimate a customer rating from 1.0 to 5.0 (Google-style).
2. Estimate how many cars are typically in stock (whole number).

Respond ONLY as JSON like:
{{"rating": 4.3, "inventory": 35}}
"""

    try:
        resp = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt,
            temperature=0.2,
            max_output_tokens=100,
        )
        text = resp.output_text.strip()
        # crude JSON-ish parse
        m_rating = re.search(r'"rating"\s*:\s*([0-9]+(\.[0-9]+)?)', text)
        m_inv = re.search(r'"inventory"\s*:\s*([0-9]+)', text)
        rating = float(m_rating.group(1)) if m_rating else None
        inventory = int(m_inv.group(1)) if m_inv else None
        return rating, inventory
    except Exception:
        return None, None


def decide_qualification(company_status: str, company_age: int, fca_status: str, inventory: Optional[int]) -> tuple[str, list]:
    """
    Business rules:
    - REJECT if dissolved / liquidation.
    - REJECT if NOT FCA registered AND < 2 years.
    - otherwise PASS.
    """
    reasons = []
    status_lower = (company_status or "").lower()
    clear_to_call = "FAIL"

    if "dissolved" in status_lower or "liquid" in status_lower or "insolv" in status_lower:
        clear_to_call = "REJECT"
        reasons.append("Company dissolved/liquidated/insolvent")
        return clear_to_call, reasons

    if fca_status == "no" and company_age < 2:
        clear_to_call = "REJECT"
        reasons.append("Not FCA registered and less than 2 years trading")
        return clear_to_call, reasons

    clear_to_call = "PASS"
    reasons.append("Meets qualification criteria")

    if fca_status == "yes":
        reasons.append("FCA registered")
    elif fca_status == "unknown":
        reasons.append("FCA status unknown")
    else:
        reasons.append("Not FCA registered but 2+ years trading")

    if inventory is not None:
        if inventory >= 20:
            reasons.append("Inventory appears sufficient")
        elif inventory >= 10:
            reasons.append("Inventory moderate")
        else:
            reasons.append("Inventory appears small")

    return clear_to_call, reasons


# ========= MAIN ENDPOINT =========

@app.post("/qualify_dealer", response_model=DealerResponse)
def qualify_dealer(req: DealerRequest):
    """
    Core API used by Apps Script.
    """
    # 1) Companies House
    ch_data = get_companies_house_best_match(req.dealer_name, req.postcode)
    if ch_data:
        company_status = ch_data["status"]
        company_age = ch_data["company_age"]
        ch_url = ch_data["url"]
        final_postcode = ch_data["postcode"] or req.postcode
    else:
        company_status = "Not Found"
        company_age = 0
        ch_url = None
        final_postcode = req.postcode

    # 2) FCA check (NO company-number-based search, only name + postcode)
    fca_status, fca_url = check_fca_authorisation(req.dealer_name, final_postcode)

    # 3) AI rating & inventory (optional)
    website_html = fetch_website_content(req.website_url)
    rating, inventory = ai_estimate_rating_and_inventory(req.dealer_name, website_html)

    # 4) Business decision
    decision, reasons = decide_qualification(company_status, company_age, fca_status, inventory)

    return DealerResponse(
        company_status=company_status,
        company_age=company_age,
        companies_house_url=ch_url,
        fca_status=fca_status,
        fca_register_url=fca_url,
        google_rating=rating,
        inventory_estimate=inventory,
        decision=decision,
        reasons=reasons,
    )
