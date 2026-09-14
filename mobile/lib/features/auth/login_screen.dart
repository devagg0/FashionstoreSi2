import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/theme/app_theme.dart';
import 'login_models.dart';
import 'login_service.dart';
import 'login_validators.dart';
import 'widgets/auth_components.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({
    super.key,
    this.loginGateway,
    this.onLoginSuccess,
    this.onCreateAccount,
    this.onForgotPassword,
  });

  final ClientLoginGateway? loginGateway;
  final ValueChanged<AuthenticatedUser>? onLoginSuccess;
  final VoidCallback? onCreateAccount;
  final VoidCallback? onForgotPassword;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();

  late final ClientLoginGateway _loginGateway;
  late final bool _ownsLoginService;

  bool _showPassword = false;
  bool _isSubmitting = false;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _ownsLoginService = widget.loginGateway == null;
    _loginGateway = widget.loginGateway ?? LoginService();
  }

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    if (_ownsLoginService && _loginGateway is LoginService) {
      _loginGateway.close();
    }
    super.dispose();
  }

  Future<void> _submit() async {
    if (_isSubmitting) {
      return;
    }

    FocusManager.instance.primaryFocus?.unfocus();
    setState(() => _errorMessage = null);
    if (!(_formKey.currentState?.validate() ?? false)) {
      return;
    }

    final request = LoginRequest(
      email: _emailController.text.trim().toLowerCase(),
      password: _passwordController.text,
    );

    setState(() => _isSubmitting = true);
    try {
      final user = await _loginGateway.login(request);
      if (!mounted) {
        return;
      }
      TextInput.finishAutofillContext();
      widget.onLoginSuccess?.call(user);
    } on LoginFailure catch (error) {
      if (mounted) {
        setState(() => _errorMessage = error.message);
      }
    } catch (_) {
      if (mounted) {
        setState(
          () => _errorMessage = 'No pudimos iniciar sesión en este momento. Inténtalo nuevamente.',
        );
      }
    } finally {
      if (mounted) {
        setState(() => _isSubmitting = false);
      }
    }
  }

  void _clearError() {
    if (_errorMessage != null) {
      setState(() => _errorMessage = null);
    }
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
            key: const Key('loginScrollView'),
            keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
            slivers: [
              SliverToBoxAdapter(child: FashionAuthHeader(compact: compact)),
              SliverPadding(
                padding: EdgeInsets.fromLTRB(
                  horizontalPadding,
                  compact ? 25 : 34,
                  horizontalPadding,
                  mediaQuery.viewInsets.bottom + 28,
                ),
                sliver: SliverToBoxAdapter(
                  child: Center(
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 480),
                      child: _buildForm(context),
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

  Widget _buildForm(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'BIENVENIDO DE NUEVO',
          style: TextStyle(
            color: AppColors.terracotta,
            fontSize: 11,
            fontWeight: FontWeight.w800,
            letterSpacing: 2.1,
          ),
        ),
        const SizedBox(height: 10),
        Text(
          'Inicia sesión',
          style: Theme.of(context).textTheme.headlineMedium?.copyWith(
            color: AppColors.espresso,
            fontSize: 34,
            fontWeight: FontWeight.w700,
            letterSpacing: -1.2,
          ),
        ),
        const SizedBox(height: 9),
        const Text(
          'Vuelve a tu espacio personal de FashionStore.',
          style: TextStyle(color: AppColors.muted, fontSize: 15, height: 1.5),
        ),
        const SizedBox(height: 28),
        AutofillGroup(
          child: Form(
            key: _formKey,
            autovalidateMode: AutovalidateMode.onUserInteraction,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                TextFormField(
                  key: const Key('loginEmailField'),
                  controller: _emailController,
                  autofillHints: const [AutofillHints.username],
                  keyboardType: TextInputType.emailAddress,
                  textInputAction: TextInputAction.next,
                  autocorrect: false,
                  decoration: const InputDecoration(
                    labelText: 'Correo electrónico',
                    hintText: 'cliente@correo.com',
                    prefixIcon: Icon(Icons.mail_outline_rounded),
                  ),
                  validator: LoginValidators.email,
                  onChanged: (_) => _clearError(),
                ),
                const SizedBox(height: 16),
                TextFormField(
                  key: const Key('loginPasswordField'),
                  controller: _passwordController,
                  autofillHints: const [AutofillHints.password],
                  obscureText: !_showPassword,
                  autocorrect: false,
                  enableSuggestions: false,
                  textInputAction: TextInputAction.done,
                  decoration: InputDecoration(
                    labelText: 'Contraseña',
                    hintText: 'Ingresa tu contraseña',
                    prefixIcon: const Icon(Icons.lock_outline_rounded),
                    suffixIcon: IconButton(
                      tooltip: _showPassword
                          ? 'Ocultar contraseña'
                          : 'Mostrar contraseña',
                      onPressed: () =>
                          setState(() => _showPassword = !_showPassword),
                      icon: Icon(
                        _showPassword
                            ? Icons.visibility_off_outlined
                            : Icons.visibility_outlined,
                      ),
                    ),
                  ),
                  validator: LoginValidators.password,
                  onChanged: (_) => _clearError(),
                  onFieldSubmitted: (_) => _submit(),
                ),
                Align(
                  alignment: Alignment.centerRight,
                  child: TextButton(
                    key: const Key('forgotPasswordLink'),
                    onPressed: _isSubmitting ? null : widget.onForgotPassword,
                    style: TextButton.styleFrom(
                      foregroundColor: AppColors.terracotta,
                    ),
                    child: const Text('¿Olvidaste tu contraseña?'),
                  ),
                ),
                if (_errorMessage != null) ...[
                  const SizedBox(height: 4),
                  AuthStatusBanner(
                    key: const Key('loginError'),
                    message: _errorMessage!,
                  ),
                  const SizedBox(height: 18),
                ] else
                  const SizedBox(height: 12),
                FilledButton(
                  key: const Key('loginSubmitButton'),
                  onPressed: _isSubmitting ? null : _submit,
                  child: AnimatedSwitcher(
                    duration: const Duration(milliseconds: 180),
                    child: _isSubmitting
                        ? const Row(
                            key: ValueKey('loading'),
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              SizedBox.square(
                                dimension: 18,
                                child: CircularProgressIndicator(
                                  key: Key('loginLoading'),
                                  strokeWidth: 2,
                                  color: AppColors.white,
                                ),
                              ),
                              SizedBox(width: 11),
                              Text('Ingresando...'),
                            ],
                          )
                        : const Text('Iniciar sesión', key: ValueKey('ready')),
                  ),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 24),
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Flexible(
              child: Text(
                '¿Aún no tienes cuenta?',
                style: TextStyle(color: AppColors.muted),
              ),
            ),
            TextButton(
              key: const Key('createAccountLink'),
              onPressed: _isSubmitting ? null : widget.onCreateAccount,
              child: const Text('Crear cuenta'),
            ),
          ],
        ),
        const SizedBox(height: 12),
        const Divider(color: AppColors.line),
        const SizedBox(height: 16),
        const Center(
          child: Text(
            'FashionStore · Tierra & Lino',
            style: TextStyle(
              color: AppColors.muted,
              fontSize: 11,
              letterSpacing: 0.8,
            ),
          ),
        ),
      ],
    );
  }
}
