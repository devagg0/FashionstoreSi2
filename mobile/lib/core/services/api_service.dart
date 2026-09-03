import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/api_config.dart';


class ApiService {
  static Future<dynamic> get(String endpoint) async {
    final response = await http.get(
      Uri.parse('${ApiConfig.baseUrl}$endpoint'),
    );

    return _processResponse(response);
  }


  static Future<dynamic> post(
    String endpoint,
    Map<String, dynamic> data,
  ) async {
    final response = await http.post(
      Uri.parse('${ApiConfig.baseUrl}$endpoint'),
      headers: {
        'Content-Type': 'application/json',
      },
      body: jsonEncode(data),
    );

    return _processResponse(response);
  }


  static dynamic _processResponse(http.Response response) {
    if (response.statusCode >= 200 &&
        response.statusCode < 300) {
      return jsonDecode(response.body);
    }

    throw Exception(
      'Error ${response.statusCode}: ${response.body}',
    );
  }
}