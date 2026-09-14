import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import 'registration_models.dart';
import 'registration_service.dart';
import 'registration_validators.dart';
import 'widgets/auth_components.dart';

class RegisterScreen extends StatefulWidget {
  const RegisterScreen({
    super.key,
    this.registrationGateway,
    this.onLoginRequested,
  });

  final ClientRegistrationGateway? registrationGateway;
  final VoidCallback? onLoginRequested;

  @override
  State<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends State<RegisterScreen> {
  final _formKey = GlobalKey<FormState>();
  final _firstNameController = TextEditingController();
  final _lastNameController = TextEditingController();
  final _emailController = TextEditingController();
  final _phoneController = TextEditingController();
  final _passwordController = TextEditingController();
  final _confirmationController = TextEditingController();

  late final ClientRegistrationGateway _registrationGateway;
  late final bool _ownsRegistrationService;

  bool _isSubmitting = false;
  bool _showPassword = false;
  bool _showConfirmation = false;
  bool _emailTaken = false;
  String? _serverMessage;
  ClientRegistrationResult? _result;

  @override
  void initState() {
    super.initState();
    _ownsRegistrationService = widget.registrationGateway == null;
    _registrationGateway = widget.registrationGateway ?? RegistrationService();
  }

  @override
  void dispose() {
    _firstNameController.dispose();
    _lastNameController.dispose();
    _emailController.dispose();
    _phoneController.dispose();
    _passwordController.dispose();
    _confirmationController.dispose();
    if (_ownsRegistrationService &&
        _registrationGateway is RegistrationService) {
      _registrationGateway.close();
    }
    super.dispose();
  }

  Future<void> _submit() async {
    if (_isSubmitting) {
      return;
    }

    FocusManager.instance.primaryFocus?.unfocus();
    setState(() {
      _serverMessage = null;
      _emailTaken = false;
    });

    if (!(_formKey.currentState?.validate() ?? false)) {
      setState(() => _serverMessage = 'Revisa los datos ingresados.');
      return;
    }

    final phone = _phoneController.text.trim();
    final request = ClientRegistrationRequest(
      firstName: _firstNameController.text.trim(),
      lastName: _lastNameController.text.trim(),
      email: _emailController.text.trim().toLowerCase(),
      phone: phone.isEmpty ? null : phone,
      password: _passwordController.text,
      confirmPassword: _confirmationController.text,
    );

    setState(() => _isSubmitting = true);
    try {
      final result = await _registrationGateway.register(request);
      if (!mounted) {
        return;
      }
      setState(() => _result = result);
    } on RegistrationFailure catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        if (error.type == RegistrationFailureType.duplicateEmail) {
          _emailTaken = true;
        } else {
          _serverMessage = error.message;
        }
      });
      if (error.type == RegistrationFailureType.duplicateEmail) {
        _formKey.currentState?.validate();
      }
    } finally {
      if (mounted) {
        setState(() => _isSubmitting = false);
      }
    }
  }

  void _resetForm() {
    _formKey.currentState?.reset();
    _firstNameController.clear();
    _lastNameController.clear();
    _emailController.clear();
    _phoneController.clear();
    _passwordController.clear();
    _confirmationController.clear();
    setState(() {
      _result = null;
      _serverMessage = null;
      _emailTaken = false;
      _showPassword = false;
      _showConfirmation = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    final mediaQuery = MediaQuery.of(context);
    final compact = mediaQuery.size.height < 720;
    final horizontalPadding = mediaQuery.size.width < 370 ? 18.0 : 24.0;

    return Scaffold(
      resizeToAvoidBottomInset: true,
      body: SafeArea(
        child: GestureDetector(
          onTap: () => FocusManager.instance.primaryFocus?.unfocus(),
          child: CustomScrollView(
            keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
            slivers: [
              SliverToBoxAdapter(child: FashionAuthHeader(compact: compact)),
              SliverPadding(
                padding: EdgeInsets.fromLTRB(
                  horizontalPadding,
                  compact ? 26 : 34,
                  horizontalPadding,
                  mediaQuery.viewInsets.bottom + 30,
                ),
                sliver: SliverToBoxAdapter(
                  child: Center(
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 560),
                      child: AnimatedSwitcher(
                        duration: const Duration(milliseconds: 280),
                        child: _result == null
                            ? _buildForm(context)
                            : _SuccessCard(
                                key: const Key('registrationSuccess'),
                                result: _result!,
                                onLoginRequested: widget.onLoginRequested,
                                onRegisterAnother: _resetForm,
                              ),
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

  Widget _buildForm(BuildContext context) {
    return Column(
      key: const ValueKey('registrationForm'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'TU ESTILO, TU CUENTA',
          style: TextStyle(
            color: AppColors.terracotta,
            fontSize: 11,
            fontWeight: FontWeight.w800,
            letterSpacing: 2.1,
          ),
        ),
        const SizedBox(height: 10),
        Text(
          'Crea tu cuenta',
          style: Theme.of(context).textTheme.headlineMedium?.copyWith(
            color: AppColors.espresso,
            fontSize: 34,
            fontWeight: FontWeight.w700,
            letterSpacing: -1.2,
          ),
        ),
        const SizedBox(height: 9),
        const Text(
          'Únete a FashionStore y descubre prendas pensadas para tu estilo.',
          style: TextStyle(color: AppColors.muted, fontSize: 15, height: 1.5),
        ),
        const SizedBox(height: 28),
        AutofillGroup(
          child: Form(
            key: _formKey,
            autovalidateMode: AutovalidateMode.onUserInteraction,
            child: LayoutBuilder(
              builder: (context, constraints) {
                final useColumns = constraints.maxWidth >= 500;
                return Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    if (useColumns)
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Expanded(child: _buildFirstNameField()),
                          const SizedBox(width: 14),
                          Expanded(child: _buildLastNameField()),
                        ],
                      )
                    else ...[
                      _buildFirstNameField(),
                      const SizedBox(height: 16),
                      _buildLastNameField(),
                    ],
                    const SizedBox(height: 16),
                    TextFormField(
                      key: const Key('registerEmailField'),
                      controller: _emailController,
                      autofillHints: const [AutofillHints.email],
                      keyboardType: TextInputType.emailAddress,
                      textInputAction: TextInputAction.next,
                      autocorrect: false,
                      decoration: const InputDecoration(
                        labelText: 'Correo electrónico *',
                        hintText: 'andres@correo.com',
                        prefixIcon: Icon(Icons.mail_outline_rounded),
                      ),
                      forceErrorText: _emailTaken
                          ? 'Este correo ya se encuentra registrado.'
                          : null,
                      validator: RegistrationValidators.email,
                      onChanged: (_) {
                        if (_emailTaken) {
                          setState(() => _emailTaken = false);
                        }
                      },
                    ),
                    const SizedBox(height: 16),
                    TextFormField(
                      key: const Key('registerPhoneField'),
                      controller: _phoneController,
                      autofillHints: const [AutofillHints.telephoneNumber],
                      keyboardType: TextInputType.phone,
                      textInputAction: TextInputAction.next,
                      maxLength: 30,
                      decoration: const InputDecoration(
                        labelText: 'Teléfono (opcional)',
                        hintText: 'Ej. 70012345',
                        prefixIcon: Icon(Icons.phone_outlined),
                        counterText: '',
                      ),
                      validator: RegistrationValidators.phone,
                    ),
                    const SizedBox(height: 16),
                    TextFormField(
                      key: const Key('registerPasswordField'),
                      controller: _passwordController,
                      autofillHints: const [AutofillHints.newPassword],
                      obscureText: !_showPassword,
                      autocorrect: false,
                      enableSuggestions: false,
                      textInputAction: TextInputAction.next,
                      maxLength: 128,
                      decoration: InputDecoration(
                        labelText: 'Contraseña *',
                        hintText: 'Crea una contraseña segura',
                        prefixIcon: const Icon(Icons.lock_outline_rounded),
                        counterText: '',
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
                      validator: RegistrationValidators.password,
                      onChanged: (_) => setState(() {}),
                    ),
                    const SizedBox(height: 12),
                    PasswordRequirementsPanel(
                      password: _passwordController.text,
                    ),
                    const SizedBox(height: 16),
                    TextFormField(
                      key: const Key('registerConfirmationField'),
                      controller: _confirmationController,
                      autofillHints: const [AutofillHints.newPassword],
                      obscureText: !_showConfirmation,
                      autocorrect: false,
                      enableSuggestions: false,
                      textInputAction: TextInputAction.done,
                      maxLength: 128,
                      decoration: InputDecoration(
                        labelText: 'Confirmar contraseña *',
                        hintText: 'Repite tu contraseña',
                        prefixIcon: const Icon(Icons.lock_outline_rounded),
                        counterText: '',
                        suffixIcon: IconButton(
                          tooltip: _showConfirmation
                              ? 'Ocultar confirmación'
                              : 'Mostrar confirmación',
                          onPressed: () => setState(
                            () => _showConfirmation = !_showConfirmation,
                          ),
                          icon: Icon(
                            _showConfirmation
                                ? Icons.visibility_off_outlined
                                : Icons.visibility_outlined,
                          ),
                        ),
                      ),
                      validator: (value) => RegistrationValidators.confirmation(
                        value,
                        _passwordController.text,
                      ),
                      onFieldSubmitted: (_) => _submit(),
                    ),
                    if (_serverMessage != null) ...[
                      const SizedBox(height: 16),
                      AuthStatusBanner(
                        key: const Key('registrationError'),
                        message: _serverMessage!,
                      ),
                    ],
                    const SizedBox(height: 22),
                    FilledButton(
                      key: const Key('registerSubmitButton'),
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
                                      key: Key('registrationLoading'),
                                      strokeWidth: 2,
                                      color: AppColors.white,
                                    ),
                                  ),
                                  SizedBox(width: 11),
                                  Text('Creando cuenta...'),
                                ],
                              )
                            : const Text(
                                'Crear cuenta',
                                key: ValueKey('ready'),
                              ),
                      ),
                    ),
                    if (widget.onLoginRequested != null) ...[
                      const SizedBox(height: 18),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          const Flexible(
                            child: Text(
                              '¿Ya tienes cuenta?',
                              style: TextStyle(color: AppColors.muted),
                            ),
                          ),
                          TextButton(
                            key: const Key('registerLoginLink'),
                            onPressed: _isSubmitting
                                ? null
                                : widget.onLoginRequested,
                            child: const Text('Iniciar sesión'),
                          ),
                        ],
                      ),
                    ],
                  ],
                );
              },
            ),
          ),
        ),
        const SizedBox(height: 26),
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

  Widget _buildFirstNameField() => TextFormField(
    key: const Key('registerFirstNameField'),
    controller: _firstNameController,
    autofillHints: const [AutofillHints.givenName],
    textCapitalization: TextCapitalization.words,
    textInputAction: TextInputAction.next,
    maxLength: 100,
    decoration: const InputDecoration(
      labelText: 'Nombre *',
      hintText: 'Andrés',
      prefixIcon: Icon(Icons.person_outline_rounded),
      counterText: '',
    ),
    validator: (value) =>
        RegistrationValidators.requiredName(value, label: 'El nombre'),
  );

  Widget _buildLastNameField() => TextFormField(
    key: const Key('registerLastNameField'),
    controller: _lastNameController,
    autofillHints: const [AutofillHints.familyName],
    textCapitalization: TextCapitalization.words,
    textInputAction: TextInputAction.next,
    maxLength: 100,
    decoration: const InputDecoration(
      labelText: 'Apellido *',
      hintText: 'García',
      prefixIcon: Icon(Icons.person_outline_rounded),
      counterText: '',
    ),
    validator: (value) =>
        RegistrationValidators.requiredName(value, label: 'El apellido'),
  );
}

class _SuccessCard extends StatelessWidget {
  const _SuccessCard({
    super.key,
    required this.result,
    required this.onLoginRequested,
    required this.onRegisterAnother,
  });

  final ClientRegistrationResult result;
  final VoidCallback? onLoginRequested;
  final VoidCallback onRegisterAnother;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      liveRegion: true,
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.symmetric(horizontal: 26, vertical: 34),
        decoration: BoxDecoration(
          color: AppColors.white,
          border: Border.all(color: AppColors.line),
          borderRadius: BorderRadius.circular(16),
          boxShadow: const [
            BoxShadow(
              color: Color(0x142B2625),
              blurRadius: 28,
              offset: Offset(0, 10),
            ),
          ],
        ),
        child: Column(
          children: [
            Container(
              width: 58,
              height: 58,
              decoration: const BoxDecoration(
                color: AppColors.terracotta,
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
              'Cuenta creada correctamente',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: AppColors.espresso,
                fontSize: 25,
                fontWeight: FontWeight.w700,
                letterSpacing: -0.6,
              ),
            ),
            const SizedBox(height: 10),
            Text(
              '${result.client.firstName}, tu cuenta está lista. '
              'Ya puedes iniciar sesión con ${result.client.email}.',
              textAlign: TextAlign.center,
              style: const TextStyle(
                color: AppColors.muted,
                fontSize: 14,
                height: 1.55,
              ),
            ),
            const SizedBox(height: 26),
            if (onLoginRequested != null)
              FilledButton(
                onPressed: onLoginRequested,
                child: const Text('Ir a iniciar sesión'),
              )
            else
              OutlinedButton(
                onPressed: onRegisterAnother,
                style: OutlinedButton.styleFrom(
                  minimumSize: const Size.fromHeight(50),
                  foregroundColor: AppColors.espresso,
                  side: const BorderSide(color: AppColors.espresso),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(10),
                  ),
                ),
                child: const Text('Registrar otra cuenta'),
              ),
          ],
        ),
      ),
    );
  }
}
