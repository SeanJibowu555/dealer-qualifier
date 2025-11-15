{\rtf1\ansi\ansicpg1252\cocoartf2709
\cocoatextscaling0\cocoaplatform0{\fonttbl\f0\fswiss\fcharset0 Helvetica;}
{\colortbl;\red255\green255\blue255;}
{\*\expandedcolortbl;;}
\paperw11900\paperh16840\margl1440\margr1440\vieww11520\viewh8400\viewkind0
\pard\tx720\tx1440\tx2160\tx2880\tx3600\tx4320\tx5040\tx5760\tx6480\tx7200\tx7920\tx8640\pardirnatural\partightenfactor0

\f0\fs24 \cf0 # main.py\
import os\
import math\
import requests\
from typing import Optional, List, Dict, Any\
\
from fastapi import FastAPI, HTTPException\
from pydantic import BaseModel\
from openai import OpenAI\
\
# ---------- CONFIG FROM ENVIRONMENT ----------\
\
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")\
CH_API_KEY = os.getenv("COMPANIES_HOUSE_API_KEY")\
GOOGLE_API_KEY = os.getenv("GOOGLE_CUSTOM_SEARCH_API_KEY")\
GOOGLE_CX_ID = os.getenv("GOOGLE_CUSTOM_SEARCH_ENGINE_ID")\
\
if not OPENAI_API_KEY:\
    raise RuntimeError("OPENAI_API_KEY environment variable is not set")\
\
# Create OpenAI client\
client = OpenAI(api_key=OPENAI_API_KEY)\
\
# ---------- FASTAPI APP ----------\
\
app = FastAPI(title="Dealer Qualification Backend")\
\
\
# ---------- REQUEST / RESPONSE MODELS ----------\
\
class QualifyRequest(BaseModel):\
    dealer_name: str\
    postcode: Optional[str] = None\
    dealer_url: Optional[str] = None\
\
\
class CompanyHouseInfo(BaseModel):\
    company_name: str\
    status: str\
    company_age: int\
    company_number: str\
    postcode: Optional[str] = None\
    address: Optional[str] = None\
    url: Optional[str] = None\
\
\
class QualifyResponse(BaseModel):\
    decision: str              # "PASS" / "REJECT"\
    reasons: List[str]\
    companies_house: Optional[CompanyHouseInfo] = None\
    fca_status: str            # "yes" / "no" / "unknown"\
    fca_register_url: Optional[str] = None\
    google_rating: Optional[float] = None\
    inventory_estimate: Optional[int] = None\
    updated_dealer_url: Optional[str] = None\
\
\
# ---------- UTILS ----------\
\
def call_openai_for_choice(prompt: str) -> str:\
    """\
    Simple helper that calls OpenAI and returns plain text.\
    Use a small/cheap model like gpt-4.1-mini or gpt-4o-mini.\
    """\
    response = client.chat.completions.create(\
        model="gpt-4.1-mini",\
        messages=[\
            \{"role": "system", "content": "You are a precise assistant. Respond with concise answers only."\},\
            \{"role": "user", "content": prompt\},\
        ],\
        temperature=0\
    )\
    return response.choices[0].message.content.strip()\
\
\
# ---------- COMPANIES HOUSE LOGIC ----------\
\
def fetch_companies_house_candidates(name: str, postcode: Optional[str]) -> List[Dict[str, Any]]:\
    if not CH_API_KEY:\
        return []\
\
    query = name\
    url = f"https://api.company-information.service.gov.uk/search/companies?q=\{requests.utils.quote(query)\}&items_per_page=20"\
    headers = \{\
        "Authorization": "Basic " + requests.utils.quote(f"\{CH_API_KEY\}:")\
    \}\
\
    r = requests.get(url, headers=headers, timeout=10)\
    if r.status_code != 200:\
        return []\
\
    data = r.json()\
    return data.get("items", [])\
\
\
def choose_best_company_with_ai(\
    dealer_name: str,\
    dealer_postcode: Optional[str],\
    candidates: List[Dict[str, Any]]\
) -> Optional[Dict[str, Any]]:\
    """\
    Use OpenAI to decide which Companies House result best matches this dealer.\
    We send a small list of candidates (max 6) plus their names / postcodes / statuses.\
    The model returns the index of the best match or -1 if none.\
    """\
\
    if not candidates:\
        return None\
\
    # limit candidates to avoid huge prompts\
    candidates_small = candidates[:6]\
\
    # prepare a concise description list\
    lines = []\
    for idx, c in enumerate(candidates_small):\
        title = c.get("title", "")\
        status = c.get("company_status", "")\
        addr = c.get("address_snippet", "") or ""\
        pc = ""\
        if c.get("address") and c["address"].get("postal_code"):\
            pc = c["address"]["postal_code"]\
        lines.append(\
            f"\{idx\}: name='\{title\}', postcode='\{pc\}', status='\{status\}', address='\{addr\}'"\
        )\
\
    candidate_block = "\\n".join(lines)\
    target_pc = dealer_postcode or ""\
\
    prompt = f"""\
You are matching a UK car dealership to its correct Companies House record.\
\
Dealer:\
- Name: \{dealer_name\}\
- Postcode: \{target_pc\}\
\
Candidates:\
\{candidate_block\}\
\
Instructions:\
- Choose the single candidate that best matches by BOTH name and postcode.\
- If postcodes differ slightly (missing space, partial), that is okay.\
- If no candidate is clearly the same entity, answer -1.\
\
Respond with ONLY the index number (e.g. 0) or -1 if no match.\
"""\
\
    answer = call_openai_for_choice(prompt)\
    # extract first integer\
    import re\
    m = re.search(r"-?\\d+", answer)\
    if not m:\
        return None\
    idx = int(m.group(0))\
    if idx < 0 or idx >= len(candidates_small):\
        return None\
    return candidates_small[idx]\
\
\
def build_company_info(ch_item: Dict[str, Any]) -> CompanyHouseInfo:\
    title = ch_item.get("title", "")\
    status = ch_item.get("company_status", "unknown")\
    number = ch_item.get("company_number", "")\
    addr_snippet = ch_item.get("address_snippet", "")\
    postcode = ""\
    if ch_item.get("address") and ch_item["address"].get("postal_code"):\
        postcode = ch_item["address"]["postal_code"]\
\
    # compute age in years\
    creation = ch_item.get("date_of_creation")\
    age_years = 0\
    if creation:\
        try:\
            from datetime import datetime\
            d = datetime.strptime(creation, "%Y-%m-%d").date()\
            today = datetime.utcnow().date()\
            age_years = today.year - d.year - ((today.month, today.day) < (d.month, d.day))\
        except Exception:\
            age_years = 0\
\
    url = f"https://find-and-update.company-information.service.gov.uk/company/\{number\}" if number else None\
\
    return CompanyHouseInfo(\
        company_name=title,\
        status=status,\
        company_age=age_years,\
        company_number=number,\
        postcode=postcode,\
        address=addr_snippet,\
        url=url\
    )\
\
\
# ---------- FCA CHECKING ----------\
\
def check_fca_status_simple(name: str, postcode: Optional[str]) -> (str, Optional[str]):\
    """\
    Simple HTML scraping of FCA register search page.\
    This is still brittle if FCA changes their markup, but better than Apps Script regex only.\
    You can later swap this to use any official FCA API you have.\
    """\
    query_parts = [name]\
    if postcode:\
        query_parts.append(postcode)\
    q = " ".join(query_parts)\
    search_url = f"https://register.fca.org.uk/s/search?q=\{requests.utils.quote(q)\}"\
\
    headers = \{\
        "User-Agent": "Mozilla/5.0 (qualification-bot; +https://example.com)"\
    \}\
\
    try:\
        r = requests.get(search_url, headers=headers, timeout=15)\
    except Exception:\
        return "unknown", None\
\
    if r.status_code != 200:\
        return "unknown", None\
\
    html = r.text\
\
    # quick-and-dirty pattern check\
    patterns_yes = [\
        "Status: Authorised",\
        "Authorised and regulated",\
        "Authorised - FCA",\
        "Authorised & regulated"\
    ]\
    for p in patterns_yes:\
        if p.lower() in html.lower():\
            return "yes", search_url\
\
    # Use OpenAI as a backup to inspect a trimmed version of HTML\
    snippet = html[:8000]  # avoid huge prompts\
    prompt = f"""\
You are checking if a UK firm appears authorised on the FCA Financial Services Register.\
\
Search page HTML (truncated):\
\\"\\"\\"\{snippet\}\\"\\"\\"\
\
Question:\
Does this page appear to show an authorised firm in the results?\
Answer ONLY 'yes' or 'no'.\
"""\
    try:\
        ans = call_openai_for_choice(prompt).lower()\
        if "yes" in ans:\
            return "yes", search_url\
        if "no" in ans:\
            return "no", search_url\
    except Exception:\
        pass\
\
    return "no", search_url\
\
\
# ---------- WEBSITE DISCOVERY & ANALYSIS ----------\
\
def discover_website_via_google(name: str, postcode: Optional[str]) -> Optional[str]:\
    if not GOOGLE_API_KEY or not GOOGLE_CX_ID:\
        return None\
\
    q_parts = [name]\
    if postcode:\
        q_parts.append(postcode)\
    q_parts.append("car dealer website")\
    query = " ".join(q_parts)\
\
    url = (\
        "https://www.googleapis.com/customsearch/v1"\
        f"?key=\{GOOGLE_API_KEY\}&cx=\{GOOGLE_CX_ID\}&q=\{requests.utils.quote(query)\}"\
    )\
    r = requests.get(url, timeout=10)\
    if r.status_code != 200:\
        return None\
    data = r.json()\
    items = data.get("items") or []\
    if not items:\
        return None\
\
    for item in items:\
        link = item.get("link")\
        if not link:\
            continue\
        # crude filter to prefer proper sites\
        if any(t in link for t in [".co.uk", ".com", ".net"]):\
            return link\
    return items[0].get("link")\
\
\
def fetch_website_html(url: str) -> str:\
    try:\
        headers = \{"User-Agent": "Mozilla/5.0 (dealer-qualifier; +https://example.com)"\}\
        r = requests.get(url, headers=headers, timeout=15)\
        if r.status_code != 200:\
            return ""\
        return r.text[:15000]  # truncate to keep tokens reasonable\
    except Exception:\
        return ""\
\
\
def analyse_site_with_openai_for_rating_and_inventory(\
    dealer_name: str,\
    website_html: str\
) -> (Optional[float], Optional[int]):\
    """\
    Use OpenAI to estimate Google-style rating (1\'965) and inventory count.\
    """\
\
    if not website_html:\
        return None, None\
\
    prompt = f"""\
You are analyzing a UK used car dealership's website.\
\
Dealer name: \{dealer_name\}\
\
Website HTML (truncated):\
\\"\\"\\"\{website_html\}\\"\\"\\"\
\
Tasks:\
1) Estimate a realistic Google-style rating from 1.0 to 5.0 based on:\
   - Customer testimonials/reviews text\
   - Awards / trust badges\
   - Professionalism of page\
   - General tone\
\
2) Estimate the typical number of cars in stock (inventory), as a whole number.\
\
Respond in EXACT JSON like:\
\{\{\
  "rating": 4.3,\
  "inventory": 27\
\}\}\
If you are unsure, set rating to 0 and inventory to 0.\
"""\
\
    answer = call_openai_for_choice(prompt)\
\
    import json\
    try:\
        data = json.loads(answer)\
        rating = float(data.get("rating", 0)) if data.get("rating") is not None else None\
        inventory = int(data.get("inventory", 0)) if data.get("inventory") is not None else None\
    except Exception:\
        rating = None\
        inventory = None\
\
    return rating, inventory\
\
\
# ---------- BUSINESS LOGIC ----------\
\
def make_business_decision(\
    ch_info: Optional[CompanyHouseInfo],\
    fca_status: str,\
    google_rating: Optional[float],\
    inventory_estimate: Optional[int]\
) -> (str, List[str]):\
    """\
    Replicates your logic:\
    - REJECT if dissolved/liquidated.\
    - REJECT if not FCA and < 2 years old.\
    - Otherwise PASS, with detailed reasons.\
    """\
\
    reasons: List[str] = []\
\
    if ch_info:\
        status_lower = (ch_info.status or "").lower()\
        if "dissolved" in status_lower or "liquid" in status_lower:\
            reasons.append("Company dissolved/liquidated")\
            return "REJECT", reasons\
\
        if fca_status != "yes" and ch_info.company_age < 2:\
            reasons.append("Not FCA registered and less than 2 years trading")\
            return "REJECT", reasons\
\
    # If we reach here, it's a PASS\
    reasons.append("Meets qualification criteria")\
\
    if fca_status == "yes":\
        reasons.append("FCA registered")\
    else:\
        reasons.append("Not FCA registered but 2+ years trading")\
\
    if google_rating is not None and google_rating > 0:\
        if google_rating >= 4.0:\
            reasons.append("Good Google rating")\
        else:\
            reasons.append("Average Google rating")\
\
    if inventory_estimate is not None and inventory_estimate >= 20:\
        reasons.append("Inventory appears sufficient")\
\
    return "PASS", reasons\
\
\
# ---------- MAIN ENDPOINT ----------\
\
@app.post("/qualify-dealer", response_model=QualifyResponse)\
def qualify_dealer(req: QualifyRequest):\
    dealer_name = req.dealer_name.strip()\
    if not dealer_name:\
        raise HTTPException(status_code=400, detail="dealer_name is required")\
\
    postcode = (req.postcode or "").strip()\
    dealer_url = (req.dealer_url or "").strip() or None\
\
    # 1) Companies House\
    ch_info: Optional[CompanyHouseInfo] = None\
    if CH_API_KEY:\
        candidates = fetch_companies_house_candidates(dealer_name, postcode)\
        best = choose_best_company_with_ai(dealer_name, postcode, candidates)\
        if best:\
            ch_info = build_company_info(best)\
\
    # 2) FCA check\
    fca_status, fca_url = check_fca_status_simple(dealer_name, postcode)\
\
    # 3) Website discovery\
    if not dealer_url:\
        dealer_url = discover_website_via_google(dealer_name, postcode)\
\
    # 4) Website analysis (rating + inventory)\
    google_rating = None\
    inventory_estimate = None\
    if dealer_url:\
        html = fetch_website_html(dealer_url)\
        google_rating, inventory_estimate = analyse_site_with_openai_for_rating_and_inventory(\
            dealer_name,\
            html\
        )\
\
    # 5) Business decision\
    decision, reasons = make_business_decision(\
        ch_info=ch_info,\
        fca_status=fca_status,\
        google_rating=google_rating,\
        inventory_estimate=inventory_estimate\
    )\
\
    # 6) Build updated dealer_url string with CH & FCA links\
    updated_url_string = dealer_url or ""\
    if ch_info and ch_info.url:\
        updated_url_string = (updated_url_string + " | " if updated_url_string else "") + f"CH: \{ch_info.url\}"\
    if fca_url:\
        updated_url_string = (updated_url_string + " | " if updated_url_string else "") + f"FCA: \{fca_url\}"\
\
    return QualifyResponse(\
        decision=decision,\
        reasons=reasons,\
        companies_house=ch_info,\
        fca_status=fca_status,\
        fca_register_url=fca_url,\
        google_rating=google_rating,\
        inventory_estimate=inventory_estimate,\
        updated_dealer_url=updated_url_string or None\
    )\
}