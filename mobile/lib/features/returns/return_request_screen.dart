import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../auth/widgets/auth_components.dart';
import '../purchases/purchase_models.dart';
import 'return_models.dart';
import 'return_service.dart';

class ReturnRequestScreen extends StatefulWidget {
  const ReturnRequestScreen({
    super.key,
    required this.purchase,
    this.returnGateway,
    required this.onBack,
    this.onReturnCreated,
    this.onSessionInvalidated,
  });

  final PurchaseDetail purchase;
  final ReturnGateway? returnGateway;
  final VoidCallback onBack;
  final ValueChanged<ReturnRequestData>? onReturnCreated;
  final Future<void> Function(String message)? onSessionInvalidated;

  @override
  State<ReturnRequestScreen> createState() => _ReturnRequestScreenState();
}

class _ReturnRequestScreenState extends State<ReturnRequestScreen> {
  late final ReturnGateway _gateway;
  late final bool _ownsService;
  late final TextEditingController _reasonController;
  late final TextEditingController _descriptionController;
  final Map<int, int> _quantities = {};
  final Map<int, int> _usedByVariant = {};

  ReturnRequestData? _submitted;
  String? _errorMessage;
  bool _checkingHistory = true;
  bool _saving = false;
  late final String _idempotencyKey;

  @override
  void initState() {
    super.initState();
    _ownsService = widget.returnGateway == null;
    _gateway = widget.returnGateway ?? ReturnService();
    _idempotencyKey = ReturnService.newIdempotencyKey();
    _reasonController = TextEditingController();
    _descriptionController = TextEditingController();
    for (final item in widget.purchase.products) {
      _quantities[item.detailId] = 0;
    }
    _loadActiveHistory();
  }

  @override
  void dispose() {
    _reasonController.dispose();
    _descriptionController.dispose();
    if (_ownsService && _gateway is ReturnService) _gateway.close();
    super.dispose();
  }

  bool get _canRequest => widget.purchase.state == 'COMPLETADA';

  Future<void> _loadActiveHistory() async {
    final ids = widget.purchase.returns
        .where((request) => request.state != 'RECHAZADA')
        .map((request) => request.returnId)
        .toList(growable: false);
    if (ids.isEmpty) {
      if (mounted) setState(() => _checkingHistory = false);
      return;
    }
    try {
      final requests = await Future.wait(ids.map(_gateway.loadReturn));
      if (!mounted) return;
      final used = <int, int>{};
      for (final request in requests) {
        for (final line in request.lines) {
          used.update(
            line.variantId,
            (quantity) => quantity + line.quantity,
            ifAbsent: () => line.quantity,
          );
        }
      }
      setState(() {
        _usedByVariant
          ..clear()
          ..addAll(used);
        _checkingHistory = false;
      });
    } on ReturnFailure catch (error) {
      if (!mounted) return;
      if (error.invalidatesSession && widget.onSessionInvalidated != null) {
        await widget.onSessionInvalidated!(error.message);
      } else {
        setState(() {
          _checkingHistory = false;
          _errorMessage = error.message;
        });
      }
    }
  }

  int _availableQuantity(PurchaseItem item) =>
      (item.quantity - (_usedByVariant[item.variantId] ?? 0)).clamp(0, item.quantity);

  Future<void> _submit() async {
    if (_saving || _checkingHistory || !_canRequest) return;
    final reason = _reasonController.text.trim();
    final description = _descriptionController.text.trim();
    if (reason.isEmpty || reason.length > 500) {
      setState(() => _errorMessage = 'Escribe un motivo de entre 1 y 500 caracteres.');
      return;
    }
    final lines = widget.purchase.products
        .map((item) => ReturnRequestLine(
              detailId: item.detailId,
              quantity: (_quantities[item.detailId] ?? 0).clamp(
                0,
                _availableQuantity(item),
              ),
            ))
        .where((line) => line.quantity > 0)
        .toList(growable: false);
    if (lines.isEmpty) {
      setState(() => _errorMessage = 'Existe una devolución activa o no quedan unidades disponibles.');
      return;
    }
    final fullReason = description.isEmpty ? reason : '$reason\n\nDescripción: $description';
    if (fullReason.length > 500) {
      setState(() => _errorMessage = 'El motivo y la descripción no pueden superar 500 caracteres.');
      return;
    }
    setState(() {
      _saving = true;
      _errorMessage = null;
    });
    try {
      final result = await _gateway.requestReturn(
        saleId: widget.purchase.saleId,
        reason: fullReason,
        lines: lines,
        idempotencyKey: _idempotencyKey,
      );
      if (!mounted) return;
      setState(() => _submitted = result);
      widget.onReturnCreated?.call(result);
    } on ReturnFailure catch (error) {
      if (!mounted) return;
      if (error.invalidatesSession && widget.onSessionInvalidated != null) {
        await widget.onSessionInvalidated!(error.message);
      } else {
        setState(() => _errorMessage = error.message);
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    body: SafeArea(
      child: CustomScrollView(
        slivers: [
          SliverAppBar(
            pinned: true,
            backgroundColor: AppColors.linen,
            surfaceTintColor: AppColors.linen,
            leading: IconButton(
              key: const Key('returnBackButton'),
              tooltip: 'Volver al detalle',
              onPressed: widget.onBack,
              icon: const Icon(Icons.arrow_back_rounded),
            ),
            title: const Text('SOLICITAR DEVOLUCIÓN'),
          ),
          SliverPadding(
            padding: const EdgeInsets.fromLTRB(22, 18, 22, 32),
            sliver: SliverToBoxAdapter(
              child: Center(
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 720),
                  child: _content(),
                ),
              ),
            ),
          ),
        ],
      ),
    ),
  );

  Widget _content() {
    if (_submitted != null) return _submittedView(_submitted!);
    if (!_canRequest) {
      return const AuthStatusBanner(message: 'Las devoluciones están disponibles para compras completadas.');
    }
    if (_checkingHistory) {
      return const Center(child: CircularProgressIndicator());
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('SOLICITUD DE DEVOLUCIÓN / REEMBOLSO', style: TextStyle(color: AppColors.terracotta, fontSize: 11, fontWeight: FontWeight.w800, letterSpacing: 1.5)),
        const SizedBox(height: 8),
        const Text('Selecciona los productos y cantidades que deseas devolver.', style: TextStyle(color: AppColors.muted)),
        const SizedBox(height: 18),
        ...widget.purchase.products.map(_productSelector),
        const SizedBox(height: 10),
        TextField(
          key: const Key('returnReasonField'),
          controller: _reasonController,
          maxLength: 500,
          decoration: const InputDecoration(labelText: 'Motivo', hintText: 'Indica el motivo de la devolución'),
        ),
        const SizedBox(height: 10),
        TextField(
          key: const Key('returnDescriptionField'),
          controller: _descriptionController,
          maxLines: 3,
          maxLength: 500,
          decoration: const InputDecoration(labelText: 'Descripción opcional', hintText: 'Agrega detalles si son necesarios'),
        ),
        if (_errorMessage != null) ...[
          const SizedBox(height: 8),
          AuthStatusBanner(message: _errorMessage!),
        ],
        const SizedBox(height: 14),
        SizedBox(
          width: double.infinity,
          child: FilledButton.icon(
            key: const Key('submitReturnButton'),
            onPressed: _saving || _checkingHistory ? null : _submit,
            icon: _saving ? const SizedBox.square(dimension: 18, child: CircularProgressIndicator(strokeWidth: 2)) : const Icon(Icons.send_rounded),
            label: Text(_saving ? 'Enviando...' : 'Enviar solicitud'),
          ),
        ),
      ],
    );
  }

  Widget _productSelector(PurchaseItem item) {
    final quantity = _quantities[item.detailId] ?? 0;
    final available = _availableQuantity(item);
    final unavailable = available == 0;
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(color: AppColors.white, borderRadius: BorderRadius.circular(12), border: Border.all(color: AppColors.line)),
      child: Row(
        children: [
          Expanded(
            child: Text(
              '${item.name ?? 'Variante #${item.variantId}'}\n${unavailable ? 'Devolución activa o sin unidades disponibles' : 'Disponible: $available'}',
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                color: unavailable ? AppColors.muted : AppColors.espresso,
              ),
            ),
          ),
          const SizedBox(width: 10),
          DropdownButton<int>(
            key: Key('returnQuantity-${item.detailId}'),
            value: quantity,
            items: List.generate(available + 1, (index) => DropdownMenuItem(value: index, child: Text('$index'))),
            onChanged: _saving || unavailable
                ? null
                : (value) => setState(() => _quantities[item.detailId] = value ?? 0),
          ),
        ],
      ),
    );
  }

  Widget _submittedView(ReturnRequestData request) => Column(
    key: const ValueKey('returnSubmitted'),
    children: [
      Icon(request.state == 'RECHAZADA' ? Icons.cancel_outlined : Icons.check_circle_rounded, color: AppColors.terracotta, size: 52),
      const SizedBox(height: 16),
      Text('Solicitud ${request.state}', textAlign: TextAlign.center, style: const TextStyle(color: AppColors.espresso, fontSize: 22, fontWeight: FontWeight.w800)),
      const SizedBox(height: 10),
      Text('Solicitud #${request.returnId}', style: const TextStyle(color: AppColors.muted)),
      const SizedBox(height: 22),
      SizedBox(width: double.infinity, child: OutlinedButton.icon(onPressed: widget.onBack, icon: const Icon(Icons.arrow_back_rounded), label: const Text('Volver al detalle'))),
    ],
  );
}
