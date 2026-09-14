class ApiConfig {
  ApiConfig._();

  static const String environmentKey = 'API_URL';
  static const String emulatorDefaultUrl = 'http://10.0.2.2:8000';
  static const bool _isRelease = bool.fromEnvironment('dart.vm.product');

  /// API origin selected at compile time with `--dart-define=API_URL=...`.
  ///
  /// Debug builds default to the Android emulator host alias. Release builds
  /// are validated to require HTTPS, so forgetting the production definition
  /// cannot silently enable cleartext traffic.
  static const String baseUrl = String.fromEnvironment(
    environmentKey,
    defaultValue: emulatorDefaultUrl,
  );

  static Uri get baseUri {
    final value = baseUrl.trim();
    final uri = Uri.tryParse(value);

    if (value.isEmpty ||
        uri == null ||
        !uri.hasScheme ||
        uri.host.isEmpty ||
        (uri.scheme != 'http' && uri.scheme != 'https')) {
      throw const ApiConfigurationException(
        'API_URL debe ser una URL absoluta http:// o https:// válida.',
      );
    }

    if (uri.hasQuery || uri.hasFragment) {
      throw const ApiConfigurationException(
        'API_URL no debe contener query parameters ni fragmentos.',
      );
    }

    if (_isRelease && uri.scheme != 'https') {
      throw const ApiConfigurationException(
        'Una compilación release requiere una API_URL con HTTPS.',
      );
    }

    return uri;
  }

  static Uri uriFor(String endpoint, {Map<String, String>? queryParameters}) {
    final endpointUri = Uri.tryParse(endpoint);
    if (endpointUri == null ||
        endpointUri.hasScheme ||
        endpointUri.hasAuthority) {
      throw const ApiConfigurationException(
        'El endpoint debe ser una ruta relativa de la API.',
      );
    }

    final base = baseUri.toString().replaceFirst(RegExp(r'/+$'), '');
    final path = endpoint.replaceFirst(RegExp(r'^/+'), '');
    return Uri.parse('$base/$path').replace(queryParameters: queryParameters);
  }

  static void validate() => baseUri;
}

class ApiConfigurationException implements Exception {
  const ApiConfigurationException(this.message);

  final String message;

  @override
  String toString() => 'ApiConfigurationException: $message';
}
