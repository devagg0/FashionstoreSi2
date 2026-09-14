import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mobile/core/services/api_service.dart';
import 'package:mobile/core/storage/token_storage.dart';
import 'package:mobile/features/reservations/reservation_models.dart';
import 'package:mobile/features/reservations/reservation_service.dart';

import 'reservation_test_data.dart';

void main() {
  test('confirma múltiples prendas en un único POST autenticado', () async {
    late http.Request captured;
    final service = _service(
      MockClient((request) async {
        captured = request;
        return http.Response(
          jsonEncode({
            'success': true,
            'data': reservationJson(),
            'message': 'Reserva creada correctamente',
          }),
          201,
        );
      }),
    );
    final request = {
      'id_sucursal': 1,
      'fecha_atencion_programada': '2026-09-14T14:00:00-04:00',
      'items': [
        {'id_variante_producto': 90, 'cantidad': 2},
        {'id_variante_producto': 92, 'cantidad': 1},
      ],
    };

    final result = await service.create(request);

    expect(captured.method, 'POST');
    expect(captured.url.path, ReservationService.endpoint);
    expect(jsonDecode(captured.body), request);
    expect(captured.headers['authorization'], 'Bearer jwt');
    expect(result.code, 'RSV-20260913-ABC123');
  });

  test('lista, consulta detalle y cancela usando contratos reales', () async {
    final requests = <http.Request>[];
    final service = _service(
      MockClient((request) async {
        requests.add(request);
        if (request.method == 'GET' &&
            request.url.path == ReservationService.endpoint) {
          final summary = Map<String, dynamic>.from(reservationJson())
            ..remove('items');
          return http.Response(
            jsonEncode({
              'success': true,
              'data': [summary],
              'pagination': {
                'page': 1,
                'page_size': 10,
                'total': 1,
                'total_pages': 1,
              },
            }),
            200,
          );
        }
        return http.Response(
          jsonEncode({
            'success': true,
            'data': reservationJson(
              state: request.method == 'PATCH' ? 'CANCELADA' : 'PENDIENTE',
              cancelable: request.method != 'PATCH',
            ),
          }),
          200,
        );
      }),
    );

    final page = await service.list(state: ReservationState.pendiente);
    final detail = await service.getDetail(9);
    final cancelled = await service.cancel(9);

    expect(requests[0].url.queryParameters['estado'], 'PENDIENTE');
    expect(requests[1].url.path, '/api/client/reservations/9');
    expect(requests[2].method, 'PATCH');
    expect(requests[2].url.path, '/api/client/reservations/9/cancel');
    expect(jsonDecode(requests[2].body), <String, dynamic>{});
    expect(page.data.single.code, detail.code);
    expect(cancelled.state, ReservationState.cancelada);
    expect(cancelled.cancelable, isFalse);
  });

  test('mapea 401, 403, 409, 422, timeout y conexión', () async {
    final scenarios = <(ReservationService, ReservationFailureType)>[
      (_errorService(401), ReservationFailureType.unauthorized),
      (_errorService(403), ReservationFailureType.forbidden),
      (_errorService(409), ReservationFailureType.conflict),
      (_errorService(422), ReservationFailureType.invalidData),
      (
        _service(
          MockClient((_) async => throw http.ClientException('sin red')),
        ),
        ReservationFailureType.connection,
      ),
      (
        ReservationService(
          apiService: ApiService(
            client: MockClient((_) async {
              await Future<void>.delayed(const Duration(milliseconds: 20));
              return http.Response('{}', 200);
            }),
            tokenStorage: _TokenStorage('jwt'),
            timeout: const Duration(milliseconds: 1),
          ),
        ),
        ReservationFailureType.timeout,
      ),
    ];
    for (final scenario in scenarios) {
      await expectLater(
        scenario.$1.list(),
        throwsA(
          isA<ReservationFailure>().having(
            (error) => error.type,
            'type',
            scenario.$2,
          ),
        ),
      );
    }
  });
}

ReservationService _errorService(int status) => _service(
  MockClient(
    (_) async => http.Response(
      jsonEncode({'success': false, 'message': 'Error real'}),
      status,
    ),
  ),
);

ReservationService _service(http.Client client) => ReservationService(
  apiService: ApiService(client: client, tokenStorage: _TokenStorage('jwt')),
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
