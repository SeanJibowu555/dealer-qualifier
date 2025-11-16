from fastapi import FastAPI
from pydantic import BaseModel
from fca_checker import get_fca_status
from companies_house import get_company_data
from google_rating import get_google_rating
from name_matcher import choose_best_match
from inventory import estimate_inventory

app = FastAPI()

class Dealer(BaseModel):
    dealer_name: str
    postcode: str | None = None
    website: str | None = None

@app.post("/qualify")
def qualify(dealer: Dealer):
    # 1. Companies House
    ch = get_company_data(dealer.dealer_name, dealer.postcode)

    # 2. FCA browser-level scrape
    fca_results = get_fca_status(dealer.dealer_name)

    # 3. Choose the best FCA record using AI
    best_fca = choose_best_match(dealer.dealer_name, fca_results)

    # 4. Google rating
    google_rating = get_google_rating(dealer.dealer_name, dealer.postcode)

    # 5. Inventory AI estimation
    inv = estimate_inventory(dealer.website, dealer.dealer_name)

    # Final response to Sheets
    return {
        "company_house": ch,
        "fca": best_fca,
        "google_rating": google_rating,
        "inventory": inv
    }
