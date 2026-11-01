import { CommonModule, CurrencyPipe, DatePipe } from '@angular/common';
import { Component, computed, inject, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import {
  OfflineBranchData,
  OfflineCategoryData,
  OfflineClientData,
  OfflineProductData,
  OfflineReceiptData,
  OfflineReservationDetailLocal,
  OfflineReservationLineItem,
  OfflineReservationLocal,
  OfflineStockData,
  OfflineStoredSummary,
  OfflineSyncQueueItem,
  OfflineVariantData,
} from '../../core/models/offline.model';
import { OfflineStorageService } from '../../core/services/offline-storage.service';
import { SessionService } from '../../core/services/session.service';
import { Icon } from '../../shared/components/icon/icon';

@Component({
  selector: 'app-offline-reservation-create',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, DatePipe, CurrencyPipe, Icon],
  templateUrl: './offline-reservation-create.html',
  styleUrl: './offline-reservation-create.scss',
})
export class OfflineReservationCreate implements OnInit {
  private readonly session = inject(SessionService);
  private readonly storage = inject(OfflineStorageService);
  private readonly router = inject(Router);

  readonly user = this.session.currentUser;

  // Estado general de carga y envío
  readonly isLoading = signal<boolean>(true);
  readonly isSubmitting = signal<boolean>(false);
  readonly summary = signal<OfflineStoredSummary | null>(null);

  // Almacenes cargados desde IndexedDB
  readonly branches = signal<OfflineBranchData[]>([]);
  readonly clients = signal<OfflineClientData[]>([]);
  readonly products = signal<OfflineProductData[]>([]);
  readonly variants = signal<OfflineVariantData[]>([]);
  readonly stock = signal<OfflineStockData[]>([]);
  readonly categories = signal<OfflineCategoryData[]>([]);
  readonly pendingReservedQuantities = signal<Map<string, number>>(new Map());

  // Formulario: Selección de Sucursal y Cliente
  readonly selectedBranchId = signal<number | null>(null);
  readonly selectedClientId = signal<number | null>(null);
  readonly clientSearchTerm = signal<string>('');

  // Formulario: Selección de Prenda / Variante
  readonly selectedProductId = signal<number | null>(null);
  readonly selectedVariantId = signal<number | null>(null);
  readonly lineQuantity = signal<number>(1);
  readonly lineItems = signal<OfflineReservationLineItem[]>([]);

  // Formulario: Fechas y condiciones
  readonly fechaAtencionProgramada = signal<string>('');
  readonly adelantoEfectivo = signal<number>(0);
  readonly observaciones = signal<string>('');

  // Mensajes y modales
  readonly errorMessage = signal<string | null>(null);
  readonly validationErrors = signal<string[]>([]);
  readonly successReservation = signal<OfflineReceiptData | null>(null);
  readonly showSuccessModal = signal<boolean>(false);

  // Computados de sesión y roles
  readonly isAdmin = computed(() => this.user()?.rol?.toUpperCase() === 'ADMINISTRADOR');
  readonly isEncargado = computed(() => this.user()?.rol?.toUpperCase() === 'ENCARGADO_SUCURSAL');
  readonly isCajero = computed(() => this.user()?.rol?.toUpperCase() === 'CAJERO');

  readonly offlineHomeUrl = computed(() => {
    return this.isAdmin() ? '/admin/offline' : '/staff/offline';
  });

  readonly offlineCatalogUrl = computed(() => {
    return this.isAdmin() ? '/admin/offline/catalogo' : '/staff/offline/catalogo';
  });

  // Sucursal seleccionada
  readonly selectedBranch = computed(() => {
    const id = this.selectedBranchId();
    if (!id) return null;
    return this.branches().find((b) => b.id_sucursal === id) ?? null;
  });

  // Clientes filtrados por término de búsqueda
  readonly filteredClients = computed(() => {
    const term = this.clientSearchTerm().trim().toLowerCase();
    const all = this.clients();
    if (!term) return all.slice(0, 10);
    return all
      .filter((c) => {
        const full = `${c.nombre} ${c.apellido}`.toLowerCase();
        const doc = (c.correo || '').toLowerCase();
        const phone = (c.telefono || '').toLowerCase();
        const id = c.id_cliente.toString();
        return full.includes(term) || doc.includes(term) || phone.includes(term) || id.includes(term);
      })
      .slice(0, 20);
  });

  // Cliente seleccionado
  readonly selectedClient = computed(() => {
    const id = this.selectedClientId();
    if (!id) return null;
    return this.clients().find((c) => c.id_cliente === id) ?? null;
  });

  // Variantes del producto seleccionado
  readonly variantsForSelectedProduct = computed(() => {
    const prodId = this.selectedProductId();
    if (!prodId) return [];
    return this.variants().filter((v) => v.id_producto === prodId && v.estado);
  });

  // Variante seleccionada
  readonly selectedVariant = computed(() => {
    const varId = this.selectedVariantId();
    if (!varId) return null;
    return this.variants().find((v) => v.id_variante_producto === varId) ?? null;
  });

  // Producto seleccionado
  readonly selectedProduct = computed(() => {
    const prodId = this.selectedProductId();
    if (!prodId) return null;
    return this.products().find((p) => p.id_producto === prodId) ?? null;
  });

  // Stock estimado disponible para la variante en la sucursal seleccionada
  readonly estimatedStockForSelectedVariant = computed(() => {
    const branchId = this.selectedBranchId();
    const varId = this.selectedVariantId();
    if (!branchId || !varId) return 0;

    const stockEntry = this.stock().find(
      (s) => s.id_sucursal === branchId && s.id_variante_producto === varId,
    );
    const baseAvailable = stockEntry ? stockEntry.stock_disponible : 0;

    const key = `${branchId}_${varId}`;
    const pendingReserved = this.pendingReservedQuantities().get(key) || 0;

    // Descontar lo que ya se agregó al carrito local actual
    const inCurrentCart =
      this.lineItems().find((item) => item.id_variante_producto === varId)?.cantidad || 0;

    return Math.max(0, baseAvailable - pendingReserved - inCurrentCart);
  });

  // Totales de la reserva
  readonly totalReferencial = computed(() => {
    return this.lineItems().reduce((acc, curr) => acc + curr.subtotal, 0);
  });

  readonly saldoPendiente = computed(() => {
    const total = this.totalReferencial();
    const adelanto = this.adelantoEfectivo() || 0;
    return Math.max(0, total - adelanto);
  });

  async ngOnInit(): Promise<void> {
    await this.loadInitialData();
  }

  /**
   * Carga exclusivamente desde IndexedDB. Sin ninguna petición HTTP.
   */
  async loadInitialData(): Promise<void> {
    const user = this.user();
    if (!user || !user.id_empresa) {
      this.errorMessage.set('Sesión no válida o expirada. Por favor inicie sesión nuevamente.');
      this.isLoading.set(false);
      return;
    }

    this.isLoading.set(true);
    this.errorMessage.set(null);

    try {
      const empresaId = user.id_empresa;
      const userId = user.id_usuario;

      const [
        summary,
        branches,
        clients,
        products,
        variants,
        stock,
        categories,
        pendingMap,
      ] = await Promise.all([
        this.storage.getStoredPackageSummary(empresaId, userId),
        this.storage.getBranches(empresaId, userId),
        this.storage.getClients(empresaId, userId),
        this.storage.getCatalogProducts(empresaId, userId),
        this.storage.getVariants(empresaId, userId),
        this.storage.getInventory(empresaId, userId),
        this.storage.getCategories(empresaId, userId),
        this.storage.getPendingReservedQuantities(empresaId, userId),
      ]);

      this.summary.set(summary);
      this.branches.set(branches);
      this.clients.set(clients);
      this.products.set(products.filter((p) => p.estado));
      this.variants.set(variants);
      this.stock.set(stock);
      this.categories.set(categories);
      this.pendingReservedQuantities.set(pendingMap);

      // Preseleccionar sucursal si hay solo una autorizada
      if (branches.length === 1) {
        this.selectedBranchId.set(branches[0].id_sucursal);
      } else if (summary?.metadata.sucursales_autorizadas_ids?.length === 1) {
        this.selectedBranchId.set(summary.metadata.sucursales_autorizadas_ids[0]);
      }

      // Fecha límite sugerida por defecto: dentro de 48 horas
      const defaultDate = new Date(Date.now() + 48 * 3600 * 1000);
      defaultDate.setMinutes(0);
      defaultDate.setSeconds(0);
      defaultDate.setMilliseconds(0);
      const iso = defaultDate.toISOString().slice(0, 16);
      this.fechaAtencionProgramada.set(iso);

      // Validar si el paquete existe
      if (!summary) {
        this.errorMessage.set(
          'No se encontró un paquete offline almacenado. Debe descargar el catálogo en Operación Offline antes de registrar reservas.',
        );
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Error al acceder a IndexedDB.';
      this.errorMessage.set(`No se pudo leer el almacenamiento local IndexedDB: ${msg}`);
    } finally {
      this.isLoading.set(false);
    }
  }

  onProductChange(productIdStr: string): void {
    const prodId = Number(productIdStr);
    this.selectedProductId.set(prodId || null);
    this.selectedVariantId.set(null);
    this.lineQuantity.set(1);
  }

  onVariantChange(variantIdStr: string): void {
    const varId = Number(variantIdStr);
    this.selectedVariantId.set(varId || null);
    this.lineQuantity.set(1);
  }

  onSelectClient(clientId: number): void {
    this.selectedClientId.set(clientId);
    const client = this.clients().find((c) => c.id_cliente === clientId);
    if (client) {
      this.clientSearchTerm.set(`${client.nombre} ${client.apellido}`);
    }
  }

  /**
   * Agrega la prenda/variante seleccionada al listado de la reserva con validación de stock.
   */
  addLineItem(): void {
    this.validationErrors.set([]);
    const errors: string[] = [];

    const branch = this.selectedBranch();
    if (!branch) {
      errors.push('Debe seleccionar primero una sucursal autorizada.');
    }

    const prod = this.selectedProduct();
    const variant = this.selectedVariant();
    if (!prod || !variant) {
      errors.push('Debe seleccionar un producto y una variante válida (talla y color).');
    }

    const qty = Number(this.lineQuantity());
    if (!qty || qty <= 0) {
      errors.push('La cantidad a reservar debe ser un entero positivo mayor a 0.');
    }

    const available = this.estimatedStockForSelectedVariant();
    if (qty > available) {
      errors.push(
        `La cantidad ingresada (${qty}) supera el stock disponible estimado (${available}) en esta sucursal.`,
      );
    }

    if (errors.length > 0) {
      this.validationErrors.set(errors);
      return;
    }

    if (!prod || !variant || !branch) return;

    const unitPrice = variant.precio ? Number(variant.precio) : Number(prod.precio);
    const existingIndex = this.lineItems().findIndex(
      (item) => item.id_variante_producto === variant.id_variante_producto,
    );

    if (existingIndex >= 0) {
      const currentList = [...this.lineItems()];
      const currentItem = currentList[existingIndex];
      const newQty = currentItem.cantidad + qty;
      currentList[existingIndex] = {
        ...currentItem,
        cantidad: newQty,
        subtotal: newQty * unitPrice,
      };
      this.lineItems.set(currentList);
    } else {
      const newItem: OfflineReservationLineItem = {
        id_variante_producto: variant.id_variante_producto,
        id_producto: prod.id_producto,
        producto_nombre: prod.nombre,
        sku: variant.sku,
        talla: variant.talla || 'Única',
        color: variant.color || 'Único',
        precio_referencial: unitPrice,
        cantidad: qty,
        subtotal: qty * unitPrice,
        stock_disponible_estimado: available,
      };
      this.lineItems.set([...this.lineItems(), newItem]);
    }

    // Limpiar selección de prenda tras agregarla
    this.selectedProductId.set(null);
    this.selectedVariantId.set(null);
    this.lineQuantity.set(1);
  }

  removeLineItem(index: number): void {
    const list = [...this.lineItems()];
    list.splice(index, 1);
    this.lineItems.set(list);
  }

  /**
   * Registra atómicamente la reserva offline en IndexedDB.
   * Asigna estrictamente el estado REGISTRADA_LOCAL sin llamadas HTTP.
   */
  async submitReservation(): Promise<void> {
    this.validationErrors.set([]);
    this.errorMessage.set(null);

    const user = this.user();
    if (!user || !user.id_empresa) {
      this.errorMessage.set('Sesión no válida o expirada.');
      return;
    }

    const summary = this.summary();
    if (!summary) {
      this.errorMessage.set('No se puede registrar sin un paquete offline cargado.');
      return;
    }

    const errors: string[] = [];

    // 1. Validar sucursal autorizada
    const branchId = this.selectedBranchId();
    if (!branchId) {
      errors.push('Debe seleccionar una sucursal.');
    } else if (
      summary.metadata.sucursales_autorizadas_ids &&
      !summary.metadata.sucursales_autorizadas_ids.includes(branchId)
    ) {
      errors.push('La sucursal seleccionada no está autorizada para este usuario.');
    }

    // 2. Validar cliente
    const clientId = this.selectedClientId();
    if (!clientId) {
      errors.push('Debe seleccionar un cliente registrado del paquete local.');
    }

    // 3. Validar líneas
    const items = this.lineItems();
    if (items.length === 0) {
      errors.push('Debe agregar al menos una prenda al listado de la reserva.');
    }

    // 4. Validar fecha programada
    const fechaProg = this.fechaAtencionProgramada();
    if (!fechaProg) {
      errors.push('Debe especificar la fecha y hora límite de retiro.');
    } else {
      const scheduledDate = new Date(fechaProg);
      if (isNaN(scheduledDate.getTime())) {
        errors.push('La fecha límite de retiro ingresada no tiene un formato válido.');
      } else if (scheduledDate.getTime() <= Date.now()) {
        errors.push('La fecha límite de retiro debe ser una fecha y hora futura.');
      }
    }

    // 5. Validar adelanto en efectivo
    const total = this.totalReferencial();
    const adelanto = Number(this.adelantoEfectivo() || 0);
    if (adelanto < 0) {
      errors.push('El monto de adelanto no puede ser negativo.');
    } else if (adelanto > total) {
      errors.push(
        `El adelanto (${adelanto.toFixed(2)}) no puede exceder el total referencial (${total.toFixed(2)}).`,
      );
    }

    if (errors.length > 0) {
      this.validationErrors.set(errors);
      return;
    }

    // Generar identificadores únicos locales
    const uuidReserva = crypto.randomUUID();
    const shortHash = uuidReserva.replace(/-/g, '').slice(0, 8).toUpperCase();
    const codigoLocal = `RES-LOC-${shortHash}`;
    const now = new Date();
    const nowIso = now.toISOString();
    const fechaProgIso = new Date(fechaProg).toISOString();

    const branch = this.selectedBranch();
    const client = this.selectedClient();

    // 1. Entidad Reserva Local
    const reservationRecord: OfflineReservationLocal = {
      uuid_reserva_offline: uuidReserva,
      codigo_local: codigoLocal,
      id_empresa: user.id_empresa,
      id_usuario: user.id_usuario,
      id_sucursal: branchId!,
      id_cliente: clientId!,
      fecha_reserva_offline: nowIso,
      fecha_atencion_programada: fechaProgIso,
      observaciones: this.observaciones().trim() || null,
      adelanto_efectivo: adelanto > 0 ? adelanto : 0,
      total_referencial: total,
      saldo_pendiente: Math.max(0, total - adelanto),
      estado: 'REGISTRADA_LOCAL',
      created_at: nowIso,
      sucursal_nombre: branch?.nombre,
      cliente_nombre: client ? `${client.nombre} ${client.apellido}` : undefined,
      cliente_telefono: client?.telefono || undefined,
    };

    // 2. Entidades Detalle de Reserva
    const detailRecords: OfflineReservationDetailLocal[] = items.map((item) => ({
      uuid_reserva_offline: uuidReserva,
      id_variante_producto: item.id_variante_producto,
      id_producto: item.id_producto,
      producto_nombre: item.producto_nombre,
      sku: item.sku,
      talla: item.talla,
      color: item.color,
      cantidad: item.cantidad,
      precio_referencial: item.precio_referencial,
      subtotal: item.subtotal,
    }));

    // 3. Entidad Cola de Sincronización (Outbox) compatible con el contrato de FastAPI CU10
    const queueRecord: OfflineSyncQueueItem = {
      uuid_operacion: crypto.randomUUID(),
      tipo_operacion: 'RESERVA',
      uuid_entidad: uuidReserva,
      estado: 'REGISTRADA_LOCAL',
      payload: {
        uuid_reserva_offline: uuidReserva,
        id_sucursal: branchId!,
        id_cliente: clientId!,
        fecha_reserva_offline: nowIso,
        fecha_atencion_programada: fechaProgIso,
        detalles: items.map((i) => ({
          id_variante_producto: i.id_variante_producto,
          cantidad: i.cantidad,
          precio_referencial: i.precio_referencial,
        })),
        observaciones: this.observaciones().trim() || null,
      },
      reintentos: 0,
      ultimo_error: null,
      created_at: nowIso,
      updated_at: nowIso,
    };

    this.isSubmitting.set(true);

    try {
      await this.storage.saveOfflineReservationAtomic(
        user.id_empresa,
        user.id_usuario,
        reservationRecord,
        detailRecords,
        queueRecord,
      );

      // Actualizar el mapa de reservas pendientes en memoria para recalculación de stock
      const updatedMap = new Map(this.pendingReservedQuantities());
      for (const item of items) {
        const key = `${branchId}_${item.id_variante_producto}`;
        const prev = updatedMap.get(key) || 0;
        updatedMap.set(key, prev + item.cantidad);
      }
      this.pendingReservedQuantities.set(updatedMap);

      // Datos para el comprobante imprimible local
      const receiptData: OfflineReceiptData = {
        uuid_reserva_offline: uuidReserva,
        codigo_local: codigoLocal,
        fecha_registro: nowIso,
        fecha_limite: fechaProgIso,
        sucursal_nombre: branch?.nombre || `Sucursal #${branchId}`,
        sucursal_direccion: branch?.direccion,
        cliente_nombre: client ? `${client.nombre} ${client.apellido}` : `Cliente #${clientId}`,
        cliente_telefono: client?.telefono || undefined,
        detalles: detailRecords,
        total_referencial: total,
        adelanto_efectivo: adelanto,
        saldo_pendiente: Math.max(0, total - adelanto),
        observaciones: reservationRecord.observaciones,
        estado: 'REGISTRADA_LOCAL',
        atendido_por: `${user.nombre} ${user.apellido}`,
      };

      this.successReservation.set(receiptData);
      this.showSuccessModal.set(true);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Error desconocido de almacenamiento';
      this.errorMessage.set(
        `Error al guardar en el almacenamiento local: ${msg}. Sus datos se conservan en pantalla.`,
      );
    } finally {
      this.isSubmitting.set(false);
    }
  }

  printReceipt(): void {
    window.print();
  }

  startNewReservation(): void {
    this.showSuccessModal.set(false);
    this.successReservation.set(null);
    this.lineItems.set([]);
    this.selectedClientId.set(null);
    this.clientSearchTerm.set('');
    this.adelantoEfectivo.set(0);
    this.observaciones.set('');
    this.validationErrors.set([]);
    this.errorMessage.set(null);

    // Reiniciar fecha a 48h futuras
    const defaultDate = new Date(Date.now() + 48 * 3600 * 1000);
    defaultDate.setMinutes(0);
    defaultDate.setSeconds(0);
    defaultDate.setMilliseconds(0);
    this.fechaAtencionProgramada.set(defaultDate.toISOString().slice(0, 16));
  }

  closeModal(): void {
    this.showSuccessModal.set(false);
  }
}

