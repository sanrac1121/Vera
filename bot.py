import os
import json
import urllib.request
import urllib.error

def call_gemini(system_prompt: str, user_prompt: str, api_key: str) -> dict:
    api_key = (api_key or "").strip().strip('"').strip("'")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is empty.")

    full_prompt = f"{system_prompt}\n\n{user_prompt}"
    body = {
        "contents": [{"parts": [{"text": full_prompt}]}],
        "generationConfig": {
            "temperature": 0.0,
            "responseMimeType": "application/json"
        }
    }

    models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-3.6-flash"]
    last_err = None
    for m in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={api_key}"
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        try:
            resp = urllib.request.urlopen(req, timeout=30)
            data = json.loads(resp.read().decode("utf-8"))
            content = data["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(content)
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8", errors="ignore")
            last_err = f"HTTP {e.code} ({m}): {err_msg}"
        except Exception as e:
            last_err = str(e)

    raise RuntimeError(f"Gemini API error: {last_err}")

def call_openai(system_prompt: str, user_prompt: str, api_key: str) -> dict:
    url = "https://api.openai.com/v1/chat/completions"
    
    body = {
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.0,
        "response_format": {"type": "json_object"}
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
    )
    
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        data = json.loads(resp.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
        return json.loads(content)
    except Exception as e:
        raise RuntimeError(f"OpenAI API error: {str(e)}")

def compose(category: dict, merchant: dict, trigger: dict, customer: dict | None = None) -> dict:
    """
    Primary message composition function.
    Returns a dict with keys: body, cta, send_as, suppression_key, rationale.
    """
    system_prompt = """You are Vera, magicpin's elite merchant-AI assistant.
Your task is to compose a WhatsApp message to a merchant or their customer based on the provided contexts.

CRITICAL PRINCIPLES TO STRICTLY FOLLOW:
1. Data Anchoring & Verifiability: Base messaging on concrete, verifiable facts from the contexts (exact metric deltas, peer benchmarks, research samples, or service prices like "Haircut @ ₹99"). NO generic promotional claims like "10% off" or "boost sales".
2. Vertical Domain Adaptation:
   - Dentists: Clinical, peer-to-peer tone ("Dr. [Name]"), clinical vocabulary (e.g., "fluoride recall").
   - Salons: Warm, practical, and inviting tone.
   - Restaurants: Operator-to-operator tone (inventory, footfall, metrics).
   - Gyms: Encouraging, coaching-oriented.
   - Pharmacies: Precise, reliable, trustworthy.
3. Merchant Personalization & Cultural Alignment: Address owners using their primary name or business identity. STRICTLY adhere to language preference (e.g., use natural, professional Hinglish for "hi-en mix", pure Hindi for "hi", etc.).
4. Event-Driven Trigger Hooks: Establish contextual relevance in the very FIRST line by citing the exact trigger event (e.g., upcoming seasonal beat, fresh research digest, performance spike).
5. Low-Friction Engagement & CTA: Use engagement levers like loss aversion ("missing searches") or effort externalization ("I've drafted this for you"). End with a SINGLE, clear, binary call-to-action (e.g., "Reply YES to publish", "Reply 1 for Wed, 2 for Thu"). If purely informational, CTA should be "none".
6. Guardrails & Data Integrity: STRICT Anti-Hallucination. Do NOT invent stats, names, offers, or medical citations not explicitly provided in the context. Jargon Suppression: Do NOT expose raw JSON keys, database IDs, or system flags.

You must output ONLY a valid JSON object with the following schema:
{
    "body": "The actual WhatsApp message body",
    "cta": "The specific CTA used (e.g., 'YES/STOP', 'Reply 1 or 2', 'open_ended', 'none')",
    "send_as": "'vera' if the message is to the merchant, or 'merchant_on_behalf' if the message is to the customer",
    "suppression_key": "A unique key derived from the trigger's suppression_key",
    "rationale": "A short 1-sentence explanation of why this message was crafted this way (identifying the levers used)"
}
"""

    context_payload = {
        "category_context": category,
        "merchant_context": merchant,
        "trigger_context": trigger,
    }
    if customer:
        context_payload["customer_context"] = customer

    user_prompt = f"""
Please generate the message based on the following contexts.
Strictly adhere to the system principles.

CONTEXT:
{json.dumps(context_payload, indent=2)}
"""

    gemini_key = os.environ.get("GEMINI_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")
    
    if not gemini_key and not openai_key:
        try:
            from judge_simulator import LLM_API_KEY, LLM_PROVIDER
            if LLM_PROVIDER == "gemini" and LLM_API_KEY:
                gemini_key = LLM_API_KEY
            elif LLM_PROVIDER == "openai" and LLM_API_KEY:
                openai_key = LLM_API_KEY
        except Exception:
            pass
    
    result = None
    try:
        if gemini_key:
            result = call_gemini(system_prompt, user_prompt, gemini_key)
        elif openai_key:
            result = call_openai(system_prompt, user_prompt, openai_key)
        else:
            # Fallback when no keys are provided
            raise RuntimeError("No GEMINI_API_KEY or OPENAI_API_KEY environment variable found.")
            
        # Ensure fallback suppression_key if LLM missed it
        if "suppression_key" not in result or not result["suppression_key"]:
            result["suppression_key"] = trigger.get("suppression_key", f"fallback_{trigger.get('id')}")
            
        return {
            "body": result.get("body", ""),
            "cta": result.get("cta", "none"),
            "send_as": result.get("send_as", "vera"),
            "suppression_key": result["suppression_key"],
            "rationale": result.get("rationale", "")
        }
        
    except Exception as e:
        # Graceful fallback logic
        send_as = "merchant_on_behalf" if customer else "vera"
        merchant_name = merchant.get("identity", {}).get("name", "Merchant")
        body = f"Hi {merchant_name}, we noticed an update based on recent activity. Reply YES to review or learn more."
        
        return {
            "body": body,
            "cta": "YES/STOP",
            "send_as": send_as,
            "suppression_key": trigger.get("suppression_key", "fallback_key"),
            "rationale": f"Fallback triggered due to error: {str(e)}"
        }
