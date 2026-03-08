import requests
from flask import current_app

AI_TOOLS = {
    "caption": "Write a catchy social media caption. Keep it short and attractive.",
    "hashtags": "Generate 10 relevant hashtags only. Output only hashtags separated by spaces.",
    "comment": "Write a short friendly comment reply for this post."
}

def generate_ai_text(tool_name, user_input):
    base_prompt = AI_TOOLS.get(tool_name, "Respond helpfully.")
    final_prompt = f"{base_prompt}\n\nInput: {user_input}"

    payload = {
        "model": current_app.config["OLLAMA_MODEL"],
        "prompt": final_prompt,
        "stream": False
    }

    try:
        response = requests.post(
            current_app.config["OLLAMA_URL"],
            json=payload,
            timeout=current_app.config["OLLAMA_TIMEOUT"]
        )
        response.raise_for_status()
        data = response.json()
        return data.get("response", "").strip()
    except Exception as e:
        return f"AI offline/error: {e}"