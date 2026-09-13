import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { environment } from '../../../../../environments/environment';
import { SessionService } from '../../../../core/services/session.service';
import { CatalogProductDetail } from '../../../../core/services/catalog.service';
import { StaffReservationDetail } from '../../../../core/services/staff-reservations.service';
import { SaleBranch, SaleData, SaleQuote } from '../../../../core/services/staff-sales.service';
import { NewSale } from './new-sale';

const url = `${environment.apiUrl}/api/staff/sales`;
const catalogUrl = `${environment.apiUrl}/api/catalog/products`;
const branch: SaleBranch = {
  id_sucursal: 2,
  nombre: 'Centro',
  ciudad: 'La Paz',
  direccion: 'Av. 1',
  id_empleado_sucursal: 3,
};
const product: CatalogProductDetail = {
  id_producto: 3,
  nombre: 'Camisa Oxford',
  descripcion: null,
  seccion: 'HOMBRE',
  id_categoria: 1,
  categoria: 'Camisas',
  id_temporada: null,
  temporada: null,
  precio_base: '100.00',
  precio_final: '90.00',
  tiene_promocion: true,
  promociones_vigentes: [],
  promocion_destacada: null,
  porcentaje_descuento: null,
  monto_descuento: '10.00',
  imagen_principal: '/camisa.jpg',
  galeria: [],
  tallas: [],
  colores: [],
  colecciones: [],
  variantes: [
    {
      id_variante_producto: 8,
      sku: 'CAM-M-NEG',
      talla: { id_talla: 1, nombre: 'M' },
      color: { id_color: 1, nombre: 'Negro', codigo_hex: null },
      disponibilidad_sucursal: { id_sucursal: 2, estado: 'DISPONIBLE', cantidad_disponible: 10 },
    },
  ],
};
const reservation: StaffReservationDetail = {
  id_reserva: 4,
  codigo: 'RSV-ABC',
  estado: 'ATENDIDA',
  created_at: '2026-09-11T12:00:00Z',
  fecha_atencion_programada: '2026-09-12T20:00:00Z',
  fecha_expiracion: '2026-09-12T21:00:00Z',
  fecha_atencion: '2026-09-12T20:00:00Z',
  cliente: { id_cliente: 7, nombre: 'Ana', apellido: 'Lopez', correo: 'a@b.com', telefono: null },
  sucursal: {
    id_sucursal: 2,
    nombre: 'Centro',
    direccion: 'Av. 1',
    ciudad: { id_ciudad: 1, nombre: 'La Paz' },
  },
  cantidad_prendas: 3,
  total: '240.00',
  prendas: [8, 9].map((id, i) => ({
    id_variante_producto: id,
    sku: `SKU-${id}`,
    id_producto: 3,
    producto: i ? 'Polera' : 'Camisa Oxford',
    imagen_principal: '/camisa.jpg',
    talla: { id_talla: 1, nombre: 'M' },
    color: { id_color: 1, nombre: 'Negro', codigo_hex: null },
    cantidad: i ? 1 : 2,
    precio_reservado: '80.00',
    subtotal: i ? '80.00' : '160.00',
  })),
};
const quote: SaleQuote = {
  sucursal: branch,
  id_empleado: 5,
  id_cliente: null,
  id_reserva: null,
  detalles: [
    {
      id_variante_producto: 8,
      sku: 'CAM-M-NEG',
      producto: 'Camisa Oxford',
      talla: 'M',
      color: 'Negro',
      cantidad: 1,
      precio_unitario: '100.00',
      descuento_unitario: '10.00',
      id_promocion: 2,
      subtotal_linea: '90.00',
      cantidad_disponible: 10,
    },
  ],
  liberaciones: [],
  subtotal: '100.00',
  descuento_total: '10.00',
  total: '90.00',
};
const sale: SaleData = {
  id_venta: 12,
  numero_venta: 'VTA-3-test',
  estado: 'PENDIENTE',
  id_sucursal: 2,
  id_empleado: 5,
  id_cliente: null,
  id_reserva: null,
  sucursal: branch,
  cajero: { id_usuario: 3, id_empleado: 5, nombre: 'Leo', apellido: 'Paz' },
  cliente: null,
  reserva: null,
  fecha_venta: '2026-09-12T20:00:00Z',
  detalles: quote.detalles,
  subtotal: '100.00',
  descuento_total: '10.00',
  total: '90.00',
  movimiento: {
    id_movimiento_inventario: 15,
    id_empleado_sucursal: 3,
    tipo_movimiento: 'VENTA',
    estado: 'PENDIENTE',
  },
};

describe('NewSale CU20', () => {
  let fixture: ComponentFixture<NewSale>;
  let page: NewSale;
  let http: HttpTestingController;
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    const session = TestBed.inject(SessionService);
    session.saveAccessToken('token');
    session.saveUser({
      id_usuario: 3,
      nombre: 'Leo',
      apellido: 'Paz',
      correo: 'l@b.com',
      rol: 'CAJERO',
    });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(NewSale);
    page = fixture.componentInstance;
    fixture.detectChanges();
    // jsdom does not implement the native dialog API; real focus behavior is checked in Chrome.
    const dialog = fixture.nativeElement.querySelector('dialog') as HTMLDialogElement;
    dialog.showModal = () => {
      dialog.open = true;
    };
    dialog.close = () => {
      dialog.open = false;
    };
  });
  afterEach(() => {
    fixture.destroy();
    http.verify();
    localStorage.clear();
    sessionStorage.clear();
  });
  function branches(data = [branch]) {
    http.expectOne(url + '/branches').flush({ success: true, data });
    fixture.detectChanges();
  }
  function add() {
    page.selectedProduct.set(product);
    page.addVariant(product.variantes[0]);
    fixture.detectChanges();
  }
  function quoted() {
    page.quoteSale();
    http.expectOne(url + '/quote').flush({ success: true, data: quote });
    fixture.detectChanges();
  }
  function reserved(data = reservation) {
    page.changeMode('reservation');
    page.code = ' RSV-ABC ';
    page.searchReservation();
    const request = http.expectOne(`${environment.apiUrl}/api/staff/reservations/code/RSV-ABC`);
    expect(request.request.headers.get('Authorization')).toBe('Bearer token');
    request.flush({ success: true, data, message: '' });
    fixture.detectChanges();
  }
  it('loads branches with a separate loading state and auto-selects a single branch', () => {
    expect(page.loadingBranches()).toBe(true);
    expect(fixture.nativeElement.textContent).toContain('Cargando sucursales');
    branches();
    expect(page.loadingBranches()).toBe(false);
    expect(page.branchId()).toBe(2);
    for (const text of ['Centro', 'La Paz', 'Av. 1'])
      expect(fixture.nativeElement.textContent).toContain(text);
    expect(fixture.nativeElement.querySelector('#branch')).toBeNull();
  });
  it('offers only returned branches when several exist', () => {
    branches([branch, { ...branch, id_sucursal: 7, nombre: 'Norte' }]);
    expect(page.branchId()).toBeNull();
    expect(fixture.nativeElement.querySelectorAll('#branch option').length).toBe(3);
    page.changeBranch(99);
    expect(page.branchId()).toBeNull();
    page.changeBranch(7);
    expect(page.branchId()).toBe(7);
  });
  it('handles no assigned branches', () => {
    branches([]);
    expect(page.canQuote()).toBe(false);
    expect(fixture.nativeElement.textContent).toContain('No hay sucursales');
  });
  it('starts in direct mode', () => {
    branches();
    expect(page.mode()).toBe('direct');
    expect(fixture.nativeElement.querySelector('#product-search')).toBeTruthy();
  });
  it('changes to reservation mode without external product controls', () => {
    branches();
    page.changeMode('reservation');
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('#reservation-code')).toBeTruthy();
    expect(fixture.nativeElement.querySelector('#product-search')).toBeNull();
  });
  it('confirms mode changes and clears lines, product, reservation and quote', () => {
    branches();
    add();
    quoted();
    page.changeMode('reservation');
    fixture.detectChanges();
    expect(page.mode()).toBe('direct');
    expect(fixture.nativeElement.querySelector('[role="alertdialog"]')).toBeTruthy();
    page.confirmMode();
    expect(page.lines()).toEqual([]);
    expect(page.quote()).toBeNull();
    expect(page.selectedProduct()).toBeNull();
    expect(page.mode()).toBe('reservation');
  });
  it('can cancel mode change without losing lines', () => {
    branches();
    add();
    page.changeMode('reservation');
    page.pendingMode.set(null);
    expect(page.lines().length).toBe(1);
    expect(page.mode()).toBe('direct');
  });
  it.each(['Camisa', 'CAM-M-NEG'])('reuses catalog search for %s', (search) => {
    branches();
    page.search = search;
    page.searchProducts();
    expect(page.searchingProducts()).toBe(true);
    expect(page.loadingBranches()).toBe(false);
    const request = http.expectOne((r) => r.url === catalogUrl);
    expect(request.request.params.get('search')).toBe(search);
    expect(request.request.params.get('id_sucursal')).toBe('2');
    request.flush({ data: [{ ...product }], pagination: { total_pages: 1 } });
    fixture.detectChanges();
    expect(page.products().length).toBe(1);
    expect(page.searchingProducts()).toBe(false);
  });
  it('retrieves variants for selected product and branch', () => {
    branches();
    page.selectProduct(3);
    http.expectOne(catalogUrl + '/3?id_sucursal=2').flush({ data: product });
    fixture.detectChanges();
    expect(page.selectedProduct()).toEqual(product);
    expect(fixture.nativeElement.textContent).toContain('CAM-M-NEG');
  });
  it('adds a variant with image, SKU, size, color and indicative price', () => {
    branches();
    add();
    expect(page.payload()).toEqual({
      id_sucursal: 2,
      items: [{ id_variante_producto: 8, cantidad: 1 }],
    });
    for (const text of ['Camisa Oxford', 'CAM-M-NEG', 'Negro', 'Bs 90,00'])
      expect(fixture.nativeElement.textContent).toContain(text);
    expect(fixture.nativeElement.querySelector('img').getAttribute('src')).toBe('/camisa.jpg');
  });
  it('increments an existing variant without duplicate lines', () => {
    branches();
    add();
    add();
    expect(page.lines().length).toBe(1);
    expect(page.lines()[0].cantidad).toBe(2);
  });
  it('increases and decreases quantities', () => {
    branches();
    add();
    page.setQuantity(8, 3);
    expect(page.units()).toBe(3);
    page.setQuantity(8, 2);
    expect(page.units()).toBe(2);
  });
  it.each([0, -1, 1.5, NaN, 2147483648])('rejects direct quantity %s', (quantity) => {
    branches();
    add();
    page.setQuantity(8, quantity);
    expect(page.units()).toBe(1);
  });
  it('removes a direct line', () => {
    branches();
    add();
    page.removeLine(8);
    expect(page.lines()).toEqual([]);
    expect(page.canQuote()).toBe(false);
  });
  it('quotes exact items without client-authoritative prices', () => {
    branches();
    add();
    page.quoteSale();
    const request = http.expectOne(url + '/quote');
    expect(request.request.body).toEqual({
      id_sucursal: 2,
      items: [{ id_variante_producto: 8, cantidad: 1 }],
    });
    request.flush({ data: quote });
    expect(page.quote()).toEqual(quote);
  });
  it('renders backend promotion, subtotal, discount, total and availability', () => {
    branches();
    add();
    quoted();
    for (const text of ['Promoción #2', 'Bs 100,00', 'Bs 10,00', 'Bs 90,00', 'Disponible: 10'])
      expect(fixture.nativeElement.textContent).toContain(text);
  });
  it.each(['quantity', 'remove', 'branch', 'add'] as const)(
    'invalidates quote on %s change',
    (action) => {
      branches([branch, { ...branch, id_sucursal: 7 }]);
      page.changeBranch(2);
      add();
      quoted();
      if (action === 'quantity') page.setQuantity(8, 2);
      if (action === 'remove') page.removeLine(8);
      if (action === 'branch') page.changeBranch(7);
      if (action === 'add') add();
      fixture.detectChanges();
      expect(page.quote()).toBeNull();
      expect(page.stale()).toBe(true);
      expect(page.canCreate()).toBe(false);
      expect(fixture.nativeElement.textContent).toContain('Cotización desactualizada');
    },
  );
  it('shows attended reservation, client and reserved garments', () => {
    branches();
    reserved();
    for (const text of [
      'RSV-ABC',
      'Ana Lopez',
      'ATENDIDA',
      'Reservado: 2',
      'Comprar',
      'Precio reservado: Bs 80,00',
    ])
      expect(fixture.nativeElement.textContent).toContain(text);
    expect(page.lines().length).toBe(2);
  });
  it.each(['PENDIENTE', 'CONFIRMADA', 'CANCELADA', 'EXPIRADA'] as const)(
    'rejects reservation state %s',
    (estado) => {
      branches();
      reserved({ ...reservation, estado });
      expect(page.lines()).toEqual([]);
      expect(page.canQuote()).toBe(false);
      expect(page.error()).toBe('Esta reserva todavía no está disponible para procesar una venta.');
    },
  );
  it('rejects reservation outside cashier branches', () => {
    branches([{ ...branch, id_sucursal: 7 }]);
    reserved();
    expect(page.lines()).toEqual([]);
    expect(page.error()).toContain('no está autorizada');
  });
  it('selects reservation branch from authorized list', () => {
    branches([branch, { ...branch, id_sucursal: 7 }]);
    reserved();
    expect(page.branchId()).toBe(2);
    page.changeBranch(7);
    expect(page.branchId()).toBe(2);
  });
  it('defaults to total purchase', () => {
    branches();
    reserved();
    expect(page.payload().items).toEqual([
      { id_variante_producto: 8, cantidad: 2 },
      { id_variante_producto: 9, cantidad: 1 },
    ]);
  });
  it('supports partial purchase and omits zero quantities in quote', () => {
    branches();
    reserved();
    page.setQuantity(8, 1);
    page.setQuantity(9, 0);
    page.quoteSale();
    const request = http.expectOne(url + '/quote');
    expect(request.request.body).toEqual({
      id_sucursal: 2,
      id_reserva: 4,
      items: [{ id_variante_producto: 8, cantidad: 1 }],
    });
    request.flush({ data: { ...quote, id_reserva: 4 } });
    expect(page.quote()?.id_reserva).toBe(4);
  });
  it.each([-1, 3, 1.5])('rejects reserved quantity %s', (quantity) => {
    branches();
    reserved();
    page.setQuantity(8, quantity);
    expect(page.lines()[0].cantidad).toBe(2);
  });
  it('allows zero but blocks all-zero purchase and registration', () => {
    branches();
    reserved();
    page.setQuantity(8, 0);
    page.setQuantity(9, 0);
    fixture.detectChanges();
    expect(page.units()).toBe(0);
    expect(page.canQuote()).toBe(false);
    page.createSale();
    http.expectNone(url);
    expect(fixture.nativeElement.textContent).toContain(
      'Selecciona al menos una prenda para la venta.',
    );
  });
  it('blocks adding external variants or removing reserved entries', () => {
    branches();
    reserved();
    page.selectedProduct.set(product);
    page.addVariant({ ...product.variantes[0], id_variante_producto: 99 });
    page.removeLine(8);
    expect(page.lines().length).toBe(2);
    expect(page.lines().some((l) => l.id_variante_producto === 99)).toBe(false);
  });
  it('does not depend on catalog availability for reserved garment images', () => {
    branches();
    reserved({
      ...reservation,
      prendas: reservation.prendas.map((p) => ({ ...p, imagen_principal: null })),
    });
    http.expectOne(catalogUrl + '/3').flush({}, { status: 404, statusText: 'Not found' });
    expect(page.canQuote()).toBe(true);
  });
  it('generates one UUID, persists it and prevents double POST while processing', () => {
    branches();
    add();
    quoted();
    page.createSale();
    const key = page.attempt()!.key;
    page.createSale();
    expect(key).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i);
    expect(sessionStorage.getItem('fashionstore-cu20-3')).toContain(key);
    const request = http.expectOne(url);
    expect(request.request.headers.get('Idempotency-Key')).toBe(key);
    expect(page.creatingSale()).toBe(true);
    expect(page.attempt()!.key).toBe(key);
    request.flush({ data: sale });
    expect(page.attempt()).toBeNull();
    expect(sessionStorage.getItem('fashionstore-cu20-3')).toBeNull();
  });
  it('shows PENDIENTE result without payment request or completed copy', () => {
    branches();
    add();
    quoted();
    page.createSale();
    http.expectOne(url).flush({ data: sale });
    fixture.detectChanges();
    const text = fixture.nativeElement.textContent;
    for (const value of [
      'Venta registrada',
      'PENDIENTE',
      'Pago pendiente',
      'Bs 90,00',
      'Pendiente de pago en caja',
    ])
      expect(text).toContain(value);
    expect(text).not.toMatch(/Venta completada|Compra completada|Pago realizado/);
    expect(fixture.nativeElement.querySelector('a[href*="pago"]')).toBeNull();
  });
  it('cleans state for new sale and generates another key', () => {
    branches();
    add();
    quoted();
    page.createSale();
    const key = page.attempt()!.key;
    http.expectOne(url).flush({ data: sale });
    page.newSale();
    expect(page.lines()).toEqual([]);
    expect(page.result()).toBeNull();
    expect(page.quote()).toBeNull();
    add();
    quoted();
    page.createSale();
    expect(page.attempt()!.key).not.toBe(key);
    http.expectOne(url).flush({ data: sale });
  });
  it('cannot register without a current quote', () => {
    branches();
    add();
    page.createSale();
    http.expectNone(url);
    expect(page.attempt()).toBeNull();
  });
  it.each([401, 403, 404, 409, 422, 500])('handles HTTP %s without raw JSON', (status) => {
    branches();
    add();
    page.quoteSale();
    http
      .expectOne(url + '/quote')
      .flush({ detail: [{ msg: 'raw validation' }] }, { status, statusText: 'Error' });
    fixture.detectChanges();
    expect(page.error().length).toBeGreaterThan(0);
    expect(fixture.nativeElement.textContent).not.toContain('raw validation');
    expect(page.quoting()).toBe(false);
    expect(page.canCreate()).toBe(false);
  });
  it.each(['Stock cambió en la sucursal', 'La reserva ya tiene una venta asociada'])(
    'shows backend business conflict: %s',
    (message) => {
      branches();
      add();
      quoted();
      page.createSale();
      http.expectOne(url).flush({ message }, { status: 409, statusText: 'Conflict' });
      expect(page.error()).toBe(message);
      expect(page.quote()).toBeNull();
      expect(page.uncertain()).toBe(false);
    },
  );
  it('blocks ambiguous idempotency conflict without automatic resubmission', () => {
    branches();
    add();
    quoted();
    page.createSale();
    const key = page.attempt()!.key;
    http
      .expectOne(url)
      .flush(
        { message: 'Esta solicitud de venta ya fue registrada' },
        { status: 409, statusText: 'Conflict' },
      );
    page.createSale();
    page.retryAttempt();
    page.newSale();
    http.expectNone(url);
    expect(page.attempt()!.key).toBe(key);
    expect(page.uncertain()).toBe(true);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('La venta ya pudo registrarse');
  });
  it.each([0, 500])(
    'preserves intent after %s and only retries explicitly with original key and payload',
    (status) => {
      branches();
      add();
      quoted();
      page.createSale();
      const attempt = page.attempt()!;
      http.expectOne(url).flush({}, { status, statusText: 'Error' });
      expect(page.uncertain()).toBe(true);
      http.expectNone(url);
      page.setQuantity(8, 5);
      page.retryAttempt();
      const retry = http.expectOne(url);
      expect(retry.request.headers.get('Idempotency-Key')).toBe(attempt.key);
      expect(retry.request.body).toEqual(attempt.payload);
      retry.flush({ data: sale });
    },
  );
  it('recovers persisted intent after page refresh', () => {
    branches();
    add();
    quoted();
    page.createSale();
    const key = page.attempt()!.key;
    http.expectOne(url).flush({}, { status: 500, statusText: 'Error' });
    fixture.destroy();
    fixture = TestBed.createComponent(NewSale);
    page = fixture.componentInstance;
    fixture.detectChanges();
    branches();
    expect(page.uncertain()).toBe(true);
    expect(page.attempt()?.key).toBe(key);
    page.createSale();
    http.expectNone(url);
  });
  it('consults a known sale ID and validates it against the attempt UUID', () => {
    branches();
    add();
    quoted();
    page.createSale();
    const key = page.attempt()!.key;
    http.expectOne(url).flush({}, { status: 500, statusText: 'Error' });
    page.saleId = '12';
    page.consultSale();
    http
      .expectOne(url + '/12')
      .flush({ data: { ...sale, numero_venta: `VTA-3-${key.replaceAll('-', '')}` } });
    expect(page.result()?.id_venta).toBe(12);
    expect(page.uncertain()).toBe(false);
  });
  it('does not resolve intent using an unrelated sale', () => {
    branches();
    add();
    quoted();
    page.createSale();
    http.expectOne(url).flush({}, { status: 500, statusText: 'Error' });
    page.saleId = '12';
    page.consultSale();
    http.expectOne(url + '/12').flush({ data: sale });
    expect(page.uncertain()).toBe(true);
    expect(page.result()).toBeNull();
    expect(page.error()).toContain('no corresponde');
  });
  it('locks edits, mode, branch and repeated quote while quoting', () => {
    branches();
    add();
    page.quoteSale();
    page.setQuantity(8, 4);
    page.changeMode('reservation');
    page.changeBranch(null);
    page.removeLine(8);
    page.quoteSale();
    fixture.detectChanges();
    expect(page.units()).toBe(1);
    expect(page.mode()).toBe('direct');
    expect(page.branchId()).toBe(2);
    expect(fixture.nativeElement.querySelector('.register-sale').disabled).toBe(true);
    http.expectOne(url + '/quote').flush({ data: quote });
  });
  it('locks primary action and edits during creation', () => {
    branches();
    add();
    quoted();
    page.createSale();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.register-sale').disabled).toBe(true);
    expect(fixture.nativeElement.textContent).toContain('Registrando venta');
    page.setQuantity(8, 2);
    page.changeMode('reservation');
    expect(page.units()).toBe(1);
    expect(page.mode()).toBe('direct');
    http.expectOne(url).flush({ data: sale });
  });
  it('uses responsive cards and labelled accessible controls without a main table', () => {
    branches();
    add();
    expect(fixture.nativeElement.querySelector('.sale-grid .sale-line')).toBeTruthy();
    expect(fixture.nativeElement.querySelector('.sale-summary')).toBeTruthy();
    expect(fixture.nativeElement.querySelector('table')).toBeNull();
    expect(
      fixture.nativeElement.querySelector(
        'button[aria-label="Aumentar cantidad de Camisa Oxford"]',
      ),
    ).toBeTruthy();
    expect(fixture.nativeElement.querySelector('label[for="product-search"]')).toBeTruthy();
  });
});
