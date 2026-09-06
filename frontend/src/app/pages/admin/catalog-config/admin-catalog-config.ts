import { Component, signal } from '@angular/core';
import { AdminCategories } from './admin-categories';
import { AdminSizes } from './admin-sizes';
import { AdminColors } from './admin-colors';

type CatalogTab = 'categories' | 'sizes' | 'colors';

@Component({
  selector: 'app-admin-catalog-config',
  imports: [AdminCategories, AdminSizes, AdminColors],
  templateUrl: './admin-catalog-config.html',
  styleUrl: './admin-catalog-config.scss',
})
export class AdminCatalogConfig {
  protected readonly tabs: { id: CatalogTab; label: string }[] = [
    { id: 'categories', label: 'Categorías' },
    { id: 'sizes', label: 'Tallas' },
    { id: 'colors', label: 'Colores' },
  ];
  protected readonly activeTab = signal<CatalogTab>('categories');
  protected readonly visited = signal<ReadonlySet<CatalogTab>>(new Set(['categories']));

  protected selectTab(tab: CatalogTab): void {
    this.visited.update((previous) => new Set([...previous, tab]));
    this.activeTab.set(tab);
  }

  protected moveTab(event: KeyboardEvent, index: number): void {
    const next =
      event.key === 'ArrowRight'
        ? (index + 1) % 3
        : event.key === 'ArrowLeft'
          ? (index + 2) % 3
          : event.key === 'Home'
            ? 0
            : event.key === 'End'
              ? 2
              : null;
    if (next === null) return;
    event.preventDefault();
    this.selectTab(this.tabs[next].id);
    const button = event.currentTarget as HTMLElement;
    (button.parentElement?.children[next] as HTMLElement)?.focus();
  }
}
