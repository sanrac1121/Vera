from flask import Flask, request, jsonify
import json
import logging
import traceback
from bot import compose
from conversation_handlers import respond

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# In-memory context storage
contexts = {
    "category": {},
    "merchant": {},
    "trigger": {},
    "customer": {}
}

# In-memory conversation state
conversations = {}

@app.route("/v1/healthz", methods=["GET"])
def healthz():
    return jsonify({"status": "ok"})

@app.route("/v1/metadata", methods=["GET"])
def metadata():
    return jsonify({
        "team_name": "Sanchit Agrawal",
        "model": "gemini-1.5-pro / openai-gpt-4o"
    })

@app.route("/v1/context", methods=["POST"])
def push_context():
    data = request.json
    scope = data.get("scope")
    context_id = data.get("context_id")
    payload = data.get("payload")
    
    if scope in contexts:
        contexts[scope][context_id] = payload
        return jsonify({"accepted": True})
    return jsonify({"accepted": False, "error": "Invalid scope"}), 400

@app.route("/v1/tick", methods=["POST"])
def tick():
    data = request.json
    available_triggers = data.get("available_triggers", [])
    
    actions = []
    for tid in available_triggers:
        try:
            trigger = contexts["trigger"].get(tid)
            if not trigger:
                continue
                
            # Usually the payload is what bot.py expects as 'trigger'
            trigger_payload = trigger.get("payload", {})
            merchant_id = trigger_payload.get("merchant_id")
            
            # fallback mapping if merchant_id is directly on trigger dict
            if not merchant_id:
                merchant_id = trigger.get("merchant_id")
                
            merchant = contexts["merchant"].get(merchant_id) if merchant_id else None
            
            category = None
            if merchant:
                cat_slug = merchant.get("category_slug")
                category = contexts["category"].get(cat_slug)
                
            if not category:
                cat_slug = trigger_payload.get("category")
                if cat_slug:
                    category = contexts["category"].get(cat_slug)
                    
            customer_id = trigger_payload.get("customer_id")
            customer = contexts["customer"].get(customer_id) if customer_id else None
            
            # Passing the full trigger object (which has id, scope, payload) to compose
            if category and merchant and trigger:
                action = compose(category, merchant, trigger, customer)
                actions.append(action)
        except Exception as e:
            logger.error(f"Error processing tick for {tid}: {e}")
            traceback.print_exc()
            
    return jsonify({"actions": actions})

@app.route("/v1/reply", methods=["POST"])
def reply():
    try:
        data = request.json
        conv_id = data.get("conversation_id")
        merchant_id = data.get("merchant_id")
        message = data.get("message")
        
        # Initialize conversation state
        if conv_id not in conversations:
            conversations[conv_id] = {"history": []}
            
        state = conversations[conv_id]
        
        # Determine the action
        result = respond(state, message)
        
        # Update history
        state["history"].append({
            "role": "merchant",
            "content": message
        })
        
        if result.get("action") == "send" and result.get("body"):
            state["history"].append({
                "role": "vera",
                "content": result.get("body")
            })
            
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error processing reply: {e}")
        traceback.print_exc()
        return jsonify({"action": "end", "body": "Internal server error."})

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
