---
slug: /learn/fix-pronunciation/
title: Fix pronunciation
metaTitle: Fix AI Voice Pronunciation of Names, Brands and Short Forms | AiWazz
metaDescription: Make AiWazz say names, brands, places and abbreviations correctly: a one-word fix in the script with [word](say-as), or your own pronunciation list in Settings.
order: 5.5
category: Better results
---

# Fix pronunciation

AI voices get most words right, but names, brands, places and short forms can come out wrong. AiWazz gives you two
ways to fix them. Both change only what the voice **says**; your script and your character count stay the same.

## Fix one word in one script: `[word](say it as)`
Put the word in square brackets and how to say it in round brackets, right in the script:

```text
Hamara naya store [Kalyan](कल्याण) mein khul gaya hai.
Pay with [UPI](U P I) or card.
```

- The fix is highlighted in the editor, and the **Will be read as** box under the editor shows what the voice will read.
- Only the text in round brackets is spoken. Characters are counted on your script as you typed it.

## Fix a word everywhere: your pronunciation list
Open **Settings → Pronunciations** (or the **Pronunciations** link under the editor):

1. Type the **word** as it appears in your scripts, for example `Kalyan`.
2. Type how to **say it**, for example `कल्याण`.
3. Press **▶** to hear it in the voice you pick. Tests are free: they don't use your characters.
4. Press **Add**. From now on, every voiceover and every API call uses it.

How matching works:
- **Whole words only.** `GST` matches "GST" and "gst" but not "GSTIN".
- **Any capitalisation.** `aiwazz`, `AiWazz` and `AIWAZZ` all match.
- **Phrases work too:** `GST number` → `G S T नंबर`. Longer entries win over shorter ones.
- Up to 500 words per account. Edit or remove them any time.

## Built in for everyone
AiWazz already fixes a few words for every account: **AiWazz** → "Ai Wazz", **GST** → "G S T", **UPI** → "U P I",
**API** → "A P I". The **₹** sign is read as "रुपये" by Hindi voices and "rupees" by English voices, and amounts are
read the Indian way: ₹2,00,000 → "दो लाख रुपये". If the same word is in your list, **your list wins**.

## Which fix wins?
1. `[word](say it as)` in the script
2. `pronunciations` sent with an API request
3. your list in Settings
4. the built-in list

## Writing a good "say it as"
| Problem | Try |
|---|---|
| A Hindi name sounds English | write it in Devanagari: `Kalyan` → `कल्याण` |
| Letters are read as a word | add spaces: `GST` → `G S T`, or Hindi letters: `जी एस टी` |
| An English brand sounds odd in a Hindi voice | split it: `AiWazz` → `Ai Wazz`, or spell it as it sounds |
| Stress on the wrong part | add a nukta or matra: `फ़`, `ज़`; or a hyphen: `Rad-ha` |
| A number reads wrongly | write it in words: `24x7` → `twenty four seven` |

**Hinglish tip:** with **Transliterate Hinglish** on, your fixes are used exactly as you typed them. They are not converted
to Devanagari, so write Hindi sounds in Devanagari.

## In the API
Your Settings list is used automatically. You can also send fixes for one request:

```bash
curl -s https://login.aiwazz.in/api/tts?wait=true \
  -H "X-API-Key: $AIWAZZ_API_KEY" -H "Content-Type: application/json" \
  -d '{"text":"Order Kalyan store se.","voice":"hf_alpha","pronunciations":[{"word":"Kalyan","say_as":"कल्याण"}]}'
```

Up to 100 entries per request. To check a script without generating it, use `POST /api/read-as`
with `{"text": "...", "transliterate": false}` and look at the returned `text`.

Next: [Use your audio in your editor](/learn/using-audio-in-editors/)
