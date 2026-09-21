import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../auth/widgets/auth_components.dart';
import '../catalog/widgets/catalog_widgets.dart';
import 'purchase_models.dart';
import 'purchase_service.dart';

class PurchasesScreen extends StatefulWidget {
  const PurchasesScreen({
    super.key,
    this.purchaseGateway,
    required this.onBack,
    this.onOpenReturnRequest,
    this.onOpenReceipt,
    this.onSessionInvalidated,
  });

  final PurchaseGateway? purchaseGateway;
  final VoidCallback onBack;
  final ValueChanged<PurchaseDetail>? onOpenReturnRequest;
  final ValueChanged<int>? onOpenReceipt;
  final Future<void> Function(String message)? onSessionInvalidated;

  @override
  State<PurchasesScreen> createState() => _PurchasesScreenState();
}

class _PurchasesScreenState extends State<PurchasesScreen> {
  late final PurchaseGateway _gateway;
  late final bool _ownsService;

  final List<PurchaseSummary> _items = [];
  PurchaseDetail? _detail;
  String? _errorMessage;
  bool _loading = true;
  bool _loadingMore = false;
  bool _hasMore = false;
  int _total = 0;

  @override
  void initState() {
    super.initState();
    _ownsService = widget.purchaseGateway == null;
    _gateway = widget.purchaseGateway ?? PurchaseService();
    _load();
  }

  @override
  void dispose() {
    if (_ownsService && _gateway is PurchaseService) _gateway.close();
    super.dispose();
  }

  Future<void> _load({bool append = false}) async {
    if (append && (_loadingMore || !_hasMore)) return;
    setState(() {
      if (append) {
        _loadingMore = true;
      } else {
        _loading = true;
        _errorMessage = null;
        _detail = null;
      }
    });
    try {
      final page = await _gateway.loadPurchases(offset: append ? _items.length : 0);
      if (!mounted) return;
      setState(() {
        if (!append) _items.clear();
        final ids = _items.map((item) => item.saleId).toSet();
        _items.addAll(page.items.where((item) => ids.add(item.saleId)));
        _total = page.total;
        _hasMore = _items.length < page.total;
      });
    } on PurchaseFailure catch (error) {
      await _handleFailure(error);
    } catch (_) {
      if (mounted) setState(() => _errorMessage = 'No pudimos consultar tus compras.');
    } finally {
      if (mounted) {
        setState(() {
          _loading = false;
          _loadingMore = false;
        });
      }
    }
  }

  Future<void> _openDetail(PurchaseSummary purchase) async {
    setState(() {
      _detail = null;
      _errorMessage = null;
      _loading = true;
    });
    try {
      final detail = await _gateway.loadPurchaseDetail(purchase.saleId);
      if (!mounted) return;
      setState(() => _detail = detail);
    } on PurchaseFailure catch (error) {
      await _handleFailure(error);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _handleFailure(PurchaseFailure error) async {
    if (!mounted) return;
    if (error.invalidatesSession && widget.onSessionInvalidated != null) {
      await widget.onSessionInvalidated!(error.message);
      return;
    }
    setState(() => _errorMessage = error.message);
  }

  @override
  Widget build(BuildContext context) {
    final padding = MediaQuery.sizeOf(context).width < 370 ? 18.0 : 22.0;
    return Scaffold(
      body: SafeArea(
        child: CustomScrollView(
          slivers: [
            SliverAppBar(
              pinned: true,
              backgroundColor: AppColors.linen,
              surfaceTintColor: AppColors.linen,
              leading: IconButton(
                key: const Key('purchasesBackButton'),
                tooltip: 'Volver',
                onPressed: _detail == null ? widget.onBack : () => setState(() => _detail = null),
                icon: const Icon(Icons.arrow_back_rounded),
              ),
              title: Text(_detail == null ? 'MIS COMPRAS' : 'DETALLE DE COMPRA'),
            ),
            SliverPadding(
              padding: EdgeInsets.fromLTRB(padding, 18, padding, 32),
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
  }

  Widget _content() {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_errorMessage != null) {
      return Column(
        children: [
          AuthStatusBanner(message: _errorMessage!),
          const SizedBox(height: 18),
          FilledButton.icon(
            key: const Key('retryPurchasesButton'),
            onPressed: () => _load(),
            icon: const Icon(Icons.refresh_rounded),
            label: const Text('Reintentar'),
          ),
        ],
      );
    }
    if (_detail != null) return _detailView(_detail!);
    if (_items.isEmpty) return const _EmptyPurchases();
    return Column(
      key: const ValueKey('purchasesList'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          '$_total compras registradas',
          style: const TextStyle(color: AppColors.muted, fontWeight: FontWeight.w600),
        ),
        const SizedBox(height: 14),
        ..._items.map(_purchaseCard),
        if (_hasMore) ...[
          const SizedBox(height: 8),
          SizedBox(
            width: double.infinity,
            child: OutlinedButton.icon(
              key: const Key('loadMorePurchasesButton'),
              onPressed: _loadingMore ? null : () => _load(append: true),
              icon: _loadingMore
                  ? const SizedBox.square(dimension: 18, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.expand_more_rounded),
              label: const Text('Cargar más'),
            ),
          ),
        ],
      ],
    );
  }

  Widget _purchaseCard(PurchaseSummary purchase) => InkWell(
    key: Key('purchaseCard-${purchase.saleId}'),
    borderRadius: BorderRadius.circular(14),
    onTap: () => _openDetail(purchase),
    child: Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppColors.line),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Text(
                  purchase.purchaseCode,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(color: AppColors.espresso, fontSize: 17, fontWeight: FontWeight.w800),
                ),
              ),
              const SizedBox(width: 10),
              _StatusPill(state: purchase.state),
            ],
          ),
          const SizedBox(height: 10),
          _compactRow(Icons.calendar_today_outlined, _formatDate(purchase.date)),
          _compactRow(Icons.store_outlined, purchase.branch.name),
          const Divider(height: 20),
          Row(
            children: [
              Expanded(child: Text(purchase.channel, style: const TextStyle(color: AppColors.muted, fontWeight: FontWeight.w700))),
              Flexible(
                child: Text(formatCatalogMoney(purchase.total), textAlign: TextAlign.right, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(color: AppColors.espresso, fontSize: 17, fontWeight: FontWeight.w800)),
              ),
            ],
          ),
          const SizedBox(height: 12),
          SizedBox(
            width: double.infinity,
            child: OutlinedButton.icon(
              key: Key('purchaseDetailButton-${purchase.saleId}'),
              onPressed: () => _openDetail(purchase),
              icon: const Icon(Icons.visibility_outlined),
              label: const Text('Ver detalle'),
            ),
          ),
          if (purchase.state == 'COMPLETADA' && widget.onOpenReceipt != null) ...[
            const SizedBox(height: 8),
            SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                key: Key('purchaseReceiptButton-${purchase.saleId}'),
                onPressed: () => widget.onOpenReceipt!(purchase.saleId),
                icon: const Icon(Icons.print_outlined),
                label: const Text('Imprimir comprobante'),
              ),
            ),
          ],
        ],
      ),
    ),
  );

  Widget _detailView(PurchaseDetail purchase) => Column(
    key: const ValueKey('purchaseDetail'),
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Text(
              purchase.purchaseCode,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(color: AppColors.espresso, fontSize: 24, fontWeight: FontWeight.w800),
            ),
          ),
          const SizedBox(width: 10),
          _StatusPill(state: purchase.state),
        ],
      ),
      const SizedBox(height: 12),
      _compactRow(Icons.calendar_today_outlined, _formatDate(purchase.date)),
      _compactRow(Icons.store_outlined, purchase.branch.name),
      const SizedBox(height: 20),
      const Text('PRODUCTOS', style: TextStyle(color: AppColors.terracotta, fontSize: 11, fontWeight: FontWeight.w800, letterSpacing: 2)),
      const SizedBox(height: 10),
      ...purchase.products.map(_productRow),
      const SizedBox(height: 12),
      _totals(purchase),
      const SizedBox(height: 20),
      _payments(purchase),
      if (purchase.returns.isNotEmpty) ...[
        const SizedBox(height: 22),
        const Text('SOLICITUDES DE DEVOLUCIÓN', style: TextStyle(color: AppColors.terracotta, fontSize: 11, fontWeight: FontWeight.w800, letterSpacing: 1.5)),
        const SizedBox(height: 10),
        ...purchase.returns.map(
          (request) => Container(
            width: double.infinity,
            margin: const EdgeInsets.only(bottom: 8),
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(color: AppColors.white, borderRadius: BorderRadius.circular(12), border: Border.all(color: AppColors.line)),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Text(
                    '${request.type}\n${request.reason}',
                    maxLines: 3,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                const SizedBox(width: 10),
                _StatusPill(state: request.state),
              ],
            ),
          ),
        ),
      ],
      if (_canRequestReturn(purchase)) ...[
        const SizedBox(height: 22),
        SizedBox(
          width: double.infinity,
          child: FilledButton.icon(
            key: const Key('openReturnRequestButton'),
            onPressed: widget.onOpenReturnRequest == null
                ? null
                : () => widget.onOpenReturnRequest!(purchase),
            icon: const Icon(Icons.assignment_return_outlined),
            label: const Text('Solicitar devolución/reembolso'),
          ),
        ),
      ],
    ],
  );

  bool _canRequestReturn(PurchaseDetail purchase) =>
      purchase.state == 'COMPLETADA';

  Widget _productRow(PurchaseItem item) => Container(
    width: double.infinity,
    margin: const EdgeInsets.only(bottom: 10),
    padding: const EdgeInsets.all(14),
    decoration: BoxDecoration(color: AppColors.white, borderRadius: BorderRadius.circular(12), border: Border.all(color: AppColors.line)),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: Text(
            '${item.name ?? 'Variante #${item.variantId}'}\n${item.size ?? ''}${item.color == null ? '' : ' · ${item.color}'}',
            maxLines: 3,
            overflow: TextOverflow.ellipsis,
          ),
        ),
        const SizedBox(width: 12),
        Flexible(child: Text('${item.quantity} x ${formatCatalogMoney(item.unitPrice - item.unitDiscount)}', textAlign: TextAlign.right, maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w700))),
      ],
    ),
  );

  Widget _totals(PurchaseSummary purchase) => Container(
    width: double.infinity,
    padding: const EdgeInsets.all(16),
    decoration: BoxDecoration(color: AppColors.white, borderRadius: BorderRadius.circular(12), border: Border.all(color: AppColors.line)),
    child: Column(
      children: [
        _valueRow('Subtotal', formatCatalogMoney(purchase.subtotal)),
        _valueRow('Descuento', formatCatalogMoney(purchase.discountTotal)),
        const Divider(height: 18),
        _valueRow('Total', formatCatalogMoney(purchase.total), strong: true),
      ],
    ),
  );

  Widget _payments(PurchaseDetail purchase) {
    if (purchase.payments.isEmpty) {
      return const Text('Sin información de pago registrada.', style: TextStyle(color: AppColors.muted));
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('PAGO', style: TextStyle(color: AppColors.terracotta, fontSize: 11, fontWeight: FontWeight.w800, letterSpacing: 2)),
        const SizedBox(height: 10),
        ...purchase.payments.map((payment) => Container(
          width: double.infinity,
          margin: const EdgeInsets.only(bottom: 8),
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(color: AppColors.white, borderRadius: BorderRadius.circular(12), border: Border.all(color: AppColors.line)),
          child: Row(
            children: [
              Expanded(child: Text('${payment.method}\n${payment.state}', maxLines: 2, overflow: TextOverflow.ellipsis)),
              const SizedBox(width: 10),
              Flexible(child: Text(formatCatalogMoney(payment.amount), textAlign: TextAlign.right, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w800))),
            ],
          ),
        )),
      ],
    );
  }

  Widget _valueRow(String label, String value, {bool strong = false}) => Padding(
    padding: const EdgeInsets.only(bottom: 8),
    child: Row(
      children: [
        Text(label, style: TextStyle(color: strong ? AppColors.espresso : AppColors.muted, fontWeight: strong ? FontWeight.w800 : FontWeight.w600)),
        const Spacer(),
        const SizedBox(width: 12),
        Flexible(child: Text(value, textAlign: TextAlign.right, maxLines: 2, overflow: TextOverflow.ellipsis, style: TextStyle(color: AppColors.espresso, fontWeight: strong ? FontWeight.w800 : FontWeight.w700))),
      ],
    ),
  );

  Widget _compactRow(IconData icon, String value) => Padding(
    padding: const EdgeInsets.only(bottom: 6),
    child: Row(
      children: [
        Icon(icon, size: 16, color: AppColors.terracotta),
        const SizedBox(width: 8),
        Expanded(child: Text(value, maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(color: AppColors.muted))),
      ],
    ),
  );

  String _formatDate(DateTime? value) {
    if (value == null) return 'Fecha no disponible';
    return MaterialLocalizations.of(context).formatMediumDate(value.toLocal());
  }
}

class _StatusPill extends StatelessWidget {
  const _StatusPill({required this.state});
  final String state;

  @override
  Widget build(BuildContext context) => Container(
    constraints: const BoxConstraints(maxWidth: 120),
    padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 6),
    decoration: BoxDecoration(color: AppColors.linen, borderRadius: BorderRadius.circular(20)),
    child: Text(state, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(color: AppColors.terracotta, fontSize: 10, fontWeight: FontWeight.w800)),
  );
}

class _EmptyPurchases extends StatelessWidget {
  const _EmptyPurchases();

  @override
  Widget build(BuildContext context) => const Column(
    children: [
      Icon(Icons.receipt_long_outlined, size: 52, color: AppColors.terracotta),
      SizedBox(height: 16),
      Text('Aún no tienes compras.', style: TextStyle(color: AppColors.espresso, fontSize: 20, fontWeight: FontWeight.w700)),
      SizedBox(height: 8),
      Text('Tus compras aparecerán aquí.', textAlign: TextAlign.center, style: TextStyle(color: AppColors.muted)),
    ],
  );
}
