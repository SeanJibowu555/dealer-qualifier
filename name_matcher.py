from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def choose_best_match(target, options):
    if not options:
        return None

    prompt = f"""
    Target company: {target}

    FCA search results:
    {options}

    Choose the best match. Return JSON with:
    - title
    - status
    - frn
    """

    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )

    return res.choices[0].message.content

