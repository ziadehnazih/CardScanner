import base64
import json
import os
from flask import Flask, jsonify, render_template, redirect, url_for, request
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from openai import OpenAI

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///cards.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Debug check for OpenAI API key
api_key_check = os.environ.get("OPENAI_API_KEY")
client = OpenAI(api_key=api_key_check)

# --- Database Models ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    collections = db.relationship('Collection', backref='owner', lazy=True)

class Collection(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, default="Default Collection")
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    cards = db.relationship('CardScan', backref='collection', lazy=True)

class CardScan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    set_name = db.Column(db.String(150), nullable=False)
    card_number = db.Column(db.String(50), nullable=False)
    raw_price = db.Column(db.Float, nullable=False)
    graded_prices_json = db.Column(db.Text, nullable=False) # stored as json string
    image_url = db.Column(db.Text, nullable=False)
    collection_id = db.Column(db.Integer, db.ForeignKey('collection.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

with app.app_context():
    db.create_all()

# --- Routes ---
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    username = data.get("username")
    if not username:
        return jsonify({"success": False, "error": "Username required"}), 400
    
    user = User.query.filter_by(username=username).first()
    if not user:
        user = User(username=username)
        db.session.add(user)
        db.session.commit()
        # Create a default collection for new user
        default_col = Collection(name="Main Portfolio", user_id=user.id)
        db.session.add(default_col)
        db.session.commit()
        
    login_user(user)
    return jsonify({"success": True, "username": user.username})

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route("/scan", methods=["POST"])
def scan():
  try:
    data = request.get_json()
    image_data = data.get("image")
    collection_id = data.get("collection_id")

    if not image_data:
      return jsonify({"success": False, "error": "No image provided"}), 400

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
                    {"type": "text", "text": "Identify this card and give market values."},
                    {"type": "image_url", "image_url": {"url": image_data}},
                ],
            },
        ],
        max_tokens=400,
        timeout=30.0,
    )

    content = response.choices[0].message.content
    parsed_data = json.loads(content)
    
    scan_result = {
        "success": True,
        "image_url": image_data,
        "name": parsed_data.get("name", "Unknown Card"),
        "set": parsed_data.get("set", "Unknown Set"),
        "number": parsed_data.get("number", "N/A"),
        "raw_price": float(parsed_data.get("raw_price", 0.0)),
        "graded_prices": parsed_data.get("graded_prices", {"PSA 10": 0.0, "PSA 9": 0.0}),
    }

    # If user is logged in and selected a collection, save to database!
    if current_user.is_authenticated and collection_id:
        new_scan = CardScan(
            name=scan_result["name"],
            set_name=scan_result["set"],
            card_number=scan_result["number"],
            raw_price=scan_result["raw_price"],
            graded_prices_json=json.dumps(scan_result["graded_prices"]),
            image_url=image_data,
            collection_id=int(collection_id)
        )
        db.session.add(new_scan)
        db.session.commit()

    return jsonify(scan_result)

  except Exception as e:
    print(f"CRITICAL SCAN ERROR: {str(e)}")
    return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/collections", methods=["GET"])
@login_required
def get_collections():
    cols = Collection.query.filter_by(user_id=current_user.id).all()
    result = []
    for c in cols:
        cards_list = []
        total_val = 0
        for card in c.cards:
            total_val += card.raw_price
            cards_list.append({
                "id": card.id,
                "name": card.name,
                "set": card.set_name,
                "number": card.card_number,
                "raw_price": card.raw_price,
                "graded_prices": json.loads(card.graded_prices_json),
                "image_url": card.image_url
            })
        result.append({
            "id": c.id,
            "name": c.name,
            "total_value": total_val,
            "cards": cards_list
        })
    return jsonify({"success": True, "collections": result})

@app.route("/api/collections/create", methods=["POST"])
@login_required
def create_collection():
    data = request.get_json()
    name = data.get("name")
    if not name:
        return jsonify({"success": False, "error": "Collection name required"}), 400
    
    new_col = Collection(name=name, user_id=current_user.id)
    db.session.add(new_col)
    db.session.commit()
    return jsonify({"success": True, "id": new_col.id, "name": new_col.name})

if __name__ == "__main__":
  app.run(debug=True)