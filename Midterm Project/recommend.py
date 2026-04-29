from inventory_db import list_items
from recommender_prompt import build_prompt
from openai import OpenAI
import json

client = OpenAI(api_key="OPENAI KEY HERE")

def pretty_print_outfit(result: dict, items_by_id: dict) -> None:
    outfit = result.get("outfit", {}) or {}
    reason = result.get("reason", "")
    confidence = result.get("confidence", None)

    def show_one(key: str, title: str):
        item_id = outfit.get(key)
        if item_id is None:
            print(f"{title}: (none)")
            return
        item = items_by_id.get(item_id)
        if not item:
            print(f"{title}: (invalid id {item_id})")
            return
        print(f"{title}: {item['label']}  [id={item_id}]")

    print("\nRecommended outfit:\n")
    show_one("top_id", "Top")
    show_one("outerwear_id", "Outerwear")
    show_one("bottoms_id", "Bottoms")
    show_one("shoes_id", "Shoes")

    acc = outfit.get("accessory_ids", []) or []
    if acc:
        names = []
        for aid in acc:
            item = items_by_id.get(aid)
            names.append(item["label"] if item else f"(invalid id {aid})")
        print("Accessories: " + ", ".join(names))
    else:
        print("Accessories: (none)")

    if reason:
        print("\nReason:", reason)
    if confidence is not None:
        print("Confidence:", confidence)

def parse_json_or_raise(text: str) -> dict:
    text = (text or "").strip()
    if not text:
        raise ValueError("Model returned empty output_text")

    # If it ever wraps in code fences, strip them
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()

    return json.loads(text)

def recommend_outfit(temp_c, humidity):
    items = list_items()
    items_by_id = {it["id"]: it for it in items}

    if len(items) == 0:
        print("No wardrobe items found.")
        return

    prefs = {"style": "casual"}

    prompt = build_prompt(temp_c, humidity, items, prefs)

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt,
    )

    result = json.loads(response.output_text)
    out_text = response.output_text
    try:
        result = parse_json_or_raise(out_text)
    except Exception as e:
        retry_prompt = prompt + "\n\nREMINDER: Output ONLY valid JSON. No extra text."
        retry = client.responses.create(model="gpt-4.1-mini", input=retry_prompt)
        result = parse_json_or_raise(retry.output_text)
    
    pretty_print_outfit(result, items_by_id)



if __name__ == "__main__":
    temp = float(input("Temperature (C): "))
    humidity = float(input("Humidity (%): "))

    recommend_outfit(temp, humidity)