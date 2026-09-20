import base64
import json
import os
from flask import Flask, jsonify, render_template, request
from openai import OpenAI

app = Flask(__name__)

# Initialize OpenAI client
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


@app.route("/")
def index():
  return render_template("index.html")


@app.route("/scan", methods=["POST"])
def scan():
  try:
    data = request.get_json()
    image_data = data.get("image")

    if not image_data:
      return jsonify({"success": False, "error": "No image provided"}), 400

    # Call OpenAI Vision API with JSON mode
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an expert card appraiser. Analyze the image and"
                    " return a valid JSON object with keys: 'name' (string),"
                    " 'set' (string), 'number' (string), 'raw_price' (float),"
                    " and 'graded_prices' (object with 'PSA 8', 'PSA 9', 'PSA 10'"
                    " as float values)."
                ),
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Identify this card and give market values.",
                    },
                    {"type": "image_url", "image_url": {"url": image_data}},
                ],
            },
        ],
        max_tokens=400,
    )

    content = response.choices[0].message.content
    parsed_data = json.loads(content)

    return jsonify({
        "success": True,
        "image_url": image_data,
        "name": parsed_data.get("name", "Unknown Card"),
        "set": parsed_data.get("set", "Unknown Set"),
        "number": parsed_data.get("number", "N/A"),
        "raw_price": float(parsed_data.get("raw_price", 0.0)),
        "graded_prices": parsed_data.get(
            "graded_prices", {"PSA 10": 0.0, "PSA 9": 0.0}
        ),
    })

  except Exception as e:
    print(f"CRITICAL SCAN ERROR: {str(e)}")
    return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
  app.run(debug=True)