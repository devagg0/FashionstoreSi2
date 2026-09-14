class PasswordRecoveryRequest {
  const PasswordRecoveryRequest({required this.email});

  final String email;

  Map<String, dynamic> toJson() => {'correo': email};
}

class PasswordRecoveryVerificationRequest {
  const PasswordRecoveryVerificationRequest({
    required this.email,
    required this.code,
  });

  final String email;
  final String code;

  Map<String, dynamic> toJson() => {'correo': email, 'codigo': code};
}

class PasswordResetRequest {
  const PasswordResetRequest({
    required this.resetToken,
    required this.newPassword,
    required this.confirmPassword,
  });

  final String resetToken;
  final String newPassword;
  final String confirmPassword;

  Map<String, dynamic> toJson() => {
    'reset_token': resetToken,
    'new_password': newPassword,
    'confirm_password': confirmPassword,
  };
}

class PasswordRecoveryVerificationResult {
  const PasswordRecoveryVerificationResult({
    required this.message,
    required this.resetToken,
  });

  final String message;
  final String resetToken;
}
