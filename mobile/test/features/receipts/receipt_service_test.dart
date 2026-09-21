import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mobile/core/services/api_service.dart';
import 'package:mobile/core/storage/token_storage.dart';
import 'package:mobile/features/receipts/receipt_service.dart';

void main() {
  test('consulta el comprobante CU25 de una venta completada', () async {
    late http.Request request;
    final service = ReceiptService(
      apiService: ApiService(
        client: MockClient((value) async {
          request = value;
          return http.Response(jsonEncode({
            'success': true,
            'data': {
              'numero_venta': 'DIG-31',
              'fecha_completada': '2026-09-21T10:00:00',
              'canal': 'DIGITAL',
              'sucursal': {'nombre': 'Centro', 'direccion': 'Av. Principal'},
              'cliente': {'nombre': 'Ana', 'apellido': 'Lopez'},
              'productos': [
                {'nombre': 'Camisa', 'talla': 'M', 'color': 'Azul', 'cantidad': 1,
                 'precio_unitario': 100, 'descuento_unitario': 0, 'subtotal_linea': 100},
              ],
              'subtotal': 100, 'descuento_total': 0, 'total': 100, 'moneda': 'BOB',
              'pago': {'medio': 'TARJETA', 'estado': 'APROBADO', 'monto': 100},
            },
          }), 200);
        }),
        tokenStorage: _TokenStorage(),
      ),
    );

    final receipt = await service.loadReceipt(31);

    expect(request.method, 'GET');
    expect(request.url.path, '/api/client/purchases/31/receipt');
    expect(receipt.saleCode, 'DIG-31');
    expect(receipt.payment.state, 'APROBADO');
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
