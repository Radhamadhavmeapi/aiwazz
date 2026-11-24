"""Speaking styles + pronunciation dictionary (inline syntax, user list, global list, ▶ test)."""
from tests.conftest import identity, signup
from tts.hinglish import to_devanagari
from tts.pronounce import Entry, apply, check_entry, render, strip_inline
from tts.text import normalize


# ── pure functions ──
def test_apply_priority_whole_word_and_case():
    entries = [Entry("api", "ए पी आई"), Entry("API", "ignored, later duplicate"), Entry("GST", "G S T"),
               Entry("GST number", "G S T नंबर"), Entry("₹", "rupaye")]
    out = render(apply("Api aur APIs. gst-free, GST number, GSTIN. [Kalyan](कल्याण) ₹", entries))
    assert out == "ए पी आई aur APIs. G S T-free, G S T नंबर, GSTIN. कल्याण rupaye"


def test_inline_wins_and_is_not_replaced_again():
    assert render(apply("[GST](जी एस टी) and GST", [Entry("GST", "G S T")])) == "जी एस टी and G S T"
    assert strip_inline("Say [GST](G S T) now") == "Say GST now"
    assert render(apply("[only brackets] (and parens)")) == "[only brackets] (and parens)"


def test_transliteration_skips_replacements_and_keeps_context():
    out = render(apply("Order [Kalyan](kalyaan) mein aaya"), to_devanagari)
    assert out == "Order kalyaan में आया"   # say-as kept exactly; "mein" still read as में from the sentence


def test_check_entry():
    assert check_entry("GST", "G S T") is None
    assert check_entry("GST", "gst") is not None
    assert check_entry("a(b)", "x") is not None
    assert check_entry(" ", "x") is not None


def test_lone_rupee_by_language():
    assert normalize("Prices in ₹. Only ₹499!", "a") == "Prices in rupees. Only 499 rupees!"
    assert normalize("कीमत ₹ में", "h") == "कीमत रुपये में"


# ── API ──
def _spy(client):
    """Record the sentences the (fake) engine is asked to read."""
    eng = client.app.state.jobs.engine
    said, orig = [], eng.synthesize

    def synth(sentence, voice, lang, speed):
        said.append((sentence, speed))
        return orig(sentence, voice, lang, speed)
    eng.synthesize = synth
    return said


def test_styles_endpoint():
    from tts.styles import STYLES
    assert [s.name for s in STYLES.values()] == ["Energetic reel", "Calm narrator", "Ad announcer", "Friendly explainer"]
    assert not any("emotion" in (s.name + s.description).lower() for s in STYLES.values())


def test_style_sets_pace_loudness_and_is_stored(client):
    assert [s["id"] for s in client.get("/api/styles").json()["styles"]][0] == "energetic-reel"
    assert client.post("/api/tts", json={"text": "Hi.", "style": "angry"}).status_code == 422
    said = _spy(client)
    r = client.post("/api/tts?wait=true", json={"text": "Pehla. Doosra.", "style": "calm-narrator"})
    assert r.status_code == 200, r.text
    assert r.json()["loudness"]["target_lufs"] == -16.0
    assert {sp for _, sp in said} == {0.92}
    r = client.post("/api/tts?wait=true", json={"text": "Teen.", "style": "energetic-reel", "speed": 1.0, "loudness_lufs": -18})
    assert said[-1][1] == 1.0 and r.json()["loudness"]["target_lufs"] == -18.0   # explicit values win
    h = client.get("/api/history").json()["items"]
    assert [i["style"] for i in h] == ["energetic-reel", "calm-narrator"]


def test_user_list_crud_and_isolation(anon, make_invite):
    make_invite("AAAA-AAAA")
    make_invite("BBBB-BBBB")
    signup(anon, email="a@example.com", code="AAAA-AAAA")
    r = anon.post("/api/pronunciations", json={"word": "  Kalyan ", "say_as": "कल्याण"})
    assert r.status_code == 200 and r.json()["word"] == "Kalyan"
    eid = r.json()["id"]
    assert anon.post("/api/pronunciations", json={"word": "kalyan", "say_as": "कल्यान"}).json()["id"] == eid   # upsert
    assert anon.post("/api/pronunciations", json={"word": "x", "say_as": "X"}).status_code == 422
    lst = anon.get("/api/pronunciations").json()
    assert [(i["word"], i["say_as"]) for i in lst["items"]] == [("kalyan", "कल्यान")]
    assert lst["can_edit_global"] is False and lst["builtin"][0]["word"] == "₹"
    # Regular users can't touch the global list (404, like every admin route)
    assert anon.post("/api/admin/pronunciations", json={"word": "GST", "say_as": "G S T"}).status_code == 404
    anon.post("/api/auth/logout")
    signup(anon, email="b@example.com", code="BBBB-BBBB")
    assert anon.get("/api/pronunciations").json()["items"] == []
    assert anon.delete(f"/api/pronunciations/{eid}").status_code == 404


def test_global_list_read_as_and_tts_use_all_lists(staff):
    anon = staff("admin")                      # the global list is edited in the admin panel (2FA unlocked)
    assert anon.post("/api/admin/pronunciations", json={"word": "GST", "say_as": "G S T"}).status_code == 200
    assert anon.post("/api/admin/pronunciations", json={"word": "UPI", "say_as": "U P I"}).status_code == 200
    anon.post("/api/pronunciations", json={"word": "UPI", "say_as": "यू पी आई"})   # own list beats global
    lst = anon.get("/api/pronunciations").json()
    assert lst["can_edit_global"] is False and [g["word"] for g in lst["global"]] == ["GST", "UPI"]
    assert [a["action"] for a in anon.get("/api/admin/audit?action=pronunciation").json()["items"]] == \
        ["pronunciation.global.save"] * 2

    r = anon.post("/api/read-as", json={"text": "UPI se GST bharo, [Kalyan](कल्याण) mein", "transliterate": True,
                                       "pronunciations": [{"word": "bharo", "say_as": "भरो"}]})
    assert r.json() == {"text": "यू पी आई से G S T भरो, कल्याण में", "changed": True}

    said = _spy(anon)
    text = "GST [Kalyan](कल्याण)."
    r = anon.post("/api/tts?wait=true", json={"text": text})
    assert r.status_code == 200
    assert said[-1][0] == "G S T कल्याण."
    assert anon.get("/api/usage").json()["used"] == len(text)            # counted on the original script
    assert anon.get("/api/history").json()["items"][0]["text_excerpt"] == "GST Kalyan."

    gid = lst["global"][0]["id"]
    key = anon.post("/api/keys", json={"name": "k"}).json()["key"]
    with identity(anon):  # an admin's API key can't edit the global list (session only)
        assert anon.delete(f"/api/admin/pronunciations/{gid}", headers={"X-API-Key": key}).status_code == 404
    assert anon.delete(f"/api/admin/pronunciations/{gid}").status_code == 200
    anon.post("/api/admin/lock")
    assert anon.post("/api/admin/pronunciations", json={"word": "X", "say_as": "Y"}).status_code == 401   # locked


def test_replacements_cannot_blow_up_the_script(client):
    client.post("/api/pronunciations", json={"word": "a", "say_as": "x" * 120})
    r = client.post("/api/tts", json={"text": " ".join(["a"] * 2000)})
    assert r.status_code == 422 and "too long" in r.json()["detail"]


def test_pronunciation_test_returns_audio_and_is_not_counted(client):
    r = client.post("/api/pronunciations/test", json={"say_as": "कल्याण", "voice": "hf_alpha"})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg" and len(r.content) > 500
    assert client.get("/api/history").json()["items"] == []
    assert client.get("/api/usage").json()["used"] == 0
    assert client.post("/api/pronunciations/test", json={"say_as": "x", "voice": "nope"}).status_code == 422


def test_custom_voice_preview_is_unlocked_staff_only(anon, make_invite, staff, tmp_path, monkeypatch):
    from routes import preview
    (tmp_path / "x.mp3").write_bytes(b"ID3fake")
    (tmp_path / "index.html").write_text("<h1>lab</h1>")
    (tmp_path / "secret.wav").write_bytes(b"RIFF")
    monkeypatch.setitem(preview.ROOTS, "custom-voice", tmp_path)
    assert anon.get("/api/preview/custom-voice/").status_code == 404             # signed out
    make_invite("USER-CODE")
    signup(anon, email="u@example.com", code="USER-CODE")
    assert anon.get("/api/preview/custom-voice/").status_code == 404             # not staff
    assert staff("support").get("/api/preview/custom-voice/").status_code == 404  # staff without voices.read
    a = staff("admin")
    r = a.get("/api/preview/custom-voice/")
    assert r.status_code == 200 and "lab" in r.text and "noindex" in r.headers["x-robots-tag"]
    assert a.get("/api/preview/custom-voice/x.mp3").headers["content-type"] == "audio/mpeg"
    assert a.get("/api/preview/custom-voice/secret.wav").status_code == 404      # only html/mp3/json
    assert a.get("/api/preview/custom-voice/..%2F..%2Fetc%2Fpasswd").status_code == 404
    assert a.get("/api/preview/other/").status_code == 404
    a.post("/api/admin/lock")
    assert a.get("/api/preview/custom-voice/").status_code == 404                # admin panel locked → 404
