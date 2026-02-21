import os
import time
import requests
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder="static")
CORS(app)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

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
    model = data.get("model", "gemini-2.0-flash")
    # Nomes de modelos válidos (atualizado)
    valid_models = ["gemini-2.0-flash", "gemini-2.5-flash-preview-04-17", "gemini-2.5-pro-preview-06-05"]
    if model not in valid_models:
        model = "gemini-2.0-flash"

    if not prompt:
        return jsonify({"error": "Prompt vazio."}), 400
    if not GEMINI_API_KEY:
        return jsonify({"error": "GEMINI_API_KEY não configurada no servidor."}), 500

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"

    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 2048},
    }

    # Retry automático em caso de 429 (rate limit)
    max_retries = 4
    wait_seconds = 15
    resp = None
    for attempt in range(max_retries):
        try:
            resp = requests.post(url, json=payload, timeout=60)
            if resp.status_code == 429:
                if attempt < max_retries - 1:
                    time.sleep(wait_seconds)
                    wait_seconds *= 2  # backoff exponencial: 15s, 30s, 60s
                    continue
            resp.raise_for_status()
            break
        except requests.exceptions.RequestException as e:
            if attempt == max_retries - 1:
                return jsonify({"error": f"Erro ao contactar Gemini: {str(e)}"}), 502
            time.sleep(wait_seconds)
            wait_seconds *= 2

    if resp is None or not resp.ok:
        return jsonify({"error": "Limite de pedidos atingido. Tenta novamente em 1 minuto."}), 429

    result = resp.json()
    code = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")

    # Limpar markdown se o modelo o incluir
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
