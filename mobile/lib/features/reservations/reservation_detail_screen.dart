import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../auth/widgets/auth_components.dart';
import '../catalog/widgets/catalog_widgets.dart';
import 'my_reservations_screen.dart';
import 'reservation_models.dart';
import 'reservation_service.dart';

class ReservationDetailScreen extends StatefulWidget {
  const ReservationDetailScreen({
    super.key,
    required this.reservationId,
    required this.onBack,
    required this.onSessionInvalidated,
    this.initialReservation,
    this.created = false,
    this.reservationGateway,
  });
  final int reservationId;
  final VoidCallback onBack;
  final Future<void> Function(String message) onSessionInvalidated;
  final ReservationDetail? initialReservation;
  final bool created;
  final ReservationGateway? reservationGateway;

  @override
  State<ReservationDetailScreen> createState() =>
      _ReservationDetailScreenState();
}

class _ReservationDetailScreenState extends State<ReservationDetailScreen> {
  late final ReservationGateway _gateway;
  late final bool _ownsService;
  ReservationDetail? _reservation;
  bool _loading = true;
  bool _cancelling = false;
  String? _error;
  String? _success;

  @override
  void initState() {
    super.initState();
    _ownsService = widget.reservationGateway == null;
    _gateway = widget.reservationGateway ?? ReservationService();
    _reservation = widget.initialReservation;
    _success = widget.created ? 'Tu reserva fue creada correctamente.' : null;
    if (_reservation == null) {
      _load();
    } else {
      _loading = false;
    }
  }

  @override
  void dispose() {
    if (_ownsService && _gateway is ReservationService) _gateway.close();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final result = await _gateway.getDetail(widget.reservationId);
      if (mounted) setState(() => _reservation = result);
    } on ReservationFailure catch (error) {
      await _handleFailure(error);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _cancel() async {
    if (_cancelling || _reservation?.cancelable != true) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Cancelar reserva'),
        content: const Text('¿Quieres cancelar esta reserva?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Volver'),
          ),
          FilledButton(
            key: const Key('confirmCancelReservationButton'),
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Cancelar reserva'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    setState(() {
      _cancelling = true;
      _error = null;
    });
    try {
      final result = await _gateway.cancel(widget.reservationId);
      if (mounted) {
        setState(() {
          _reservation = result;
          _success = 'La reserva fue cancelada correctamente.';
        });
      }
    } on ReservationFailure catch (error) {
      await _handleFailure(error);
      if (mounted && error.type == ReservationFailureType.conflict) {
        await _load();
      }
    } finally {
      if (mounted) setState(() => _cancelling = false);
    }
  }

  Future<void> _handleFailure(ReservationFailure error) async {
    if (!mounted) return;
    if (error.type == ReservationFailureType.unauthorized ||
        error.type == ReservationFailureType.forbidden) {
      await widget.onSessionInvalidated(error.message);
    } else {
      setState(() => _error = error.message);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    body: SafeArea(
      child: CustomScrollView(
        key: const Key('reservationDetailScrollView'),
        slivers: [
          SliverAppBar(
            pinned: true,
            backgroundColor: AppColors.linen,
            surfaceTintColor: AppColors.linen,
            leading: IconButton(
              onPressed: widget.onBack,
              icon: const Icon(Icons.arrow_back_rounded),
            ),
            title: const Text('DETALLE DE RESERVA'),
          ),
          SliverPadding(
            padding: const EdgeInsets.fromLTRB(18, 18, 18, 36),
            sliver: SliverToBoxAdapter(child: _content()),
          ),
        ],
      ),
    ),
  );

  Widget _content() {
    if (_loading) {
      return const Center(
        child: CircularProgressIndicator(key: Key('reservationDetailLoading')),
      );
    }
    if (_reservation == null) {
      return Column(
        children: [
          AuthStatusBanner(message: _error ?? 'No pudimos cargar la reserva.'),
          FilledButton(onPressed: _load, child: const Text('Reintentar')),
        ],
      );
    }
    final row = _reservation!;
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 720),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (_success != null) ...[
              _SuccessBanner(_success!),
              const SizedBox(height: 14),
            ],
            if (_error != null) ...[
              AuthStatusBanner(message: _error!),
              const SizedBox(height: 14),
            ],
            Row(
              children: [
                Expanded(
                  child: Text(
                    row.code,
                    style: const TextStyle(
                      fontSize: 23,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ),
                ReservationStateBadge(row.state),
              ],
            ),
            const SizedBox(height: 16),
            _info(
              'Sucursal',
              '${row.branch.name} · ${row.branch.cityName}\n${row.branch.address}',
            ),
            _info('Fecha y hora', formatReservationDate(row.scheduledAt)),
            _info('Cantidad de prendas', '${row.garmentCount}'),
            const SizedBox(height: 10),
            ...row.items.map(_item),
            const Divider(height: 28),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text(
                  'Total',
                  style: TextStyle(fontWeight: FontWeight.w700),
                ),
                Text(
                  formatCatalogMoney(row.total),
                  style: const TextStyle(
                    fontSize: 21,
                    fontWeight: FontWeight.w800,
                  ),
                ),
              ],
            ),
            if (row.cancelable) ...[
              const SizedBox(height: 18),
              OutlinedButton.icon(
                key: const Key('cancelReservationButton'),
                onPressed: _cancelling ? null : _cancel,
                icon: const Icon(Icons.cancel_outlined),
                label: Text(_cancelling ? 'Cancelando...' : 'Cancelar reserva'),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _info(String label, String value) => Padding(
    padding: const EdgeInsets.only(bottom: 13),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: const TextStyle(color: AppColors.muted, fontSize: 12),
        ),
        Text(value, style: const TextStyle(height: 1.4)),
      ],
    ),
  );

  Widget _item(ReservationItem item) => Container(
    key: Key('reservationDetailItem-${item.variantId}'),
    margin: const EdgeInsets.only(bottom: 10),
    padding: const EdgeInsets.all(12),
    decoration: BoxDecoration(
      color: AppColors.white,
      border: Border.all(color: AppColors.line),
      borderRadius: BorderRadius.circular(12),
    ),
    child: Row(
      children: [
        SizedBox.square(
          dimension: 60,
          child: ClipRRect(
            borderRadius: BorderRadius.circular(8),
            child: CatalogImageView(imageUrl: item.imageUrl),
          ),
        ),
        const SizedBox(width: 11),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                item.productName,
                style: const TextStyle(fontWeight: FontWeight.w800),
              ),
              Text(
                '${item.color.name} · Talla ${item.size.name} · ${item.sku}',
                style: const TextStyle(color: AppColors.muted, fontSize: 11),
              ),
              Text('${item.quantity} × ${formatCatalogMoney(item.unitPrice)}'),
            ],
          ),
        ),
        Text(
          formatCatalogMoney(item.subtotal),
          style: const TextStyle(fontWeight: FontWeight.w800),
        ),
      ],
    ),
  );
}

class _SuccessBanner extends StatelessWidget {
  const _SuccessBanner(this.message);
  final String message;
  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(13),
    decoration: BoxDecoration(
      color: const Color(0xFFE7F3EA),
      borderRadius: BorderRadius.circular(8),
    ),
    child: Row(
      children: [
        const Icon(Icons.check_circle_outline, color: AppColors.success),
        const SizedBox(width: 9),
        Expanded(child: Text(message)),
      ],
    ),
  );
}
