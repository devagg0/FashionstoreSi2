import 'dart:math';

import '../../core/errors/api_exception.dart';
import '../../core/services/api_service.dart';
import 'return_models.dart';

abstract interface class ReturnGateway {
  Future<ReturnRequestData> requestReturn({
    required int saleId,
    required String reason,
    required List<ReturnRequestLine> lines,
    required String idempotencyKey,
  });

  Future<ReturnRequestData> loadReturn(int returnId);
}

class ReturnRequestLine {
  const ReturnRequestLine({required this.detailId, required this.quantity});
  final int detailId;
  final int quantity;
}

class ReturnService implements ReturnGateway {
  ReturnService({ApiService? apiService})
    : _apiService = apiService ?? ApiService(),
      _ownsApiService = apiService == null;

  final ApiService _apiService;
  final bool _ownsApiService;
  static const endpoint = '/api/client/purchases';

  @override
  Future<ReturnRequestData> requestReturn({
    required int saleId,
    required String reason,
    required List<ReturnRequestLine> lines,
    required String idempotencyKey,
  }) async {
    try {
      final response = await _apiService.post(
        '$endpoint/$saleId/returns',
        {
          'motivo': reason,
          'lineas': lines
              .map((line) => {
                    'id_detalle_venta': line.detailId,
                    'cantidad': line.quantity,
                  })
              .toList(growable: false),
        },
        headers: {'Idempotency-Key': idempotencyKey},
      );
      return _parse(response);
    } catch (error) {
      throw _mapFailure(error);
    }
  }

  @override
  Future<ReturnRequestData> loadReturn(int returnId) async {
    try {
      return _parse(await _apiService.get('/api/client/returns/$returnId'));
    } catch (error) {
      throw _mapFailure(error);
    }
  }

  ReturnRequestData _parse(dynamic response) {
    if (response is! Map<String, dynamic> || response['success'] != true) {
      throw const FormatException('Respuesta de devolución inválida.');
    }
    final data = response['data'];
    if (data is! Map<String, dynamic>) {
      throw const FormatException('Datos de devolución ausentes.');
    }
    return ReturnRequestData.fromJson(data);
  }

  ReturnFailure _mapFailure(Object error) {
    if (error is ReturnFailure) return error;
    if (error is ApiTimeoutException) {
      return const ReturnFailure(ReturnFailureType.timeout, 'La solicitud tardó demasiado. Inténtalo nuevamente.');
    }
    if (error is ApiNetworkException) {
      return const ReturnFailure(ReturnFailureType.connection, 'No pudimos conectar con FashionStore. Revisa tu conexión.');
    }
    if (error is ApiInvalidResponseException || error is FormatException) {
      return const ReturnFailure(ReturnFailureType.invalidResponse, 'Recibimos una respuesta inesperada de la devolución.');
    }
    if (error is ApiException) {
      final type = switch (error.statusCode) {
        401 => ReturnFailureType.unauthorized,
        403 => ReturnFailureType.forbidden,
        404 => ReturnFailureType.notFound,
        409 => ReturnFailureType.conflict,
        422 => ReturnFailureType.invalidData,
        _ => ReturnFailureType.server,
      };
      final message = error.statusCode == 409 || error.statusCode == 422
          ? error.message
          : switch (type) {
        ReturnFailureType.unauthorized => 'Tu sesión expiró. Inicia sesión nuevamente.',
        ReturnFailureType.forbidden => 'No tienes permiso para solicitar esta devolución.',
        ReturnFailureType.notFound => 'La compra o solicitud no está disponible.',
        ReturnFailureType.conflict => 'La compra ya no admite esta solicitud o ya existe una solicitud activa.',
        ReturnFailureType.invalidData => 'Revisa el motivo y las cantidades seleccionadas.',
        _ => 'No pudimos registrar la devolución. Inténtalo nuevamente.',
      };
      return ReturnFailure(type, message);
    }
    return const ReturnFailure(ReturnFailureType.server, 'No pudimos registrar la devolución. Inténtalo nuevamente.');
  }

  static String newIdempotencyKey() {
    final random = Random.secure();
    final parts = [8, 4, 4, 4, 12].map((length) => List.generate(length, (_) => random.nextInt(16).toRadixString(16)).join()).toList();
    return '${parts[0]}-${parts[1]}-4${parts[2].substring(1)}-a${parts[3].substring(1)}-${parts[4]}';
  }

  void close() {
    if (_ownsApiService) _apiService.close();
  }
}
