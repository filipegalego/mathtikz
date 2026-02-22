import os
import io
import time
import requests
import tempfile
import subprocess
from flask import Flask, request, jsonify, send_from_directory, send_file
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
- Se usares pgfplots, usa SEMPRE \\pgfplotsset{compat=1.14} (nunca versões superiores)
- Nas coordenadas de pgfplots usa SEMPRE valores numéricos decimais (ex: 3.14159, 6.28318) — NUNCA expressões simbólicas como pi, 2*pi, pi/4, sqrt(2), etc.
- Em `axis cs:` e em `xtick`, `ytick` usa sempre números decimais com 4 casas (ex: xtick={0, 1.5708, 3.1416, 4.7124, 6.2832})
- Texto e labels em português
- Código limpo, com comentários
- Imagem com boa margem e proporções para impressão A4
- Verifica SEMPRE a correção matemática: coordenadas, interseções, vértices, ângulos e labels devem ser matematicamente exatos
- Em gráficos de funções: calcula analiticamente os zeros, vértices e pontos notáveis antes de os marcar
- Labels e coordenadas NUNCA devem sobrepor-se: usa deslocamentos explícitos com node[above left], node[below right], node[anchor=north], etc.
- Nas marcas dos eixos usa node[below] para eixo x e node[left] para eixo y, com espaçamento suficiente
- RESPONDE APENAS com o código LaTeX puro, sem explicações, sem blocos markdown, sem crases."""

VALID_MODELS = {
    "gemini-2.5-pro": "gemini-2.5-pro",
    "gemini-2.0-flash": "gemini-2.0-flash",
}


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json()
    prompt = data.get("prompt", "").strip()
    model_key = data.get("model", "gemini-2.5-pro")

    if not prompt:
        return jsonify({"error": "Prompt vazio."}), 400
    if not GEMINI_API_KEY:
        return jsonify({"error": "GEMINI_API_KEY não configurada no servidor."}), 500

    model_id = VALID_MODELS.get(model_key, VALID_MODELS["gemini-2.5-pro"])
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={GEMINI_API_KEY}"

    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 4096},
    }

    resp = None
    wait = 5
    for attempt in range(3):
        try:
            resp = requests.post(url, json=payload, timeout=60)
            if resp.status_code == 429 and attempt < 2:
                time.sleep(wait)
                wait += 5
                continue
            resp.raise_for_status()
            break
        except requests.exceptions.RequestException as e:
            if attempt == 2:
                return jsonify({"error": f"Erro ao contactar Gemini: {str(e)}"}), 502
            time.sleep(wait)
            wait += 5

    if resp is None or not resp.ok:
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text[:300] if resp else "sem resposta"
        return jsonify({"error": f"Erro {resp.status_code if resp else 0}: {detail}"}), 429

    try:
        result = resp.json()
    except Exception:
        return jsonify({"error": f"Resposta inválida: {resp.text[:300]}"}), 500

    code = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
    code = code.strip()
    if code.startswith("```"):
        code = code.split("\n", 1)[-1]
    if code.endswith("```"):
        code = code.rsplit("```", 1)[0]
    code = code.strip()

    if not code:
        return jsonify({"error": "O modelo não devolveu código LaTeX válido."}), 500

    return jsonify({"code": code})


@app.route("/png", methods=["POST"])
def generate_png():
    data = request.get_json()
    code = data.get("code", "").strip()
    if not code:
        return jsonify({"error": "Código LaTeX vazio."}), 400

    try:
        from pdf2image import convert_from_bytes

        with tempfile.TemporaryDirectory() as tmpdir:
            tex_path = os.path.join(tmpdir, "main.tex")
            pdf_path = os.path.join(tmpdir, "main.pdf")

            with open(tex_path, "w", encoding="utf-8") as f:
                f.write(code)

            result = subprocess.run(
                ["pdflatex", "-interaction=nonstopmode", "-output-directory", tmpdir, tex_path],
                capture_output=True, text=True, timeout=30
            )

            if not os.path.exists(pdf_path):
                return jsonify({"error": "Erro de compilação LaTeX: " + result.stdout[-500:]}), 500

            images = convert_from_bytes(open(pdf_path, "rb").read(), dpi=200)
            img_io = io.BytesIO()
            images[0].save(img_io, format="PNG")
            img_io.seek(0)

            return send_file(img_io, mimetype="image/png",
                             as_attachment=True, download_name="imagem-matematica.png")

    except FileNotFoundError:
        return jsonify({"error": "pdflatex não está instalado no servidor."}), 500
    except Exception as e:
        return jsonify({"error": f"Erro ao gerar PNG: {str(e)}"}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
