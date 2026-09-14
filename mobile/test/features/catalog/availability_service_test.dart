import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mobile/core/services/api_service.dart';
import 'package:mobile/core/storage/token_storage.dart';
import 'package:mobile/features/catalog/availability_service.dart';

void main() {
  test('consulta la variante exacta y transforma varias sucursales', () async {
    late http.Request captured;
    final service = _service(
      MockClient((request) async {
        captured = request;
        return http.Response(jsonEncode(_response), 200);
      }),
      token: 'jwt-no-necesario',
    );

    final result = await service.loadVariantAvailability(
      productId: 10,
      variantId: 90,
    );

    expect(captured.method, 'GET');
    expect(captured.url.path, '/api/catalog/products/10/availability');
    expect(captured.url.queryParameters, {'id_variante_producto': '90'});
    expect(captured.headers.containsKey('authorization'), isFalse);
    expect(result.productName, 'Chaqueta urbana');
    expect(result.branches, hasLength(2));
    expect(result.branches.first.branchName, 'Sucursal Centro');
    expect(result.branches.first.availableStock, 6);
  });

  test(
    'mapea variante inválida, sin conexión y respuesta incorrecta',
    () async {
      final invalidVariant = _service(
        MockClient(
          (_) async => http.Response(jsonEncode({'detail': 'x'}), 400),
        ),
      );
      final disconnected = _service(
        MockClient((_) async => throw http.ClientException('sin red')),
      );
      final invalidResponse = _service(
        MockClient(
          (_) async => http.Response(jsonEncode({'success': true}), 200),
        ),
      );

      for (final scenario in [
        (invalidVariant, AvailabilityFailureType.invalidVariant),
        (disconnected, AvailabilityFailureType.connection),
        (invalidResponse, AvailabilityFailureType.invalidResponse),
      ]) {
        await expectLater(
          scenario.$1.loadVariantAvailability(productId: 10, variantId: 90),
          throwsA(
            isA<AvailabilityFailure>().having(
              (error) => error.type,
              'type',
              scenario.$2,
            ),
          ),
        );
      }
    },
  );
}

CatalogAvailabilityService _service(http.Client client, {String? token}) =>
    CatalogAvailabilityService(
      apiService: ApiService(
        client: client,
        tokenStorage: _TokenStorage(token),
      ),
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

const _variant = {
  'id_variante_producto': 90,
  'sku': 'CHA-NEG-M',
  'talla': {'id_talla': 2, 'nombre': 'M'},
  'color': {'id_color': 4, 'nombre': 'Negro', 'codigo_hex': '#111111'},
  'estado': true,
};

const _response = {
  'success': true,
  'data': {
    'producto': {
      'id_producto': 10,
      'nombre': 'Chaqueta urbana',
      'estado': true,
    },
    'disponibilidad': [
      {
        'variante': _variant,
        'id_sucursal': 1,
        'nombre_sucursal': 'Sucursal Centro',
        'direccion': 'Av. Principal 100',
        'hora_apertura': '09:00:00',
        'hora_cierre': '18:00:00',
        'id_ciudad': 2,
        'nombre_ciudad': 'La Paz',
        'stock_actual': 10,
        'stock_reservado': 4,
        'stock_disponible': 6,
      },
      {
        'variante': _variant,
        'id_sucursal': 3,
        'nombre_sucursal': 'Sucursal Norte',
        'direccion': 'Calle Norte 20',
        'hora_apertura': null,
        'hora_cierre': null,
        'id_ciudad': 4,
        'nombre_ciudad': 'El Alto',
        'stock_actual': 2,
        'stock_reservado': 2,
        'stock_disponible': 0,
      },
    ],
  },
  'message': 'Disponibilidad consultada correctamente',
};
