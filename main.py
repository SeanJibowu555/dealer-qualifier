from fastapi import FastAPI
import uvicorn
import requests
import re
import os

OPENAI_KEY = os.getenv("OPENAI_API_KEY")
COMPANIES_HOUSE_KEY = os.getenv("COMPANIES_HOUSE_API_KEY")

app = FastAPI()

# ------------------------------
# 1. Companies House Search
# ------------------------------
def search_companies_house(name):
    url = f"https://api.company-information.service.gov.uk/search/companies?q={name}"
    auth = (COMPANIES_HOUSE_KEY, "")
    r = requests.get(url, auth=auth)

    if r.status_code != 200:
        return None

    data = r.json()
    if "items" not in data or len(data["items"]) == 0:
        return None

    best = data["items"][0]  # top ranked result

    return {
        "company_name": best.get("title", ""),
        "company_number": best.get("company_number", ""),
        "status": best.get("company_status", ""),
        "address": best.get("address_snippet", ""),
        "url": f"https://find-and-update.company-information.service.gov.uk/company/{best.get('company_number', '')}"
    }

# ------------------------------
# 2. FCA Checker via AI
# ------------------------------
def ai_detect_fca(dealer_name, website_text=""):
    prompt = f"""
The following car dealer may or may not be FCA registered.

Dealer name: {dealer_name}

Website text:
\"\"\"{website_text[:10000]}\"\"\"

Does this dealer appear FCA registered?
Return ONLY:
- "yes"
- "no"
"""

    r = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {OPENAI_KEY}"},
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}]
        }
    )
    result = r.json()
    answer = result["choices"][0]["message"]["content"].strip().lower()

    return "yes" if "yes" in answer else "no"

# ------------------------------
# 3. BACKEND ENDPOINT
# Called from Google Sheets or Make.com
# ------------------------------
@app.post("/qualify")
def qualify(payload: dict):

    dealer_name = payload.get("dealer_name", "")
    dealer_url = payload.get("dealer_url", "")

    # Companies House
    ch_data = search_companies_house(dealer_name)

    # FCA detection via AI
    website_text = ""
    if dealer_url:
        try:
            website_text = requests.get(dealer_url, timeout=5).text
        except:
            website_text = ""

    fca_status = ai_detect_fca(dealer_name, website_text)

    return {
        "dealer_name": dealer_name,
        "ch_data": ch_data,
        "fca_status": fca_status,
    }

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=10000)
