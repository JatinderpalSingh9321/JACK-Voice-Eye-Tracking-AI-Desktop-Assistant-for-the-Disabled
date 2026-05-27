"""
Wake Word Calibration Tool v3
==============================
Speak full sentences containing 'Jim' so Google has enough context.
Tests both en-IN and en-US to find the best language setting.

Usage:  python calibrate_wake.py
"""

import speech_recognition as sr
import json
import os
import time

RESULTS_FILE = os.path.join(os.path.dirname(__file__), "wake_calibration.json")

PROMPTS = [
    "Say: 'Hey Jim, how are you'",
    "Say: 'Wake up Jim please'",
    "Say: 'Hi Jim, what time is it'",
    "Say: 'Jim open Google'",
    "Say: 'Hey Jim play some music'",
    "Say: 'Wake up Jim I need help'",
    "Say: 'Jim search for something'",
    "Say: 'Hey Jim, Jim, Jim'",
]

LANGUAGES = ["en-IN", "en-US"]

def main():
    recognizer = sr.Recognizer()
    recognizer.energy_threshold = 150
    recognizer.dynamic_energy_threshold = True  # Let it auto-adjust
    recognizer.pause_threshold = 1.0

    print("=" * 60)
    print("  WAKE WORD CALIBRATION v3")
    print("  Speak FULL sentences containing 'Jim'")
    print("  We test both en-IN and en-US recognition.")
    print("=" * 60)

    try:
        mic = sr.Microphone()
    except Exception as e:
        print(f"\nERROR: Could not open microphone: {e}")
        return

    with mic as source:
        print("\nAdjusting for ambient noise (2s)... stay quiet...")
        recognizer.adjust_for_ambient_noise(source, duration=2)
        print(f"Energy threshold after calibration: {recognizer.energy_threshold:.0f}")
        
        # Cap threshold to avoid missing speech
        if recognizer.energy_threshold > 500:
            recognizer.energy_threshold = 500
            print(f"Capped threshold to: 500")
        
        print("\n>> Speak when you see 'SPEAK NOW' <<\n")

        all_results = []

        for idx, prompt in enumerate(PROMPTS):
            print(f"\n{'-' * 55}")
            print(f"  [{idx+1}/{len(PROMPTS)}] {prompt}")
            print(f"{'-' * 55}")
            print(f"  SPEAK NOW ... ", end="", flush=True)
            
            try:
                audio = recognizer.listen(source, timeout=10, phrase_time_limit=8)
                audio_len = len(audio.get_raw_data())
                
                if audio_len < 4800:
                    print("[too short, skipped]")
                    continue

                print(f"[captured {audio_len/32000:.1f}s]")
                
                # Test BOTH languages
                for lang in LANGUAGES:
                    try:
                        results = recognizer.recognize_google(
                            audio, language=lang, show_all=True
                        )
                        if results and isinstance(results, dict):
                            alts = results.get("alternative", [])
                            if alts:
                                top = alts[0].get("transcript", "")
                                others = [a.get("transcript", "") for a in alts[1:4]]
                                print(f"    {lang}: \"{top}\"")
                                if others:
                                    print(f"           also: {others}")
                                
                                all_results.append({
                                    "prompt": prompt,
                                    "language": lang,
                                    "heard": top.lower().strip(),
                                    "alternatives": [
                                        a.get("transcript", "").lower().strip() 
                                        for a in alts[:6] if a.get("transcript")
                                    ]
                                })
                        else:
                            print(f"    {lang}: [no result]")
                            
                    except sr.UnknownValueError:
                        print(f"    {lang}: [could not understand]")
                    except sr.RequestError as e:
                        print(f"    {lang}: [API error: {e}]")

            except sr.WaitTimeoutError:
                print("[timeout - no speech detected]")
            except Exception as e:
                print(f"[error: {e}]")

        # -- Analysis --
        print("\n\n" + "=" * 60)
        print("  CALIBRATION RESULTS")
        print("=" * 60)

        if not all_results:
            print("\n  No speech captured! Possible issues:")
            print("  1. Check mic is not muted")
            print("  2. Try speaking louder or closer to mic")
            print("  3. Check no other app is using the mic")
            return

        # Collect all words
        heard_set = set()
        jim_variants = set()   # Words where 'jim' SHOULD have been
        
        for r in all_results:
            heard_set.add(r["heard"])
            for alt in r["alternatives"]:
                heard_set.add(alt)
        
        # Extract individual words that appear where 'jim' should be
        for phrase in heard_set:
            words = phrase.lower().split()
            for word in words:
                # Check if this word appears right after hey/hi/wake/up
                idx = words.index(word)
                if idx > 0 and words[idx-1] in ("hey", "hi", "wake", "up", "hello"):
                    jim_variants.add(word)
                # Also check if it's the first word (like "Jim open google")
                if idx == 0 and len(words) > 1:
                    jim_variants.add(word)
        
        # Also add any single-word results
        for phrase in heard_set:
            if len(phrase.split()) == 1:
                jim_variants.add(phrase.lower())

        print(f"\n  Total captures: {len(all_results)}")
        print(f"  Unique full phrases heard:")
        for word in sorted(heard_set):
            print(f"    * \"{word}\"")
        
        if jim_variants:
            print(f"\n  Words Google used instead of 'Jim':")
            for w in sorted(jim_variants):
                print(f"    -> \"{w}\"")

        # Save
        output = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "raw_results": all_results,
            "all_heard_phrases": sorted(heard_set),
            "jim_variants": sorted(jim_variants),
        }
        with open(RESULTS_FILE, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        print(f"\n  Saved to: {RESULTS_FILE}")

        # Compare with existing
        try:
            from src.voice_assistant import WAKE_PHRASES, _JIM_SOUNDS
            existing = WAKE_PHRASES | _JIM_SOUNDS
            new_words = jim_variants - existing
            new_phrases = heard_set - existing
            if new_words:
                print(f"\n  >> NEW Jim-variants to add to _JIM_SOUNDS:")
                for w in sorted(new_words):
                    print(f"    + \"{w}\"")
            if new_phrases:
                print(f"\n  >> NEW full phrases to add to WAKE_PHRASES:")
                for w in sorted(new_phrases):
                    if any(kw in w for kw in ("jim", "gym", "gem", "hey", "wake", "hi")):
                        print(f"    + \"{w}\"")
            if not new_words and not new_phrases:
                print(f"\n  [OK] All words already covered!")
        except Exception:
            print("\n  (Could not compare with existing wake phrases)")

        print()


if __name__ == "__main__":
    main()
