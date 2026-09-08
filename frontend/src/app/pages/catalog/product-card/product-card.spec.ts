import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { CatalogProduct } from '../../../core/services/catalog.service';
import { CatalogProductCard } from './product-card';

const product: CatalogProduct = {
  id_producto: 7,
  nombre: 'Chaqueta urbana',
  descripcion_corta: 'Ligera y versátil',
  seccion: 'UNISEX',
  id_categoria: 2,
  categoria: 'Chaquetas',
  precio_base: '100.00',
  precio_final: '75.00',
  tiene_promocion: true,
  promocion_destacada: {
    id_promocion: 3,
    nombre: 'Oferta de temporada',
    codigo: null,
    descripcion: null,
    tipo_descuento: 'PORCENTAJE',
    valor: '25.00',
    porcentaje_descuento: '25.00',
    monto_descuento: '25.00',
    precio_resultante: '75.00',
    fecha_inicio: '2026-09-01T00:00:00',
    fecha_fin: '2026-09-30T23:59:59',
    acumulable: false,
  },
  porcentaje_descuento: '25.00',
  monto_descuento: '25.00',
  imagen_principal: 'https://cdn.test/chaqueta.jpg',
  colores_disponibles: [{ id_color: 1, nombre: 'Negro', codigo_hex: '#000000' }],
  tallas_disponibles: [{ id_talla: 1, nombre: 'M' }],
  disponibilidad_sucursal: {
    id_sucursal: 6,
    sucursal: 'Centro',
    estado: 'DISPONIBLE',
    cantidad_disponible: 4,
  },
};

describe('CatalogProductCard CU12', () => {
  let fixture: ComponentFixture<CatalogProductCard>;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideRouter([])] });
    fixture = TestBed.createComponent(CatalogProductCard);
    fixture.componentRef.setInput('product', product);
    fixture.componentRef.setInput('branchId', 6);
    fixture.detectChanges();
  });

  it('renders real price, promotion, color and branch availability', () => {
    const content = fixture.nativeElement.textContent;
    expect(content).toContain('Chaqueta urbana');
    expect(content).toContain('Bs 100,00');
    expect(content).toContain('Bs 75,00');
    expect(content).toContain('-25%');
    expect(content).toContain('Disponible');
    expect(fixture.nativeElement.querySelector('.product-card__colors span')).toBeTruthy();
  });

  it('switches to the fallback when the image fails', () => {
    fixture.nativeElement.querySelector('img').dispatchEvent(new Event('error'));
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.product-card__fallback')).toBeTruthy();
  });
});
