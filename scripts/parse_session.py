#!/usr/bin/env python3
import json, sys

fpath = sys.argv[1] if len(sys.argv) > 1 else "/home/ubuntu/.openclaw/agents/main/sessions/96289c4b-59ad-4beb-ae6c-8e89686ac522.jsonl"
with open(fpath) as f:
    for line in f:
        try:
            obj = json.loads(line.strip())
            if obj.get("type") == "message":
                msg = obj["message"]
                role = msg.get("role", "?")
                ts = obj.get("timestamp", "?")
                content = msg.get("content", [])
                texts = []
                for c in content:
                    if isinstance(c, dict):
                        if c.get("type") == "text":
                            texts.append(c["text"][:300])
                        elif c.get("type") == "toolCall":
                            args_str = json.dumps(c.get("arguments", {}), ensure_ascii=False)[:200]
                            texts.append("[TOOL:" + c.get("name","?") + "] " + args_str)
                        elif c.get("type") == "toolResult":
                            txt = ""
                            for sub in c.get("content", []):
                                if isinstance(sub, dict):
                                    txt = sub.get("text", "")[:200]
                            texts.append("[RESULT:" + c.get("toolName", "?") + "] " + txt)
                if texts:
                    combined = " | ".join(texts)[:500]
                    print("[" + ts + "] " + role + ": " + combined)
        except Exception as e:
            print("ERROR: " + str(e), file=sys.stderr)
