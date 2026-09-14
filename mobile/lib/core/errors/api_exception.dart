class ApiException implements Exception {
  const ApiException(
    this.message, {
    this.statusCode,
    this.responseBody,
    this.uri,
  });

  final String message;
  final int? statusCode;
  final Object? responseBody;
  final Uri? uri;

  @override
  String toString() {
    final status = statusCode == null ? '' : ' ($statusCode)';
    return 'ApiException$status: $message';
  }
}

class ApiTimeoutException extends ApiException {
  const ApiTimeoutException({required Uri uri})
    : super('La solicitud excedió el tiempo de espera.', uri: uri);
}

class ApiNetworkException extends ApiException {
  const ApiNetworkException({required Uri uri, Object? cause})
    : super(
        'No fue posible conectar con el servidor.',
        responseBody: cause,
        uri: uri,
      );
}

class ApiInvalidResponseException extends ApiException {
  const ApiInvalidResponseException({required Uri uri, super.responseBody})
    : super(
        'El servidor devolvió una respuesta que no es JSON válido.',
        uri: uri,
      );
}
