import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';
import '../registration_validators.dart';

class FashionAuthHeader extends StatelessWidget {
  const FashionAuthHeader({super.key, required this.compact});

  final bool compact;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: compact ? 150 : 190,
      child: DecoratedBox(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [AppColors.clay, AppColors.terracotta],
          ),
        ),
        child: Stack(
          clipBehavior: Clip.hardEdge,
          children: [
            Positioned(
              right: -55,
              top: -72,
              child: Container(
                width: 220,
                height: 220,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  border: Border.all(color: const Color(0x552B2625)),
                ),
              ),
            ),
            Positioned(
              right: -12,
              top: -30,
              child: Container(
                width: 135,
                height: 135,
                decoration: const BoxDecoration(
                  color: Color(0xCCF4EBE1),
                  shape: BoxShape.circle,
                ),
              ),
            ),
            Positioned(
              right: 27,
              top: 9,
              child: Container(
                width: 57,
                height: 57,
                decoration: const BoxDecoration(
                  color: AppColors.espresso,
                  shape: BoxShape.circle,
                ),
              ),
            ),
            Positioned(
              top: compact ? 22 : 27,
              left: 24,
              child: const Text(
                'FASHIONSTORE',
                style: TextStyle(
                  color: AppColors.espresso,
                  fontSize: 13,
                  fontWeight: FontWeight.w800,
                  letterSpacing: 2.2,
                ),
              ),
            ),
            Positioned(
              left: 24,
              right: 92,
              bottom: 22,
              child: FittedBox(
                alignment: Alignment.centerLeft,
                fit: BoxFit.scaleDown,
                child: Text(
                  'Tu estilo comienza\ncontigo.',
                  style: TextStyle(
                    color: AppColors.espresso,
                    fontSize: compact ? 25 : 30,
                    height: 1.04,
                    fontWeight: FontWeight.w700,
                    letterSpacing: -0.8,
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class AuthStatusBanner extends StatelessWidget {
  const AuthStatusBanner({super.key, required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      liveRegion: true,
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.all(13),
        decoration: BoxDecoration(
          color: const Color(0xFFFFF4EF),
          border: const Border(
            left: BorderSide(color: AppColors.error, width: 3),
          ),
          borderRadius: BorderRadius.circular(8),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Icon(
              Icons.error_outline_rounded,
              color: AppColors.error,
              size: 19,
            ),
            const SizedBox(width: 9),
            Expanded(
              child: Text(
                message,
                style: const TextStyle(
                  color: AppColors.espresso,
                  fontSize: 13,
                  height: 1.4,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class PasswordRequirementsPanel extends StatelessWidget {
  const PasswordRequirementsPanel({super.key, required this.password});

  final String password;

  @override
  Widget build(BuildContext context) {
    final requirements = <(String, bool)>[
      ('8 caracteres', RegistrationValidators.hasMinimumLength(password)),
      ('Una mayúscula', RegistrationValidators.hasUpperCase(password)),
      ('Una minúscula', RegistrationValidators.hasLowerCase(password)),
      ('Un número', RegistrationValidators.hasDigit(password)),
      (
        'Un carácter especial',
        RegistrationValidators.hasSpecialCharacter(password),
      ),
    ];

    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.white.withValues(alpha: 0.6),
        border: Border.all(color: AppColors.line),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Padding(
        padding: const EdgeInsets.all(15),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Tu contraseña debe contener:',
              style: TextStyle(
                color: AppColors.espresso,
                fontSize: 12,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 10),
            Wrap(
              spacing: 12,
              runSpacing: 8,
              children: requirements
                  .map(
                    (requirement) => SizedBox(
                      width: 145,
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(
                            requirement.$2
                                ? Icons.check_circle
                                : Icons.circle_outlined,
                            size: 14,
                            color: requirement.$2
                                ? AppColors.success
                                : AppColors.muted,
                          ),
                          const SizedBox(width: 6),
                          Flexible(
                            child: Text(
                              requirement.$1,
                              style: TextStyle(
                                color: requirement.$2
                                    ? AppColors.success
                                    : AppColors.muted,
                                fontSize: 11.5,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  )
                  .toList(),
            ),
          ],
        ),
      ),
    );
  }
}
