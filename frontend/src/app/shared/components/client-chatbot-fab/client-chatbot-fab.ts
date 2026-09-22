import { Component, computed, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { SessionService } from '../../../core/services/session.service';
import { Icon } from '../icon/icon';

@Component({
  selector: 'app-client-chatbot-fab',
  imports: [Icon, RouterLink],
  templateUrl: './client-chatbot-fab.html',
  styleUrl: './client-chatbot-fab.scss',
})
export class ClientChatbotFab {
  private readonly sessionService = inject(SessionService);

  protected readonly visible = computed(() => {
    const user = this.sessionService.currentUser();
    return Boolean(this.sessionService.getAccessToken() && user?.rol.toUpperCase() === 'CLIENTE');
  });
}