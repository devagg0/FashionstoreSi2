import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { finalize } from 'rxjs';
import {
  ChatbotMessage,
  ChatbotProduct,
  ClientChatbotService,
  chatbotErrorMessage,
} from '../../core/services/client-chatbot.service';
import { Icon } from '../../shared/components/icon/icon';

@Component({
  selector: 'app-chatbot',
  imports: [FormsModule, Icon, RouterLink],
  templateUrl: './chatbot.html',
  styleUrl: './chatbot.scss',
})
export class Chatbot {
  private readonly chatbotService = inject(ClientChatbotService);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly messages = signal<ChatbotMessage[]>([
    {
      role: 'assistant',
      content:
        'Hola. Soy tu asistente de estilo FashionStore. Puedo ayudarte a encontrar prendas, revisar disponibilidad o elegir un look.',
    },
  ]);
  protected readonly suggestedProducts = signal<ChatbotProduct[]>([]);
  protected readonly loading = signal(false);
  protected readonly errorMessage = signal('');
  protected draft = '';

  protected sendMessage(): void {
    const content = this.draft.trim();
    if (!content || this.loading()) return;

    const userMessage: ChatbotMessage = { role: 'user', content };
    const history = this.messages();
    this.messages.update((items) => [...items, userMessage]);
    this.draft = '';
    this.errorMessage.set('');
    this.loading.set(true);

    this.chatbotService
      .sendMessage({ message: content, history })
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.loading.set(false)),
      )
      .subscribe({
        next: (response) => {
          this.messages.update((items) => [
            ...items,
            { role: 'assistant', content: response.data.reply },
          ]);
          this.suggestedProducts.set(response.data.products);
        },
        error: (error: HttpErrorResponse) => {
          this.errorMessage.set(chatbotErrorMessage(error));
        },
      });
  }

  protected formatPrice(price: string): string {
    return `Bs ${Number(price).toFixed(2)}`;
  }
}