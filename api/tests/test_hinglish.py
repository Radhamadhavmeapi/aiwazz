from tts.hinglish import LEXICON, latin_share, rules, to_devanagari


def test_spec_example():
    out = to_devanagari("Raat 11 baje customer ne call kiya.")
    assert out == "रात 11 बजे customer ने call किया."


def test_common_sentences():
    assert to_devanagari("Aaj hum baat karenge ki reel ke liye accha voiceover kaise banaye.") == \
        "आज हम बात करेंगे की reel के लिए अच्छा voiceover कैसे बनाएँ."
    assert to_devanagari("Mera order abhi tak nahi aaya!") == "मेरा order अभी तक नहीं आया!"
    assert to_devanagari("Main bahut khush hoon, thank you dosto.") == "मैं बहुत ख़ुश हूँ, thank you दोस्तों."


def test_ambiguous_words_follow_the_sentence():
    assert to_devanagari("Ye video main share karo to sabko pata chale") .startswith("ये video मैं share करो तो")
    assert to_devanagari("This is the main reason to do it.") == "This is the main reason to do it."


def test_brands_numbers_devanagari_and_layout_are_kept():
    src = "...\nAiWazz pe YouTube ke liye 3 video banao. पहले से हिंदी भी ठीक है।\n\nOTP aaya?"
    out = to_devanagari(src)
    assert "AiWazz" in out and "YouTube" in out and "OTP" in out and " 3 " in out
    assert "पहले से हिंदी भी ठीक है।" in out
    assert out.startswith("...\n") and "\n\n" in out


def test_rules_by_sound():
    assert rules("kahaani") == "कहानी"
    assert rules("dosto") == "दोस्तो"
    assert rules("rang") == "रंग"
    assert rules("kiya") == "किया"
    assert rules("sunenga") == "सुनेंगा" and rules("rangat") == "रंगत"   # ng keeps the next vowel as a matra


def test_lexicon_sane():
    assert LEXICON["nahi"] == "नहीं" and LEXICON["main"] == "मैं" and LEXICON["hain"] == "हैं"
    assert all("ऀ" <= v[0] <= "ॿ" for v in LEXICON.values())


def test_latin_share():
    assert latin_share("Raat 11 baje") == 1.0 and latin_share("रात") == 0.0 and latin_share("") == 0.0


def test_reel_script():
    out = to_devanagari("Namaste dosto! Aaj main aapko bataunga ki reel ke liye accha voiceover kaise banaye.")
    assert out == "नमस्ते दोस्तों! आज मैं आपको बताऊँगा की reel के लिए अच्छा voiceover कैसे बनाएँ."
