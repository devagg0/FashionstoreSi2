import {
  afterNextRender,
  DestroyRef,
  Component,
  ElementRef,
  HostListener,
  inject,
  input,
  output,
} from '@angular/core';

@Component({
  selector: 'app-return-modal',
  template: `<dialog
    open
    aria-modal="true"
    [attr.aria-labelledby]="'return-modal-title'"
    (cancel)="cancel($event)"
  >
    <header>
      <div>
        <p>FASHIONSTORE · ATENCIÓN A TU COMPRA</p>
        <h2 id="return-modal-title">{{ title() }}</h2>
      </div>
      <button type="button" aria-label="Cerrar modal" [disabled]="busy()" (click)="closed.emit()">
        ×
      </button>
    </header>
    <ng-content />
  </dialog>`,
  styles: [
    `
      :host {
        position: fixed;
        inset: 0;
        z-index: 1000;
        background: #241b16aa;
        display: grid;
        place-items: center;
        padding: 20px;
        overflow: auto;
      }
      dialog {
        position: relative;
        margin: auto;
        width: min(760px, 100%);
        max-height: 90dvh;
        overflow: auto;
        border: 1px solid var(--color-line);
        border-radius: 18px;
        padding: 28px;
        color: var(--color-espresso);
        background: white;
        box-shadow: 0 24px 90px #0003;
      }
      header {
        display: flex;
        justify-content: space-between;
        align-items: start;
        gap: 20px;
        margin-bottom: 24px;
      }
      h2 {
        margin: 6px 0;
        font-size: 1.8rem;
      }
      p {
        font: 700 0.6rem sans-serif;
        letter-spacing: 0.12em;
        color: var(--color-terracotta);
      }
      button {
        border: 0;
        background: var(--color-linen);
        border-radius: 50%;
        width: 36px;
        height: 36px;
        font-size: 24px;
        cursor: pointer;
      }
      button:focus-visible {
        outline: 3px solid var(--color-terracotta);
      }
      @media (max-width: 600px) {
        :host {
          padding: 10px;
        }
        dialog {
          padding: 20px;
          max-height: 95dvh;
        }
      }
    `,
  ],
})
export class ReturnModal {
  readonly title = input.required<string>();
  readonly busy = input(false);
  readonly closed = output<void>();
  private readonly element = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly previous =
    typeof document === 'undefined' ? null : (document.activeElement as HTMLElement | null);
  constructor() {
    afterNextRender(() => this.focusables()[0]?.focus());
    inject(DestroyRef).onDestroy(() => this.previous?.focus());
  }
  private focusables(): HTMLElement[] {
    return Array.from(
      this.element.nativeElement.querySelectorAll<HTMLElement>(
        'button:not(:disabled),input:not(:disabled),textarea:not(:disabled),select:not(:disabled),a[href]',
      ),
    );
  }
  cancel(event: Event) {
    event.preventDefault();
    if (!this.busy()) this.closed.emit();
  }
  @HostListener('document:keydown', ['$event'])
  key(event: KeyboardEvent) {
    if (event.key === 'Escape') this.cancel(event);
    if (event.key !== 'Tab') return;
    const all = this.focusables();
    if (!all.length) {
      event.preventDefault();
      return;
    }
    const first = all[0],
      last = all[all.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }
}
