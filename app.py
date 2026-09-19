import base64
import json
import os
from flask import Flask, jsonify, render_template, request
from openai import OpenAI

os.makedirs("uploads", exist_ok=True)
app = Flask(__name__)

# This automatically grabs the API key you exported in your terminal
client = OpenAI()


@app.route("/")
def index():
  return render_template("index.html")


@app.route("/scan", methods=["POST"])
def scan_card():
  try:
    data = request.json
    image_data = data["image"]

    # Decode the base64 image from the webcam
    header, encoded = image_data.split(",", 1)
    image_bytes = base64.b64decode(encoded)

    file_path = os.path.join("uploads", "uploaded_card.jpg")
    with open(file_path, "wb") as f:
      f.write(image_bytes)

    # Ask OpenAI's Vision model to identify the card
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a collectible trading card expert. Identify the"
                    " card in the image and return a JSON object with EXACTLY"
                    ' these keys: "name" (string), "set" (string), "number"'
                    ' (string), "image_url" (string, leave empty or find a'
                    ' placeholder URL if possible), "raw_price" (float estimated'
                    ' market price), and "graded_prices" (a dictionary with'
                    ' keys like "PSA 7", "PSA 8", "PSA 9", "PSA 10" and float'
                    " values). Do not include any markdown formatting blocks like"
                    " ```json, just output raw JSON."
                ),
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "What trading card is this? Estimate its market"
                            " value and graded prices."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{encoded}"},
                    },
                ],
            },
        ],
        max_tokens=300,
    )

    # Parse the AI's response text back into a dictionary
    ai_text = response.choices[0].message.content.strip()
    # Clean up markdown code blocks if the AI accidentally adds them
    if ai_text.startswith("```"):
      ai_text = ai_text.split("```")[1]
      if ai_text.startswith("json"):
        ai_text = ai_text[4:]
    ai_text = ai_text.strip()

    card_info = json.loads(ai_text)
    card_info["success"] = True

    return jsonify(card_info)

  except Exception as e:
    print(f"Error processing scan: {e}")
    return jsonify(
        {"success": False, "error": "Could not recognize card via AI."}
    )


if __name__ == "__main__":
  app.run(debug=True, port=5000)
