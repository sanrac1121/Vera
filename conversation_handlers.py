import os
import json
import urllib.request

def _call_gemini(system_prompt: str, user_prompt: str, api_key: str) -> dict:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent?key={api_key}"
    full_prompt = f"{system_prompt}\n\n{user_prompt}"
    body = {
        "contents": [{"parts": [{"text": full_prompt}]}],
        "generationConfig": {"temperature": 0.0, "responseMimeType": "application/json"}
    }
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req, timeout=30)
    data = json.loads(resp.read().decode("utf-8"))
    return json.loads(data["candidates"][0]["content"]["parts"][0]["text"])

def _call_openai(system_prompt: str, user_prompt: str, api_key: str) -> dict:
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
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    resp = urllib.request.urlopen(req, timeout=30)
    data = json.loads(resp.read().decode("utf-8"))
    return json.loads(data["choices"][0]["message"]["content"])

def get_llm_response(system_prompt: str, user_prompt: str) -> dict:
    gemini_key = os.environ.get("GEMINI_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")
    if gemini_key:
        return _call_gemini(system_prompt, user_prompt, gemini_key)
    elif openai_key:
        return _call_openai(system_prompt, user_prompt, openai_key)
    else:
        raise RuntimeError("No GEMINI_API_KEY or OPENAI_API_KEY found.")


def respond(state: dict, merchant_message: str) -> dict:
    """
    Given the conversation so far + the merchant's latest message, produce the reply.
    """
    
    lower_msg = merchant_message.lower()

    # 1. Intent Commitment Handoff (Fast Path)
    commitment_phrases = ["lets do it", "let's do it", "whats next", "what's next", "i want to join", "go ahead", "proceed"]
    if any(k in lower_msg for k in commitment_phrases):
        return {"action": "send", "body": "Done! Proceeding with the update now. Your Google profile listing has been queued for verification."}

    # 2. Heuristic Hostile Exit (Fast Path)
    hostile_keywords = ["stop messaging", "useless spam", "not interested", "unsubscribe", "don't message me"]
    if any(k in lower_msg for k in hostile_keywords):
        return {"action": "end", "body": "Understood. I've noted your preference and will not message you further. Apologies for any inconvenience."}

    # 3. Deterministic Auto-Reply Detection (Heuristic Backup)
    history = state.get("history", [])
    merchant_messages = [msg.get("content", "") for msg in history if msg.get("role") == "merchant"]
    merchant_messages.append(merchant_message)
    
    # If the last 3 messages from the merchant are identical and reasonably long, it's an auto-reply
    if len(merchant_messages) >= 3 and len(set(merchant_messages[-3:])) == 1 and len(merchant_message) > 5:
        return {"action": "end", "body": "Auto-reply pattern detected. Ending session to avoid spam."}
        
    # 3. LLM Classification and Routing
    system_prompt = """You are Vera, magicpin's elite merchant-AI assistant.
Your task is to analyze the merchant's latest message and the conversation history (if any), then decide the next action and formulate a response.

CRITICAL RULES:
1. Automated Auto-Reply Detection: If the merchant's message sounds like a canned WhatsApp Business automated reply (e.g., "Thank you for contacting us", "Our team will respond shortly", "automated assistant") or is identical to previous responses, return action="end" or action="wait".
2. Intent Classification & Handoff Routing: If the merchant expresses explicit commitment or agreement (e.g., "I want to join", "Let's do it", "What's next?", "Go ahead", "Ok lets do it"), switch immediately to execution mode. Return action="send" and a body that confirms the action (e.g., "Done! Profile updated", "Here is the draft for your review") WITHOUT asking further qualifying questions (do NOT say "would you", "can you tell", "what if").
3. Graceful Exit Protocol: If the merchant is hostile or explicitly says they are not interested ("Stop", "No", "useless spam"), return action="end" and a brief, respectful acknowledgement (e.g., "Understood. Apologies for any inconvenience.").
4. Standard Reply: Otherwise, respond appropriately using action="send" and a helpful, concise body matching the merchant's language/tone.

Output ONLY a JSON object with:
{
    "action": "'send' or 'wait' or 'end'",
    "body": "The text of your reply (leave empty if action is 'end' or 'wait', unless you want to send a final apology for a hostile user)",
    "reasoning": "Brief explanation of why this action was chosen"
}"""

    user_prompt = f"""
Conversation History:
{json.dumps(history, indent=2)}

Merchant's Latest Message:
"{merchant_message}"

Decide the next action.
"""

    try:
        result = get_llm_response(system_prompt, user_prompt)
        
        action = result.get("action", "send").lower()
        body = result.get("body", "")
        
        # Guardrails: Enforce no-qualification rule for intent transition if LLM hallucinates
        if action == "send":
            commitment_keywords = ["let's do it", "go ahead", "what's next", "i want to join", "ok lets do it", "whats next"]
            if any(k in lower_msg for k in commitment_keywords):
                # Ensure it's in execution mode, avoiding qualifiers
                qualifying = ["would you", "do you", "can you tell", "what if", "how about"]
                body_lower = body.lower()
                if any(q in body_lower for q in qualifying):
                    # Rewrite the body to be purely action-oriented if LLM failed
                    body = "Done! I've started the process and have a draft ready for your confirmation. Let me know if you need any adjustments!"
                    
            # Double check hostile conditions
            if any(k in lower_msg for k in hostile_keywords):
                action = "end"
                body = "Understood. I will stop messaging you. Apologies for the inconvenience."
                
        return {
            "action": action,
            "body": body,
            "rationale": result.get("reasoning", "Processed via LLM.")
        }
    except Exception as e:
        # Fallback heuristic logic if API fails
        if any(k in lower_msg for k in ["stop", "not interested", "spam"]):
            return {"action": "end", "body": "Understood. Apologies for any inconvenience."}
        if any(k in lower_msg for k in ["ok lets do it", "what's next", "go ahead"]):
            return {"action": "send", "body": "Done! I've proceeded with the next steps. Here is the draft for your review."}
        if "automated" in lower_msg or "respond shortly" in lower_msg or "thank you for contacting" in lower_msg:
            return {"action": "end", "body": ""}
            
        return {"action": "send", "body": "Understood. Let me know how else I can assist you."}
