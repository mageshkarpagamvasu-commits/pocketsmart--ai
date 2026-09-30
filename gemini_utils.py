"""Gemini prompt orchestration for the Home, Party and Jewelry planners."""
import json
import os
import re
from urllib.parse import quote_plus

MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

SEARCH_URLS = {
    "amazon": "https://www.amazon.in/s?k={q}",
    "flipkart": "https://www.flipkart.com/search?q={q}",
    "ikea": "https://www.ikea.com/in/en/search/?q={q}",
    "swiggy": "https://www.swiggy.com/search?query={q}",
    "myntra": "https://www.myntra.com/{q}",
}
ALLOWED = {
    "home": ["Amazon", "Flipkart", "IKEA"],
    "party": ["Swiggy", "Zomato", "OYO", "Amazon"],
    "jewelry": ["Amazon", "Flipkart", "Myntra"],
}


def build_link(platform, name):
    """We build search links ourselves so the AI can never invent a broken URL."""
    q = quote_plus(name)
    tpl = SEARCH_URLS.get(platform.lower())
    if tpl:
        return tpl.format(q=q)
    return f"https://www.google.com/search?q={quote_plus(name + ' ' + platform)}"


def build_prompt(kind, inputs):
    budget = inputs["budget"]
    base = (f"You are PocketSmart AI, a budget planning assistant for Indian users. "
            f"Total budget: INR {budget:,.0f}. All prices must be in INR and realistic. "
            f"The sum of item prices MUST NOT exceed the budget. "
            f"Only use these platforms: {', '.join(ALLOWED[kind])}.\n")
    if kind == "home":
        base += (f"Task: home interior plan. Style: {inputs.get('style', 'modern')}. "
                 f"Rooms: {', '.join(inputs.get('rooms') or ['Living Room'])}. "
                 f"Quantities -> lights: {inputs.get('lights', 0)}, ceiling fans: {inputs.get('fans', 0)}, "
                 f"dining tables: {inputs.get('tables', 0)}, sofas: {inputs.get('sofas', 0)}, "
                 f"beds: {inputs.get('beds', 0)}. Recommend specific products for each requested item.")
    elif kind == "party":
        base += (f"Task: party plan. Event: {inputs.get('event_type', 'birthday')}, "
                 f"guests: {inputs.get('guests', 20)}, venue/city: {inputs.get('venue', 'not specified')}. "
                 f"Split the budget across catering, decoration, entertainment (and stay/venue if relevant).")
    else:
        base += (f"Task: jewelry recommendations. Occasion: {inputs.get('occasion', 'wedding')}, "
                 f"style: {inputs.get('style', 'traditional')}. If an outfit image is attached, "
                 f"match colours and aesthetics to it and mention that in the reasons.")
    base += ('\nReturn ONLY valid JSON with this shape: {"summary": "2 sentence overview", '
             '"items": [{"name": "product/service name", "category": "e.g. Lighting", '
             '"platform": "one allowed platform", "price": 1234, "reason": "one short sentence"}], '
             '"tips": ["3 short money-saving tips"]}')
    return base


def _call_gemini(prompt, image=None, mime=None):
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    parts = [prompt]
    if image:
        parts.insert(0, types.Part.from_bytes(data=image, mime_type=mime or "image/jpeg"))
    resp = client.models.generate_content(
        model=MODEL, contents=parts,
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.6))
    return resp.text


def _parse(text):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    return json.loads(text)


def _fallback(kind, budget):
    """Used when Gemini fails or returns nothing useful (Activity 5.4)."""
    plans = {
        "home": [("Lighting", .25, "Amazon"), ("Furniture", .50, "IKEA"), ("Decor & Fans", .25, "Flipkart")],
        "party": [("Catering", .50, "Zomato"), ("Decoration", .30, "Amazon"), ("Entertainment", .20, "Swiggy")],
        "jewelry": [("Main piece", .60, "Amazon"), ("Matching accessories", .40, "Flipkart")],
    }
    items = [{"name": f"{label} - budget pick", "category": label, "platform": plat,
              "price": round(budget * share), "reason": "Default suggestion based on a standard budget split."}
             for label, share, plat in plans[kind]]
    return {"summary": "AI was unavailable, so here is a standard budget split to get you started.",
            "items": items, "tips": ["Compare prices on 2-3 platforms.", "Check for sale periods.",
                                     "Keep 10% of the budget as buffer."], "fallback": True}


def get_recommendations(kind, inputs, image=None, mime=None):
    budget = float(inputs["budget"])
    try:
        if not os.getenv("GEMINI_API_KEY"):
            raise RuntimeError("GEMINI_API_KEY missing")
        data = _parse(_call_gemini(build_prompt(kind, inputs), image, mime))
        if not data.get("items"):
            raise ValueError("empty result")
    except Exception as exc:  # network, quota, bad JSON ...
        print("Gemini error:", exc)
        data = _fallback(kind, budget)

    for it in data["items"]:
        it["price"] = float(it.get("price") or 0)
        it["link"] = build_link(it.get("platform", "Google"), it.get("name", ""))
    data["total"] = sum(i["price"] for i in data["items"])
    data["over_budget"] = data["total"] > budget
    data.setdefault("tips", [])
    return data
