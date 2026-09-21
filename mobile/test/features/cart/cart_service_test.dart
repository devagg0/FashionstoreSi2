import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mobile/core/services/api_service.dart';
import 'package:mobile/core/storage/token_storage.dart';
import 'package:mobile/features/cart/cart_models.dart';
import 'package:mobile/features/cart/cart_service.dart';

void main() {
  test('consulta y gestiona el carrito usando endpoints reales de CU19', () async {
    final requests = <http.Request>[];
    final cartService = _service(
      MockClient((request) async {
        requests.add(request);
        if (request.method == 'GET' && request.url.path == '/api/client/cart') {
          return http.Response(jsonEncode(_cartResponse), 200);
        }
        if (request.method == 'POST' && request.url.path == '/api/client/cart/items') {
          expect(jsonDecode(request.body), {
            'id_variante_producto': 90,
            'cantidad': 2,
          });
          return http.Response(
            jsonEncode({
              ..._cartResponse,
              'data': {
                ...Map<String, dynamic>.from(_cartResponse['data'] as Map),
                'items': [_cartItemResponse],
                'cantidad_items': 1,
                'cantidad_unidades': 2,
                'subtotal': 200,
                'descuento_total': 20,
                'total': 180,
              },
            }),
            200,
          );
        }
        if (request.method == 'PATCH' &&
            request.url.path == '/api/client/cart/items/90') {
          expect(jsonDecode(request.body), {'cantidad': 3});
          return http.Response(
            jsonEncode({
              ..._cartResponse,
              'data': {
                ...Map<String, dynamic>.from(_cartResponse['data'] as Map),
                'items': [_cartItemResponseWithQty(3)],
                'cantidad_items': 1,
                'cantidad_unidades': 3,
                'subtotal': 300,
                'descuento_total': 30,
                'total': 270,
              },
            }),
            200,
          );
        }
        if (request.method == 'DELETE' &&
            request.url.path == '/api/client/cart/items/90') {
          return http.Response(
            jsonEncode({
              ..._cartResponse,
              'data': {'id_carrito': 7, 'estado': 'ACTIVO', 'items': [], 'cantidad_items': 0, 'cantidad_unidades': 0, 'subtotal': 0, 'descuento_total': 0, 'total': 0},
            }),
            200,
          );
        }
        if (request.method == 'DELETE' && request.url.path == '/api/client/cart/items') {
          return http.Response(
            jsonEncode({
              ..._cartResponse,
              'data': {'id_carrito': 7, 'estado': 'ACTIVO', 'items': [], 'cantidad_items': 0, 'cantidad_unidades': 0, 'subtotal': 0, 'descuento_total': 0, 'total': 0},
            }),
            200,
          );
        }
        throw StateError('Ruta no esperada: ${request.method} ${request.url.path}');
      }),
    );

    final cart = await cartService.loadCart();
    expect(requests[0].headers['authorization'], 'Bearer jwt');
    expect(cart.items.single.productName, 'Chaqueta urbana');
    expect(cart.total, 180);

    final added = await cartService.addItem(90, 2);
    expect(added.items.single.quantity, 2);
    expect(added.total, 180);

    final updated = await cartService.updateItem(90, 3);
    expect(updated.items.single.quantity, 3);
    expect(updated.total, 270);

    final removed = await cartService.deleteItem(90);
    expect(removed.items, isEmpty);

    final cleared = await cartService.clearCart();
    expect(cleared.items, isEmpty);
  });

  test('mapea errores de CU19 y los convierte en CartFailure', () async {
    final scenarios = <(CartService, CartFailureType)>[
      (_errorService(401), CartFailureType.unauthorized),
      (_errorService(403), CartFailureType.forbidden),
      (_errorService(404), CartFailureType.notFound),
      (_errorService(409), CartFailureType.conflict),
      (_errorService(422), CartFailureType.invalidData),
      (
        _service(
          MockClient((_) async {
            await Future<void>.delayed(const Duration(milliseconds: 20));
            return http.Response('{}', 200);
          }),
          timeout: const Duration(milliseconds: 1),
        ),
        CartFailureType.timeout,
      ),
      (
        _service(
          MockClient((_) async => throw http.ClientException('sin red')),
        ),
        CartFailureType.connection,
      ),
    ];

    for (final scenario in scenarios) {
      await expectLater(
        scenario.$1.loadCart(),
        throwsA(
          isA<CartFailure>().having(
            (error) => error.type,
            'type',
            scenario.$2,
          ),
        ),
      );
    }
  });
}

CartService _errorService(int status) => _service(
  MockClient(
    (_) async => http.Response(
      jsonEncode({'success': false, 'message': 'Error real'}),
      status,
    ),
  ),
);

CartService _service(
  http.Client client, {
  Duration timeout = const Duration(seconds: 20),
}) => CartService(
  apiService: ApiService(
    client: client,
    tokenStorage: _TokenStorage('jwt'),
    timeout: timeout,
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

const _cartItemResponse = {
  'id_detalle_carrito': 11,
  'id_variante_producto': 90,
  'id_producto': 10,
  'nombre_producto': 'Chaqueta urbana',
  'sku': 'CHA-NEG-M',
  'talla': {'id_talla': 2, 'nombre': 'M'},
  'color': {'id_color': 4, 'nombre': 'Negro', 'codigo_hex': '#111111'},
  'imagen_principal': 'https://img.example/chaqueta.jpg',
  'cantidad': 2,
  'precio_base': 100,
  'precio_final': 90,
  'promocion': {
    'id_promocion': 7,
    'nombre': 'Oferta',
    'codigo': 'OFERTA',
    'descripcion': 'Descuento',
    'tipo_descuento': 'PORCENTAJE',
    'valor': 10,
    'porcentaje_descuento': 10,
    'monto_descuento': 10,
    'precio_resultante': 90,
    'fecha_inicio': '2026-01-01T00:00:00',
    'fecha_fin': '2026-12-31T23:59:59',
    'acumulable': false,
  },
  'subtotal_linea': 180,
  'disponibilidad_actual': 5,
  'estado_producto': true,
  'estado_variante': true,
};

Map<String, dynamic> _cartItemResponseWithQty(int quantity) => {
  ..._cartItemResponse,
  'cantidad': quantity,
  'subtotal_linea': quantity * 90,
};

const _cartResponse = {
  'success': true,
  'message': 'Carrito consultado correctamente',
  'data': {
    'id_carrito': 7,
    'estado': 'ACTIVO',
    'items': [_cartItemResponse],
    'cantidad_items': 1,
    'cantidad_unidades': 2,
    'subtotal': 200,
    'descuento_total': 20,
    'total': 180,
  },
};
