from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import requests
from openai import OpenAI
import os
import re
from datetime import datetime
import asyncio

app = FastAPI(title="Dealer Qualification Engine")

# Initialize OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

class DealerRequest(BaseModel):
    dealer_name: str
    postcode: Optional[str] = None
    website: Optional[str] = None

class CompanyHouseInfo(BaseModel):
    status: str
    company_age: int
    company_number: Optional[str] = None
    postcode: Optional[str] = None
    url: Optional[str] = None

class QualificationResponse(BaseModel):
    company_house: Dict[str, Any]
    fca: str
    google_rating: Optional[float] = None
    inventory: Optional[int] = None

# Import your modules
try:
    from companies_house import get_companies_house_data
    from fca_checker import get_fca_status_playwright
    from google_rating import get_google_rating
    from inventory import estimate_inventory
except ImportError as e:
    print(f"Import error: {e}")

@app.post("/qualify")
async def qualify_dealer(req: DealerRequest):
    try:
        print(f"Processing dealer: {req.dealer_name}")
        
        # 1. Companies House
        ch_data = get_companies_house_data(req.dealer_name, req.postcode)
        print(f"Companies House result: {ch_data}")
        
        # 2. FCA Check
        fca_data = await get_fca_status_playwright(req.dealer_name, req.postcode)
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

@app.get("/")
async def root():
    return {"status": "Dealer Qualifier API is running", "timestamp": datetime.utcnow().isoformat()}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
