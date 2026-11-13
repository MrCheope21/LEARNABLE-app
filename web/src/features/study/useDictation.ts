import { useCallback, useEffect, useRef, useState } from "react";
import { useI18n } from "../../i18n";
import type { MessageKey } from "../../i18n/messages/en";

// The browser's speech recognition (Chrome, Edge, Safari). TypeScript's DOM library doesn't
// describe it, so only what is used is declared.
interface RecognitionEvent {
  resultIndex: number;
  results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }>;
}
interface Recognition {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((event: RecognitionEvent) => void) | null;
  onend: (() => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}
type RecognitionConstructor = new () => Recognition;

function recognitionConstructor(): RecognitionConstructor | null {
  const w = window as unknown as { SpeechRecognition?: RecognitionConstructor; webkitSpeechRecognition?: RecognitionConstructor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

const LANGUAGES: Record<string, string> = { it: "it-IT", en: "en-US", fr: "fr-FR", de: "de-DE", es: "es-ES", pt: "pt-PT" };

/** The recognition language for a course's language code, else the browser's own. */
export function recognitionLanguage(courseLanguage?: string | null): string {
  return LANGUAGES[(courseLanguage ?? "").slice(0, 2).toLowerCase()] ?? navigator.language;
}

const ERRORS: Record<string, MessageKey> = {
  "not-allowed": "dictation.blocked",
  "service-not-allowed": "dictation.blocked",
  network: "dictation.network",
  "audio-capture": "dictation.noMic",
};

/**
 * Dictation into the answer box. Final phrases go to `onFinal`; the phrase still being spoken is
 * `interim`. Nothing is recorded or stored here: the browser transcribes, and only text is used.
 */
export function useDictation(language: string, onFinal: (text: string) => void) {
  const { t } = useI18n();
  const [supported] = useState(() => recognitionConstructor() !== null);
  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState("");
  const [error, setError] = useState<string | null>(null);
  const recognition = useRef<Recognition | null>(null);
  const onFinalRef = useRef(onFinal);
  useEffect(() => {
    onFinalRef.current = onFinal;
  }, [onFinal]);

  const stop = useCallback(() => recognition.current?.stop(), []);

  const start = useCallback(() => {
    const Recognizer = recognitionConstructor();
    if (!Recognizer || recognition.current) return;
    const next = new Recognizer();
    next.lang = language;
    next.continuous = true;
    next.interimResults = true;
    next.onresult = (event) => {
      let spoken = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        if (!result) continue;
        if (result.isFinal) onFinalRef.current(result[0].transcript.trim());
        else spoken += result[0].transcript;
      }
      setInterim(spoken);
    };
    next.onerror = (event) => {
      if (event.error !== "no-speech" && event.error !== "aborted") {
        setError(t(ERRORS[event.error] ?? "dictation.stopped"));
      }
    };
    next.onend = () => {
      recognition.current = null;
      setListening(false);
      setInterim("");
    };
    recognition.current = next;
    setError(null);
    setListening(true);
    next.start();
  }, [language, t]);

  useEffect(() => () => recognition.current?.abort(), []);

  return { supported, listening, interim, error, start, stop };
}
