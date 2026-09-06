import { Component, signal } from '@angular/core';
import { AdminSeasons } from './admin-seasons';
import { AdminCollections } from './admin-collections';

type ConfigTab = 'seasons' | 'collections';

@Component({
  selector: 'app-admin-season-collection-config',
  imports: [AdminSeasons, AdminCollections],
  templateUrl: './admin-season-collection-config.html',
  styleUrl: './admin-season-collection-config.scss',
})
export class AdminSeasonCollectionConfig {
  protected readonly tabs: { id: ConfigTab; label: string }[] = [
    { id: 'seasons', label: 'Temporadas' },
    { id: 'collections', label: 'Colecciones' },
  ];
  protected readonly activeTab = signal<ConfigTab>('seasons');
  protected readonly visited = signal<ReadonlySet<ConfigTab>>(new Set(['seasons']));

  protected selectTab(tab: ConfigTab): void {
    this.visited.update((previous) => new Set([...previous, tab]));
    this.activeTab.set(tab);
  }

  protected moveTab(event: KeyboardEvent, index: number): void {
    const next =
      event.key === 'ArrowRight'
        ? (index + 1) % 2
        : event.key === 'ArrowLeft'
          ? (index + 1) % 2
          : event.key === 'Home'
            ? 0
            : event.key === 'End'
              ? 1
              : null;
    if (next === null) return;
    event.preventDefault();
    this.selectTab(this.tabs[next].id);
    const button = event.currentTarget as HTMLElement;
    (button.parentElement?.children[next] as HTMLElement)?.focus();
  }
}
