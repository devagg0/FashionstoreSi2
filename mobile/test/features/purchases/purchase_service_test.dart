import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mobile/core/services/api_service.dart';
import 'package:mobile/core/storage/token_storage.dart';
import 'package:mobile/features/purchases/purchase_service.dart';

void main() {
  test('consulta listado y detalle de compras CU23', () async {
    final requests = <http.Request>[];
    final service = PurchaseService(
      apiService: ApiService(
        client: MockClient((request) async {
          requests.add(request);
          if (request.method == 'GET' && request.url.path == '/api/client/purchases') {
            return http.Response(jsonEncode({'success': true, 'data': {
              'items': [_summary], 'total': 1, 'limit': 12, 'offset': 0,
            }}), 200);
          }
          if (request.method == 'GET' && request.url.path == '/api/client/purchases/31') {
            return http.Response(jsonEncode({'success': true, 'data': {
              ..._summary,
              'productos': [_product],
              'pagos': [_payment],
              'devoluciones': [],
              'reembolsos': [],
            }}), 200);
          }
          throw StateError('Ruta no esperada: ${request.method} ${request.url.path}');
        }),
        tokenStorage: _TokenStorage(),
      ),
    );

    final page = await service.loadPurchases();
    final detail = await service.loadPurchaseDetail(31);

    expect(page.items.single.purchaseCode, 'DIG-31');
    expect(detail.products.single.name, 'Camisa Oxford');
    expect(detail.payments.single.state, 'APROBADO');
    expect(requests, hasLength(2));
  });
}

class _TokenStorage implements TokenStorage {
  @override
  Future<void> deleteToken() async {}

  @override
  Future<String?> getToken() async => 'jwt';

  @override
  Future<void> saveToken(String token) async {}
}

const _payment = {
  'id_pago': 9,
  'medio': 'TARJETA',
  'estado': 'APROBADO',
  'monto': 320,
  'moneda': 'BOB',
  'fecha_aprobacion': '2026-09-21T10:00:00',
};

const _product = {
  'id_detalle_venta': 1,
  'id_variante_producto': 15,
  'nombre': 'Camisa Oxford',
  'talla': 'M',
  'color': 'Azul',
  'cantidad': 2,
  'precio_unitario': 180,
  'descuento_unitario': 20,
  'subtotal_linea': 320,
};

const _summary = {
  'id_venta': 31,
  'numero_venta': 'DIG-31',
  'fecha': '2026-09-21T10:00:00',
  'fecha_completada': '2026-09-21T10:05:00',
  'canal': 'DIGITAL',
  'estado': 'COMPLETADA',
  'subtotal': 360,
  'descuento_total': 40,
  'total': 320,
  'moneda': 'BOB',
  'sucursal': {'id_sucursal': 2, 'nombre': 'Centro'},
  'pago': _payment,
};
