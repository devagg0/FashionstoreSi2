import { CommonModule, CurrencyPipe, DatePipe } from '@angular/common';
import { Component, computed, inject, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import {
  OfflineBranchData,
  OfflineCategoryData,
  OfflineColorData,
  OfflineProductData,
  OfflineProductDetail,
  OfflineSizeData,
  OfflineStockData,
  OfflineStoredSummary,
  OfflineVariantData,
} from '../../core/models/offline.model';
import { OfflineStorageService } from '../../core/services/offline-storage.service';
import { SessionService } from '../../core/services/session.service';
import { Icon } from '../../shared/components/icon/icon';

export interface CatalogListItem {
  producto: OfflineProductData;
  categoriaNombre: string;
  totalStockDisponible: number;
  totalVariantes: number;
  tallasDisponibles: string[];
  coloresDisponibles: string[];
  skus: string[];
}

@Component({
  selector: 'app-offline-catalog',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, DatePipe, CurrencyPipe, Icon],
  templateUrl: './offline-catalog.html',
  styleUrl: './offline-catalog.scss',
})
export class OfflineCatalog implements OnInit {
  private readonly session = inject(SessionService);
  private readonly storage = inject(OfflineStorageService);
  private readonly router = inject(Router);

  readonly user = this.session.currentUser;
  readonly isLoading = signal<boolean>(true);
  readonly summary = signal<OfflineStoredSummary | null>(null);

  readonly rawProducts = signal<OfflineProductData[]>([]);
  readonly rawCategories = signal<OfflineCategoryData[]>([]);
  readonly rawSizes = signal<OfflineSizeData[]>([]);
  readonly rawColors = signal<OfflineColorData[]>([]);
  readonly rawVariants = signal<OfflineVariantData[]>([]);
  readonly rawStock = signal<OfflineStockData[]>([]);
  readonly rawBranches = signal<OfflineBranchData[]>([]);

  // Filtros locales (reactivos y en memoria, sin HTTP)
  readonly searchTerm = signal<string>('');
  readonly selectedCategory = signal<string>('TODAS');
  readonly selectedSize = signal<string>('TODAS');
  readonly selectedColor = signal<string>('TODAS');
  readonly selectedBranch = signal<string>('TODAS');
  readonly onlyInStock = signal<boolean>(false);

  // Detalle del producto seleccionado (modal / drawer)
  readonly selectedProductDetail = signal<OfflineProductDetail | null>(null);
  readonly isDetailOpen = signal<boolean>(false);
  readonly isLoadingDetail = signal<boolean>(false);

  readonly isAdmin = computed(() => {
    return this.user()?.rol?.toUpperCase() === 'ADMINISTRADOR';
  });

  readonly offlineOperationUrl = computed(() => {
    return this.isAdmin() ? '/admin/offline' : '/staff/offline';
  });

  readonly enrichedItems = computed<CatalogListItem[]>(() => {
    const products = this.rawProducts();
    const categories = this.rawCategories();
    const sizes = this.rawSizes();
    const colors = this.rawColors();
    const variants = this.rawVariants();
    const allStock = this.rawStock();

    const catMap = new Map(categories.map((c) => [c.id_categoria, c.nombre]));
    const sizeMap = new Map(sizes.map((s) => [s.id_talla, s.nombre]));
    const colorMap = new Map(colors.map((c) => [c.id_color, c.nombre]));

    return products.map((prod) => {
      const prodVariants = variants.filter((v) => v.id_producto === prod.id_producto);
      const variantIds = new Set(prodVariants.map((v) => v.id_variante_producto));
      const prodStock = allStock.filter((s) => variantIds.has(s.id_variante_producto));

      const totalStock = prodStock.reduce((acc, curr) => acc + curr.stock_disponible, 0);

      const sizeNames = Array.from(
        new Set(
          prodVariants
            .map((v) => v.talla || sizeMap.get(v.id_talla))
            .filter((t): t is string => Boolean(t)),
        ),
      );

      const colorNames = Array.from(
        new Set(
          prodVariants
            .map((v) => v.color || colorMap.get(v.id_color))
            .filter((c): c is string => Boolean(c)),
        ),
      );

      const skus = prodVariants.map((v) => v.sku);

      return {
        producto: prod,
        categoriaNombre: prod.categoria || catMap.get(prod.id_categoria) || 'Sin categoría',
        totalStockDisponible: totalStock,
        totalVariantes: prodVariants.length,
        tallasDisponibles: sizeNames,
        coloresDisponibles: colorNames,
        skus,
      };
    });
  });

  readonly filteredItems = computed<CatalogListItem[]>(() => {
    const items = this.enrichedItems();
    const search = this.searchTerm().trim().toLowerCase();
    const cat = this.selectedCategory();
    const size = this.selectedSize();
    const color = this.selectedColor();
    const branch = this.selectedBranch();
    const onlyStock = this.onlyInStock();
    const allStock = this.rawStock();
    const variants = this.rawVariants();

    return items.filter((item) => {
      // 1. Búsqueda por nombre o SKU
      if (search) {
        const matchesName = item.producto.nombre.toLowerCase().includes(search);
        const matchesSku = item.skus.some((sku) => sku.toLowerCase().includes(search));
        const matchesDesc = (item.producto.descripcion || '').toLowerCase().includes(search);
        if (!matchesName && !matchesSku && !matchesDesc) {
          return false;
        }
      }

      // 2. Filtro por categoría
      if (cat !== 'TODAS') {
        if (
          item.categoriaNombre !== cat &&
          item.producto.id_categoria.toString() !== cat
        ) {
          return false;
        }
      }

      // 3. Filtro por talla
      if (size !== 'TODAS') {
        if (!item.tallasDisponibles.includes(size)) {
          return false;
        }
      }

      // 4. Filtro por color
      if (color !== 'TODAS') {
        if (!item.coloresDisponibles.includes(color)) {
          return false;
        }
      }

      // 5. Filtro por sucursal específica
      if (branch !== 'TODAS') {
        const branchId = Number(branch);
        const prodVariants = variants.filter(
          (v) => v.id_producto === item.producto.id_producto,
        );
        const vIds = new Set(prodVariants.map((v) => v.id_variante_producto));
        const branchStock = allStock.filter(
          (s) => vIds.has(s.id_variante_producto) && s.id_sucursal === branchId,
        );
        const branchAvailable = branchStock.reduce(
          (acc, curr) => acc + curr.stock_disponible,
          0,
        );
        if (branchAvailable <= 0) {
          return false;
        }
      }

      // 6. Filtro sólo con existencias disponibles
      if (onlyStock && item.totalStockDisponible <= 0) {
        return false;
      }

      return true;
    });
  });

  async ngOnInit(): Promise<void> {
    await this.loadOfflineCatalog();
  }

  /**
   * Carga exclusivamente desde IndexedDB. Sin ninguna petición HTTP.
   */
  async loadOfflineCatalog(): Promise<void> {
    const user = this.user();
    if (!user || !user.id_empresa) {
      this.isLoading.set(false);
      return;
    }

    this.isLoading.set(true);
    try {
      const empresaId = user.id_empresa;
      const userId = user.id_usuario;

      const [
        summary,
        products,
        categories,
        sizes,
        colors,
        variants,
        stock,
        branches,
      ] = await Promise.all([
        this.storage.getStoredPackageSummary(empresaId, userId),
        this.storage.getCatalogProducts(empresaId, userId),
        this.storage.getCategories(empresaId, userId),
        this.storage.getSizes(empresaId, userId),
        this.storage.getColors(empresaId, userId),
        this.storage.getVariants(empresaId, userId),
        this.storage.getInventory(empresaId, userId),
        this.storage.getBranches(empresaId, userId),
      ]);

      // Deducir las reservas registradas localmente para calcular la disponibilidad estimada real (CU10)
      const pendingMap = this.storage.getPendingReservedQuantities
        ? await this.storage.getPendingReservedQuantities(empresaId, userId)
        : new Map<string, number>();

      const adjustedStock = stock.map((s) => {
        const pending = pendingMap.get(`${s.id_sucursal}_${s.id_variante_producto}`) || 0;
        if (pending > 0) {
          return {
            ...s,
            stock_reservado: s.stock_reservado + pending,
            stock_disponible: Math.max(0, s.stock_disponible - pending),
          };
        }
        return s;
      });

      this.summary.set(summary);
      this.rawProducts.set(products);
      this.rawCategories.set(categories);
      this.rawSizes.set(sizes);
      this.rawColors.set(colors);
      this.rawVariants.set(variants);
      this.rawStock.set(adjustedStock);
      this.rawBranches.set(branches);
    } catch {
      this.summary.set(null);
    } finally {
      this.isLoading.set(false);
    }
  }

  /**
   * Abre el detalle del producto con variantes y stock por sucursal.
   */
  async openProductDetail(productId: number): Promise<void> {
    const user = this.user();
    if (!user || !user.id_empresa) return;

    this.isLoadingDetail.set(true);
    this.isDetailOpen.set(true);

    try {
      const detail = await this.storage.getProductDetail(
        user.id_empresa,
        user.id_usuario,
        productId,
      );
      this.selectedProductDetail.set(detail);
    } finally {
      this.isLoadingDetail.set(false);
    }
  }

  closeProductDetail(): void {
    this.isDetailOpen.set(false);
    this.selectedProductDetail.set(null);
  }

  resetFilters(): void {
    this.searchTerm.set('');
    this.selectedCategory.set('TODAS');
    this.selectedSize.set('TODAS');
    this.selectedColor.set('TODAS');
    this.selectedBranch.set('TODAS');
    this.onlyInStock.set(false);
  }

  handleImageError(event: Event): void {
    const imgElement = event.target as HTMLImageElement;
    imgElement.style.display = 'none';
    const fallback = imgElement.parentElement?.querySelector('.offline-img-fallback');
    if (fallback) {
      (fallback as HTMLElement).style.display = 'flex';
    }
  }
}

