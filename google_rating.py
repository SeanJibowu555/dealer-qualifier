import requests
import os
from typing import Optional

def get_google_rating(dealer_name: str, postcode: str = None) -> Optional[float]:
    """
    Get Google rating using Custom Search API (your existing method)
    """
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
