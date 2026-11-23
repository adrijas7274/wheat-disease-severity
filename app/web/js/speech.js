// Read messages aloud with the phone's own text-to-speech, in the chosen language.
// Android app (Capacitor): the @capacitor-community/text-to-speech plugin, because Android WebView has no
// speechSynthesis. Browser: the Web Speech API. Nothing is sent over the network by this code; whether a voice
// works offline depends on the voices installed on the phone.

let cached;
const plugin = () => {
  if (cached !== undefined) return cached;
  const cap = globalThis.Capacitor;
  // no bundler: call the native plugin through the bridge's nativePromise (the same call registerPlugin makes)
  const call = (m) => (o = {}) => cap.nativePromise("TextToSpeech", m, o);
  cached = cap?.isNativePlatform?.() && cap.nativePromise
    ? { speak: call("speak"), stop: call("stop"), isLanguageSupported: call("isLanguageSupported"),
        getSupportedLanguages: call("getSupportedLanguages") }
    : null;
  return cached;
};

function webVoices() {
  return new Promise((resolve) => {
    if (!("speechSynthesis" in globalThis)) return resolve([]);
    const v = speechSynthesis.getVoices();
    if (v.length) return resolve(v);
    const done = () => resolve(speechSynthesis.getVoices());
    speechSynthesis.addEventListener("voiceschanged", done, { once: true });
    setTimeout(done, 1500);
  });
}

const base = (tag) => String(tag).toLowerCase().replace("_", "-").split("-")[0];

/** Is there a voice for this BCP-47 tag? Returns {ok, voice?, offline?} (offline only known in browsers). */
export async function findVoice(tag) {
  const p = plugin();
  if (p) {
    try {
      const { supported } = await p.isLanguageSupported({ lang: tag });
      if (supported) return { ok: true };
      const { languages } = await p.getSupportedLanguages();
      return { ok: (languages || []).some((l) => base(l) === base(tag)) };
    } catch {
      return { ok: false };
    }
  }
  const voices = await webVoices();
  const exact = voices.find((v) => v.lang.toLowerCase() === tag.toLowerCase());
  const voice = exact || voices.find((v) => base(v.lang) === base(tag));
  return voice ? { ok: true, voice, offline: voice.localService } : { ok: false };
}

/** Speak `text`; resolves false (never throws) when no voice is available. */
export async function speak(text, tag) {
  const p = plugin();
  if (p) {
    try {
      await p.stop().catch(() => {});
      await p.speak({ text, lang: tag, rate: 0.9, pitch: 1.0, volume: 1.0, category: "playback" });
      return true;
    } catch {
      return false;
    }
  }
  const found = await findVoice(tag);
  if (!found.ok) return false;
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.voice = found.voice;
  u.lang = found.voice.lang;
  u.rate = 0.9;
  speechSynthesis.speak(u);
  return true;
}

export function stop() {
  plugin()?.stop?.().catch?.(() => {});
  if ("speechSynthesis" in globalThis) speechSynthesis.cancel();
}

/** Voice check for every language (for the About screen and the phone test). */
export async function voiceReport(langs) {
  const out = [];
  for (const l of langs) {
    const f = await findVoice(l.tts);
    out.push({ code: l.code, native: l.native, tts: l.tts, ok: f.ok, offline: f.offline ?? null,
               voice: f.voice ? f.voice.name : null });
  }
  return out;
}
