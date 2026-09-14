import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../auth/login_models.dart';

class ClientHomeScreen extends StatefulWidget {
  const ClientHomeScreen({
    super.key,
    required this.user,
    required this.onLogout,
    required this.onOpenProfile,
    required this.onOpenCatalog,
    required this.onOpenReservations,
  });

  final AuthenticatedUser user;
  final Future<void> Function() onLogout;
  final VoidCallback onOpenProfile;
  final VoidCallback onOpenCatalog;
  final VoidCallback onOpenReservations;

  @override
  State<ClientHomeScreen> createState() => _ClientHomeScreenState();
}

class _ClientHomeScreenState extends State<ClientHomeScreen> {
  bool _isLoggingOut = false;

  Future<void> _logout() async {
    if (_isLoggingOut) {
      return;
    }
    setState(() => _isLoggingOut = true);
    try {
      await widget.onLogout();
    } finally {
      if (mounted) {
        setState(() => _isLoggingOut = false);
      }
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
          slivers: [
            SliverToBoxAdapter(
              child: Container(
                padding: EdgeInsets.fromLTRB(
                  horizontalPadding,
                  22,
                  horizontalPadding,
                  28,
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
                    const Expanded(
                      child: Text(
                        'FASHIONSTORE',
                        style: TextStyle(
                          color: AppColors.espresso,
                          fontSize: 13,
                          fontWeight: FontWeight.w800,
                          letterSpacing: 2.2,
                        ),
                      ),
                    ),
                    IconButton.filled(
                      key: const Key('logoutButton'),
                      tooltip: 'Cerrar sesión',
                      onPressed: _isLoggingOut ? null : _logout,
                      style: IconButton.styleFrom(
                        backgroundColor: AppColors.espresso,
                        foregroundColor: AppColors.white,
                        disabledBackgroundColor: AppColors.muted,
                      ),
                      icon: _isLoggingOut
                          ? const SizedBox.square(
                              dimension: 18,
                              child: CircularProgressIndicator(
                                key: Key('logoutLoading'),
                                strokeWidth: 2,
                                color: AppColors.white,
                              ),
                            )
                          : const Icon(Icons.logout_rounded),
                    ),
                  ],
                ),
              ),
            ),
            SliverPadding(
              padding: EdgeInsets.fromLTRB(
                horizontalPadding,
                42,
                horizontalPadding,
                32,
              ),
              sliver: SliverToBoxAdapter(
                child: Center(
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 640),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          'TU ESPACIO PERSONAL',
                          style: TextStyle(
                            color: AppColors.terracotta,
                            fontSize: 11,
                            fontWeight: FontWeight.w800,
                            letterSpacing: 2.1,
                          ),
                        ),
                        const SizedBox(height: 12),
                        Text(
                          'Hola, ${widget.user.firstName}',
                          key: const Key('clientGreeting'),
                          style: Theme.of(context).textTheme.headlineMedium
                              ?.copyWith(
                                color: AppColors.espresso,
                                fontSize: 34,
                                fontWeight: FontWeight.w700,
                                letterSpacing: -1.2,
                              ),
                        ),
                        const SizedBox(height: 12),
                        const Text(
                          'Tu sesión de cliente está activa. Muy pronto podrás '
                          'explorar la experiencia móvil completa.',
                          style: TextStyle(
                            color: AppColors.muted,
                            fontSize: 15,
                            height: 1.55,
                          ),
                        ),
                        const SizedBox(height: 28),
                        FilledButton.icon(
                          key: const Key('openCatalogButton'),
                          onPressed: widget.onOpenCatalog,
                          style: FilledButton.styleFrom(
                            minimumSize: const Size.fromHeight(54),
                            backgroundColor: AppColors.espresso,
                            foregroundColor: AppColors.white,
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(10),
                            ),
                          ),
                          icon: const Icon(Icons.checkroom_outlined),
                          label: const Text('Explorar catálogo'),
                        ),
                        const SizedBox(height: 10),
                        OutlinedButton.icon(
                          key: const Key('openReservationsButton'),
                          onPressed: widget.onOpenReservations,
                          style: OutlinedButton.styleFrom(
                            minimumSize: const Size.fromHeight(52),
                            foregroundColor: AppColors.espresso,
                            side: const BorderSide(color: AppColors.espresso),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(10),
                            ),
                          ),
                          icon: const Icon(Icons.event_note_outlined),
                          label: const Text('Mis reservas'),
                        ),
                        const SizedBox(height: 16),
                        Container(
                          width: double.infinity,
                          padding: const EdgeInsets.all(20),
                          decoration: BoxDecoration(
                            color: AppColors.white,
                            border: Border.all(color: AppColors.line),
                            borderRadius: BorderRadius.circular(14),
                          ),
                          child: Row(
                            children: [
                              Container(
                                width: 46,
                                height: 46,
                                decoration: const BoxDecoration(
                                  color: AppColors.linen,
                                  shape: BoxShape.circle,
                                ),
                                child: const Icon(
                                  Icons.person_outline_rounded,
                                  color: AppColors.terracotta,
                                ),
                              ),
                              const SizedBox(width: 14),
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(
                                      widget.user.fullName,
                                      style: const TextStyle(
                                        color: AppColors.espresso,
                                        fontSize: 15,
                                        fontWeight: FontWeight.w700,
                                      ),
                                    ),
                                    const SizedBox(height: 3),
                                    Text(
                                      widget.user.email,
                                      overflow: TextOverflow.ellipsis,
                                      style: const TextStyle(
                                        color: AppColors.muted,
                                        fontSize: 13,
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(height: 16),
                        OutlinedButton.icon(
                          key: const Key('openProfileButton'),
                          onPressed: widget.onOpenProfile,
                          style: OutlinedButton.styleFrom(
                            minimumSize: const Size.fromHeight(52),
                            foregroundColor: AppColors.espresso,
                            side: const BorderSide(color: AppColors.espresso),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(10),
                            ),
                          ),
                          icon: const Icon(Icons.person_outline_rounded),
                          label: const Text('Mi perfil'),
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
    );
  }
}
