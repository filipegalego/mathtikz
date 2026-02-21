import os
import time
import requests
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder="static")
CORS(app)

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

SYSTEM_PROMPT = """És um especialista em TikZ e LaTeX para matemática escolar portuguesa (ensino básico e secundário).
Dado um prompt descrevendo uma imagem matemática, gera APENAS o código LaTeX completo e funcional.

Regras obrigatórias:
- Usa \\documentclass[border=8pt]{standalone}
- Inclui \\usepackage{tikz} e outros packages necessários (pgfplots, amsmath, amssymb, etc.)
- Usa \\usetikzlibrary adequadas: arrows.meta, angles, quotes, calc, patterns, decorations.pathreplacing
- Texto e labels em português
- Código limpo, com comentários
- Imagem com boa margem e proporções para impressão A4
- RESPONDE APENAS com o código LaTeX puro, sem explicações, sem blocos markdown, sem crases."""


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json()
    prompt = data.get("prompt", "").strip()
    model = data.get("model", "google/gemini-2.0-flash-exp:free")

    if not prompt:
        return jsonify({"error": "Prompt vazio."}), 400
    if not OPENROUTER_API_KEY:
        return jsonify({"error": "OPENROUTER_API_KEY não configurada no servidor."}), 500

    url = "https://openrouter.ai/api/v1/chat/completions"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2,
        "max_tokens": 2048,
    }

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://mathtikz.app",
        "X-Title": "MathTikZ"
    }

    resp = None
    wait = 5
    for attempt in range(3):
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
            if resp.status_code == 429 and attempt < 2:
                time.sleep(wait)
                wait += 5
                continue
            resp.raise_for_status()
            break
        except requests.exceptions.RequestException as e:
            if attempt == 2:
                return jsonify({"error": f"Erro ao contactar o modelo: {str(e)}"}), 502
            time.sleep(wait)
            wait += 5

    if resp is None or not resp.ok:
        return jsonify({"error": "Limite de pedidos atingido. Aguarda 1 minuto e tenta de novo."}), 429

    result = resp.json()
    code = result.get("choices", [{}])[0].get("message", {}).get("content", "")

    code = code.strip()
    if code.startswith("```"):
        code = code.split("\n", 1)[-1]
    if code.endswith("```"):
        code = code.rsplit("```", 1)[0]
    code = code.strip()

    if not code:
        return jsonify({"error": "O modelo não devolveu código LaTeX válido."}), 500

    return jsonify({"code": code})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
