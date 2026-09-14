import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mobile/core/services/api_service.dart';
import 'package:mobile/core/storage/token_storage.dart';
import 'package:mobile/features/catalog/catalog_models.dart';
import 'package:mobile/features/catalog/catalog_service.dart';

void main() {
  test(
    'envía los filtros exactos y carga el catálogo sin Authorization',
    () async {
      late http.Request captured;
      final service = _service(
        MockClient((request) async {
          captured = request;
          return http.Response(jsonEncode(_listResponse), 200);
        }),
        token: 'jwt-que-no-debe-enviarse',
      );

      final result = await service.loadProducts(
        const CatalogFilters(
          search: ' chaqueta ',
          section: CatalogSection.unisex,
          categoryId: 3,
          sizeId: 2,
          colorId: 4,
          minimumPrice: 50,
          maximumPrice: 150.5,
          onPromotion: true,
          sort: CatalogSort.precioAsc,
          page: 2,
          pageSize: 12,
        ),
      );

      expect(captured.method, 'GET');
      expect(captured.url.path, CatalogService.endpoint);
      expect(captured.url.queryParameters, {
        'search': 'chaqueta',
        'seccion': 'UNISEX',
        'id_categoria': '3',
        'id_talla': '2',
        'id_color': '4',
        'precio_min': '50',
        'precio_max': '150.5',
        'en_promocion': 'true',
        'sort': 'precio_asc',
        'page': '2',
        'page_size': '12',
      });
      expect(captured.headers.containsKey('authorization'), isFalse);
      expect(result.products.single.name, 'Chaqueta urbana');
      expect(result.products.single.finalPrice, 80);
      expect(result.pagination.totalPages, 1);
    },
  );

  test(
    'consulta el detalle real y transforma variantes y colecciones',
    () async {
      late http.Request captured;
      final service = _service(
        MockClient((request) async {
          captured = request;
          return http.Response(jsonEncode(_detailResponse), 200);
        }),
      );

      final detail = await service.loadProductDetail(10);

      expect(captured.url.path, '${CatalogService.endpoint}/10');
      expect(detail.gallery.single.url, 'https://img.example/chaqueta.jpg');
      expect(detail.variants.single.sku, 'CHA-NEG-M');
      expect(detail.collections.single.name, 'Esenciales');
    },
  );

  test('mapea errores de filtros, conexión y respuesta inválida', () async {
    final invalidFilters = _service(
      MockClient((_) async => http.Response(jsonEncode({'detail': 'x'}), 422)),
    );
    final disconnected = _service(
      MockClient((_) async => throw http.ClientException('sin red')),
    );
    final invalidResponse = _service(
      MockClient(
        (_) async => http.Response(jsonEncode({'success': true}), 200),
      ),
    );

    await expectLater(
      invalidFilters.loadProducts(const CatalogFilters()),
      throwsA(
        isA<CatalogFailure>().having(
          (error) => error.type,
          'type',
          CatalogFailureType.invalidFilters,
        ),
      ),
    );
    await expectLater(
      disconnected.loadProducts(const CatalogFilters()),
      throwsA(
        isA<CatalogFailure>().having(
          (error) => error.type,
          'type',
          CatalogFailureType.connection,
        ),
      ),
    );
    await expectLater(
      invalidResponse.loadProducts(const CatalogFilters()),
      throwsA(
        isA<CatalogFailure>().having(
          (error) => error.type,
          'type',
          CatalogFailureType.invalidResponse,
        ),
      ),
    );
  });
}

CatalogService _service(http.Client client, {String? token}) => CatalogService(
  apiService: ApiService(client: client, tokenStorage: _TokenStorage(token)),
);

class _TokenStorage implements TokenStorage {
  _TokenStorage(this.token);
  String? token;
  @override
  Future<void> deleteToken() async => token = null;
  @override
  Future<String?> getToken() async => token;
  @override
  Future<void> saveToken(String token) async => this.token = token;
}

const _promotion = {
  'id_promocion': 7,
  'nombre': 'Oferta de temporada',
  'codigo': null,
  'descripcion': null,
  'tipo_descuento': 'PORCENTAJE',
  'valor': 20,
  'porcentaje_descuento': 20,
  'monto_descuento': 20,
  'precio_resultante': 80,
  'fecha_inicio': '2026-01-01T00:00:00',
  'fecha_fin': '2026-12-31T23:59:59',
  'acumulable': false,
};

const _product = {
  'id_producto': 10,
  'nombre': 'Chaqueta urbana',
  'descripcion_corta': 'Chaqueta ligera',
  'seccion': 'UNISEX',
  'id_categoria': 3,
  'categoria': 'Chaquetas',
  'precio_base': 100,
  'precio_final': 80,
  'tiene_promocion': true,
  'promocion_destacada': _promotion,
  'porcentaje_descuento': 20,
  'monto_descuento': 20,
  'imagen_principal': null,
  'colores_disponibles': [
    {'id_color': 4, 'nombre': 'Negro', 'codigo_hex': '#111111'},
  ],
  'tallas_disponibles': [
    {'id_talla': 2, 'nombre': 'M'},
  ],
  'disponibilidad_sucursal': null,
};

const _listResponse = {
  'success': true,
  'data': [_product],
  'pagination': {'page': 1, 'page_size': 12, 'total': 1, 'total_pages': 1},
};

const _detailResponse = {
  'success': true,
  'data': {
    ..._product,
    'descripcion': 'Una prenda versátil.',
    'id_temporada': 2,
    'temporada': 'Invierno',
    'promociones_vigentes': [_promotion],
    'galeria': [
      {
        'id_imagen_producto': 8,
        'url_imagen': 'https://img.example/chaqueta.jpg',
        'es_principal': true,
      },
    ],
    'variantes': [
      {
        'id_variante_producto': 90,
        'sku': 'CHA-NEG-M',
        'talla': {'id_talla': 2, 'nombre': 'M'},
        'color': {'id_color': 4, 'nombre': 'Negro', 'codigo_hex': '#111111'},
        'disponibilidad_sucursal': null,
      },
    ],
    'tallas': [
      {'id_talla': 2, 'nombre': 'M'},
    ],
    'colores': [
      {'id_color': 4, 'nombre': 'Negro', 'codigo_hex': '#111111'},
    ],
    'colecciones': [
      {'id_coleccion': 5, 'nombre': 'Esenciales'},
    ],
  },
};
