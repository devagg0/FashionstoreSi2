import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mobile/core/services/api_service.dart';
import 'package:mobile/core/storage/token_storage.dart';
import 'package:mobile/features/payment/payment_models.dart';
import 'package:mobile/features/payment/payment_service.dart';

void main() {
  test('gestiona el intento Stripe y sincroniza el pago', () async {
    final requests = <http.Request>[];
    final service = PaymentService(
      apiService: ApiService(
        client: MockClient((request) async {
          requests.add(request);
          if (request.method == 'POST' &&
              request.url.path == '/api/sales/31/payments') {
            expect(request.headers['idempotency-key'], 'key-31');
            expect(jsonDecode(request.body), {'medio': 'TARJETA'});
            return http.Response(jsonEncode(_paymentResponse), 200);
          }
          if (request.method == 'POST' &&
              request.url.path ==
                  '/api/payments/9/stripe/checkout-session') {
            return http.Response(jsonEncode(_checkoutResponse), 200);
          }
          if (request.method == 'POST' &&
              request.url.path == '/api/payments/9/stripe/sync') {
            return http.Response(
              jsonEncode({
                'success': true,
                'data': {
                  ..._paymentResponse['data'] as Map<String, dynamic>,
                  'estado': 'APROBADO',
                  'estado_venta': 'COMPLETADA',
                },
              }),
              200,
            );
          }
          throw StateError('Ruta no esperada: ${request.method} ${request.url.path}');
        }),
        tokenStorage: _TokenStorage(),
      ),
    );

    final payment = await service.startPayment(
      saleId: 31,
      idempotencyKey: 'key-31',
    );
    final checkout = await service.createCheckoutSession(payment.paymentId);
    final synced = await service.syncStripe(payment.paymentId);

    expect(payment.state, 'PENDIENTE');
    expect(checkout.sessionId, 'cs_test_demo');
    expect(checkout.url, startsWith('https://checkout.stripe.com/'));
    expect(synced.uiState, PaymentState.approved);
    expect(requests, hasLength(3));
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

const _paymentResponse = {
  'success': true,
  'data': {
    'id_pago': 9,
    'id_venta': 31,
    'medio': 'TARJETA',
    'proveedor': 'STRIPE',
    'entorno': 'TEST',
    'estado': 'PENDIENTE',
    'monto': 320,
    'moneda': 'BOB',
    'referencia_externa': 'cs_test_demo',
    'clave_idempotencia': 'key-31',
    'fecha_aprobacion': null,
    'estado_venta': 'PENDIENTE',
  },
};

final _checkoutResponse = {
  'success': true,
  'data': {
    'payment': _paymentResponse['data'],
    'session_id': 'cs_test_demo',
    'url': 'https://checkout.stripe.com/c/pay/cs_test_demo',
  },
};
