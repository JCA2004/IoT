import json
from openai import OpenAI
from typing import Optional

def build_prompt(temp_c: float, humidity: float, items: list[dict], prefs: Optional[dict] = None) -> str:
    prefs = prefs or {"style": "casual"}
    # Keep only fields the AI needs
    wardrobe = [
        {
            "id": it["id"],
            "label": it["label"],
            "category": it["category"],
            "color": it.get("color"),
            "warmth": it.get("warmth", 3),
            "waterproof": it.get("waterproof", 0),
            "formality": it.get("formality", 2),
        }
        for it in items
    ]

    schema = {
        "outfit": {
            "top_id": "integer or null",
            "outerwear_id": "integer or null",
            "bottoms_id": "integer or null",
            "shoes_id": "integer or null",
            "accessory_ids": "array of integers (can be empty)"
        },
        "reason": "short string",
        "confidence": "number 0..1"
    }

    return f"""
            You are a wardrobe-based outfit recommender.

            Constraints:
            - You MUST choose ONLY from the provided wardrobe_items by ID.
            - If no suitable item exists for a required category, return null for that field.
            - Output MUST be valid JSON ONLY, matching this schema: {json.dumps(schema)}

            Inputs:
            temperature_c: {temp_c}
            humidity_percent: {humidity}
            user_prefs: {json.dumps(prefs)}
            wardrobe_items: {json.dumps(wardrobe)}
            """.strip()


fake_items = [
    {
        "id": 1,
        "label": "gray hoodie",
        "category": "top",
        "color": "gray",
        "warmth": 3,
        "waterproof": 0,
        "formality": 1
    },
    {
        "id": 2,
        "label": "black jacket",
        "category": "outerwear",
        "color": "black",
        "warmth": 4,
        "waterproof": 1,
        "formality": 2
    },
    {
        "id": 3,
        "label": "blue jeans",
        "category": "bottoms",
        "color": "blue",
        "warmth": 3,
        "waterproof": 0,
        "formality": 2
    },
    {
        "id": 4,
        "label": "white sneakers",
        "category": "shoes",
        "color": "white",
        "warmth": 2,
        "waterproof": 0,
        "formality": 1
    }
]

fake_prefs = {
    "style": "casual",
    "avoid_colors": ["pink"]
}

client = OpenAI(api_key="API KEY HERE")
prompt = build_prompt(22, 35, fake_items, fake_prefs)
response = client.responses.create(
    model="gpt-5.2",
    input= prompt
)

print(prompt)
print(response.output_text)