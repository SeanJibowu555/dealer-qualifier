from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import requests
from openai import OpenAI
import os
import re
from datetime import datetime

app = FastAPI(title="Dealer Qualification Engine")

# Initialize OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

class DealerRequest(BaseModel):
    dealer_name: str
    postcode: Optional[str] = None
    website: Optional[str] = None

class QualificationResponse(BaseModel):
    company_house: Dict[str, Any]
    fca: str
    google_rating: Optional[float] = None
    inventory: Optional[int] = None

@app.post("/qualify")
def qualify_dealer(req: DealerRequest):
    try:
        print(f"Processing dealer: {req.dealer_name}")
        
        # 1. Companies House
        ch_data = get_companies_house_data(req.dealer_name, req.postcode)
        print(f"Companies House result: {ch_data}")
        
        # 2. FCA Check
        fca_data = get_fca_status_simple(req.dealer_name, req.postcode)
        print(f"FCA result: {fca_data}")
        
        # 3. Google Rating
        google_rating = get_google_rating(req.dealer_name, req.postcode)
        print(f"Google rating: {google_rating}")
        
        # 4. Inventory
        inventory_est = estimate_inventory(req.website, req.dealer_name)
        print(f"Inventory estimate: {inventory_est}")
        
        # Build response matching your Apps Script expectations
        response = QualificationResponse(
            company_house={
                "status": ch_data.get("status", "Not Found") if ch_data else "Not Found",
                "company_age": ch_data.get("company_age", 0) if ch_data else 0,
                "company_number": ch_data.get("company_number", "") if ch_data else "",
                "postcode": ch_data.get("postcode", "") if ch_data else "",
                "url": ch_data.get("url", "") if ch_data else ""
            },
            fca=fca_data.get("status", "Not Found"),
            google_rating=google_rating,
            inventory=inventory_est
        )
        
        return response
        
    except Exception as e:
        print(f"Error in qualify_dealer: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # Return a safe response that won't break your Apps Script
        return QualificationResponse(
            company_house={
                "status": "Error",
                "company_age": 0,
                "company_number": "",
                "postcode": "",
                "url": ""
            },
            fca="Error",
            google_rating=0,
            inventory=0
        )

def get_companies_house_data(company_name: str, postcode: str = None):
    """Get Companies House data"""
    try:
        api_key = os.getenv("COMPANIES_HOUSE_API_KEY")
        if not api_key:
            return None
            
        encoded_name = requests.utils.quote(company_name)
        url = f"https://api.company-information.service.gov.uk/search/companies?q={encoded_name}&items_per_page=10"
        
        response = requests.get(url, auth=(api_key, ''), timeout=10)
        
        if response.status_code != 200:
            return None
            
        data = response.json()
        
        if not data.get('items'):
            return None
            
        # Take the first result
        company = data['items'][0]
        
        # Calculate company age
        from datetime import datetime
        creation_date = datetime.strptime(company['date_of_creation'], '%Y-%m-%d')
        today = datetime.now()
        company_age = today.year - creation_date.year
        
        # Extract postcode
        extracted_postcode = ""
        if company.get('address') and company['address'].get('postal_code'):
            extracted_postcode = company['address']['postal_code']
        elif company.get('address_snippet'):
            postcode_match = re.search(r'[A-Z]{1,2}[0-9][A-Z0-9]? ?[0-9][A-Z]{2}', company['address_snippet'])
            if postcode_match:
                extracted_postcode = postcode_match.group()
        
        return {
            "status": company.get('company_status', 'unknown'),
            "company_age": company_age,
            "company_number": company.get('company_number', ''),
            "postcode": extracted_postcode,
            "url": f"https://find-and-update.company-information.service.gov.uk/company/{company.get('company_number', '')}"
        }
        
    except Exception as e:
        print(f"Companies House error: {e}")
        return None

def get_fca_status_simple(dealer_name: str, postcode: str = None):
    """Simple FCA check without browser automation"""
    try:
        # Clean the name for search
        clean_name = re.sub(r'\b(LIMITED|LTD|PLC|UK|MOTORS|CARS)\b', '', dealer_name, flags=re.IGNORECASE).strip()
        
        # Build search query
        search_terms = [clean_name]
        if postcode:
            search_terms.append(postcode)
        query = " ".join(search_terms)
        
        # FCA search URL
        search_url = f"https://register.fca.org.uk/s/search?q={requests.utils.quote(query)}"
        
        # Try to get the page content
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(search_url, headers=headers, timeout=15)
        
        if response.status_code != 200:
            return {"status": "Error", "url": search_url}
        
        content = response.text
        
        # Check for FCA indicators
        fca_indicators = [
            "Status: Authorised",
            "Authorised and regulated", 
            "Current status: Authorised",
            "This firm is authorised",
            "FCA authorised"
        ]
        
        for indicator in fca_indicators:
            if indicator.lower() in content.lower():
                return {"status": "Authorised", "url": search_url}
        
        return {"status": "Not Authorised", "url": search_url}
        
    except Exception as e:
        print(f"FCA check error: {e}")
        return {"status": "Error", "url": ""}

def get_google_rating(dealer_name: str, postcode: str = None):
    """Get Google rating using Custom Search API"""
    try:
        api_key = os.getenv("GOOGLE_CUSTOM_SEARCH_API_KEY")
        search_engine_id = os.getenv("GOOGLE_CUSTOM_SEARCH_ENGINE_ID")
        
        if not api_key or not search_engine_id:
            return None
            
        query = f"{dealer_name} {postcode if postcode else ''} car dealer reviews rating"
        url = f"https://www.googleapis.com/customsearch/v1?key={api_key}&cx={search_engine_id}&q={requests.utils.quote(query)}"
        
        response = requests.get(url, timeout=10)
        
        if response.status_code != 200:
            return None
            
        data = response.json()
        
        if data.get('items') and len(data['items']) > 0:
            snippet = data['items'][0].get('snippet', '')
            # Look for rating patterns
            rating_match = re.search(r'(\d+\.\d+)\s*★', snippet)
            if rating_match:
                return float(rating_match.group(1))
                
        return None
        
    except Exception as e:
        print(f"Google rating error: {e}")
        return None

def estimate_inventory(website: Optional[str], dealer_name: str) -> int:
    """Estimate inventory count with safe fallbacks"""
    try:
        if not website:
            return 20  # Safe default
            
        # Try to get website content
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(website, headers=headers, timeout=10)
        
        if response.status_code != 200:
            return 20
            
        html_content = response.text[:4000]  # First 4000 chars
        
        # Use AI to estimate inventory
        prompt = f"""
        Estimate the typical number of cars in stock for {dealer_name} based on their website.
        
        Website content snippet: {html_content}
        
        Provide a reasonable estimate as a whole number. If unsure, estimate around 20-30.
        Return ONLY the number.
        """
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        
        answer = response.choices[0].message.content.strip()
        
        # Extract first number from response
        numbers = re.findall(r'\d+', answer)
        if numbers:
            inventory = int(numbers[0])
            # Ensure reasonable bounds
            return max(5, min(inventory, 100))
            
        return 20  # Fallback
        
    except Exception as e:
        print(f"Inventory estimation error: {e}")
        return 20  # Safe fallback

@app.get("/")
def root():
    return {"status": "Dealer Qualifier API is running", "timestamp": datetime.utcnow().isoformat()}

@app.get("/health")
def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
