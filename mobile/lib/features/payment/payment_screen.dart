import 'dart:async';
import 'dart:math';

import 'package:app_links/app_links.dart';
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/theme/app_theme.dart';
import '../auth/widgets/auth_components.dart';
import '../catalog/widgets/catalog_widgets.dart';
import '../checkout/checkout_models.dart';
import 'payment_models.dart';
import 'payment_service.dart';

class PaymentScreen extends StatefulWidget {
  const PaymentScreen({
    super.key,
    required this.sale,
    this.paymentGateway,
    required this.onBack,
    this.onSessionInvalidated,
  });

  final DigitalSale sale;
  final PaymentGateway? paymentGateway;
  final VoidCallback onBack;
  final Future<void> Function(String message)? onSessionInvalidated;

  @override
  State<PaymentScreen> createState() => _PaymentScreenState();
}

class _PaymentScreenState extends State<PaymentScreen>
    with WidgetsBindingObserver {
  late final PaymentGateway _gateway;
  late final bool _ownsGateway;
  late final String _idempotencyKey;
  final _appLinks = AppLinks();
  StreamSubscription<Uri>? _linkSubscription;

  PaymentData? _payment;
  Uri? _pendingReturn;
  String? _errorMessage;
  String? _returnMessage;
  bool _loading = true;
  bool _busy = false;
  bool _checkoutOpened = false;
  bool _backgrounded = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _ownsGateway = widget.paymentGateway == null;
    _gateway = widget.paymentGateway ?? PaymentService();
    _idempotencyKey = _newIdempotencyKey();
    _listenForDeepLinks();
    _preparePayment();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _linkSubscription?.cancel();
    if (_ownsGateway && _gateway is PaymentService) _gateway.close();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.paused ||
        state == AppLifecycleState.inactive) {
      _backgrounded = true;
    }
    if (state == AppLifecycleState.resumed &&
        _backgrounded &&
        _checkoutOpened &&
        _payment?.uiState == PaymentState.pending) {
      _backgrounded = false;
      _syncPayment();
    }
  }

  Future<void> _preparePayment() async {
    setState(() {
      _loading = true;
      _errorMessage = null;
    });
    try {
      final payment = await _gateway.startPayment(
        saleId: widget.sale.saleId,
        idempotencyKey: _idempotencyKey,
      );
      if (!mounted) return;
      setState(() => _payment = payment);
      final pendingReturn = _pendingReturn;
      _pendingReturn = null;
      if (pendingReturn != null) {
        await _handleStripeReturn(pendingReturn);
        return;
      }
      if (payment.uiState == PaymentState.pending) {
        await _openCheckout(payment);
      }
    } on PaymentFailure catch (error) {
      await _handleFailure(error);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _openCheckout(PaymentData payment) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _errorMessage = null;
    });
    try {
      final checkout = await _gateway.createCheckoutSession(payment.paymentId);
      if (!mounted) return;
      setState(() {
        _payment = checkout.payment;
        _checkoutOpened = true;
        _returnMessage = 'Abriendo Stripe Checkout...';
      });
      final opened = await launchUrl(
        Uri.parse(checkout.url),
        mode: LaunchMode.externalApplication,
      );
      if (!opened && mounted) {
        setState(() {
          _checkoutOpened = false;
          _returnMessage = null;
          _errorMessage = 'No pudimos abrir Stripe Checkout.';
        });
      }
    } on PaymentFailure catch (error) {
      await _handleFailure(error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _syncPayment() async {
    final payment = _payment;
    if (payment == null || _busy || payment.uiState != PaymentState.pending) {
      return;
    }
    setState(() {
      _busy = true;
      _loading = true;
      _returnMessage = 'Verificando el resultado del pago...';
      _errorMessage = null;
    });
    try {
      final updated = await _gateway.syncStripe(payment.paymentId);
      if (!mounted) return;
      setState(() {
        _payment = updated;
        _checkoutOpened = false;
        _returnMessage = updated.uiState == PaymentState.approved
            ? 'Pago realizado correctamente.'
            : updated.uiState == PaymentState.canceled
            ? 'Pago cancelado. Tu compra continúa pendiente.'
            : 'Tu pago continúa pendiente.';
      });
    } on PaymentFailure catch (error) {
      await _handleFailure(error);
    } finally {
      if (mounted) {
        setState(() {
          _busy = false;
          _loading = false;
        });
      }
    }
  }

  Future<void> _listenForDeepLinks() async {
    _linkSubscription = _appLinks.uriLinkStream.listen(_handleStripeReturn);
    try {
      final initialUri = await _appLinks.getInitialLink();
      if (initialUri != null) await _handleStripeReturn(initialUri);
    } catch (_) {
      // El retorno también puede resolverse mediante el ciclo de vida de la app.
    }
  }

  Future<void> _handleStripeReturn(Uri uri) async {
    if (uri.scheme != 'fashionstore' ||
        uri.host != 'payment-return' ||
        uri.queryParameters['checkout'] == null) {
      return;
    }
    final paymentId = int.tryParse(uri.queryParameters['payment_id'] ?? '');
    final currentPayment = _payment;
    if (paymentId == null ||
        paymentId <= 0 ||
        (currentPayment != null && currentPayment.paymentId != paymentId)) {
      return;
    }
    if (currentPayment == null) {
      _pendingReturn = uri;
      return;
    }
    _checkoutOpened = false;
    await _syncPayment();
  }

  Future<void> _handleFailure(PaymentFailure error) async {
    if (!mounted) return;
    if (error.invalidatesSession && widget.onSessionInvalidated != null) {
      await widget.onSessionInvalidated!(error.message);
      return;
    }
    setState(() => _errorMessage = error.message);
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
              key: const Key('paymentBackButton'),
              tooltip: 'Volver a la compra',
              onPressed: widget.onBack,
              icon: const Icon(Icons.arrow_back_rounded),
            ),
            title: const Text('PAGO DIGITAL'),
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
    if (_loading && _payment == null) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_errorMessage != null && _payment == null) {
      return Column(
        children: [
          AuthStatusBanner(message: _errorMessage!),
          const SizedBox(height: 18),
          FilledButton.icon(
            key: const Key('retryPaymentButton'),
            onPressed: _preparePayment,
            icon: const Icon(Icons.refresh_rounded),
            label: const Text('Reintentar'),
          ),
        ],
      );
    }
    final payment = _payment;
    if (payment == null) return const SizedBox.shrink();
    return Column(
      key: const ValueKey('paymentContent'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _stateHeader(payment),
        if (_returnMessage != null) ...[
          const SizedBox(height: 12),
          Text(_returnMessage!, style: const TextStyle(color: AppColors.muted)),
        ],
        if (_errorMessage != null) ...[
          const SizedBox(height: 12),
          AuthStatusBanner(message: _errorMessage!),
        ],
        const SizedBox(height: 22),
        _summary(payment),
        const SizedBox(height: 22),
        ..._actions(payment),
      ],
    );
  }

  Widget _stateHeader(PaymentData payment) {
    final state = payment.uiState;
    final icon = switch (state) {
      PaymentState.approved => Icons.check_circle_rounded,
      PaymentState.canceled => Icons.cancel_outlined,
      PaymentState.pending => Icons.schedule_rounded,
    };
    final title = switch (state) {
      PaymentState.approved => 'Pago aprobado',
      PaymentState.canceled => 'Pago cancelado',
      PaymentState.pending => 'Pago pendiente',
    };
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, color: AppColors.terracotta, size: 44),
        const SizedBox(width: 12),
        Expanded(
          child: Text(
            title,
            style: const TextStyle(color: AppColors.espresso, fontSize: 24, fontWeight: FontWeight.w800),
          ),
        ),
      ],
    );
  }

  Widget _summary(PaymentData payment) => Container(
    width: double.infinity,
    padding: const EdgeInsets.all(16),
    decoration: BoxDecoration(
      color: AppColors.white,
      borderRadius: BorderRadius.circular(12),
      border: Border.all(color: AppColors.line),
    ),
    child: Column(
      children: [
        _row('Venta', '#${payment.saleId}'),
        _row('Pago', '#${payment.paymentId}'),
        _row('Estado', payment.state),
        _row('Total', formatCatalogMoney(payment.amount), strong: true),
      ],
    ),
  );

  List<Widget> _actions(PaymentData payment) {
    if (payment.uiState == PaymentState.approved) {
      return [
        SizedBox(
          width: double.infinity,
          child: OutlinedButton.icon(
            key: const Key('approvedPaymentBackButton'),
            onPressed: widget.onBack,
            icon: const Icon(Icons.arrow_back_rounded),
            label: const Text('Volver a la compra'),
          ),
        ),
      ];
    }
    return [
      SizedBox(
        width: double.infinity,
        child: FilledButton.icon(
          key: const Key('openStripeCheckoutButton'),
          onPressed: _busy ? null : () => _openCheckout(payment),
          icon: const Icon(Icons.open_in_new_rounded),
          label: const Text('Abrir Stripe Checkout'),
        ),
      ),
      const SizedBox(height: 10),
      SizedBox(
        width: double.infinity,
        child: OutlinedButton.icon(
          key: const Key('syncPaymentButton'),
          onPressed: _busy ? null : _syncPayment,
          icon: const Icon(Icons.sync_rounded),
          label: const Text('Consultar estado'),
        ),
      ),
    ];
  }

  Widget _row(String label, String value, {bool strong = false}) => Padding(
    padding: const EdgeInsets.only(bottom: 8),
    child: Row(
      children: [
        Text(label, style: TextStyle(color: AppColors.muted, fontWeight: strong ? FontWeight.w800 : FontWeight.w600)),
        const Spacer(),
        Flexible(
          child: Text(
            value,
            textAlign: TextAlign.right,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(color: AppColors.espresso, fontWeight: strong ? FontWeight.w800 : FontWeight.w700),
          ),
        ),
      ],
    ),
  );

  String _newIdempotencyKey() {
    final random = Random.secure();
    String hex(int count) => List.generate(
      count,
      (_) => random.nextInt(16).toRadixString(16),
    ).join();
    return '${hex(8)}-${hex(4)}-4${hex(3)}-${(8 + random.nextInt(4)).toRadixString(16)}${hex(3)}-${hex(12)}';
  }
}
