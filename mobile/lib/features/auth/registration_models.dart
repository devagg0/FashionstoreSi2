class ClientRegistrationRequest {
  const ClientRegistrationRequest({
    required this.firstName,
    required this.lastName,
    required this.email,
    required this.phone,
    required this.password,
    required this.confirmPassword,
  });

  final String firstName;
  final String lastName;
  final String email;
  final String? phone;
  final String password;
  final String confirmPassword;

  Map<String, dynamic> toJson() => {
    'nombre': firstName,
    'apellido': lastName,
    'correo': email,
    'telefono': phone,
    'password': password,
    'confirm_password': confirmPassword,
  };
}

class RegisteredClient {
  const RegisteredClient({
    required this.userId,
    required this.firstName,
    required this.lastName,
    required this.email,
  });

  final int userId;
  final String firstName;
  final String lastName;
  final String email;

  factory RegisteredClient.fromJson(Map<String, dynamic> json) {
    final userId = json['id_usuario'];
    final firstName = json['nombre'];
    final lastName = json['apellido'];
    final email = json['correo'];
    if (userId is! int ||
        firstName is! String ||
        lastName is! String ||
        email is! String) {
      throw const FormatException('Datos de cliente incompletos.');
    }

    return RegisteredClient(
      userId: userId,
      firstName: firstName,
      lastName: lastName,
      email: email,
    );
  }
}

class ClientRegistrationResult {
  const ClientRegistrationResult({required this.message, required this.client});

  final String message;
  final RegisteredClient client;
}
