import { Component, computed, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterOutlet } from '@angular/router';
import { filter, map } from 'rxjs';
import { PublicFooter } from './layout/public-footer/public-footer';
import { PublicHeader } from './layout/public-header/public-header';
import { ClientChatbotFab } from './shared/components/client-chatbot-fab/client-chatbot-fab';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, PublicHeader, PublicFooter, ClientChatbotFab],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  private readonly router = inject(Router);
  private readonly activeUrl = toSignal(
    this.router.events.pipe(
      filter((event): event is NavigationEnd => event instanceof NavigationEnd),
      map((event) => event.urlAfterRedirects),
    ),
    { initialValue: this.router.url },
  );

  protected readonly showPublicChrome = computed(
    () => !/^\/(login|registro|admin|staff)(?:[/?#]|$)/.test(this.activeUrl()),
  );
}
