import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/theme/app_theme.dart';
import 'password_recovery_models.dart';
import 'password_recovery_service.dart';
import 'password_recovery_validators.dart';
import 'widgets/auth_components.dart';

enum _RecoveryStep { email, code, password, success }

class PasswordRecoveryScreen extends StatefulWidget {
  const PasswordRecoveryScreen({
    super.key,
    this.recoveryGateway,
    this.onBackToLogin,
  });

  final PasswordRecoveryGateway? recoveryGateway;
  final VoidCallback? onBackToLogin;

  @override
  State<PasswordRecoveryScreen> createState() => _PasswordRecoveryScreenState();
}

class _PasswordRecoveryScreenState extends State<PasswordRecoveryScreen> {
  final _emailFormKey = GlobalKey<FormState>();
  final _codeFormKey = GlobalKey<FormState>();
  final _passwordFormKey = GlobalKey<FormState>();
  final _emailController = TextEditingController();
  final _codeController = TextEditingController();
  final _passwordController = TextEditingController();
  final _confirmationController = TextEditingController();

  late final PasswordRecoveryGateway _gateway;
  late final bool _ownsService;

  _RecoveryStep _step = _RecoveryStep.email;
  bool _isSubmitting = false;
  bool _showPassword = false;
  bool _showConfirmation = false;
  bool _requiresNewCode = false;
  String? _email;
  String? _resetToken;
  String? _statusMessage;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _ownsService = widget.recoveryGateway == null;
    _gateway = widget.recoveryGateway ?? PasswordRecoveryService();
  }

  @override
  void dispose() {
    _emailController.dispose();
    _codeController.dispose();
    _passwordController.dispose();
    _confirmationController.dispose();
    if (_ownsService && _gateway is PasswordRecoveryService) {
      _gateway.close();
    }
    super.dispose();
  }

  void _clearError() {
    if (_errorMessage != null) {
      setState(() => _errorMessage = null);
    }
  }

  Future<void> _requestRecovery({bool resend = false}) async {
    if (_isSubmitting) {
      return;
    }
    FocusManager.instance.primaryFocus?.unfocus();

    final email = resend ? _email! : _emailController.text.trim().toLowerCase();
    if (!resend && !(_emailFormKey.currentState?.validate() ?? false)) {
      return;
    }

    setState(() {
      _isSubmitting = true;
      _errorMessage = null;
      _statusMessage = null;
    });
    try {
      final message = await _gateway.requestRecovery(
        PasswordRecoveryRequest(email: email),
      );
      if (!mounted) {
        return;
      }
      setState(() {
        _email = email;
        _codeController.clear();
        _resetToken = null;
        _requiresNewCode = false;
        _statusMessage = message;
        _step = _RecoveryStep.code;
      });
    } on PasswordRecoveryFailure catch (error) {
      if (mounted) {
        setState(() => _errorMessage = error.message);
      }
    } catch (_) {
      if (mounted) {
        setState(
          () => _errorMessage =
              'No pudimos solicitar la recuperación en este momento.',
        );
      }
    } finally {
      if (mounted) {
        setState(() => _isSubmitting = false);
      }
    }
  }

  Future<void> _verifyCode() async {
    if (_isSubmitting || !(_codeFormKey.currentState?.validate() ?? false)) {
      return;
    }
    FocusManager.instance.primaryFocus?.unfocus();
    setState(() {
      _isSubmitting = true;
      _errorMessage = null;
      _statusMessage = null;
    });
    try {
      final result = await _gateway.verifyCode(
        PasswordRecoveryVerificationRequest(
          email: _email!,
          code: _codeController.text.trim(),
        ),
      );
      if (!mounted) {
        return;
      }
      setState(() {
        _resetToken = result.resetToken;
        _statusMessage = result.message;
        _step = _RecoveryStep.password;
      });
    } on PasswordRecoveryFailure catch (error) {
      if (mounted) {
        setState(() => _errorMessage = error.message);
      }
    } catch (_) {
      if (mounted) {
        setState(() => _errorMessage = 'No pudimos verificar el código.');
      }
    } finally {
      if (mounted) {
        setState(() => _isSubmitting = false);
      }
    }
  }

  Future<void> _resetPassword() async {
    if (_isSubmitting ||
        !(_passwordFormKey.currentState?.validate() ?? false)) {
      return;
    }
    FocusManager.instance.primaryFocus?.unfocus();
    setState(() {
      _isSubmitting = true;
      _errorMessage = null;
      _statusMessage = null;
      _requiresNewCode = false;
    });
    try {
      final message = await _gateway.resetPassword(
        PasswordResetRequest(
          resetToken: _resetToken!,
          newPassword: _passwordController.text,
          confirmPassword: _confirmationController.text,
        ),
      );
      if (!mounted) {
        return;
      }
      TextInput.finishAutofillContext();
      _codeController.clear();
      _passwordController.clear();
      _confirmationController.clear();
      setState(() {
        _resetToken = null;
        _statusMessage = message;
        _step = _RecoveryStep.success;
      });
    } on PasswordRecoveryFailure catch (error) {
      if (mounted) {
        setState(() {
          _errorMessage = error.message;
          _requiresNewCode =
              error.type == PasswordRecoveryFailureType.invalidResetToken;
        });
      }
    } catch (_) {
      if (mounted) {
        setState(() => _errorMessage = 'No pudimos actualizar la contraseña.');
      }
    } finally {
      if (mounted) {
        setState(() => _isSubmitting = false);
      }
    }
  }

  void _useAnotherEmail() {
    if (_isSubmitting) {
      return;
    }
    setState(() {
      _step = _RecoveryStep.email;
      _email = null;
      _resetToken = null;
      _codeController.clear();
      _passwordController.clear();
      _confirmationController.clear();
      _statusMessage = null;
      _errorMessage = null;
      _requiresNewCode = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    final mediaQuery = MediaQuery.of(context);
    final compact = mediaQuery.size.height < 700;
    final horizontalPadding = mediaQuery.size.width < 370 ? 18.0 : 24.0;

    return Scaffold(
      resizeToAvoidBottomInset: true,
      body: SafeArea(
        child: GestureDetector(
          onTap: () => FocusManager.instance.primaryFocus?.unfocus(),
          child: CustomScrollView(
            key: const Key('passwordRecoveryScrollView'),
            keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
            slivers: [
              SliverToBoxAdapter(child: FashionAuthHeader(compact: compact)),
              SliverPadding(
                padding: EdgeInsets.fromLTRB(
                  horizontalPadding,
                  compact ? 24 : 32,
                  horizontalPadding,
                  mediaQuery.viewInsets.bottom + 28,
                ),
                sliver: SliverToBoxAdapter(
                  child: Center(
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 480),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          if (_step != _RecoveryStep.success)
                            _RecoveryProgress(step: _step.index),
                          const SizedBox(height: 20),
                          AnimatedSwitcher(
                            duration: const Duration(milliseconds: 220),
                            child: switch (_step) {
                              _RecoveryStep.email => _buildEmailStep(context),
                              _RecoveryStep.code => _buildCodeStep(context),
                              _RecoveryStep.password => _buildPasswordStep(
                                context,
                              ),
                              _RecoveryStep.success => _buildSuccessStep(),
                            },
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildEmailStep(BuildContext context) {
    return Column(
      key: const ValueKey('recoveryEmailStep'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _title(
          context,
          eyebrow: 'RECUPERA TU ACCESO',
          title: '¿Olvidaste tu contraseña?',
          description: 'Ingresa tu correo. Si está registrado, recibirás un código temporal.',
        ),
        const SizedBox(height: 26),
        Form(
          key: _emailFormKey,
          autovalidateMode: AutovalidateMode.onUserInteraction,
          child: TextFormField(
            key: const Key('recoveryEmailField'),
            controller: _emailController,
            autofillHints: const [AutofillHints.email],
            keyboardType: TextInputType.emailAddress,
            textInputAction: TextInputAction.done,
            autocorrect: false,
            decoration: const InputDecoration(
              labelText: 'Correo electrónico',
              hintText: 'cliente@correo.com',
              prefixIcon: Icon(Icons.mail_outline_rounded),
            ),
            validator: PasswordRecoveryValidators.email,
            onChanged: (_) => _clearError(),
            onFieldSubmitted: (_) => _requestRecovery(),
          ),
        ),
        _messages(),
        const SizedBox(height: 20),
        _submitButton(
          key: const Key('requestRecoveryButton'),
          readyText: 'Enviar código',
          loadingText: 'Enviando...',
          onPressed: _requestRecovery,
        ),
        _backToLoginButton(),
      ],
    );
  }

  Widget _buildCodeStep(BuildContext context) {
    return Column(
      key: const ValueKey('recoveryCodeStep'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _title(
          context,
          eyebrow: 'VERIFICA TU CORREO',
          title: 'Ingresa el código',
          description: 'Escribe el código de 6 dígitos enviado a $_email.',
        ),
        const SizedBox(height: 24),
        Form(
          key: _codeFormKey,
          autovalidateMode: AutovalidateMode.onUserInteraction,
          child: TextFormField(
            key: const Key('recoveryCodeField'),
            controller: _codeController,
            keyboardType: TextInputType.number,
            textInputAction: TextInputAction.done,
            maxLength: 6,
            inputFormatters: [FilteringTextInputFormatter.digitsOnly],
            textAlign: TextAlign.center,
            style: const TextStyle(
              color: AppColors.espresso,
              fontSize: 22,
              fontWeight: FontWeight.w700,
              letterSpacing: 8,
            ),
            decoration: const InputDecoration(
              labelText: 'Código de recuperación',
              hintText: '000000',
              counterText: '',
            ),
            validator: PasswordRecoveryValidators.code,
            onChanged: (_) => _clearError(),
            onFieldSubmitted: (_) => _verifyCode(),
          ),
        ),
        _messages(),
        const SizedBox(height: 20),
        _submitButton(
          key: const Key('verifyRecoveryCodeButton'),
          readyText: 'Verificar código',
          loadingText: 'Verificando...',
          onPressed: _verifyCode,
        ),
        const SizedBox(height: 10),
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            TextButton(
              key: const Key('resendRecoveryCodeButton'),
              onPressed: _isSubmitting
                  ? null
                  : () => _requestRecovery(resend: true),
              child: const Text('Reenviar código'),
            ),
            const Text('·', style: TextStyle(color: AppColors.muted)),
            TextButton(
              key: const Key('changeRecoveryEmailButton'),
              onPressed: _isSubmitting ? null : _useAnotherEmail,
              child: const Text('Cambiar correo'),
            ),
          ],
        ),
        _backToLoginButton(),
      ],
    );
  }

  Widget _buildPasswordStep(BuildContext context) {
    return Column(
      key: const ValueKey('recoveryPasswordStep'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _title(
          context,
          eyebrow: 'CREA UNA NUEVA CLAVE',
          title: 'Nueva contraseña',
          description:
              'Elige una contraseña segura que no compartas con nadie.',
        ),
        const SizedBox(height: 24),
        Form(
          key: _passwordFormKey,
          autovalidateMode: AutovalidateMode.onUserInteraction,
          child: Column(
            children: [
              TextFormField(
                key: const Key('recoveryPasswordField'),
                controller: _passwordController,
                autofillHints: const [AutofillHints.newPassword],
                obscureText: !_showPassword,
                autocorrect: false,
                enableSuggestions: false,
                textInputAction: TextInputAction.next,
                maxLength: 128,
                decoration: InputDecoration(
                  labelText: 'Nueva contraseña',
                  counterText: '',
                  prefixIcon: const Icon(Icons.lock_outline_rounded),
                  suffixIcon: IconButton(
                    tooltip: _showPassword
                        ? 'Ocultar nueva contraseña'
                        : 'Mostrar nueva contraseña',
                    onPressed: () =>
                        setState(() => _showPassword = !_showPassword),
                    icon: Icon(
                      _showPassword
                          ? Icons.visibility_off_outlined
                          : Icons.visibility_outlined,
                    ),
                  ),
                ),
                validator: PasswordRecoveryValidators.password,
                onChanged: (_) {
                  _clearError();
                  setState(() {});
                },
              ),
              const SizedBox(height: 12),
              PasswordRequirementsPanel(password: _passwordController.text),
              const SizedBox(height: 16),
              TextFormField(
                key: const Key('recoveryConfirmationField'),
                controller: _confirmationController,
                autofillHints: const [AutofillHints.newPassword],
                obscureText: !_showConfirmation,
                autocorrect: false,
                enableSuggestions: false,
                textInputAction: TextInputAction.done,
                maxLength: 128,
                decoration: InputDecoration(
                  labelText: 'Confirmar contraseña',
                  counterText: '',
                  prefixIcon: const Icon(Icons.lock_outline_rounded),
                  suffixIcon: IconButton(
                    tooltip: _showConfirmation
                        ? 'Ocultar confirmación'
                        : 'Mostrar confirmación',
                    onPressed: () =>
                        setState(() => _showConfirmation = !_showConfirmation),
                    icon: Icon(
                      _showConfirmation
                          ? Icons.visibility_off_outlined
                          : Icons.visibility_outlined,
                    ),
                  ),
                ),
                validator: (value) => PasswordRecoveryValidators.confirmation(
                  value,
                  _passwordController.text,
                ),
                onChanged: (_) => _clearError(),
                onFieldSubmitted: (_) => _resetPassword(),
              ),
            ],
          ),
        ),
        _messages(),
        if (_requiresNewCode) ...[
          const SizedBox(height: 10),
          Center(
            child: TextButton(
              key: const Key('restartRecoveryButton'),
              onPressed: _isSubmitting ? null : _useAnotherEmail,
              child: const Text('Solicitar un nuevo código'),
            ),
          ),
        ],
        const SizedBox(height: 20),
        _submitButton(
          key: const Key('resetPasswordButton'),
          readyText: 'Actualizar contraseña',
          loadingText: 'Actualizando...',
          onPressed: _resetPassword,
        ),
        _backToLoginButton(),
      ],
    );
  }

  Widget _buildSuccessStep() {
    return Semantics(
      key: const Key('passwordRecoverySuccess'),
      liveRegion: true,
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.symmetric(horizontal: 26, vertical: 34),
        decoration: BoxDecoration(
          color: AppColors.white,
          border: Border.all(color: AppColors.line),
          borderRadius: BorderRadius.circular(16),
        ),
        child: Column(
          children: [
            Container(
              width: 58,
              height: 58,
              decoration: const BoxDecoration(
                color: AppColors.success,
                shape: BoxShape.circle,
              ),
              child: const Icon(
                Icons.check_rounded,
                color: AppColors.white,
                size: 30,
              ),
            ),
            const SizedBox(height: 22),
            const Text(
              'Contraseña actualizada',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: AppColors.espresso,
                fontSize: 25,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 10),
            Text(
              _statusMessage ?? 'Contraseña restablecida correctamente',
              textAlign: TextAlign.center,
              style: const TextStyle(
                color: AppColors.muted,
                fontSize: 14,
                height: 1.5,
              ),
            ),
            const SizedBox(height: 26),
            FilledButton(
              key: const Key('recoveryBackToLoginButton'),
              onPressed: widget.onBackToLogin,
              child: const Text('Volver a iniciar sesión'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _title(
    BuildContext context, {
    required String eyebrow,
    required String title,
    required String description,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          eyebrow,
          style: const TextStyle(
            color: AppColors.terracotta,
            fontSize: 11,
            fontWeight: FontWeight.w800,
            letterSpacing: 2.1,
          ),
        ),
        const SizedBox(height: 10),
        Text(
          title,
          style: Theme.of(context).textTheme.headlineMedium?.copyWith(
            color: AppColors.espresso,
            fontSize: 32,
            fontWeight: FontWeight.w700,
            letterSpacing: -1,
          ),
        ),
        const SizedBox(height: 9),
        Text(
          description,
          style: const TextStyle(
            color: AppColors.muted,
            fontSize: 15,
            height: 1.5,
          ),
        ),
      ],
    );
  }

  Widget _messages() {
    return Column(
      children: [
        if (_statusMessage != null) ...[
          const SizedBox(height: 16),
          _RecoveryInfoBanner(message: _statusMessage!),
        ],
        if (_errorMessage != null) ...[
          const SizedBox(height: 16),
          AuthStatusBanner(
            key: const Key('passwordRecoveryError'),
            message: _errorMessage!,
          ),
        ],
      ],
    );
  }

  Widget _submitButton({
    required Key key,
    required String readyText,
    required String loadingText,
    required Future<void> Function() onPressed,
  }) {
    return FilledButton(
      key: key,
      onPressed: _isSubmitting ? null : onPressed,
      child: _isSubmitting
          ? Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                const SizedBox.square(
                  dimension: 18,
                  child: CircularProgressIndicator(
                    key: Key('passwordRecoveryLoading'),
                    strokeWidth: 2,
                    color: AppColors.white,
                  ),
                ),
                const SizedBox(width: 11),
                Text(loadingText),
              ],
            )
          : Text(readyText),
    );
  }

  Widget _backToLoginButton() {
    return Center(
      child: TextButton.icon(
        key: const Key('cancelPasswordRecoveryButton'),
        onPressed: _isSubmitting ? null : widget.onBackToLogin,
        icon: const Icon(Icons.arrow_back_rounded, size: 18),
        label: const Text('Volver al login'),
      ),
    );
  }
}

class _RecoveryProgress extends StatelessWidget {
  const _RecoveryProgress({required this.step});

  final int step;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: List.generate(3, (index) {
        final active = index <= step;
        return Expanded(
          child: Container(
            height: 3,
            margin: EdgeInsets.only(right: index == 2 ? 0 : 7),
            decoration: BoxDecoration(
              color: active ? AppColors.terracotta : AppColors.line,
              borderRadius: BorderRadius.circular(3),
            ),
          ),
        );
      }),
    );
  }
}

class _RecoveryInfoBanner extends StatelessWidget {
  const _RecoveryInfoBanner({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      key: const Key('passwordRecoveryInfo'),
      liveRegion: true,
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.all(13),
        decoration: BoxDecoration(
          color: const Color(0xFFF3F2E8),
          border: const Border(
            left: BorderSide(color: AppColors.success, width: 3),
          ),
          borderRadius: BorderRadius.circular(8),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Icon(
              Icons.mark_email_read_outlined,
              color: AppColors.success,
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
