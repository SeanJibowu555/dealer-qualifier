from openai import OpenAI
import requests
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def estimate_inventory(website, name):
    if not website:
        return 20  # default

    html = requests.get(website, timeout=10).text[:5000]

    prompt = f"""
    Based on this website HTML, estimate the number of cars in stock.
    If unsure, give a safe estimate.

    HTML:
    {html[:4000]}
    """

    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )

    txt = res.choices[0].message.content
    digits = [int(s) for s in txt.split() if s.isdigit()]
    return digits[0] if digits else 20
