import os
import json
from pathlib import Path
from bot import compose

def main():
    base_dir = Path(__file__).parent / "dataset" / "expanded"
    test_pairs_path = base_dir / "test_pairs.json"
    
    if not test_pairs_path.exists():
        print(f"Error: {test_pairs_path} not found. Please generate expanded dataset first.")
        return
        
    with open(test_pairs_path, "r", encoding="utf-8") as f:
        pairs_data = json.load(f)
        
    test_pairs = pairs_data.get("pairs", [])
    print(f"Loaded {len(test_pairs)} test benchmark pairs.")
    
    # Load categories index
    categories = {}
    cat_dir = base_dir / "categories"
    if cat_dir.exists():
        for f in cat_dir.glob("*.json"):
            data = json.load(open(f, encoding="utf-8"))
            categories[data.get("slug", f.stem)] = data
            
    # Load merchants index
    merchants = {}
    merch_dir = base_dir / "merchants"
    if merch_dir.exists():
        for f in merch_dir.glob("*.json"):
            data = json.load(open(f, encoding="utf-8"))
            merchants[data.get("merchant_id", f.stem)] = data

    # Load triggers index
    triggers = {}
    trig_dir = base_dir / "triggers"
    if trig_dir.exists():
        for f in trig_dir.glob("*.json"):
            data = json.load(open(f, encoding="utf-8"))
            triggers[data.get("id", f.stem)] = data

    # Load customers index
    customers = {}
    cust_dir = base_dir / "customers"
    if cust_dir.exists():
        for f in cust_dir.glob("*.json"):
            data = json.load(open(f, encoding="utf-8"))
            customers[data.get("customer_id", f.stem)] = data

    output_lines = []
    
    for item in test_pairs:
        test_id = item["test_id"]
        trig_id = item["trigger_id"]
        merch_id = item["merchant_id"]
        cust_id = item.get("customer_id")
        
        trigger = triggers.get(trig_id)
        merchant = merchants.get(merch_id)
        customer = customers.get(cust_id) if cust_id else None
        
        if not trigger or not merchant:
            print(f"Skipping {test_id}: missing trigger or merchant context.")
            continue
            
        cat_slug = merchant.get("category_slug")
        if not cat_slug and trigger.get("payload"):
            cat_slug = trigger["payload"].get("category")
            
        category = categories.get(cat_slug)
        if not category:
            print(f"Skipping {test_id}: category context for {cat_slug} not found.")
            continue
            
        print(f"Composing {test_id} ({cat_slug} / {merch_id[:15]} / {trig_id[:20]})...")
        action = compose(category, merchant, trigger, customer)
        
        submission_entry = {
            "test_id": test_id,
            "body": action.get("body", ""),
            "cta": action.get("cta", "none"),
            "send_as": action.get("send_as", "vera"),
            "suppression_key": action.get("suppression_key", ""),
            "rationale": action.get("rationale", "")
        }
        output_lines.append(submission_entry)
        
    out_file = Path(__file__).parent / "submission.jsonl"
    with open(out_file, "w", encoding="utf-8") as f:
        for entry in output_lines:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            
    print(f"\nSuccessfully generated {len(output_lines)} entries in {out_file}")

if __name__ == "__main__":
    main()
