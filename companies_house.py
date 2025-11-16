import requests

API = "https://api.company-information.service.gov.uk/search/companies"

def get_company_data(name, postcode=None):
    r = requests.get(API, auth=("65f4a1a8-35fa-43f7-a990-69c89cbea4ca", ""), params={"q": name})
    data = r.json()

    if "items" not in data:
        return None

    best = data["items"][0]

    return {
        "name": best["title"],
        "number": best["company_number"],
        "status": best["company_status"],
        "url": f"https://find-and-update.company-information.service.gov.uk/company/{best['company_number']}"
    }
