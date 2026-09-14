class LoginRequest {
  const LoginRequest({required this.email, required this.password});

  final String email;
  final String password;

  Map<String, dynamic> toJson() => {'correo': email, 'password': password};
}

class AuthenticatedUser {
  const AuthenticatedUser({
    required this.userId,
    required this.firstName,
    required this.lastName,
    required this.email,
    required this.role,
  });

  final int userId;
  final String firstName;
  final String lastName;
  final String email;
  final String role;

  String get fullName => '$firstName $lastName'.trim();

  bool get isClient => role.trim().toUpperCase() == 'CLIENTE';

  factory AuthenticatedUser.fromJson(Map<String, dynamic> json) {
    final userId = json['id_usuario'];
    final firstName = json['nombre'];
    final lastName = json['apellido'];
    final email = json['correo'];
    final role = json['rol'];

    if (userId is! int ||
        firstName is! String ||
        lastName is! String ||
        email is! String ||
        role is! String ||
        firstName.trim().isEmpty ||
        lastName.trim().isEmpty ||
        email.trim().isEmpty ||
        role.trim().isEmpty) {
      throw const FormatException('Datos de usuario inválidos.');
    }

    return AuthenticatedUser(
      userId: userId,
      firstName: firstName.trim(),
      lastName: lastName.trim(),
      email: email.trim().toLowerCase(),
      role: role.trim(),
    );
  }

  Map<String, dynamic> toJson() => {
    'id_usuario': userId,
    'nombre': firstName,
    'apellido': lastName,
    'correo': email,
    'rol': role,
  };
}

class LoginResult {
  const LoginResult({
    required this.message,
    required this.accessToken,
    required this.tokenType,
    required this.expiresIn,
    required this.user,
  });

  final String message;
  final String accessToken;
  final String tokenType;
  final int expiresIn;
  final AuthenticatedUser user;

  factory LoginResult.fromJson(Map<String, dynamic> json) {
    final message = json['message'];
    final accessToken = json['access_token'];
    final tokenType = json['token_type'];
    final expiresIn = json['expires_in'];
    final rawUser = json['usuario'];

    if (json['success'] != true ||
        message is! String ||
        accessToken is! String ||
        accessToken.trim().isEmpty ||
        tokenType != 'bearer' ||
        expiresIn is! int ||
        expiresIn <= 0 ||
        rawUser is! Map<String, dynamic>) {
      throw const FormatException('Respuesta de login inválida.');
    }

    return LoginResult(
      message: message,
      accessToken: accessToken.trim(),
      tokenType: tokenType as String,
      expiresIn: expiresIn,
      user: AuthenticatedUser.fromJson(rawUser),
    );
  }
}
