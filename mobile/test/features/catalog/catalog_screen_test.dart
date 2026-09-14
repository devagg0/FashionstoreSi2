import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/core/theme/app_theme.dart';
import 'package:mobile/features/catalog/catalog_models.dart';
import 'package:mobile/features/catalog/catalog_screen.dart';
import 'package:mobile/features/catalog/catalog_service.dart';

import 'catalog_test_data.dart';

void main() {
  testWidgets('entra mostrando solo secciones reales y permite cambiarlas', (
    tester,
  ) async {
    final gateway = _FakeCatalogGateway();
    await _pumpCatalog(tester, gateway);
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('catalogSection-HOMBRE')), findsOneWidget);
    expect(find.byKey(const Key('catalogSection-MUJER')), findsOneWidget);
    expect(find.byKey(const Key('catalogSection-UNISEX')), findsOneWidget);
    expect(find.byKey(const Key('catalogSectionPrompt')), findsOneWidget);
    expect(find.byKey(const Key('catalogProduct-10')), findsNothing);

    await tester.tap(find.byKey(const Key('catalogSection-HOMBRE')));
    await tester.pumpAndSettle();
    expect(gateway.listFilters.last.section, CatalogSection.hombre);
    expect(find.text('Seleccionada'), findsOneWidget);

    await tester.tap(find.byKey(const Key('catalogSection-MUJER')));
    await tester.pumpAndSettle();
    expect(gateway.listFilters.last.section, CatalogSection.mujer);
    expect(find.text('Chaqueta urbana'), findsOneWidget);
  });

  testWidgets('oculta una sección sin productos devueltos por el backend', (
    tester,
  ) async {
    final gateway = _FakeCatalogGateway(
      sectionHandler: (filters) async =>
          filters.section == CatalogSection.hombre
          ? catalogPage(products: const [])
          : catalogPage(products: [catalogProduct(section: filters.section!)]),
    );
    await _pumpCatalog(tester, gateway);
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('catalogSection-HOMBRE')), findsNothing);
    expect(find.byKey(const Key('catalogSection-MUJER')), findsOneWidget);
    expect(find.byKey(const Key('catalogSection-UNISEX')), findsOneWidget);
  });

  testWidgets('muestra skeleton y luego el listado con fallback de imagen', (
    tester,
  ) async {
    final completer = Completer<CatalogPage>();
    final gateway = _FakeCatalogGateway(listHandler: (_) => completer.future);
    await _pumpCatalog(tester, gateway);

    expect(find.byKey(const Key('catalogSectionLoading')), findsOneWidget);
    expect(find.text('Chaqueta urbana'), findsNothing);

    await tester.pumpAndSettle();
    expect(find.byKey(const Key('catalogSectionPrompt')), findsOneWidget);
    expect(find.text('Chaqueta urbana'), findsNothing);
    await tester.tap(find.byKey(const Key('catalogSection-UNISEX')));
    await tester.pump();
    expect(find.byKey(const Key('catalogLoadingSkeleton')), findsOneWidget);

    completer.complete(catalogPage());
    await tester.pumpAndSettle();

    expect(find.text('Chaqueta urbana'), findsOneWidget);
    expect(find.text('Bs 100.00'), findsOneWidget);
    expect(find.text('Bs 80.00'), findsOneWidget);
    expect(find.byKey(const Key('catalogImageFallback')), findsOneWidget);
  });

  testWidgets('envía búsqueda y filtros seleccionados', (tester) async {
    final gateway = _FakeCatalogGateway();
    await _pumpCatalog(tester, gateway);
    await _selectSection(tester, CatalogSection.mujer);

    await tester.enterText(
      find.byKey(const Key('catalogSearchField')),
      'chaqueta',
    );
    await tester.tap(find.byKey(const Key('toggleCatalogFiltersButton')));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byKey(const Key('catalogPromotionFilter')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('catalogPromotionFilter')));
    await tester.enterText(
      find.byKey(const Key('catalogMinimumPriceFilter')),
      '50',
    );
    await tester.enterText(
      find.byKey(const Key('catalogMaximumPriceFilter')),
      '150.5',
    );
    await tester.ensureVisible(
      find.byKey(const Key('applyCatalogFiltersButton')),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('applyCatalogFiltersButton')));
    await tester.pumpAndSettle();

    final filters = gateway.listFilters.last;
    expect(filters.search, 'chaqueta');
    expect(filters.section, CatalogSection.mujer);
    expect(filters.onPromotion, isTrue);
    expect(filters.minimumPrice, 50);
    expect(filters.maximumPrice, 150.5);
    expect(filters.page, 1);
  });

  testWidgets('valida rango de precio antes de llamar al backend', (
    tester,
  ) async {
    final gateway = _FakeCatalogGateway();
    await _pumpCatalog(tester, gateway);
    await _selectSection(tester, CatalogSection.hombre);
    await tester.tap(find.byKey(const Key('toggleCatalogFiltersButton')));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const Key('catalogMinimumPriceFilter')),
      '200',
    );
    await tester.enterText(
      find.byKey(const Key('catalogMaximumPriceFilter')),
      '100',
    );
    await tester.ensureVisible(
      find.byKey(const Key('applyCatalogFiltersButton')),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('applyCatalogFiltersButton')));
    await tester.pump();

    expect(find.textContaining('no puede ser mayor'), findsOneWidget);
    expect(gateway.listFilters, hasLength(1));
  });

  testWidgets('muestra error, permite reintentar y contempla lista vacía', (
    tester,
  ) async {
    var fail = true;
    final gateway = _FakeCatalogGateway(
      listHandler: (_) async {
        if (fail) {
          throw const CatalogFailure(
            CatalogFailureType.connection,
            'No pudimos conectar con FashionStore. Revisa tu conexión.',
          );
        }
        return catalogPage(products: const []);
      },
    );
    await _pumpCatalog(tester, gateway);
    await _selectSection(tester, CatalogSection.unisex);

    expect(find.textContaining('Revisa tu conexión'), findsOneWidget);
    fail = false;
    final retry = find.byKey(const Key('retryCatalogButton'));
    await tester.ensureVisible(retry);
    await tester.pumpAndSettle();
    await tester.tap(retry);
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('emptyCatalogState')), findsOneWidget);
    expect(gateway.listFilters, hasLength(2));
  });

  testWidgets('carga progresivamente la página siguiente del contrato', (
    tester,
  ) async {
    final gateway = _FakeCatalogGateway(
      listHandler: (filters) async => CatalogPage(
        products: filters.page == 1 ? [catalogProduct()] : const [],
        pagination: CatalogPagination(
          page: filters.page,
          pageSize: 12,
          total: 2,
          totalPages: 2,
        ),
      ),
    );
    await _pumpCatalog(tester, gateway);
    await _selectSection(tester, CatalogSection.unisex);

    await tester.drag(
      find.byKey(const Key('catalogScrollView')),
      const Offset(0, -700),
    );
    await tester.pumpAndSettle();
    final more = find.byKey(const Key('loadMoreCatalogButton'));
    await tester.tap(more);
    await tester.pumpAndSettle();

    expect(gateway.listFilters.map((item) => item.page), [1, 2]);
    expect(find.text('Chaqueta urbana'), findsOneWidget);
  });

  testWidgets('navega del listado al detalle real de la prenda', (
    tester,
  ) async {
    final gateway = _FakeCatalogGateway();
    await _pumpCatalog(tester, gateway);
    await _selectSection(tester, CatalogSection.unisex);

    final product = find.byKey(const Key('catalogProduct-10'));
    await tester.ensureVisible(product);
    await tester.pumpAndSettle();
    await tester.tap(product);
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('productDetailName')), findsOneWidget);
    expect(
      find.text('Una prenda versátil para todos los días.'),
      findsOneWidget,
    );
    expect(find.text('CHA-NEG-M'), findsOneWidget);
    expect(find.text('Esenciales'), findsOneWidget);
    expect(gateway.detailIds, [10]);
  });

  for (final size in const [Size(320, 568), Size(390, 844), Size(600, 960)]) {
    testWidgets('catálogo no desborda en ${size.width.toInt()} px', (
      tester,
    ) async {
      tester.view.physicalSize = size;
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await _pumpCatalog(tester, _FakeCatalogGateway());
      await tester.pumpAndSettle();
      await tester.drag(
        find.byKey(const Key('catalogScrollView')),
        const Offset(0, -350),
      );
      await tester.pump();
      expect(tester.takeException(), isNull);
    });
  }
}

Future<void> _pumpCatalog(WidgetTester tester, CatalogGateway gateway) =>
    tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        home: CatalogScreen(catalogGateway: gateway, onBack: () {}),
      ),
    );

Future<void> _selectSection(WidgetTester tester, CatalogSection section) async {
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(Key('catalogSection-${section.apiValue}')));
  await tester.pumpAndSettle();
}

class _FakeCatalogGateway implements CatalogGateway {
  _FakeCatalogGateway({this.listHandler, this.sectionHandler});
  final Future<CatalogPage> Function(CatalogFilters filters)? listHandler;
  final Future<CatalogPage> Function(CatalogFilters filters)? sectionHandler;
  final List<CatalogFilters> filters = [];
  final List<int> detailIds = [];
  List<CatalogFilters> get listFilters => filters
      .where((filters) => filters.pageSize == 12)
      .toList(growable: false);

  @override
  Future<CatalogPage> loadProducts(CatalogFilters filters) {
    this.filters.add(filters);
    if (filters.pageSize == 1) {
      return sectionHandler?.call(filters) ??
          Future.value(
            catalogPage(products: [catalogProduct(section: filters.section!)]),
          );
    }
    return listHandler?.call(filters) ??
        Future.value(
          catalogPage(products: [catalogProduct(section: filters.section!)]),
        );
  }

  @override
  Future<CatalogProductDetail> loadProductDetail(int productId) {
    detailIds.add(productId);
    return Future.value(catalogDetail());
  }
}
