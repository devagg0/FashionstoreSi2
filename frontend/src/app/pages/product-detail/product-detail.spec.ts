import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { CatalogProductDetail } from '../../core/services/catalog.service';
import { ProductDetail } from './product-detail';

const detail: CatalogProductDetail = {
  id_producto: 7,
  nombre: 'Chaqueta urbana',
  descripcion: 'Ligera y versátil',
  seccion: 'UNISEX',
  id_categoria: 2,
  categoria: 'Chaquetas',
  id_temporada: null,
  temporada: null,
  precio_base: '100.00',
  precio_final: '100.00',
  tiene_promocion: false,
  promociones_vigentes: [],
  promocion_destacada: null,
  porcentaje_descuento: null,
  monto_descuento: null,
  imagen_principal: null,
  galeria: [],
  tallas: [{ id_talla: 1, nombre: 'M' }],
  colores: [{ id_color: 2, nombre: 'Negro', codigo_hex: '#000000' }],
  colecciones: [],
  variantes: [
    {
      id_variante_producto: 9,
      sku: 'CHA-M-NEG',
      talla: { id_talla: 1, nombre: 'M' },
      color: { id_color: 2, nombre: 'Negro', codigo_hex: '#000000' },
      disponibilidad_sucursal: {
        id_sucursal: 6,
        estado: 'DISPONIBLE',
        cantidad_disponible: 2,
      },
    },
  ],
};

describe('ProductDetail CU12', () => {
  let fixture: ComponentFixture<ProductDetail>;
  let page: ProductDetail;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    });
    fixture = TestBed.createComponent(ProductDetail);
    page = fixture.componentInstance;
    page['product'].set(detail);
    page['branchId'].set(6);
    page['errorMessage'].set('');
    page['loading'].set(false);
    fixture.detectChanges();
  });

  it('identifies a variant from the selected color and size', () => {
    page['selectColor'](2);
    page['selectSize'](1);
    fixture.detectChanges();
    expect(page['selectedVariant']()?.sku).toBe('CHA-M-NEG');
    expect(page['availabilityLabel'](detail.variantes[0])).toBe('Pocas unidades');
  });

  it('keeps the reservation selector separate from the future purchase flow', () => {
    expect(fixture.nativeElement.querySelector('.future-purchase')).toBeNull();
    expect(fixture.nativeElement.querySelector('.reservation-selector')).toBeNull();
  });
});
