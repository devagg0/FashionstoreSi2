import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { environment } from '../../../../environments/environment';
import {
  RecommendationItem,
  RecommendationOrigin,
} from '../../../core/services/client-recommendations.service';
import { formatBs } from '../../../core/utils/money';
import { Recommendations } from './recommendations';

const url = `${environment.apiUrl}/api/client/recommendations`;
const cartUrl = `${environment.apiUrl}/api/client/cart/items`;

function item(changes: Partial<RecommendationItem> = {}): RecommendationItem {
  return {
    id_producto: 7,
    nombre: 'Chaqueta urbana',
    descripcion_corta: 'Ligera y versátil',
    seccion: 'UNISEX',
    id_categoria: 2,
    categoria: 'Chaquetas',
    id_temporada: 1,
    temporada: 'Invierno',
    precio_base: '400.00',
    precio_final: '360.00',
    tiene_promocion: true,
    promocion: {
      id_promocion: 3,
      nombre: 'Invierno',
      codigo: 'INV',
      descripcion: null,
      tipo_descuento: 'PORCENTAJE',
      valor: '10.00',
      fecha_inicio: '2026-09-01T00:00:00',
      fecha_fin: '2026-09-30T23:59:59',
      acumulable: false,
    },
    monto_descuento: '40.00',
    porcentaje_descuento: '10.00',
    imagen_principal: 'https://cdn.test/7.jpg',
    variante_sugerida: {
      id_variante_producto: 11,
      sku: 'CHA-M-NEG',
      id_talla: 2,
      talla: 'M',
      id_color: 1,
      color: 'Negro',
      codigo_hex: '#000000',
      stock_disponible: 8,
    },
    score: 0.9312,
    motivo: 'Basado en tus compras',
    ya_comprado: false,
    ...changes,
  };
}

describe('Recommendations CU26', () => {
  let fixture: ComponentFixture<Recommendations>;
  let http: HttpTestingController;

  const asClient = () => {
    localStorage.setItem('fashionstore_access_token', 'client-token');
    localStorage.setItem(
      'fashionstore_user',
      JSON.stringify({
        id_usuario: 1,
        nombre: 'Ana',
        apellido: 'Lopez',
        correo: 'ana@test.com',
        rol: 'CLIENTE',
      }),
    );
  };

  const create = (inputs: Record<string, unknown> = {}) => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    });
    fixture = TestBed.createComponent(Recommendations);
    http = TestBed.inject(HttpTestingController);
    // Los inputs deben fijarse antes del primer ciclo: ngOnInit ya dispara la carga.
    for (const [name, value] of Object.entries(inputs)) {
      fixture.componentRef.setInput(name, value);
    }
    fixture.detectChanges();
  };

  const flush = (data: RecommendationItem[], origen: RecommendationOrigin = 'PERSONALIZADO') => {
    http.expectOne((request) => request.url === url).flush({
      success: true,
      data,
      origen,
      message: 'ok',
    });
    fixture.detectChanges();
  };

  const text = () => fixture.nativeElement.textContent as string;
  const html = () => fixture.nativeElement.innerHTML as string;

  afterEach(() => {
    localStorage.clear();
  });

  describe('as an authenticated client', () => {
    beforeEach(() => {
      asClient();
      create();
    });

    afterEach(() => http.verify());

    it('shows the personalized heading and hides the internal score', () => {
      flush([item()], 'PERSONALIZADO');

      expect(text()).toContain('Recomendado para ti');
      expect(text()).toContain('tus compras');
      expect(text()).not.toContain('0.9312');
      expect(html()).not.toContain('score');
    });

    it('shows the fallback heading for a client without history', () => {
      flush([item({ motivo: 'Popular entre clientes similares' })], 'FALLBACK');

      expect(text()).toContain('Descubre estas prendas');
      expect(text()).toContain('lo más buscado');
      expect(text()).not.toContain('Recomendado para ti');
    });

    it('renders product, reason, suggested variant and discreet stock', () => {
      flush([item()]);
      const content = text();

      expect(content).toContain('Chaqueta urbana');
      expect(content).toContain('Basado en tus compras');
      expect(content).toContain('Talla M');
      expect(content).toContain('Negro');
      expect(content).toContain('Disponible');
      expect(content).toContain('Ver producto');
    });

    it('shows both prices and the discount badge when there is a promotion', () => {
      flush([item()]);
      const content = text();

      expect(content).toContain(formatBs('400.00'));
      expect(content).toContain(formatBs('360.00'));
      expect(content).toContain('-10%');
    });

    it('shows a single price and no badge without promotion', () => {
      flush([
        item({
          tiene_promocion: false,
          promocion: null,
          monto_descuento: null,
          porcentaje_descuento: null,
          precio_final: '400.00',
        }),
      ]);

      expect(text()).toContain(formatBs('400.00'));
      expect(fixture.nativeElement.querySelector('.recommendation-card__badge')).toBeNull();
      expect(fixture.nativeElement.querySelector('.recommendation-card__prices s')).toBeNull();
    });

    it('warns when stock is low', () => {
      flush([item({ variante_sugerida: { ...item().variante_sugerida!, stock_disponible: 3 } })]);
      expect(text()).toContain('Últimas 3 unidades');
    });

    it('adds the suggested variant to the cart reusing CU19', () => {
      flush([item()]);
      fixture.nativeElement.querySelector('.recommendation-card__actions button').click();

      const request = http.expectOne(cartUrl);
      expect(request.request.method).toBe('POST');
      expect(request.request.body).toEqual({ id_variante_producto: 11, cantidad: 1 });
      expect(request.request.headers.get('Authorization')).toBe('Bearer client-token');

      request.flush({ success: true, data: {}, message: 'ok' });
      fixture.detectChanges();
      expect(text()).toContain('se agregó a tu carrito');
    });

    it('reports a cart failure without breaking the list', () => {
      flush([item()]);
      fixture.nativeElement.querySelector('.recommendation-card__actions button').click();
      http.expectOne(cartUrl).flush(
        { success: false, message: 'No hay stock suficiente para esta cantidad.' },
        { status: 409, statusText: 'Conflict' },
      );
      fixture.detectChanges();

      expect(text()).toContain('No hay stock suficiente');
      expect(text()).toContain('Chaqueta urbana');
    });

    it('disables adding when there is no suggested variant but keeps the link', () => {
      flush([item({ variante_sugerida: null })]);
      const button = fixture.nativeElement.querySelector('.recommendation-card__actions button');

      expect(button.disabled).toBe(true);
      expect(text()).toContain('Elige talla y color en el detalle');
      expect(
        fixture.nativeElement.querySelector('.recommendation-card__actions a').getAttribute('href'),
      ).toContain('/catalogo/producto/7');

      button.click();
      http.expectNone(cartUrl);
    });

    it('shows skeletons while loading', () => {
      expect(fixture.nativeElement.querySelectorAll('.product-skeleton').length).toBeGreaterThan(0);
      expect(text()).not.toContain('No pudimos cargar');
      flush([item()]);
      expect(fixture.nativeElement.querySelectorAll('.product-skeleton').length).toBe(0);
    });

    it('shows an empty state with a catalog link', () => {
      flush([]);
      expect(text()).toContain('Todavía no tenemos sugerencias');
      expect(fixture.nativeElement.querySelector('.recommendation-card')).toBeNull();
    });

    it('shows an error with retry and reloads on demand', () => {
      http
        .expectOne((request) => request.url === url)
        .flush({ message: 'boom' }, { status: 500, statusText: 'Server Error' });
      fixture.detectChanges();

      expect(text()).toContain('No pudimos cargar tus recomendaciones');
      expect(text()).not.toContain('boom');

      fixture.nativeElement.querySelector('.recommendations__state button').click();
      flush([item()]);
      expect(text()).toContain('Chaqueta urbana');
    });

    it('requests the default limit of the section', () => {
      const request = http.expectOne((r) => r.url === url);
      expect(request.request.params.get('limit')).toBe('8');
      request.flush({ success: true, data: [], origen: 'FALLBACK', message: 'ok' });
    });
  });

  it('forwards a custom limit and branch to the API', () => {
    asClient();
    create({ limit: 6, idSucursal: 3 });
    const request = http.expectOne((r) => r.url === url);
    expect(request.request.params.get('limit')).toBe('6');
    expect(request.request.params.get('id_sucursal')).toBe('3');
    request.flush({ success: true, data: [], origen: 'FALLBACK', message: 'ok' });
    http.verify();
  });

  it('renders nothing and calls no API without a client session', () => {
    create();
    http.expectNone((request) => request.url === url);
    expect(fixture.nativeElement.querySelector('.recommendations')).toBeNull();
    http.verify();
  });

  it('renders nothing for a non-client role', () => {
    localStorage.setItem('fashionstore_access_token', 'staff-token');
    localStorage.setItem(
      'fashionstore_user',
      JSON.stringify({
        id_usuario: 2,
        nombre: 'Luis',
        apellido: 'Paz',
        correo: 'luis@test.com',
        rol: 'ADMINISTRADOR',
      }),
    );
    create();
    http.expectNone((request) => request.url === url);
    expect(fixture.nativeElement.querySelector('.recommendations')).toBeNull();
    http.verify();
  });
});
