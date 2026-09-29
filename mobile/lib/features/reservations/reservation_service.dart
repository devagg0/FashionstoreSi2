import '../../core/errors/api_exception.dart';
import '../../core/services/api_service.dart';
import 'reservation_models.dart';

abstract interface class ReservationGateway {
  Future<ReservationDetail> create(Map<String, dynamic> request);
  Future<ReservationPage> list({
    ReservationState? state,
    int page = 1,
    int pageSize = 10,
  });
  Future<ReservationDetail> getDetail(int reservationId);
  Future<ReservationDetail> cancel(int reservationId);
}

abstract interface class ReservationAvailabilityGateway {
  Future<Set<String>> occupiedTimes({
    required int variantId,
    required int branchId,
    required String date,
  });
}

enum ReservationFailureType {
  unauthorized,
  forbidden,
  notFound,
  conflict,
  invalidData,
  timeout,
  connection,
  server,
  invalidResponse,
}

class ReservationFailure implements Exception {
  const ReservationFailure(this.type, this.message);
  final ReservationFailureType type;
  final String message;
}

class ReservationService
    implements ReservationGateway, ReservationAvailabilityGateway {
  ReservationService({ApiService? apiService})
    : _apiService = apiService ?? ApiService(),
      _ownsApiService = apiService == null;

  static const endpoint = '/api/client/reservations';
  final ApiService _apiService;
  final bool _ownsApiService;

  @override
  Future<ReservationDetail> create(Map<String, dynamic> request) =>
      _detailRequest(() => _apiService.post(endpoint, request));

  @override
  Future<Set<String>> occupiedTimes({
    required int variantId,
    required int branchId,
    required String date,
  }) async {
    try {
      final response = _success(
        await _apiService.get(
          '$endpoint/availability',
          queryParameters: {
            'id_sucursal': '$branchId',
            'id_variante_producto': '$variantId',
            'fecha': date,
          },
        ),
      );
      final data = response['data'];
      if (data is! Map<String, dynamic>) {
        throw const FormatException('Disponibilidad de reservas invÃ¡lida.');
      }
      final values = data['occupied_times'];
      if (values is! List || values.any((value) => value is! String)) {
        throw const FormatException('Horarios ocupados invÃ¡lidos.');
      }
      return values.cast<String>().toSet();
    } catch (error) {
      throw _mapFailure(error);
    }
  }

  @override
  Future<ReservationPage> list({
    ReservationState? state,
    int page = 1,
    int pageSize = 10,
  }) async {
    try {
      final response = await _apiService.get(
        endpoint,
        queryParameters: {
          'page': '$page',
          'page_size': '$pageSize',
          if (state != null) 'estado': state.apiValue,
        },
      );
      final map = _success(response);
      final data = map['data'];
      final pagination = map['pagination'];
      if (data is! List || pagination is! Map<String, dynamic>) {
        throw const FormatException('Lista de reservas inválida.');
      }
      return ReservationPage(
        data: data
            .map((item) {
              if (item is! Map<String, dynamic>) {
                throw const FormatException('Reserva inválida.');
              }
              return ReservationSummary.fromJson(item);
            })
            .toList(growable: false),
        pagination: ReservationPagination.fromJson(pagination),
      );
    } catch (error) {
      throw _mapFailure(error);
    }
  }

  @override
  Future<ReservationDetail> getDetail(int reservationId) =>
      _detailRequest(() => _apiService.get('$endpoint/$reservationId'));

  @override
  Future<ReservationDetail> cancel(int reservationId) => _detailRequest(
    () => _apiService.patch('$endpoint/$reservationId/cancel', const {}),
  );

  Future<ReservationDetail> _detailRequest(
    Future<dynamic> Function() request,
  ) async {
    try {
      final response = _success(await request());
      final data = response['data'];
      if (data is! Map<String, dynamic>) {
        throw const FormatException('Detalle de reserva inválido.');
      }
      return ReservationDetail.fromJson(data);
    } catch (error) {
      throw _mapFailure(error);
    }
  }

  Map<String, dynamic> _success(dynamic response) {
    if (response is! Map<String, dynamic> || response['success'] != true) {
      throw const FormatException('Respuesta de reservas inválida.');
    }
    return response;
  }

  ReservationFailure _mapFailure(Object error) {
    if (error is ReservationFailure) return error;
    if (error is ApiTimeoutException) {
      return const ReservationFailure(
        ReservationFailureType.timeout,
        'La solicitud tardó demasiado. Inténtalo nuevamente.',
      );
    }
    if (error is ApiNetworkException) {
      return const ReservationFailure(
        ReservationFailureType.connection,
        'No pudimos conectar con FashionStore. Revisa tu conexión.',
      );
    }
    if (error is ApiInvalidResponseException || error is FormatException) {
      return const ReservationFailure(
        ReservationFailureType.invalidResponse,
        'Recibimos una respuesta inesperada de reservas.',
      );
    }
    if (error is ApiException) {
      final type = switch (error.statusCode) {
        401 => ReservationFailureType.unauthorized,
        403 => ReservationFailureType.forbidden,
        404 => ReservationFailureType.notFound,
        409 => ReservationFailureType.conflict,
        422 => ReservationFailureType.invalidData,
        _ => ReservationFailureType.server,
      };
      final message = switch (type) {
        ReservationFailureType.unauthorized =>
          'Tu sesión expiró. Inicia sesión nuevamente.',
        ReservationFailureType.forbidden =>
          'Tu cuenta no puede gestionar reservas de cliente.',
        ReservationFailureType.server =>
          'No pudimos procesar tus reservas. Inténtalo nuevamente.',
        _ => error.message,
      };
      return ReservationFailure(type, message);
    }
    return const ReservationFailure(
      ReservationFailureType.server,
      'No pudimos procesar tus reservas. Inténtalo nuevamente.',
    );
  }

  void close() {
    if (_ownsApiService) _apiService.close();
  }
}
