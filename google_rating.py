import requests
import os

API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")

def get_google_rating(name, postcode):
    query = f"{name} {postcode} car dealer"
    url = (
        "https://maps.googleapis.com/maps/api/place/textsearch/json?"
        f"query={query}&key={API_KEY}"
    )

    r = requests.get(url)
    data = r.json()

    if "results" in data and data["results"]:
        return data["results"][0].get("rating", None)

    return None
