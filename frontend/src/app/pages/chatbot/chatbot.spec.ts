import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { provideRouter } from '@angular/router';
import { environment } from '../../../environments/environment';
import { Chatbot } from './chatbot';

describe('Chatbot CU27', () => {
  let fixture: ComponentFixture<Chatbot>;
  let http: HttpTestingController;

  beforeEach(async () => {
    localStorage.setItem('fashionstore_access_token', 'client-token');
    await TestBed.configureTestingModule({
      imports: [Chatbot],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    }).compileComponents();
    fixture = TestBed.createComponent(Chatbot);
    http = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
  });

  afterEach(() => {
    http.verify();
    localStorage.clear();
  });

  it('envía el mensaje y muestra la respuesta y el producto sugerido', () => {
    const textarea = fixture.nativeElement.querySelector('textarea') as HTMLTextAreaElement;
    textarea.value = 'Busco un vestido rojo para una fiesta';
    textarea.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    fixture.nativeElement.querySelector('form').dispatchEvent(new Event('submit'));

    const request = http.expectOne(`${environment.apiUrl}/api/client/chatbot/message`);
    expect(request.request.headers.get('Authorization')).toBe('Bearer client-token');
    expect(request.request.body.message).toBe('Busco un vestido rojo para una fiesta');
    request.flush({
      success: true,
      data: {
        reply: 'Encontré un vestido rojo disponible en talla M.',
        products: [{
          id_producto: 7,
          nombre: 'Vestido rojo de fiesta',
          categoria: 'Vestidos',
          precio: '200.00',
          colores: ['Rojo'],
          tallas: ['M'],
          disponibilidad: 'DISPONIBLE',
          cantidad_disponible: 3,
        }],
      },
    });
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('Encontré un vestido rojo disponible');
    expect(fixture.nativeElement.textContent).toContain('Vestido rojo de fiesta');
    expect(fixture.debugElement.query(By.css('.product-suggestion'))).toBeTruthy();
  });
});