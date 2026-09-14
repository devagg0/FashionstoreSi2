import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/theme/app_theme.dart';
import '../auth/widgets/auth_components.dart';
import 'change_password_models.dart';
import 'change_password_service.dart';
import 'change_password_validators.dart';

class ChangePasswordScreen extends StatefulWidget {
  const ChangePasswordScreen({
    super.key,
    this.changePasswordGateway,
    required this.onBackToProfile,
    this.onSessionInvalidated,
  });

  final ChangePasswordGateway? changePasswordGateway;
  final VoidCallback onBackToProfile;
  final Future<void> Function(String message)? onSessionInvalidated;

  @override
  State<ChangePasswordScreen> createState() => _ChangePasswordScreenState();
}

class _ChangePasswordScreenState extends State<ChangePasswordScreen> {
  final _formKey = GlobalKey<FormState>();
  final _currentPasswordController = TextEditingController();
  final _newPasswordController = TextEditingController();
  final _confirmationController = TextEditingController();

  late final ChangePasswordGateway _gateway;
  late final bool _ownsService;

  bool _isSubmitting = false;
  bool _showCurrentPassword = false;
  bool _showNewPassword = false;
  bool _showConfirmation = false;
  bool _currentPasswordIncorrect = false;
  String? _errorMessage;
  String? _successMessage;

  @override
  void initState() {
    super.initState();
    _ownsService = widget.changePasswordGateway == null;
    _gateway = widget.changePasswordGateway ?? ChangePasswordService();
  }

  @override
  void dispose() {
    _currentPasswordController.dispose();
    _newPasswordController.dispose();
    _confirmationController.dispose();
    if (_ownsService && _gateway is ChangePasswordService) {
      _gateway.close();
    }
    super.dispose();
  }

  Future<void> _submit() async {
    if (_isSubmitting) {
      return;
    }
    FocusManager.instance.primaryFocus?.unfocus();
    setState(() {
      _errorMessage = null;
      _currentPasswordIncorrect = false;
    });
    if (!(_formKey.currentState?.validate() ?? false)) {
      return;
    }

    setState(() => _isSubmitting = true);
    try {
      final message = await _gateway.changePassword(
        ChangePasswordRequest(
          currentPassword: _currentPasswordController.text,
          newPassword: _newPasswordController.text,
          confirmPassword: _confirmationController.text,
        ),
      );
      if (!mounted) {
        return;
      }
      TextInput.finishAutofillContext();
      _currentPasswordController.clear();
      _newPasswordController.clear();
      _confirmationController.clear();
      setState(() => _successMessage = message);
    } on ChangePasswordFailure catch (error) {
      if (!mounted) {
        return;
      }
      if (error.invalidatesSession && widget.onSessionInvalidated != null) {
        await widget.onSessionInvalidated!(error.message);
        return;
      }
      setState(() {
        _errorMessage = error.message;
        _currentPasswordIncorrect =
            error.type == ChangePasswordFailureType.incorrectCurrentPassword;
      });
      if (_currentPasswordIncorrect) {
        _formKey.currentState?.validate();
      }
    } catch (_) {
      if (mounted) {
        setState(
          () => _errorMessage =
              'No pudimos actualizar la contraseña en este momento.',
        );
      }
    } finally {
      if (mounted) {
        setState(() => _isSubmitting = false);
      }
    }
  }

  void _clearError() {
    if (_errorMessage != null || _currentPasswordIncorrect) {
      setState(() {
        _errorMessage = null;
        _currentPasswordIncorrect = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final mediaQuery = MediaQuery.of(context);
    final horizontalPadding = mediaQuery.size.width < 370 ? 18.0 : 24.0;

    return Scaffold(
      resizeToAvoidBottomInset: true,
      body: SafeArea(
        child: GestureDetector(
          onTap: () => FocusManager.instance.primaryFocus?.unfocus(),
          child: CustomScrollView(
            key: const Key('changePasswordScrollView'),
            keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
            slivers: [
              SliverToBoxAdapter(child: _buildHeader()),
              SliverPadding(
                padding: EdgeInsets.fromLTRB(
                  horizontalPadding,
                  30,
                  horizontalPadding,
                  mediaQuery.viewInsets.bottom + 30,
                ),
                sliver: SliverToBoxAdapter(
                  child: Center(
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 500),
                      child: AnimatedSwitcher(
                        duration: const Duration(milliseconds: 220),
                        child: _successMessage == null
                            ? _buildForm(context)
                            : _buildSuccess(),
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

  Widget _buildHeader() {
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 16, 24, 22),
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [AppColors.clay, AppColors.terracotta],
        ),
      ),
      child: Row(
        children: [
          IconButton(
            key: const Key('changePasswordBackButton'),
            tooltip: 'Volver a Mi perfil',
            onPressed: _isSubmitting ? null : widget.onBackToProfile,
            icon: const Icon(Icons.arrow_back_rounded),
          ),
          const SizedBox(width: 6),
          const Expanded(
            child: Text(
              'CAMBIAR CONTRASEÑA',
              style: TextStyle(
                color: AppColors.espresso,
                fontSize: 13,
                fontWeight: FontWeight.w800,
                letterSpacing: 1.8,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildForm(BuildContext context) {
    return Column(
      key: const ValueKey('changePasswordForm'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'SEGURIDAD DE TU CUENTA',
          style: TextStyle(
            color: AppColors.terracotta,
            fontSize: 11,
            fontWeight: FontWeight.w800,
            letterSpacing: 2.1,
          ),
        ),
        const SizedBox(height: 10),
        Text(
          'Crea una nueva clave',
          style: Theme.of(context).textTheme.headlineMedium?.copyWith(
            color: AppColors.espresso,
            fontSize: 31,
            fontWeight: FontWeight.w700,
          ),
        ),
        const SizedBox(height: 9),
        const Text(
          'Confirma tu contraseña actual y elige una nueva contraseña segura.',
          style: TextStyle(color: AppColors.muted, fontSize: 15, height: 1.5),
        ),
        const SizedBox(height: 26),
        AutofillGroup(
          child: Form(
            key: _formKey,
            autovalidateMode: AutovalidateMode.onUserInteraction,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                _passwordField(
                  key: const Key('currentPasswordField'),
                  controller: _currentPasswordController,
                  label: 'Contraseña actual',
                  showPassword: _showCurrentPassword,
                  tooltipPrefix: 'contraseña actual',
                  textInputAction: TextInputAction.next,
                  forceErrorText: _currentPasswordIncorrect
                      ? 'La contraseña actual es incorrecta.'
                      : null,
                  validator: ChangePasswordValidators.currentPassword,
                  onToggle: () => setState(
                    () => _showCurrentPassword = !_showCurrentPassword,
                  ),
                ),
                const SizedBox(height: 16),
                _passwordField(
                  key: const Key('newPasswordField'),
                  controller: _newPasswordController,
                  label: 'Nueva contraseña',
                  showPassword: _showNewPassword,
                  tooltipPrefix: 'nueva contraseña',
                  textInputAction: TextInputAction.next,
                  validator: (value) => ChangePasswordValidators.newPassword(
                    value,
                    _currentPasswordController.text,
                  ),
                  onToggle: () =>
                      setState(() => _showNewPassword = !_showNewPassword),
                  onChanged: (_) {
                    _clearError();
                    setState(() {});
                  },
                ),
                const SizedBox(height: 12),
                PasswordRequirementsPanel(
                  password: _newPasswordController.text,
                ),
                const SizedBox(height: 16),
                _passwordField(
                  key: const Key('newPasswordConfirmationField'),
                  controller: _confirmationController,
                  label: 'Confirmar nueva contraseña',
                  showPassword: _showConfirmation,
                  tooltipPrefix: 'confirmación',
                  textInputAction: TextInputAction.done,
                  validator: (value) => ChangePasswordValidators.confirmation(
                    value,
                    _newPasswordController.text,
                  ),
                  onToggle: () =>
                      setState(() => _showConfirmation = !_showConfirmation),
                  onFieldSubmitted: (_) => _submit(),
                ),
                if (_errorMessage != null) ...[
                  const SizedBox(height: 16),
                  AuthStatusBanner(
                    key: const Key('changePasswordError'),
                    message: _errorMessage!,
                  ),
                ],
                const SizedBox(height: 22),
                FilledButton(
                  key: const Key('changePasswordSubmitButton'),
                  onPressed: _isSubmitting ? null : _submit,
                  child: _isSubmitting
                      ? const Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            SizedBox.square(
                              dimension: 18,
                              child: CircularProgressIndicator(
                                key: Key('changePasswordLoading'),
                                strokeWidth: 2,
                                color: AppColors.white,
                              ),
                            ),
                            SizedBox(width: 11),
                            Text('Actualizando...'),
                          ],
                        )
                      : const Text('Actualizar contraseña'),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _passwordField({
    required Key key,
    required TextEditingController controller,
    required String label,
    required bool showPassword,
    required String tooltipPrefix,
    required TextInputAction textInputAction,
    required String? Function(String?) validator,
    required VoidCallback onToggle,
    String? forceErrorText,
    ValueChanged<String>? onChanged,
    ValueChanged<String>? onFieldSubmitted,
  }) {
    return TextFormField(
      key: key,
      controller: controller,
      obscureText: !showPassword,
      autocorrect: false,
      enableSuggestions: false,
      textInputAction: textInputAction,
      maxLength: 128,
      forceErrorText: forceErrorText,
      decoration: InputDecoration(
        labelText: label,
        counterText: '',
        prefixIcon: const Icon(Icons.lock_outline_rounded),
        suffixIcon: IconButton(
          tooltip: showPassword
              ? 'Ocultar $tooltipPrefix'
              : 'Mostrar $tooltipPrefix',
          onPressed: onToggle,
          icon: Icon(
            showPassword
                ? Icons.visibility_off_outlined
                : Icons.visibility_outlined,
          ),
        ),
      ),
      validator: validator,
      onChanged: onChanged ?? (_) => _clearError(),
      onFieldSubmitted: onFieldSubmitted,
    );
  }

  Widget _buildSuccess() {
    return Semantics(
      key: const Key('changePasswordSuccess'),
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
              _successMessage!,
              textAlign: TextAlign.center,
              style: const TextStyle(
                color: AppColors.muted,
                fontSize: 14,
                height: 1.5,
              ),
            ),
            const SizedBox(height: 26),
            FilledButton(
              key: const Key('changePasswordBackToProfileButton'),
              onPressed: widget.onBackToProfile,
              child: const Text('Volver a Mi perfil'),
            ),
          ],
        ),
      ),
    );
  }
}
