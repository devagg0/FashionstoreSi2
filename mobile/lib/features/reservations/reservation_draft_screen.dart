import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../auth/widgets/auth_components.dart';
import '../catalog/widgets/catalog_widgets.dart';
import 'reservation_draft.dart';
import 'reservation_models.dart';
import 'reservation_service.dart';

class ReservationDraftScreen extends StatefulWidget {
  const ReservationDraftScreen({
    super.key,
    required this.draft,
    required this.onBack,
    required this.onContinueShopping,
    required this.onCreated,
    required this.onSessionInvalidated,
    this.reservationGateway,
  });

  final ReservationDraftController draft;
  final VoidCallback onBack;
  final VoidCallback onContinueShopping;
  final ValueChanged<ReservationDetail> onCreated;
  final Future<void> Function(String message) onSessionInvalidated;
  final ReservationGateway? reservationGateway;

  @override
  State<ReservationDraftScreen> createState() => _ReservationDraftScreenState();
}

class _ReservationDraftScreenState extends State<ReservationDraftScreen> {
  late final ReservationGateway _gateway;
  late final bool _ownsService;
  bool _saving = false;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _ownsService = widget.reservationGateway == null;
    _gateway = widget.reservationGateway ?? ReservationService();
  }

  @override
  void dispose() {
    if (_ownsService && _gateway is ReservationService) _gateway.close();
    super.dispose();
  }

  Future<void> _confirm() async {
    if (_saving) return;
    final request = widget.draft.toRequestBody();
    if (request == null) {
      setState(() => _errorMessage = 'La reserva temporal está vacía.');
      return;
    }
    setState(() {
      _saving = true;
      _errorMessage = null;
    });
    try {
      final reservation = await _gateway.create(request);
      widget.draft.clear();
      if (mounted) widget.onCreated(reservation);
    } on ReservationFailure catch (error) {
      if (!mounted) return;
      if (error.type == ReservationFailureType.unauthorized ||
          error.type == ReservationFailureType.forbidden) {
        await widget.onSessionInvalidated(error.message);
        return;
      }
      setState(() => _errorMessage = error.message);
    } catch (_) {
      if (mounted) {
        setState(() => _errorMessage = 'No pudimos crear la reserva.');
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    body: SafeArea(
      child: AnimatedBuilder(
        animation: widget.draft,
        builder: (context, _) => CustomScrollView(
          key: const Key('reservationDraftScrollView'),
          slivers: [
            SliverAppBar(
              pinned: true,
              backgroundColor: AppColors.linen,
              surfaceTintColor: AppColors.linen,
              leading: IconButton(
                onPressed: widget.onBack,
                icon: const Icon(Icons.arrow_back_rounded),
              ),
              title: const Text('RESERVA TEMPORAL'),
            ),
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(18, 18, 18, 36),
              sliver: SliverToBoxAdapter(
                child: Center(
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 720),
                    child: widget.draft.isEmpty ? _empty() : _content(),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    ),
  );

  Widget _empty() => Column(
    key: const Key('emptyReservationDraft'),
    children: [
      const SizedBox(height: 70),
      const Icon(
        Icons.bookmark_border_rounded,
        size: 46,
        color: AppColors.terracotta,
      ),
      const SizedBox(height: 14),
      const Text(
        'Tu reserva temporal está vacía',
        style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800),
      ),
      const SizedBox(height: 16),
      FilledButton(
        onPressed: widget.onContinueShopping,
        child: const Text('Explorar catálogo'),
      ),
    ],
  );

  Widget _content() {
    final context = widget.draft.context!;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          '${widget.draft.itemCount} prendas por confirmar',
          style: const TextStyle(
            color: AppColors.espresso,
            fontSize: 25,
            fontWeight: FontWeight.w800,
          ),
        ),
        const SizedBox(height: 16),
        Container(
          key: const Key('reservationDraftContext'),
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: AppColors.clay,
            borderRadius: BorderRadius.circular(14),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                '${context.branchName} · ${context.cityName}',
                style: const TextStyle(fontWeight: FontWeight.w800),
              ),
              const SizedBox(height: 4),
              Text(context.address),
              Text('${context.date} · ${context.time}'),
            ],
          ),
        ),
        const SizedBox(height: 18),
        ...widget.draft.items.map(_itemCard),
        OutlinedButton.icon(
          key: const Key('continueShoppingButton'),
          onPressed: widget.onContinueShopping,
          icon: const Icon(Icons.add_rounded),
          label: const Text('Seguir explorando catálogo'),
        ),
        const SizedBox(height: 18),
        Row(
          children: [
            const Expanded(child: Text('Total referencial')),
            const SizedBox(width: 12),
            Text(
              formatCatalogMoney(widget.draft.referenceTotal),
              key: const Key('reservationDraftTotal'),
              style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800),
            ),
          ],
        ),
        if (_errorMessage != null) ...[
          const SizedBox(height: 14),
          AuthStatusBanner(message: _errorMessage!),
        ],
        const SizedBox(height: 16),
        FilledButton(
          key: const Key('confirmReservationButton'),
          onPressed: _saving ? null : _confirm,
          child: _saving
              ? const SizedBox.square(
                  key: Key('confirmReservationLoading'),
                  dimension: 20,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Text('Confirmar reserva'),
        ),
        const SizedBox(height: 8),
        const Text(
          'El backend verificará nuevamente disponibilidad, horario y precios.',
          textAlign: TextAlign.center,
          style: TextStyle(color: AppColors.muted, fontSize: 12),
        ),
      ],
    );
  }

  Widget _itemCard(ReservationDraftItem item) => Container(
    key: Key('reservationDraftItem-${item.variantId}'),
    margin: const EdgeInsets.only(bottom: 12),
    padding: const EdgeInsets.all(13),
    decoration: BoxDecoration(
      color: AppColors.white,
      border: Border.all(color: AppColors.line),
      borderRadius: BorderRadius.circular(12),
    ),
    child: LayoutBuilder(
      builder: (context, constraints) {
        if (constraints.maxWidth < 340) {
          return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(child: _itemDescription(item)),
                  _removeButton(item),
                ],
              ),
              const SizedBox(height: 8),
              _quantityControls(item),
            ],
          );
        }
        return Row(
          children: [
            _itemThumbnail(item),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _itemDescription(item),
                  const SizedBox(height: 8),
                  _quantityControls(item),
                ],
              ),
            ),
            _removeButton(item),
          ],
        );
      },
    ),
  );

  Widget _itemThumbnail(ReservationDraftItem item) => SizedBox.square(
    dimension: 60,
    child: ClipRRect(
      borderRadius: BorderRadius.circular(9),
      child: CatalogImageView(imageUrl: item.imageUrl),
    ),
  );

  Widget _itemDescription(ReservationDraftItem item) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text(
        item.productName,
        maxLines: 2,
        overflow: TextOverflow.ellipsis,
        style: const TextStyle(fontWeight: FontWeight.w800),
      ),
      Text(
        '${item.color.name} · Talla ${item.size.name} · ${item.sku}',
        maxLines: 2,
        overflow: TextOverflow.ellipsis,
        style: const TextStyle(color: AppColors.muted, fontSize: 11),
      ),
    ],
  );

  Widget _quantityControls(ReservationDraftItem item) => Row(
    mainAxisSize: MainAxisSize.min,
    children: [
      IconButton.outlined(
        key: Key('decreaseDraftItem-${item.variantId}'),
        visualDensity: VisualDensity.compact,
        onPressed: item.quantity > 1
            ? () =>
                  widget.draft.updateQuantity(item.variantId, item.quantity - 1)
            : null,
        icon: const Icon(Icons.remove_rounded, size: 17),
      ),
      SizedBox(
        width: 32,
        child: Text('${item.quantity}', textAlign: TextAlign.center),
      ),
      IconButton.outlined(
        key: Key('increaseDraftItem-${item.variantId}'),
        visualDensity: VisualDensity.compact,
        onPressed: item.quantity < item.availableStock
            ? () =>
                  widget.draft.updateQuantity(item.variantId, item.quantity + 1)
            : null,
        icon: const Icon(Icons.add_rounded, size: 17),
      ),
    ],
  );

  Widget _removeButton(ReservationDraftItem item) => IconButton(
    key: Key('removeDraftItem-${item.variantId}'),
    tooltip: 'Eliminar',
    onPressed: () => widget.draft.remove(item.variantId),
    icon: const Icon(Icons.delete_outline_rounded, color: AppColors.error),
  );
}
