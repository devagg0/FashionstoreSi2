import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';
import '../../catalog/availability_models.dart';
import '../../catalog/catalog_models.dart';
import '../reservation_draft.dart';
import '../reservation_schedule.dart';

class ReservationActionPanel extends StatefulWidget {
  const ReservationActionPanel({
    super.key,
    required this.product,
    required this.selection,
    required this.draft,
    required this.onOpenDraft,
    this.now,
  });

  final CatalogProductDetail product;
  final VariantAvailabilitySelection selection;
  final ReservationDraftController draft;
  final VoidCallback onOpenDraft;
  final DateTime? now;

  @override
  State<ReservationActionPanel> createState() => _ReservationActionPanelState();
}

class _ReservationActionPanelState extends State<ReservationActionPanel> {
  int? _branchId;
  late String _date;
  String? _time;
  int _quantity = 1;
  String? _message;

  @override
  void initState() {
    super.initState();
    _date = upcomingReservationDays(widget.now).first.value;
  }

  @override
  void didUpdateWidget(covariant ReservationActionPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.selection.variant.id != widget.selection.variant.id) {
      _branchId = null;
      _time = null;
      _quantity = 1;
      _message = null;
    }
  }

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
    animation: widget.draft,
    builder: (context, _) {
      final draftContext = widget.draft.context;
      return Container(
        key: const Key('reservationActionPanel'),
        padding: const EdgeInsets.all(18),
        decoration: BoxDecoration(
          color: AppColors.white,
          border: Border.all(color: AppColors.line),
          borderRadius: BorderRadius.circular(14),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              draftContext == null
                  ? 'Iniciar reserva'
                  : 'Añadir a esta reserva',
              style: const TextStyle(
                color: AppColors.espresso,
                fontSize: 18,
                fontWeight: FontWeight.w800,
              ),
            ),
            const SizedBox(height: 8),
            if (draftContext == null)
              ..._firstItemFields()
            else
              ..._existingContextFields(draftContext),
            if (_message != null) ...[
              const SizedBox(height: 10),
              Text(
                _message!,
                key: const Key('reservationActionMessage'),
                style: const TextStyle(color: AppColors.error, fontSize: 13),
              ),
            ],
          ],
        ),
      );
    },
  );

  List<Widget> _firstItemFields() {
    final branches = widget.selection.branches
        .where(
          (branch) =>
              branch.availableStock > 0 &&
              branch.openingTime != null &&
              branch.closingTime != null &&
              branch.openingTime != branch.closingTime,
        )
        .toList(growable: false);
    final branch = _byBranch(branches, _branchId);
    final slots = branch == null
        ? const <String>[]
        : reservationTimeSlots(
            opening: branch.openingTime!,
            closing: branch.closingTime!,
            selectedDate: _date,
            now: widget.now,
          );
    return [
      const Text('Sucursal', style: TextStyle(fontWeight: FontWeight.w700)),
      const SizedBox(height: 7),
      DropdownButtonFormField<int>(
        key: const Key('reservationBranchField'),
        initialValue: _branchId,
        hint: const Text('Selecciona una sucursal'),
        isExpanded: true,
        items: branches
            .map(
              (item) => DropdownMenuItem(
                value: item.branchId,
                child: Text('${item.branchName} · ${item.cityName}'),
              ),
            )
            .toList(growable: false),
        onChanged: (value) => setState(() {
          _branchId = value;
          _time = null;
          _quantity = 1;
          _message = null;
        }),
      ),
      const SizedBox(height: 16),
      const Text('Fecha', style: TextStyle(fontWeight: FontWeight.w700)),
      const SizedBox(height: 8),
      SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: Row(
          children: upcomingReservationDays(widget.now)
              .map(
                (day) => Padding(
                  padding: const EdgeInsets.only(right: 8),
                  child: ChoiceChip(
                    key: Key('reservationDay-${day.value}'),
                    selected: _date == day.value,
                    onSelected: (_) => setState(() {
                      _date = day.value;
                      _time = null;
                      _message = null;
                    }),
                    label: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(_weekday(day.date)),
                        Text(
                          '${day.date.day}',
                          style: const TextStyle(fontWeight: FontWeight.w800),
                        ),
                        Text(_month(day.date)),
                      ],
                    ),
                  ),
                ),
              )
              .toList(growable: false),
        ),
      ),
      const SizedBox(height: 16),
      const Text('Horario', style: TextStyle(fontWeight: FontWeight.w700)),
      const SizedBox(height: 8),
      if (branch == null)
        const Text(
          'Selecciona primero una sucursal.',
          style: TextStyle(color: AppColors.muted),
        )
      else if (slots.isEmpty)
        const Text(
          'Sin horarios disponibles para esta fecha.',
          style: TextStyle(color: AppColors.muted),
        )
      else
        Wrap(
          spacing: 7,
          runSpacing: 7,
          children: slots
              .map(
                (slot) => ChoiceChip(
                  key: Key('reservationTime-$slot'),
                  label: Text(slot),
                  selected: _time == slot,
                  onSelected: (_) => setState(() {
                    _time = slot;
                    _message = null;
                  }),
                ),
              )
              .toList(growable: false),
        ),
      const SizedBox(height: 16),
      _quantitySelector(branch?.availableStock ?? 0),
      const SizedBox(height: 14),
      FilledButton.icon(
        key: const Key('startReservationButton'),
        onPressed: branch == null || _time == null
            ? null
            : () => _start(branch),
        icon: const Icon(Icons.bookmark_add_outlined),
        label: const Text('Añadir a reserva temporal'),
      ),
    ];
  }

  List<Widget> _existingContextFields(ReservationContext context) {
    final branch = _byBranch(widget.selection.branches, context.branchId);
    final existingQuantity = widget.draft.items
        .where((item) => item.variantId == widget.selection.variant.id)
        .fold(0, (total, item) => total + item.quantity);
    final remaining = (branch?.availableStock ?? 0) - existingQuantity;
    return [
      Container(
        key: const Key('fixedReservationContext'),
        padding: const EdgeInsets.all(13),
        decoration: BoxDecoration(
          color: AppColors.linen,
          borderRadius: BorderRadius.circular(10),
        ),
        child: Text(
          '${context.branchName} · ${context.cityName}\n'
          '${context.date} · ${context.time}',
          style: const TextStyle(color: AppColors.espresso, height: 1.5),
        ),
      ),
      const SizedBox(height: 14),
      if (branch == null || remaining <= 0)
        const Text(
          'Sin disponibilidad en la sucursal de esta reserva.',
          key: Key('reservationNoStock'),
          style: TextStyle(color: AppColors.error),
        )
      else ...[
        _quantitySelector(remaining),
        const SizedBox(height: 14),
        FilledButton.icon(
          key: const Key('addToReservationButton'),
          onPressed: () => _add(branch, remaining),
          icon: const Icon(Icons.add_shopping_cart_rounded),
          label: const Text('Añadir a esta reserva'),
        ),
      ],
      const SizedBox(height: 8),
      TextButton(
        key: const Key('openReservationDraftButton'),
        onPressed: widget.onOpenDraft,
        child: Text('Ver reserva (${widget.draft.itemCount})'),
      ),
    ];
  }

  Widget _quantitySelector(int maximum) => Row(
    children: [
      const Expanded(
        child: Text('Cantidad', style: TextStyle(fontWeight: FontWeight.w700)),
      ),
      IconButton.outlined(
        key: const Key('decreaseReservationQuantity'),
        onPressed: _quantity > 1 ? () => setState(() => _quantity--) : null,
        icon: const Icon(Icons.remove_rounded),
      ),
      SizedBox(
        width: 42,
        child: Text(
          '$_quantity',
          key: const Key('reservationQuantity'),
          textAlign: TextAlign.center,
          style: const TextStyle(fontWeight: FontWeight.w800),
        ),
      ),
      IconButton.outlined(
        key: const Key('increaseReservationQuantity'),
        onPressed: _quantity < maximum
            ? () => setState(() => _quantity++)
            : null,
        icon: const Icon(Icons.add_rounded),
      ),
    ],
  );

  void _start(BranchAvailability branch) {
    final added = widget.draft.start(
      contextFromBranch(branch: branch, date: _date, time: _time!),
      _item(branch.availableStock),
    );
    setState(() {
      _message = added ? null : 'Revisa la cantidad y disponibilidad.';
    });
  }

  void _add(BranchAvailability branch, int remaining) {
    if (_quantity > remaining) {
      setState(() => _message = 'La cantidad supera el stock disponible.');
      return;
    }
    final added = widget.draft.add(_item(branch.availableStock));
    setState(() {
      _message = added ? null : 'La cantidad supera el stock disponible.';
      if (added) _quantity = 1;
    });
  }

  ReservationDraftItem _item(int stock) => ReservationDraftItem(
    productId: widget.product.id,
    variantId: widget.selection.variant.id,
    productName: widget.product.name,
    imageUrl: widget.product.primaryImage,
    sku: widget.selection.variant.sku,
    size: widget.selection.variant.size,
    color: widget.selection.variant.color,
    referencePrice: widget.product.finalPrice,
    quantity: _quantity,
    availableStock: stock,
  );

  BranchAvailability? _byBranch(
    Iterable<BranchAvailability> branches,
    int? branchId,
  ) {
    for (final branch in branches) {
      if (branch.branchId == branchId) return branch;
    }
    return null;
  }

  String _weekday(DateTime value) => const [
    'LUN',
    'MAR',
    'MIÉ',
    'JUE',
    'VIE',
    'SÁB',
    'DOM',
  ][value.weekday - 1];

  String _month(DateTime value) => const [
    'ENE',
    'FEB',
    'MAR',
    'ABR',
    'MAY',
    'JUN',
    'JUL',
    'AGO',
    'SEP',
    'OCT',
    'NOV',
    'DIC',
  ][value.month - 1];
}
