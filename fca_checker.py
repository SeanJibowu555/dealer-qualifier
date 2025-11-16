import requests
import os
from typing import Dict, Any
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def get_fca_status_playwright(dealer_name: str, postcode: str = None) -> Dict[str, Any]:
    """
    FCA check using direct API + AI fallback (more reliable than browser)
    """
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
        
        # Use AI as fallback to analyze the content
        ai_result = await analyze_fca_with_ai(dealer_name, content)
        if ai_result == "yes":
            return {"status": "Authorised", "url": search_url}
        
        return {"status": "Not Authorised", "url": search_url}
        
    except Exception as e:
        print(f"FCA check error: {e}")
        return {"status": "Error", "url": ""}

async def analyze_fca_with_ai(dealer_name: str, html_content: str) -> str:
    """
    Use OpenAI to analyze FCA search results
    """
    try:
        # Extract visible text (simplified)
        visible_text = re.sub(r'<[^>]+>', ' ', html_content)
        visible_text = ' '.join(visible_text.split()[:800])  # First 800 words
        
        prompt = f"""
        Analyze this FCA Register search results page for {dealer_name}.
        
        Page content: {visible_text}
        
        Does this page show that {dealer_name} is AUTHORISED by the FCA?
        Look for phrases like "Status: Authorised", "Authorised and regulated", etc.
        
        Answer ONLY "yes" or "no".
        """
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        
        answer = response.choices[0].message.content.strip().lower()
        return "yes" if "yes" in answer else "no"
        
    except Exception as e:
        print(f"AI FCA analysis error: {e}")
        return "no"
