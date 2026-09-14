import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../auth/widgets/auth_components.dart';
import '../catalog/widgets/catalog_widgets.dart';
import 'reservation_models.dart';
import 'reservation_service.dart';

class MyReservationsScreen extends StatefulWidget {
  const MyReservationsScreen({
    super.key,
    required this.onBack,
    required this.onOpenDetail,
    required this.onSessionInvalidated,
    this.reservationGateway,
  });

  final VoidCallback onBack;
  final ValueChanged<int> onOpenDetail;
  final Future<void> Function(String message) onSessionInvalidated;
  final ReservationGateway? reservationGateway;

  @override
  State<MyReservationsScreen> createState() => _MyReservationsScreenState();
}

class _MyReservationsScreenState extends State<MyReservationsScreen> {
  late final ReservationGateway _gateway;
  late final bool _ownsService;
  final List<ReservationSummary> _reservations = [];
  ReservationState? _state;
  bool _loading = true;
  bool _loadingMore = false;
  String? _error;
  int _page = 1;
  int _totalPages = 0;

  @override
  void initState() {
    super.initState();
    _ownsService = widget.reservationGateway == null;
    _gateway = widget.reservationGateway ?? ReservationService();
    _load(reset: true);
  }

  @override
  void dispose() {
    if (_ownsService && _gateway is ReservationService) _gateway.close();
    super.dispose();
  }

  Future<void> _load({required bool reset}) async {
    if (_loadingMore) return;
    setState(() {
      if (reset) {
        _loading = true;
        _error = null;
      } else {
        _loadingMore = true;
      }
    });
    try {
      final page = await _gateway.list(
        state: _state,
        page: reset ? 1 : _page + 1,
        pageSize: 10,
      );
      if (!mounted) return;
      setState(() {
        if (reset) _reservations.clear();
        _reservations.addAll(page.data);
        _page = page.pagination.page;
        _totalPages = page.pagination.totalPages;
      });
    } on ReservationFailure catch (error) {
      if (!mounted) return;
      if (error.type == ReservationFailureType.unauthorized ||
          error.type == ReservationFailureType.forbidden) {
        await widget.onSessionInvalidated(error.message);
        return;
      }
      setState(() => _error = error.message);
    } catch (_) {
      if (mounted) setState(() => _error = 'No pudimos cargar tus reservas.');
    } finally {
      if (mounted) {
        setState(() {
          _loading = false;
          _loadingMore = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    body: SafeArea(
      child: CustomScrollView(
        key: const Key('myReservationsScrollView'),
        slivers: [
          SliverAppBar(
            pinned: true,
            backgroundColor: AppColors.linen,
            surfaceTintColor: AppColors.linen,
            leading: IconButton(
              onPressed: widget.onBack,
              icon: const Icon(Icons.arrow_back_rounded),
            ),
            title: const Text('MIS RESERVAS'),
          ),
          SliverPadding(
            padding: const EdgeInsets.fromLTRB(18, 18, 18, 12),
            sliver: SliverToBoxAdapter(
              child: DropdownButtonFormField<ReservationState?>(
                key: ValueKey('reservationState-${_state?.apiValue ?? 'all'}'),
                initialValue: _state,
                decoration: const InputDecoration(labelText: 'Estado'),
                items: [
                  const DropdownMenuItem(value: null, child: Text('Todos')),
                  ...ReservationState.values.map(
                    (state) => DropdownMenuItem(
                      value: state,
                      child: Text(state.label),
                    ),
                  ),
                ],
                onChanged: (value) {
                  setState(() => _state = value);
                  _load(reset: true);
                },
              ),
            ),
          ),
          ..._body(),
          const SliverToBoxAdapter(child: SizedBox(height: 32)),
        ],
      ),
    ),
  );

  List<Widget> _body() {
    if (_loading) {
      return [
        SliverList.builder(
          itemCount: 4,
          itemBuilder: (_, _) => Container(
            height: 150,
            margin: const EdgeInsets.fromLTRB(18, 0, 18, 12),
            decoration: BoxDecoration(
              color: AppColors.line,
              borderRadius: BorderRadius.circular(14),
            ),
          ),
        ),
      ];
    }
    if (_error != null) {
      return [
        SliverPadding(
          padding: const EdgeInsets.all(18),
          sliver: SliverToBoxAdapter(
            child: Column(
              children: [
                AuthStatusBanner(message: _error!),
                FilledButton.icon(
                  key: const Key('retryReservationsButton'),
                  onPressed: () => _load(reset: true),
                  icon: const Icon(Icons.refresh_rounded),
                  label: const Text('Reintentar'),
                ),
              ],
            ),
          ),
        ),
      ];
    }
    if (_reservations.isEmpty) {
      return const [
        SliverPadding(
          padding: EdgeInsets.all(40),
          sliver: SliverToBoxAdapter(
            child: Column(
              key: Key('emptyReservations'),
              children: [
                Icon(
                  Icons.event_busy_outlined,
                  size: 42,
                  color: AppColors.terracotta,
                ),
                SizedBox(height: 12),
                Text('No tienes reservas para mostrar.'),
              ],
            ),
          ),
        ),
      ];
    }
    return [
      SliverList.builder(
        itemCount: _reservations.length,
        itemBuilder: (_, index) => _card(_reservations[index]),
      ),
      if (_page < _totalPages)
        SliverPadding(
          padding: const EdgeInsets.symmetric(horizontal: 18),
          sliver: SliverToBoxAdapter(
            child: OutlinedButton(
              key: const Key('loadMoreReservationsButton'),
              onPressed: _loadingMore ? null : () => _load(reset: false),
              child: _loadingMore
                  ? const CircularProgressIndicator()
                  : const Text('Cargar más'),
            ),
          ),
        ),
    ];
  }

  Widget _card(ReservationSummary row) => Card(
    key: Key('reservation-${row.id}'),
    margin: const EdgeInsets.fromLTRB(18, 0, 18, 12),
    child: InkWell(
      borderRadius: BorderRadius.circular(14),
      onTap: () => widget.onOpenDetail(row.id),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    row.code,
                    style: const TextStyle(fontWeight: FontWeight.w800),
                  ),
                ),
                _StateBadge(row.state),
              ],
            ),
            const SizedBox(height: 10),
            Text('${row.branch.name} · ${row.branch.cityName}'),
            Text(
              formatReservationDate(row.scheduledAt),
              style: const TextStyle(color: AppColors.muted),
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(child: Text('${row.garmentCount} prendas')),
                const SizedBox(width: 12),
                Text(
                  formatCatalogMoney(row.total),
                  style: const TextStyle(fontWeight: FontWeight.w800),
                ),
              ],
            ),
          ],
        ),
      ),
    ),
  );
}

class ReservationStateBadge extends StatelessWidget {
  const ReservationStateBadge(this.state, {super.key});
  final ReservationState state;
  @override
  Widget build(BuildContext context) => _StateBadge(state);
}

class _StateBadge extends StatelessWidget {
  const _StateBadge(this.state);
  final ReservationState state;
  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
    decoration: BoxDecoration(
      color:
          state == ReservationState.cancelada ||
              state == ReservationState.expirada
          ? const Color(0xFFF4E8E4)
          : const Color(0xFFE7F3EA),
      borderRadius: BorderRadius.circular(20),
    ),
    child: Text(
      state.label,
      style: const TextStyle(fontSize: 10, fontWeight: FontWeight.w800),
    ),
  );
}

String formatReservationDate(DateTime utc) {
  final value = utc.toUtc().subtract(const Duration(hours: 4));
  return '${value.day.toString().padLeft(2, '0')}/'
      '${value.month.toString().padLeft(2, '0')}/${value.year} · '
      '${value.hour.toString().padLeft(2, '0')}:'
      '${value.minute.toString().padLeft(2, '0')}';
}
