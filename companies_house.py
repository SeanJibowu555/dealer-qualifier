import requests
import os
from typing import Optional, Dict, Any
from datetime import datetime

def get_companies_house_data(company_name: str, postcode: str = None) -> Optional[Dict[str, Any]]:
    """
    Get Companies House data with basic matching
    """
    try:
        api_key = os.getenv("COMPANIES_HOUSE_API_KEY")
        if not api_key:
            return None
            
        encoded_name = requests.utils.quote(company_name)
        url = f"https://api.company-information.service.gov.uk/search/companies?q={encoded_name}&items_per_page=10"
        
        response = requests.get(
            url,
            auth=(api_key, ''),
            timeout=10
        )
        
        if response.status_code != 200:
            return None
            
        data = response.json()
        
        if not data.get('items'):
            return None
            
        # Take the first result for now (simplified)
        company = data['items'][0]
        
        # Calculate company age
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
