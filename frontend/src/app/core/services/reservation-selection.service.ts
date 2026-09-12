import { computed, Injectable, signal } from '@angular/core';

export interface ReservationSelectionItem {
  id_producto: number;
  id_variante_producto: number;
  producto: string;
  imagen_principal: string | null;
  sku: string;
  talla: string;
  color: string;
  precio_referencia: string;
  cantidad: number;
}

export interface ReservationContext {
  id_sucursal: number;
  nombre_sucursal: string;
  nombre_ciudad: string;
  direccion: string;
  hora_apertura: string;
  hora_cierre: string;
  fecha: string;
  horario: string;
}

interface StoredReservationSelection {
  context: ReservationContext | null;
  items: ReservationSelectionItem[];
}

@Injectable({ providedIn: 'root' })
export class ReservationSelectionService {
  private readonly storageKey = 'fashionstore_reservation_selection';
  private readonly initial = this.read();
  readonly context = signal<ReservationContext | null>(this.initial.context);
  readonly items = signal<ReservationSelectionItem[]>(this.initial.items);
  readonly itemCount = computed(() =>
    this.items().reduce((total, item) => total + item.cantidad, 0),
  );

  start(context: ReservationContext, item: ReservationSelectionItem): void {
    if (this.items().length) return;
    this.persist(context, [item]);
  }

  add(item: ReservationSelectionItem): boolean {
    if (!this.context()) return false;
    const current = this.items();
    const existing = current.find(
      (row) => row.id_variante_producto === item.id_variante_producto,
    );
    this.persist(
      this.context(),
      existing
        ? current.map((row) =>
            row.id_variante_producto === item.id_variante_producto
              ? { ...row, cantidad: row.cantidad + item.cantidad }
              : row,
          )
        : [...current, item],
    );
    return true;
  }

  updateQuantity(variantId: number, quantity: number): void {
    if (!Number.isInteger(quantity) || quantity < 1) return;
    this.persist(
      this.context(),
      this.items().map((item) =>
        item.id_variante_producto === variantId ? { ...item, cantidad: quantity } : item,
      ),
    );
  }

  remove(variantId: number): void {
    const items = this.items().filter((item) => item.id_variante_producto !== variantId);
    this.persist(items.length ? this.context() : null, items);
  }

  changeContext(context: ReservationContext): void {
    if (!this.items().length) return;
    this.persist(context, this.items());
  }

  clear(): void {
    this.persist(null, []);
  }

  private persist(context: ReservationContext | null, items: ReservationSelectionItem[]): void {
    this.context.set(context);
    this.items.set(items);
    sessionStorage.setItem(this.storageKey, JSON.stringify({ context, items }));
  }

  private read(): StoredReservationSelection {
    try {
      const parsed = JSON.parse(sessionStorage.getItem(this.storageKey) ?? '{}') as {
        context?: unknown;
        items?: unknown[];
      };
      if (!Array.isArray(parsed?.items) || !this.validContext(parsed.context)) {
        return { context: null, items: [] };
      }
      const items = parsed.items.filter((item): item is ReservationSelectionItem => {
        const candidate = item as Partial<ReservationSelectionItem> | null;
        return Boolean(
          candidate &&
            Number.isInteger(candidate.id_producto) &&
            Number.isInteger(candidate.id_variante_producto) &&
            Number.isInteger(candidate.cantidad) &&
            candidate.cantidad! > 0 &&
            typeof candidate.producto === 'string' &&
            typeof candidate.sku === 'string',
        );
      });
      return items.length
        ? { context: parsed.context as ReservationContext, items }
        : { context: null, items: [] };
    } catch {
      return { context: null, items: [] };
    }
  }

  private validContext(value: unknown): value is ReservationContext {
    const context = value as Partial<ReservationContext> | null;
    return Boolean(
      context &&
        Number.isInteger(context.id_sucursal) &&
        context.id_sucursal! > 0 &&
        typeof context.nombre_sucursal === 'string' &&
        typeof context.nombre_ciudad === 'string' &&
        typeof context.direccion === 'string' &&
        typeof context.hora_apertura === 'string' &&
        typeof context.hora_cierre === 'string' &&
        /^\d{4}-\d{2}-\d{2}$/.test(context.fecha ?? '') &&
        /^\d{2}:\d{2}$/.test(context.horario ?? ''),
    );
  }
}
