import hmac
import json
import os
import random
import re
import secrets
import urllib.parse
import urllib.request
import uuid
from functools import wraps
from typing import Optional

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, redirect, url_for, flash, session
from flask_bootstrap import Bootstrap5
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm, CSRFProtect
from flask_wtf.file import FileField, FileAllowed
from werkzeug.utils import secure_filename
from wtforms import StringField, BooleanField, SubmitField, PasswordField, ValidationError
from wtforms.validators import DataRequired, Optional as OptionalValidator, URL
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String, Boolean, Float

'''
Install the required packages first: 
Open the Terminal in PyCharm (bottom left). 

On Windows type:
python -m pip install -r requirements.txt

On MacOS type:
pip3 install -r requirements.txt

This will install the packages from requirements.txt for this project.
'''

load_dotenv()

app = Flask(__name__)
# Secrets live in .env (see .env.example). Without SECRET_KEY a random one is used (sessions reset on restart).
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # photo uploads up to 5 MB
UPLOAD_DIR = os.path.join(app.static_folder, 'uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)
Bootstrap5(app)
csrf = CSRFProtect(app)

# CREATE DB
class Base(DeclarativeBase):
    pass
# Connect to Database
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///cafes.db')
db = SQLAlchemy(model_class=Base)
db.init_app(app)


# Cafe TABLE Configuration
class Cafe(db.Model):
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(250), unique=True, nullable=False)
    map_url: Mapped[str] = mapped_column(String(500), nullable=False)
    img_url: Mapped[str] = mapped_column(String(500), nullable=False)
    location: Mapped[str] = mapped_column(String(250), nullable=False)
    seats: Mapped[str] = mapped_column(String(250), nullable=True)
    has_toilet: Mapped[bool] = mapped_column(Boolean, nullable=False)
    has_wifi: Mapped[bool] = mapped_column(Boolean, nullable=False)
    has_sockets: Mapped[bool] = mapped_column(Boolean, nullable=False)
    can_take_calls: Mapped[bool] = mapped_column(Boolean, nullable=False)
    coffee_price: Mapped[str] = mapped_column(String(250), nullable=True)
    lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lng: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


with app.app_context():
    db.create_all()


def first_number(text, use_max=False):
    """Pull a number out of strings like '£2.50' or '20-30' or '50+'. None if there is none."""
    numbers = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", text or "")]
    if not numbers:
        return None
    return max(numbers) if use_max else numbers[0]


SORTS = {
    "name": "Name A–Z",
    "price_asc": "Cheapest coffee",
    "price_desc": "Priciest coffee",
    "seats_desc": "Most seats",
}


@app.route("/")
def home():
    boolean_filters = {
        "wifi": Cafe.has_wifi,
        "sockets": Cafe.has_sockets,
        "calls": Cafe.can_take_calls,
        "toilet": Cafe.has_toilet,
    }
    query = db.select(Cafe).order_by(Cafe.name)
    for param, column in boolean_filters.items():
        if request.args.get(param) == "1":
            query = query.where(column == True)

    text = request.args.get("q", "").strip()
    if text:
        like = f"%{text}%"
        query = query.where(db.or_(Cafe.name.ilike(like), Cafe.location.ilike(like)))

    cafes = db.session.execute(query).scalars().all()

    # Prices are stored as text ("£2.50"), so price and seats are handled in Python.
    prices = [first_number(c.coffee_price) for c in db.session.execute(db.select(Cafe)).scalars()]
    prices = [p for p in prices if p is not None]
    price_ceiling = int(max(prices) + 0.999) if prices else 5
    max_price = request.args.get("max_price", type=float)
    if max_price is None or max_price >= price_ceiling:
        max_price = price_ceiling
    else:
        cafes = [c for c in cafes
                 if first_number(c.coffee_price) is not None and first_number(c.coffee_price) <= max_price]

    sort = request.args.get("sort", "name")
    if sort not in SORTS:
        sort = "name"
    missing = float("inf")
    if sort == "price_asc":
        cafes.sort(key=lambda c: first_number(c.coffee_price) if first_number(c.coffee_price) is not None else missing)
    elif sort == "price_desc":
        cafes.sort(key=lambda c: -(first_number(c.coffee_price) if first_number(c.coffee_price) is not None else -missing))
    elif sort == "seats_desc":
        cafes.sort(key=lambda c: -(first_number(c.seats, use_max=True) or 0))

    filters_active = bool(
        text or sort != "name" or max_price < price_ceiling
        or any(request.args.get(k) == "1" for k in boolean_filters)
    )
    return render_template(
        "index.html", cafes=cafes, q=text, sort=sort, sorts=SORTS,
        price_ceiling=price_ceiling, max_price=max_price, filters_active=filters_active,
    )


@app.route("/cafe/<int:cafe_id>")
def cafe_page(cafe_id):
    cafe = db.get_or_404(Cafe, cafe_id)
    return render_template("cafe.html", cafe=cafe)


@app.route("/api-docs")
def api_docs():
    return render_template("api_docs.html")

# HTTP GET - Read Record
@app.route("/random")
def get_random_cafe():
    all_cafes = db.session.execute(db.select(Cafe)).scalars().all()
    random_cafe = random.choice(all_cafes)
    return jsonify(cafe={
        "id": random_cafe.id,
        "name": random_cafe.name,
        "map_url": random_cafe.map_url,
        "img_url": random_cafe.img_url,
        "location": random_cafe.location,
        "seats": random_cafe.seats,
        "has_toilet": random_cafe.has_toilet,
        "has_wifi": random_cafe.has_wifi,
        "has_sockets": random_cafe.has_sockets,
        "can_take_calls": random_cafe.can_take_calls,
        "coffee_price": random_cafe.coffee_price,
    })

@app.route("/all")
def get_all_cafes():
    all_cafes = db.session.execute(db.select(Cafe)).scalars().all()
    return jsonify(cafes=[{
        "id": cafe.id,
        "name": cafe.name,
        "map_url": cafe.map_url,
        "img_url": cafe.img_url,
        "location": cafe.location,
        "seats": cafe.seats,
        "has_toilet": cafe.has_toilet,
        "has_wifi": cafe.has_wifi,
        "has_sockets": cafe.has_sockets,
        "can_take_calls": cafe.can_take_calls,
        "coffee_price": cafe.coffee_price,
    } for cafe in all_cafes])

@app.route("/search")
def search_cafe():
    query_location = request.args.get("loc")
    cafe = db.session.execute(db.select(Cafe).filter_by(location=query_location)).scalar()
    if cafe:
        return jsonify(cafe={
            "id": cafe.id,
            "name": cafe.name,
            "map_url": cafe.map_url,
            "img_url": cafe.img_url,
            "location": cafe.location,
            "seats": cafe.seats,
            "has_toilet": cafe.has_toilet,
            "has_wifi": cafe.has_wifi,
            "has_sockets": cafe.has_sockets,
            "can_take_calls": cafe.can_take_calls,
            "coffee_price": cafe.coffee_price,
        })
    else:
        return jsonify(error={"Not Found": "Sorry, we don't have a cafe at that location."})

# HTTP POST - Create Record
@csrf.exempt  # JSON/form API for scripts and Postman: no browser session, so no CSRF token
@app.route("/add", methods=["POST"])
def add_cafe():
    new_cafe = Cafe(
        name=request.form.get("name"),
        map_url=request.form.get("map_url"),
        img_url=request.form.get("img_url"),
        location=request.form.get("location"),
        seats=request.form.get("seats"),
        has_toilet=request.form.get("has_toilet") == "True",
        has_wifi=request.form.get("has_wifi") == "True",
        has_sockets=request.form.get("has_sockets") == "True",
        can_take_calls=request.form.get("can_take_calls") == "True",
        coffee_price=request.form.get("coffee_price")
    )
    db.session.add(new_cafe)
    db.session.commit()
    return jsonify(response={"success": "Successfully added a new cafe."})

# HTTP PUT/PATCH - Update Record
@csrf.exempt  # JSON/form API for scripts and Postman: no browser session, so no CSRF token
@app.route("/update-price/<int:cafe_id>", methods=["PATCH"])
def update_cafe_price(cafe_id):
    cafe = db.session.execute(db.select(Cafe).filter_by(id=cafe_id)).scalar()
    if cafe:
        cafe.coffee_price = request.args.get("new_price")
        db.session.commit()
        return jsonify(response={"success": "Successfully updated cafe price."})
    else:
        return jsonify(error={"Not Found": "Sorry, we don't have a cafe with that ID."}), 404

# HTTP DELETE - Delete Record
@csrf.exempt  # JSON/form API for scripts and Postman: no browser session, so no CSRF token
@app.route("/report-closed/<int:cafe_id>", methods=["DELETE"])
def delete_cafe(cafe_id):
    api_key = request.args.get("api-key")
    if api_key == "TopSecretAPIKey":
        cafe = db.session.execute(db.select(Cafe).filter_by(id=cafe_id)).scalar()
        if cafe:
            db.session.delete(cafe)
            db.session.commit()
            return jsonify(response={"success": "Successfully deleted the cafe from the database."})
        else:
            return jsonify(error={"Not Found": "Sorry a cafe with that id was not found in the database."}), 404
    else:
        return jsonify(error={"Forbidden": "Sorry, that's not allowed. Make sure you have the correct api_key."}), 403


# ---------- Website (HTML pages) ----------
def geocode(query):
    """Find (lat, lng) for a text query via OpenStreetMap Nominatim; (None, None) if not found."""
    url = "https://nominatim.openstreetmap.org/search?format=json&limit=1&q=" + urllib.parse.quote(query)
    req = urllib.request.Request(url, headers={"User-Agent": "cafe-and-wifi-student-project"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.load(resp)
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    except (OSError, ValueError, KeyError):
        pass
    return None, None


# ----- login (protects editing and deleting) -----
@app.context_processor
def inject_auth():
    return {"is_admin": bool(session.get("admin"))}


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin"):
            flash("Please log in to do that.", "warning")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


class LoginForm(FlaskForm):
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Log in")


@app.route("/login", methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        expected = os.environ.get("ADMIN_PASSWORD", "")
        if expected and hmac.compare_digest(form.password.data, expected):
            session["admin"] = True
            flash("Logged in.", "success")
            target = request.args.get("next", "")
            if not target.startswith("/") or target.startswith("//"):
                target = url_for("home")
            return redirect(target)
        flash("Wrong password.", "danger")
    return render_template("login.html", form=form)


@app.route("/logout", methods=["POST"])
def logout():
    session.pop("admin", None)
    flash("Logged out.", "success")
    return redirect(url_for("home"))


# ----- add / edit cafes -----
def url_or_upload(form, field):
    """Accept a normal URL or a photo already uploaded to this site."""
    if field.data and not field.data.startswith("/static/uploads/"):
        URL()(form, field)


class CafeForm(FlaskForm):
    name = StringField("Cafe name", validators=[DataRequired()])
    map_url = StringField("Google Maps URL", validators=[DataRequired(), URL()])
    img_url = StringField("Image URL", validators=[OptionalValidator(), url_or_upload])
    photo = FileField("...or upload a photo", validators=[FileAllowed(["jpg", "jpeg", "png", "webp", "gif"], "Images only.")])
    location = StringField("Location", validators=[DataRequired()])
    seats = StringField("Seats (e.g. 20-30)", validators=[DataRequired()])
    coffee_price = StringField("Coffee price (e.g. £2.50)")
    has_wifi = BooleanField("Wi-Fi")
    has_sockets = BooleanField("Power sockets")
    has_toilet = BooleanField("Toilet")
    can_take_calls = BooleanField("Can take calls")
    submit = SubmitField("Add cafe")


def save_upload(file_storage):
    """Store an uploaded photo under static/uploads and return its URL path."""
    extension = os.path.splitext(secure_filename(file_storage.filename))[1].lower()
    filename = uuid.uuid4().hex + extension
    file_storage.save(os.path.join(UPLOAD_DIR, filename))
    return url_for("static", filename="uploads/" + filename)


def remove_upload(img_url):
    """Delete a photo file we stored ourselves (never touches external URLs)."""
    prefix = "/static/uploads/"
    if img_url and img_url.startswith(prefix):
        path = os.path.join(UPLOAD_DIR, os.path.basename(img_url))
        if os.path.isfile(path):
            os.remove(path)


def name_taken(name, ignore_id=None):
    query = db.select(Cafe).where(db.func.lower(Cafe.name) == name.strip().lower())
    if ignore_id is not None:
        query = query.where(Cafe.id != ignore_id)
    return db.session.execute(query).scalar() is not None


@app.route("/add-cafe", methods=["GET", "POST"])
def add_cafe_page():
    form = CafeForm()
    if form.validate_on_submit():
        if name_taken(form.name.data):
            flash("A cafe with that name already exists.", "warning")
        elif not form.photo.data and not form.img_url.data:
            form.img_url.errors.append("Add an image URL or upload a photo.")
        else:
            img_url = save_upload(form.photo.data) if form.photo.data else form.img_url.data
            lat, lng = geocode(f"{form.name.data}, {form.location.data}, London")
            new_cafe = Cafe(
                lat=lat,
                lng=lng,
                name=form.name.data.strip(),
                map_url=form.map_url.data,
                img_url=img_url,
                location=form.location.data,
                seats=form.seats.data,
                coffee_price=form.coffee_price.data or None,
                has_wifi=form.has_wifi.data,
                has_sockets=form.has_sockets.data,
                has_toilet=form.has_toilet.data,
                can_take_calls=form.can_take_calls.data,
            )
            db.session.add(new_cafe)
            db.session.commit()
            flash(f"Added {new_cafe.name}.", "success")
            return redirect(url_for("home"))
    return render_template("add.html", form=form, heading="Add a new cafe", cancel_url=url_for("home"))


@app.route("/cafe/<int:cafe_id>/edit", methods=["GET", "POST"])
@login_required
def edit_cafe_page(cafe_id):
    cafe = db.get_or_404(Cafe, cafe_id)
    form = CafeForm(obj=cafe)
    form.submit.label.text = "Save changes"
    if form.validate_on_submit():
        if name_taken(form.name.data, ignore_id=cafe.id):
            flash("Another cafe already has that name.", "warning")
        elif not form.photo.data and not form.img_url.data:
            form.img_url.errors.append("Add an image URL or upload a photo.")
        else:
            moved = (form.name.data.strip() != cafe.name or form.location.data != cafe.location
                     or cafe.lat is None)
            old_img = cafe.img_url
            cafe.img_url = save_upload(form.photo.data) if form.photo.data else form.img_url.data
            if cafe.img_url != old_img:
                remove_upload(old_img)
            cafe.name = form.name.data.strip()
            cafe.map_url = form.map_url.data
            cafe.location = form.location.data
            cafe.seats = form.seats.data
            cafe.coffee_price = form.coffee_price.data or None
            cafe.has_wifi = form.has_wifi.data
            cafe.has_sockets = form.has_sockets.data
            cafe.has_toilet = form.has_toilet.data
            cafe.can_take_calls = form.can_take_calls.data
            if moved:
                lat, lng = geocode(f"{cafe.name}, {cafe.location}, London")
                if lat is not None:
                    cafe.lat, cafe.lng = lat, lng
            db.session.commit()
            flash(f"Saved {cafe.name}.", "success")
            return redirect(url_for("cafe_page", cafe_id=cafe.id))
    return render_template("add.html", form=form, heading=f"Edit {cafe.name}",
                           cancel_url=url_for("cafe_page", cafe_id=cafe.id))


@app.route("/delete-cafe/<int:cafe_id>", methods=["POST"])
@login_required
def delete_cafe_page(cafe_id):
    cafe = db.get_or_404(Cafe, cafe_id)
    remove_upload(cafe.img_url)
    db.session.delete(cafe)
    db.session.commit()
    flash(f"Deleted {cafe.name}.", "success")
    return redirect(url_for("home"))


if __name__ == '__main__':
    app.run(debug=True, port=5001)
