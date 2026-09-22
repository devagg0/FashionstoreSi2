import { Injectable, signal } from '@angular/core';

/** Subconjunto de la Web Speech API que este servicio necesita; no todo TS/DOM la declara. */
interface SpeechRecognitionLike extends EventTarget {
  lang: string;
  interimResults: boolean;
  maxAlternatives: number;
  onresult: ((event: SpeechRecognitionEvent) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
  start(): void;
}

/**
 * Reconocimiento de voz a texto compartido por los reportes administrativos
 * (CU28, CU29 y CU30). Envuelve la Web Speech API del navegador; no contiene
 * logica de IA: el texto transcrito se entrega para que cada reporte lo envie
 * al flujo de analisis con Gemini ya existente (ReportAIService).
 */
@Injectable({ providedIn: 'root' })
export class SpeechRecognitionService {
  /** true si el navegador expone la Web Speech API (Chrome/Edge de escritorio y Android). */
  readonly supported = signal(this.resolveConstructor() !== null);
  readonly listening = signal(false);

  /** Escucha una sola consulta hablada y resuelve con el texto transcrito. */
  listenOnce(language = 'es-BO'): Promise<string> {
    const Recognition = this.resolveConstructor();
    if (!Recognition) {
      return Promise.reject(new Error('Este navegador no admite reconocimiento de voz.'));
    }

    return new Promise<string>((resolve, reject) => {
      const recognition = new Recognition();
      recognition.lang = language;
      recognition.interimResults = false;
      recognition.maxAlternatives = 1;

      let settled = false;
      const finish = (action: () => void) => {
        if (settled) return;
        settled = true;
        this.listening.set(false);
        action();
      };

      recognition.onresult = (event: SpeechRecognitionEvent) => {
        const transcript = event.results[0]?.[0]?.transcript?.trim() ?? '';
        finish(() => transcript ? resolve(transcript) : reject(new Error('No se entendió ninguna consulta.')));
      };
      recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
        finish(() => reject(new Error(this.errorMessage(event.error))));
      };
      recognition.onend = () => finish(() => reject(new Error('No se detectó ninguna consulta por voz.')));

      this.listening.set(true);
      try {
        recognition.start();
      } catch {
        finish(() => reject(new Error('No fue posible iniciar el micrófono.')));
      }
    });
  }

  private resolveConstructor(): (new () => SpeechRecognitionLike) | null {
    const global = window as unknown as {
      SpeechRecognition?: new () => SpeechRecognitionLike;
      webkitSpeechRecognition?: new () => SpeechRecognitionLike;
    };
    return global.SpeechRecognition ?? global.webkitSpeechRecognition ?? null;
  }

  private errorMessage(code: string): string {
    if (code === 'not-allowed' || code === 'service-not-allowed') return 'Permiso de micrófono denegado.';
    if (code === 'no-speech') return 'No se detectó ninguna consulta por voz.';
    return 'No fue posible reconocer la consulta por voz.';
  }
}
