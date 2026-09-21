import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mobile/core/services/api_service.dart';
import 'package:mobile/core/storage/token_storage.dart';
import 'package:mobile/features/returns/return_service.dart';

void main() {
  test('envía una solicitud CU24 con líneas e idempotencia', () async {
    late http.Request request;
    final service = ReturnService(
      apiService: ApiService(
        client: MockClient((value) async {
          request = value;
          return http.Response(jsonEncode({
            'success': true,
            'data': {
              'id_devolucion': 12,
              'id_venta': 31,
              'tipo': 'DEVOLUCION',
              'estado': 'SOLICITADA',
              'motivo': 'Talla incorrecta',
              'created_at': '2026-09-21T10:00:00',
              'lineas': [
                {
                  'id_detalle_venta': 4,
                  'id_variante_producto': 15,
                  'cantidad': 1,
                  'cantidad_reintegrar': 0,
                  'importe_restitucion': 120,
                },
              ],
              'reembolsos': [],
            },
          }), 201);
        }),
        tokenStorage: _TokenStorage(),
      ),
    );

    final result = await service.requestReturn(
      saleId: 31,
      reason: 'Talla incorrecta',
      lines: const [ReturnRequestLine(detailId: 4, quantity: 1)],
      idempotencyKey: 'key-24',
    );

    expect(request.method, 'POST');
    expect(request.url.path, '/api/client/purchases/31/returns');
    expect(request.headers['idempotency-key'], 'key-24');
    expect(jsonDecode(request.body), {
      'motivo': 'Talla incorrecta',
      'lineas': [
        {'id_detalle_venta': 4, 'cantidad': 1},
      ],
    });
    expect(result.state, 'SOLICITADA');
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
