import requests
import os
import re
from typing import Optional
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def estimate_inventory(website: Optional[str], dealer_name: str) -> int:
    """
    Estimate inventory count with safe fallbacks
    """
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
