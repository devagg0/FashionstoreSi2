import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../auth/login_models.dart';
import '../auth/widgets/auth_components.dart';
import 'profile_service.dart';

class ProfileScreen extends StatefulWidget {
  const ProfileScreen({
    super.key,
    this.profileGateway,
    required this.onBack,
    required this.onChangePassword,
    required this.onLogout,
    this.onSessionInvalidated,
  });

  final ProfileGateway? profileGateway;
  final VoidCallback onBack;
  final VoidCallback onChangePassword;
  final Future<void> Function() onLogout;
  final Future<void> Function(String message)? onSessionInvalidated;

  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  late final ProfileGateway _gateway;
  late final bool _ownsService;

  AuthenticatedUser? _user;
  String? _errorMessage;
  bool _isLoading = true;
  bool _isLoggingOut = false;
  bool _isLeavingInvalidSession = false;

  @override
  void initState() {
    super.initState();
    _ownsService = widget.profileGateway == null;
    _gateway = widget.profileGateway ?? ProfileService();
    _loadProfile();
  }

  @override
  void dispose() {
    if (_ownsService && _gateway is ProfileService) {
      _gateway.close();
    }
    super.dispose();
  }

  Future<void> _loadProfile() async {
    if (!_isLoading) {
      setState(() {
        _isLoading = true;
        _errorMessage = null;
      });
    }
    try {
      final user = await _gateway.loadProfile();
      if (!mounted) return;
      setState(() {
        _user = user;
        _errorMessage = null;
      });
    } on ProfileFailure catch (error) {
      if (!mounted) return;
      if (error.invalidatesSession && widget.onSessionInvalidated != null) {
        setState(() => _isLeavingInvalidSession = true);
        await widget.onSessionInvalidated!(error.message);
        return;
      }
      setState(() => _errorMessage = error.message);
    } catch (_) {
      if (mounted) {
        setState(() => _errorMessage = 'No pudimos cargar tu perfil.');
      }
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  Future<void> _logout() async {
    if (_isLoggingOut) return;
    setState(() => _isLoggingOut = true);
    try {
      await widget.onLogout();
    } finally {
      if (mounted) setState(() => _isLoggingOut = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final horizontalPadding = MediaQuery.sizeOf(context).width < 370
        ? 18.0
        : 24.0;
    return Scaffold(
      body: SafeArea(
        child: CustomScrollView(
          key: const Key('profileScrollView'),
          slivers: [
            SliverToBoxAdapter(child: _buildHeader(horizontalPadding)),
            SliverPadding(
              padding: EdgeInsets.fromLTRB(
                horizontalPadding,
                34,
                horizontalPadding,
                32,
              ),
              sliver: SliverToBoxAdapter(
                child: Center(
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 600),
                    child: AnimatedSwitcher(
                      duration: const Duration(milliseconds: 220),
                      child: _buildContent(context),
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader(double horizontalPadding) {
    return Container(
      padding: EdgeInsets.fromLTRB(
        horizontalPadding - 8,
        16,
        horizontalPadding,
        24,
      ),
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
            key: const Key('profileBackButton'),
            tooltip: 'Volver al inicio',
            onPressed: _isLoggingOut ? null : widget.onBack,
            icon: const Icon(Icons.arrow_back_rounded),
          ),
          const SizedBox(width: 6),
          const Expanded(
            child: Text(
              'MI PERFIL',
              style: TextStyle(
                color: AppColors.espresso,
                fontSize: 13,
                fontWeight: FontWeight.w800,
                letterSpacing: 2.2,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildContent(BuildContext context) {
    if (_isLoading || _isLeavingInvalidSession) {
      return const _ProfileLoading(key: ValueKey('profileLoading'));
    }
    if (_errorMessage != null) {
      return _ProfileError(
        key: const ValueKey('profileError'),
        message: _errorMessage!,
        onRetry: _loadProfile,
      );
    }
    return _buildProfile(context, _user!);
  }

  Widget _buildProfile(BuildContext context, AuthenticatedUser user) {
    return Column(
      key: const ValueKey('profileContent'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'TU CUENTA FASHIONSTORE',
          style: TextStyle(
            color: AppColors.terracotta,
            fontSize: 11,
            fontWeight: FontWeight.w800,
            letterSpacing: 2.1,
          ),
        ),
        const SizedBox(height: 10),
        Text(
          'Hola, ${user.firstName}',
          style: Theme.of(context).textTheme.headlineMedium?.copyWith(
            color: AppColors.espresso,
            fontSize: 31,
            fontWeight: FontWeight.w700,
          ),
        ),
        const SizedBox(height: 24),
        Container(
          key: const Key('profileCard'),
          width: double.infinity,
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: AppColors.white,
            border: Border.all(color: AppColors.line),
            borderRadius: BorderRadius.circular(16),
            boxShadow: const [
              BoxShadow(
                color: Color(0x102B2625),
                blurRadius: 24,
                offset: Offset(0, 8),
              ),
            ],
          ),
          child: Column(
            children: [
              _ProfileRow(label: 'Nombre', value: user.firstName),
              const Divider(color: AppColors.line, height: 25),
              _ProfileRow(label: 'Apellido', value: user.lastName),
              const Divider(color: AppColors.line, height: 25),
              _ProfileRow(label: 'Correo', value: user.email),
              const Divider(color: AppColors.line, height: 25),
              const _ProfileRow(
                label: 'Teléfono',
                value: 'No disponible',
                helper: 'La API de perfil actual no expone este dato.',
              ),
              const Divider(color: AppColors.line, height: 25),
              _ProfileRow(label: 'Rol', value: user.role.toUpperCase()),
            ],
          ),
        ),
        const SizedBox(height: 24),
        Material(
          color: AppColors.white,
          shape: RoundedRectangleBorder(
            side: const BorderSide(color: AppColors.line),
            borderRadius: BorderRadius.circular(14),
          ),
          clipBehavior: Clip.antiAlias,
          child: ListTile(
            key: const Key('changePasswordOption'),
            onTap: widget.onChangePassword,
            minVerticalPadding: 18,
            leading: const CircleAvatar(
              backgroundColor: AppColors.linen,
              child: Icon(
                Icons.lock_outline_rounded,
                color: AppColors.terracotta,
              ),
            ),
            title: const Text(
              'Cambiar contraseña',
              style: TextStyle(
                color: AppColors.espresso,
                fontWeight: FontWeight.w700,
              ),
            ),
            trailing: const Icon(
              Icons.chevron_right_rounded,
              color: AppColors.muted,
            ),
          ),
        ),
        const SizedBox(height: 16),
        OutlinedButton.icon(
          key: const Key('profileLogoutButton'),
          onPressed: _isLoggingOut ? null : _logout,
          style: OutlinedButton.styleFrom(
            minimumSize: const Size.fromHeight(52),
            foregroundColor: AppColors.error,
            side: const BorderSide(color: AppColors.error),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(10),
            ),
          ),
          icon: _isLoggingOut
              ? const SizedBox.square(
                  dimension: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Icon(Icons.logout_rounded),
          label: Text(_isLoggingOut ? 'Cerrando sesión...' : 'Cerrar sesión'),
        ),
      ],
    );
  }
}

class _ProfileRow extends StatelessWidget {
  const _ProfileRow({required this.label, required this.value, this.helper});
  final String label;
  final String value;
  final String? helper;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 82,
          child: Text(
            label,
            style: const TextStyle(
              color: AppColors.muted,
              fontSize: 13,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                value,
                style: const TextStyle(
                  color: AppColors.espresso,
                  fontSize: 14,
                  fontWeight: FontWeight.w700,
                ),
              ),
              if (helper != null) ...[
                const SizedBox(height: 3),
                Text(
                  helper!,
                  style: const TextStyle(
                    color: AppColors.muted,
                    fontSize: 11,
                    height: 1.35,
                  ),
                ),
              ],
            ],
          ),
        ),
      ],
    );
  }
}

class _ProfileLoading extends StatelessWidget {
  const _ProfileLoading({super.key});
  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: 'Cargando perfil',
      liveRegion: true,
      child: const Padding(
        padding: EdgeInsets.symmetric(vertical: 80),
        child: Center(
          child: Column(
            children: [
              CircularProgressIndicator(key: Key('profileLoadingIndicator')),
              SizedBox(height: 16),
              Text(
                'Cargando tu perfil...',
                style: TextStyle(color: AppColors.muted),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ProfileError extends StatelessWidget {
  const _ProfileError({
    super.key,
    required this.message,
    required this.onRetry,
  });
  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Column(
      key: const Key('profileErrorContent'),
      children: [
        AuthStatusBanner(message: message),
        const SizedBox(height: 18),
        FilledButton.icon(
          key: const Key('retryProfileButton'),
          onPressed: onRetry,
          icon: const Icon(Icons.refresh_rounded),
          label: const Text('Reintentar'),
        ),
      ],
    );
  }
}
