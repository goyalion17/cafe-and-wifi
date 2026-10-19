import io
import re

import main


def names(response):
    return re.findall(r'data-title="([^"]+)"', response.get_data(as_text=True))


# ---------- reading ----------
def test_home_lists_all_cafes(client):
    assert sorted(names(client.get("/"))) == ["Alpha", "Beta", "Gamma"]


def test_filter_wifi_and_sockets(client):
    assert sorted(names(client.get("/?wifi=1"))) == ["Alpha", "Gamma"]
    assert names(client.get("/?wifi=1&sockets=1")) == ["Alpha"]


def test_search_by_name_or_area(client):
    assert names(client.get("/?q=peck")) == ["Alpha"]
    assert sorted(names(client.get("/?q=soho"))) == ["Beta", "Gamma"]


def test_price_filter(client):
    assert sorted(names(client.get("/?max_price=2.5"))) == ["Beta", "Gamma"]


def test_sorting(client):
    assert names(client.get("/?sort=price_asc")) == ["Beta", "Gamma", "Alpha"]
    assert names(client.get("/?sort=price_desc")) == ["Alpha", "Gamma", "Beta"]
    assert names(client.get("/?sort=seats_desc"))[0] == "Alpha"


def test_cafe_page_and_404(client):
    assert client.get("/cafe/1").status_code == 200
    assert client.get("/cafe/999").status_code == 404


# ---------- adding ----------
FORM = {"name": "Delta", "map_url": "https://maps.example/d", "img_url": "https://img.example/d.jpg",
        "location": "Brixton", "seats": "5-10", "coffee_price": "£1.90", "has_wifi": "y"}


def test_add_cafe(client):
    r = client.post("/add-cafe", data=FORM)
    assert r.status_code == 302
    assert "Delta" in names(client.get("/"))


def test_add_rejects_duplicate_name_any_case(client):
    r = client.post("/add-cafe", data={**FORM, "name": "ALPHA"})
    assert r.status_code == 200 and b"already exists" in r.data
    assert names(client.get("/")).count("Alpha") == 1


def test_add_needs_image_or_photo(client):
    r = client.post("/add-cafe", data={**FORM, "img_url": ""})
    assert r.status_code == 200 and b"Add an image URL or upload a photo" in r.data


def test_add_with_uploaded_photo(client):
    data = {**FORM, "img_url": "", "photo": (io.BytesIO(b"\x89PNG fake"), "pic.png")}
    r = client.post("/add-cafe", data=data, content_type="multipart/form-data")
    assert r.status_code == 302
    with main.app.app_context():
        cafe = main.db.session.execute(main.db.select(main.Cafe).filter_by(name="Delta")).scalar()
        assert cafe.img_url.startswith("/static/uploads/") and cafe.img_url.endswith(".png")


def test_upload_rejects_non_images(client):
    data = {**FORM, "img_url": "", "photo": (io.BytesIO(b"hello"), "evil.exe")}
    r = client.post("/add-cafe", data=data, content_type="multipart/form-data")
    assert r.status_code == 200 and b"Images only" in r.data


# ---------- login, edit, delete ----------
def test_delete_and_edit_need_login(client):
    assert client.post("/delete-cafe/1").headers["Location"].startswith("/login")
    assert client.get("/cafe/1/edit").headers["Location"].startswith("/login")
    assert "Alpha" in names(client.get("/"))


def test_login_wrong_and_right_password(client):
    assert b"Wrong password" in client.post("/login", data={"password": "nope"}).data
    r = client.post("/login", data={"password": "test-password"})
    assert r.status_code == 302


def test_login_redirect_ignores_external_targets(client):
    r = client.post("/login?next=//evil.example", data={"password": "test-password"})
    assert r.headers["Location"] == "/"


def test_delete_when_logged_in(admin):
    assert admin.post("/delete-cafe/1").status_code == 302
    assert "Alpha" not in names(admin.get("/"))


def test_buttons_only_for_admin(client):
    assert b"Delete this cafe" not in client.get("/cafe/1").data
    client.post("/login", data={"password": "test-password"})
    assert b"Delete this cafe" in client.get("/cafe/1").data


def test_edit_cafe(admin):
    form = {**FORM, "name": "Alpha Renamed", "location": "Peckham"}
    assert admin.post("/cafe/1/edit", data=form).status_code == 302
    assert "Alpha Renamed" in names(admin.get("/"))


def test_edit_cannot_take_another_cafes_name(admin):
    r = admin.post("/cafe/1/edit", data={**FORM, "name": "beta"})
    assert r.status_code == 200 and b"already has that name" in r.data


# ---------- API keeps working (with CSRF switched on) ----------
def test_api_still_works_with_csrf_enabled(client):
    main.app.config["WTF_CSRF_ENABLED"] = True
    assert len(client.get("/all").get_json()["cafes"]) == 3
    r = client.post("/add", data={"name": "ApiCafe", "map_url": "u", "img_url": "i", "location": "l", "seats": "1"})
    assert r.get_json() == {"response": {"success": "Successfully added a new cafe."}}
    r = client.delete("/report-closed/1?api-key=TopSecretAPIKey")
    assert r.status_code == 200


def test_website_forms_need_csrf_token(client):
    main.app.config["WTF_CSRF_ENABLED"] = True
    assert client.post("/add-cafe", data=FORM).status_code == 400
