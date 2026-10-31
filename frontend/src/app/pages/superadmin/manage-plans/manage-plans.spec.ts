import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { environment } from '../../../../environments/environment';
import { SaasPlan } from '../../../core/services/saas-plans.service';
import { SessionService } from '../../../core/services/session.service';
import { ManagePlans } from './manage-plans';

describe('ManagePlans PK07 CU05 (Frontend)', () => {
  let httpTesting: HttpTestingController;
  let session: SessionService;

  const mockBasico: SaasPlan = {
    id_plan_saas: 1,
    codigo: 'BASICO',
    nombre: 'Plan Básico',
    descripcion: 'Para pequeñas boutiques y tiendas',
    precio: '199.00',
    moneda: 'BOB',
    periodo_meses: 1,
    estado: true,
    suscripciones_activas: 2,
    funcionalidades: [
      { id_funcionalidad_saas: 1, codigo: 'SUCURSALES', nombre: 'Límite de Sucursales', habilitada: true, limite: 2 },
      { id_funcionalidad_saas: 2, codigo: 'REPORTES_IA', nombre: 'Reportes IA', habilitada: false, limite: null },
      { id_funcionalidad_saas: 3, codigo: 'PRODUCTOS', nombre: 'Productos', habilitada: true, limite: null },
      { id_funcionalidad_saas: 4, codigo: 'VENTAS_POS', nombre: 'Ventas POS', habilitada: true, limite: null },
      { id_funcionalidad_saas: 5, codigo: 'RESERVAS', nombre: 'Reservas', habilitada: true, limite: null },
      { id_funcionalidad_saas: 6, codigo: 'OFFLINE', nombre: 'Modo Offline', habilitada: true, limite: null },
      { id_funcionalidad_saas: 7, codigo: 'REPORTES_ESTANDAR', nombre: 'Reportes Estándar', habilitada: true, limite: null },
    ],
    created_at: '2026-10-30T12:00:00Z',
    updated_at: '2026-10-30T12:00:00Z',
  };

  const mockProfesional: SaasPlan = {
    id_plan_saas: 2,
    codigo: 'PROFESIONAL',
    nombre: 'Plan Profesional',
    descripcion: 'Diseñado para cadenas comerciales en expansión',
    precio: '499.00',
    moneda: 'BOB',
    periodo_meses: 1,
    estado: true,
    suscripciones_activas: 5,
    funcionalidades: [
      { id_funcionalidad_saas: 1, codigo: 'SUCURSALES', nombre: 'Límite de Sucursales', habilitada: true, limite: 10 },
      { id_funcionalidad_saas: 2, codigo: 'REPORTES_IA', nombre: 'Reportes IA', habilitada: true, limite: null },
      { id_funcionalidad_saas: 3, codigo: 'PRODUCTOS', nombre: 'Productos', habilitada: true, limite: null },
      { id_funcionalidad_saas: 4, codigo: 'VENTAS_POS', nombre: 'Ventas POS', habilitada: true, limite: null },
      { id_funcionalidad_saas: 5, codigo: 'RESERVAS', nombre: 'Reservas', habilitada: true, limite: null },
      { id_funcionalidad_saas: 6, codigo: 'OFFLINE', nombre: 'Modo Offline', habilitada: true, limite: null },
      { id_funcionalidad_saas: 7, codigo: 'REPORTES_ESTANDAR', nombre: 'Reportes Estándar', habilitada: true, limite: null },
    ],
    created_at: '2026-10-30T12:00:00Z',
    updated_at: '2026-10-30T12:00:00Z',
  };

  beforeEach(async () => {
    localStorage.clear();
    await TestBed.configureTestingModule({
      imports: [ManagePlans],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    }).compileComponents();

    httpTesting = TestBed.inject(HttpTestingController);
    session = TestBed.inject(SessionService);
    session.saveAccessToken('superadmin-token-123');
    session.saveUser({
      id_usuario: 1,
      nombre: 'Super',
      apellido: 'Admin',
      correo: 'superadmin@fashionstore.com',
      rol: 'SUPERADMIN',
      id_empresa: null,
    });
  });

  afterEach(() => {
    httpTesting.verify();
    localStorage.clear();
  });

  function createComponent(): { fixture: ComponentFixture<ManagePlans>; comp: ManagePlans } {
    const fixture = TestBed.createComponent(ManagePlans);
    fixture.detectChanges();

    // Responder catálogo si se solicita
    const catReq = httpTesting.match(`${environment.apiUrl}/api/saas/funcionalidades`);
    if (catReq.length > 0) {
      catReq[0].flush({
        success: true,
        data: [
          { id_funcionalidad_saas: 1, codigo: 'SUCURSALES', nombre: 'Límite de Sucursales', estado: true },
          { id_funcionalidad_saas: 2, codigo: 'REPORTES_IA', nombre: 'Reportes IA', estado: true },
        ],
        total: 2,
      });
    }

    return { fixture, comp: fixture.componentInstance };
  }

  function flushPlans(plans: SaasPlan[] = [mockBasico, mockProfesional]): void {
    const req = httpTesting.expectOne((r) => r.url === `${environment.apiUrl}/api/saas/planes`);
    expect(req.request.method).toBe('GET');
    expect(req.request.headers.get('Authorization')).toBe('Bearer superadmin-token-123');
    req.flush({ success: true, data: plans, total: plans.length });
  }

  it('1. Carga y renderiza listado de planes SaaS con tarjetas profesionales y token SUPERADMIN', () => {
    const { fixture } = createComponent();
    flushPlans();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('#plans-title')?.textContent).toContain('Planes SaaS');
    expect(compiled.querySelectorAll('.plan-card').length).toBe(2);
    expect(compiled.textContent).toContain('Plan Básico');
    expect(compiled.textContent).toContain('Plan Profesional');
  });

  it('2. Destaca visualmente PROFESIONAL como recomendado y diferencia límites oficiales (2 vs 10 sucursales, IA)', () => {
    const { fixture } = createComponent();
    flushPlans();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const cards = compiled.querySelectorAll('.plan-card');

    // Tarjeta Profesional destacada
    const profCard = cards[1] as HTMLElement;
    expect(profCard.classList.contains('plan-card--recommended')).toBe(true);
    expect(profCard.querySelector('.plan-card__ribbon')?.textContent).toContain('RECOMENDADO');
    expect(profCard.textContent).toContain('Hasta 10 sucursales');
    expect(profCard.textContent).toContain('Reportes generativos con IA incluidos');

    // Tarjeta Básico
    const basicoCard = cards[0] as HTMLElement;
    expect(basicoCard.classList.contains('plan-card--recommended')).toBe(false);
    expect(basicoCard.textContent).toContain('Hasta 2 sucursales');
    expect(basicoCard.textContent).toContain('Reportes generativos con IA (no incluido)');
  });

  it('3. Aplica filtros por término de búsqueda y estado activo/inactivo', () => {
    const { fixture, comp } = createComponent();
    flushPlans();
    fixture.detectChanges();

    comp['filtersForm'].setValue({ search: 'PROFESIONAL', estado: 'true' });
    comp.applyFilters();

    const filteredReq = httpTesting.expectOne(
      (r) =>
        r.url === `${environment.apiUrl}/api/saas/planes` &&
        r.params.get('search') === 'PROFESIONAL' &&
        r.params.get('estado') === 'true',
    );
    expect(filteredReq.request.method).toBe('GET');
    filteredReq.flush({ success: true, data: [mockProfesional], total: 1 });
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelectorAll('.plan-card').length).toBe(1);
    expect(fixture.nativeElement.textContent).toContain('Plan Profesional');
  });

  it('4. Abre modal de creación y envía nuevo plan SaaS con validaciones', () => {
    const { fixture, comp } = createComponent();
    flushPlans();
    fixture.detectChanges();

    comp.openCreateModal();
    fixture.detectChanges();

    expect(comp['activeModal']()).toBe('create');
    comp['createForm'].patchValue({
      codigo: 'EMPRENDEDOR',
      nombre: 'Plan Emprendedor',
      descripcion: 'Para emprendimientos emergentes',
      precio: 99,
      periodo_meses: 1,
      limite_sucursales: 1,
      habilitar_ia: false,
    });

    comp.submitCreate();

    const createReq = httpTesting.expectOne(`${environment.apiUrl}/api/saas/planes`);
    expect(createReq.request.method).toBe('POST');
    expect(createReq.request.body.codigo).toBe('EMPRENDEDOR');
    expect(createReq.request.body.precio).toBe(99);
    expect(createReq.request.body.funcionalidades[0].limite).toBe(1);

    const nuevoPlan: SaasPlan = {
      ...mockBasico,
      id_plan_saas: 3,
      codigo: 'EMPRENDEDOR',
      nombre: 'Plan Emprendedor',
      precio: '99.00',
    };
    createReq.flush({ success: true, message: 'Plan SaaS creado correctamente', data: nuevoPlan });

    // Recarga listado
    flushPlans([mockBasico, mockProfesional, nuevoPlan]);
    fixture.detectChanges();

    expect(comp['activeModal']()).toBeNull();
    expect(comp['successMessage']()).toContain('Plan Emprendedor');
  });

  it('5. Abre modal de edición y advierte protección comercial si tiene suscripciones activas', () => {
    const { fixture, comp } = createComponent();
    flushPlans();
    fixture.detectChanges();

    // mockProfesional tiene 5 suscripciones activas
    comp.openEditModal(mockProfesional);
    fixture.detectChanges();

    expect(comp['activeModal']()).toBe('edit');
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.warning-alert')?.textContent).toContain(
      'Plan con 5 suscriptores activos',
    );

    comp['editForm'].patchValue({
      nombre: 'Plan Profesional Enterprise Plus',
    });
    comp.submitEdit();

    const updateReq = httpTesting.expectOne(`${environment.apiUrl}/api/saas/planes/2`);
    expect(updateReq.request.method).toBe('PUT');
    expect(updateReq.request.body.nombre).toBe('Plan Profesional Enterprise Plus');

    updateReq.flush({
      success: true,
      message: 'Plan SaaS actualizado',
      data: { ...mockProfesional, nombre: 'Plan Profesional Enterprise Plus' },
    });
    flushPlans();
    fixture.detectChanges();

    expect(comp['activeModal']()).toBeNull();
    expect(comp['successMessage']()).toContain('actualizado correctamente');
  });

  it('6. Configura funcionalidades y límites de sucursales en modal especializado', () => {
    const { fixture, comp } = createComponent();
    flushPlans();
    fixture.detectChanges();

    comp.openFeaturesModal(mockBasico);
    fixture.detectChanges();

    expect(comp['activeModal']()).toBe('features');
    expect(comp.featuresArray.length).toBeGreaterThan(0);

    // Ajusta límite de sucursales
    const sucursalCtrl = comp.featuresArray.controls.find((c) => c.value.codigo === 'SUCURSALES');
    expect(sucursalCtrl).toBeDefined();
    sucursalCtrl?.patchValue({ limite: 3 });

    comp.submitFeatures();

    const featReq = httpTesting.expectOne(`${environment.apiUrl}/api/saas/planes/1/funcionalidades`);
    expect(featReq.request.method).toBe('PUT');
    expect(featReq.request.body.funcionalidades).toBeDefined();

    featReq.flush({
      success: true,
      message: 'Funcionalidades configuradas',
      data: mockBasico,
    });
    flushPlans();
    fixture.detectChanges();

    expect(comp['activeModal']()).toBeNull();
  });

  it('7. Controla conflicto 409 al desactivar o eliminar un plan con clientes activos mostrando error legible', () => {
    const { fixture, comp } = createComponent();
    flushPlans();
    fixture.detectChanges();

    // Intentar desactivar plan con suscripciones
    comp.openStatusModal(mockProfesional);
    fixture.detectChanges();
    expect(comp['activeModal']()).toBe('status');

    comp.confirmToggleStatus();

    const patchReq = httpTesting.expectOne(`${environment.apiUrl}/api/saas/planes/2/estado`);
    expect(patchReq.request.method).toBe('PATCH');
    expect(patchReq.request.body.estado).toBe(false);

    patchReq.flush(
      { message: 'No se puede desactivar un plan con suscripciones activas vigentes' },
      { status: 409, statusText: 'Conflict' },
    );
    fixture.detectChanges();

    // Modal no se cierra y muestra el mensaje de conflicto devuelto
    expect(comp['activeModal']()).toBe('status');
    expect(comp['modalErrorMessage']()).toContain('No se puede desactivar un plan con suscripciones activas');
  });
});
