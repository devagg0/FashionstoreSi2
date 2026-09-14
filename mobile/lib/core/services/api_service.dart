import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import '../errors/api_exception.dart';
import '../storage/secure_token_storage.dart';
import '../storage/token_storage.dart';

class ApiService {
  ApiService({
    http.Client? client,
    TokenStorage? tokenStorage,
    this.timeout = const Duration(seconds: 20),
  }) : _client = client ?? http.Client(),
       _ownsClient = client == null,
       _tokenStorage = tokenStorage ?? SecureTokenStorage();

  final http.Client _client;
  final bool _ownsClient;
  final TokenStorage _tokenStorage;
  final Duration timeout;

  Future<dynamic> get(
    String endpoint, {
    Map<String, String>? queryParameters,
    Map<String, String>? headers,
    bool includeAuth = true,
  }) => _send(
    method: 'GET',
    endpoint: endpoint,
    queryParameters: queryParameters,
    headers: headers,
    includeAuth: includeAuth,
  );

  Future<dynamic> post(
    String endpoint,
    Object? data, {
    Map<String, String>? queryParameters,
    Map<String, String>? headers,
    bool includeAuth = true,
  }) => _send(
    method: 'POST',
    endpoint: endpoint,
    queryParameters: queryParameters,
    headers: headers,
    data: data,
    includeAuth: includeAuth,
  );

  Future<dynamic> put(
    String endpoint,
    Object? data, {
    Map<String, String>? queryParameters,
    Map<String, String>? headers,
    bool includeAuth = true,
  }) => _send(
    method: 'PUT',
    endpoint: endpoint,
    queryParameters: queryParameters,
    headers: headers,
    data: data,
    includeAuth: includeAuth,
  );

  Future<dynamic> patch(
    String endpoint,
    Object? data, {
    Map<String, String>? queryParameters,
    Map<String, String>? headers,
    bool includeAuth = true,
  }) => _send(
    method: 'PATCH',
    endpoint: endpoint,
    queryParameters: queryParameters,
    headers: headers,
    data: data,
    includeAuth: includeAuth,
  );

  Future<dynamic> delete(
    String endpoint, {
    Object? data,
    Map<String, String>? queryParameters,
    Map<String, String>? headers,
    bool includeAuth = true,
  }) => _send(
    method: 'DELETE',
    endpoint: endpoint,
    queryParameters: queryParameters,
    headers: headers,
    data: data,
    includeAuth: includeAuth,
  );

  Future<dynamic> _send({
    required String method,
    required String endpoint,
    required bool includeAuth,
    Object? data,
    Map<String, String>? queryParameters,
    Map<String, String>? headers,
  }) async {
    final uri = ApiConfig.uriFor(endpoint, queryParameters: queryParameters);
    final request = http.Request(method, uri);
    request.headers.addAll(
      await _buildHeaders(headers, includeAuth: includeAuth),
    );
    if (data != null) {
      request.body = jsonEncode(data);
    }

    try {
      final streamedResponse = await _client.send(request).timeout(timeout);
      final response = await http.Response.fromStream(streamedResponse)
          .timeout(timeout);
      return _processResponse(response, uri);
    } on TimeoutException {
      throw ApiTimeoutException(uri: uri);
    } on SocketException catch (error) {
      throw ApiNetworkException(uri: uri, cause: error);
    } on http.ClientException catch (error) {
      throw ApiNetworkException(uri: uri, cause: error);
    }
  }

  Future<Map<String, String>> _buildHeaders(
    Map<String, String>? additionalHeaders, {
    required bool includeAuth,
  }) async {
    final headers = <String, String>{
      'Accept': 'application/json',
      'Content-Type': 'application/json; charset=utf-8',
      ...?additionalHeaders,
    };

    final hasAuthorization = headers.keys.any(
      (header) => header.toLowerCase() == 'authorization',
    );
    if (includeAuth && !hasAuthorization) {
      final token = await _tokenStorage.getToken();
      if (token != null && token.trim().isNotEmpty) {
        headers['Authorization'] = 'Bearer ${token.trim()}';
      }
    }

    return headers;
  }

  dynamic _processResponse(http.Response response, Uri uri) {
    final body = _decodeBody(response.body, uri: uri);
    if (response.statusCode >= 200 && response.statusCode < 300) {
      return body;
    }

    final message = switch (body) {
      {'detail': final Object detail} => detail.toString(),
      {'message': final Object message} => message.toString(),
      _ => 'La solicitud no pudo completarse.',
    };

    throw ApiException(
      message,
      statusCode: response.statusCode,
      responseBody: body,
      uri: uri,
    );
  }

  dynamic _decodeBody(String responseBody, {required Uri uri}) {
    if (responseBody.trim().isEmpty) {
      return null;
    }

    try {
      return jsonDecode(responseBody);
    } on FormatException {
      throw ApiInvalidResponseException(uri: uri, responseBody: responseBody);
    }
  }

  void close() {
    if (_ownsClient) {
      _client.close();
    }
  }
}
