import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:pdf/pdf.dart' as pdf;
import 'package:pdf/widgets.dart' as pw;
import 'package:printing/printing.dart';

import '../../core/theme/app_theme.dart';
import '../auth/widgets/auth_components.dart';
import '../catalog/widgets/catalog_widgets.dart';
import 'receipt_models.dart';
import 'receipt_service.dart';

class ReceiptScreen extends StatefulWidget {
  const ReceiptScreen({
    super.key,
    required this.saleId,
    this.receiptGateway,
    required this.onBack,
    this.onSessionInvalidated,
  });

  final int saleId;
  final ReceiptGateway? receiptGateway;
  final VoidCallback onBack;
  final Future<void> Function(String message)? onSessionInvalidated;

  @override
  State<ReceiptScreen> createState() => _ReceiptScreenState();
}

class _ReceiptScreenState extends State<ReceiptScreen> {
  late final ReceiptGateway _gateway;
  late final bool _ownsService;
  SaleReceipt? _receipt;
  String? _errorMessage;
  bool _loading = true;
  bool _pdfBusy = false;

  @override
  void initState() {
    super.initState();
    _ownsService = widget.receiptGateway == null;
    _gateway = widget.receiptGateway ?? ReceiptService();
    _load();
  }

  @override
  void dispose() {
    if (_ownsService && _gateway is ReceiptService) _gateway.close();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() { _loading = true; _errorMessage = null; });
    try {
      final receipt = await _gateway.loadReceipt(widget.saleId);
      if (!mounted) return;
      setState(() => _receipt = receipt);
    } on ReceiptFailure catch (error) {
      if (!mounted) return;
      if (error.invalidatesSession && widget.onSessionInvalidated != null) {
        await widget.onSessionInvalidated!(error.message);
      } else {
        setState(() => _errorMessage = error.message);
      }
    } finally {
      if (mounted) setState(() => _loading = false);
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
              key: const Key('receiptBackButton'),
              tooltip: 'Volver a compras',
              onPressed: widget.onBack,
              icon: const Icon(Icons.arrow_back_rounded),
            ),
            title: const Text('COMPROBANTE DE VENTA'),
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
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_errorMessage != null) {
      return Column(
        children: [
          AuthStatusBanner(message: _errorMessage!),
          const SizedBox(height: 18),
          FilledButton.icon(
            key: const Key('retryReceiptButton'),
            onPressed: _load,
            icon: const Icon(Icons.refresh_rounded),
            label: const Text('Reintentar'),
          ),
        ],
      );
    }
    final receipt = _receipt!;
    return Column(
      key: const ValueKey('receiptContent'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _header(receipt),
        const SizedBox(height: 14),
        SizedBox(
          width: double.infinity,
          child: FilledButton.icon(
            key: const Key('receiptPdfButton'),
            onPressed: _pdfBusy ? null : _showPdfOptions,
            icon: _pdfBusy
                ? const SizedBox.square(
                    dimension: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.picture_as_pdf_outlined),
            label: Text(_pdfBusy ? 'Preparando comprobante...' : 'Descargar / imprimir comprobante'),
          ),
        ),
        const SizedBox(height: 20),
        _section('PRODUCTOS', receipt.products.map(_productRow)),
        const SizedBox(height: 16),
        _totals(receipt),
        const SizedBox(height: 16),
        _payment(receipt.payment),
      ],
    );
  }

  Widget _header(SaleReceipt receipt) => Container(
    width: double.infinity,
    padding: const EdgeInsets.all(18),
    decoration: BoxDecoration(color: AppColors.white, borderRadius: BorderRadius.circular(14), border: Border.all(color: AppColors.line)),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('FASHIONSTORE', style: TextStyle(color: AppColors.terracotta, fontSize: 11, fontWeight: FontWeight.w800, letterSpacing: 2)),
        const SizedBox(height: 12),
        Text(receipt.saleCode, maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(color: AppColors.espresso, fontSize: 23, fontWeight: FontWeight.w800)),
        const SizedBox(height: 10),
        _infoRow('Fecha', _date(receipt.completedDate)),
        _infoRow('Cliente', receipt.client == null ? 'No disponible' : '${receipt.client!.name} ${receipt.client!.lastName}'),
        _infoRow('Sucursal', '${receipt.branch.name}\n${receipt.branch.address}'),
      ],
    ),
  );

  Widget _section(String title, Iterable<Widget> children) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text(title, style: const TextStyle(color: AppColors.terracotta, fontSize: 11, fontWeight: FontWeight.w800, letterSpacing: 1.5)),
      const SizedBox(height: 10),
      ...children,
    ],
  );

  Widget _productRow(ReceiptItem item) => Container(
    width: double.infinity,
    margin: const EdgeInsets.only(bottom: 10),
    padding: const EdgeInsets.all(14),
    decoration: BoxDecoration(color: AppColors.white, borderRadius: BorderRadius.circular(12), border: Border.all(color: AppColors.line)),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(child: Text('${item.name ?? 'Producto'}\n${item.size ?? ''}${item.color == null ? '' : ' · ${item.color}'}', maxLines: 3, overflow: TextOverflow.ellipsis)),
        const SizedBox(width: 10),
        Flexible(child: Text('${item.quantity} x ${formatCatalogMoney(item.unitPrice - item.unitDiscount)}', textAlign: TextAlign.right, maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w700))),
      ],
    ),
  );

  Widget _totals(SaleReceipt receipt) => Container(
    width: double.infinity,
    padding: const EdgeInsets.all(16),
    decoration: BoxDecoration(color: AppColors.white, borderRadius: BorderRadius.circular(12), border: Border.all(color: AppColors.line)),
    child: Column(children: [
      _infoRow('Subtotal', formatCatalogMoney(receipt.subtotal)),
      _infoRow('Descuento', formatCatalogMoney(receipt.discountTotal)),
      const Divider(height: 18),
      _infoRow('Total', formatCatalogMoney(receipt.total), strong: true),
    ]),
  );

  Widget _payment(ReceiptPayment payment) => Container(
    width: double.infinity,
    padding: const EdgeInsets.all(16),
    decoration: BoxDecoration(color: AppColors.white, borderRadius: BorderRadius.circular(12), border: Border.all(color: AppColors.line)),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('PAGO', style: TextStyle(color: AppColors.terracotta, fontSize: 11, fontWeight: FontWeight.w800, letterSpacing: 1.5)),
        const SizedBox(height: 10),
        _infoRow('Medio', payment.method),
        _infoRow('Estado', payment.state),
        _infoRow('Importe', formatCatalogMoney(payment.amount), strong: true),
      ],
    ),
  );

  Widget _infoRow(String label, String value, {bool strong = false}) => Padding(
    padding: const EdgeInsets.only(bottom: 8),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: TextStyle(color: strong ? AppColors.espresso : AppColors.muted, fontWeight: strong ? FontWeight.w800 : FontWeight.w600)),
        const Spacer(),
        const SizedBox(width: 12),
        Flexible(child: Text(value, textAlign: TextAlign.right, maxLines: 3, overflow: TextOverflow.ellipsis, style: TextStyle(color: AppColors.espresso, fontWeight: strong ? FontWeight.w800 : FontWeight.w700))),
      ],
    ),
  );

  String _date(DateTime? value) => value == null ? 'Fecha no disponible' : MaterialLocalizations.of(context).formatMediumDate(value.toLocal());

  Future<void> _showPdfOptions() async {
    final action = await showModalBottomSheet<_ReceiptPdfAction>(
      context: context,
      builder: (sheetContext) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: const Icon(Icons.share_outlined),
              title: const Text('Guardar o compartir PDF'),
              onTap: () => Navigator.of(sheetContext).pop(_ReceiptPdfAction.share),
            ),
            ListTile(
              leading: const Icon(Icons.print_outlined),
              title: const Text('Imprimir comprobante'),
              onTap: () => Navigator.of(sheetContext).pop(_ReceiptPdfAction.print),
            ),
          ],
        ),
      ),
    );
    if (!mounted || action == null) return;
    setState(() => _pdfBusy = true);
    try {
      final bytes = await _buildPdf(_receipt!);
      if (action == _ReceiptPdfAction.share) {
        await Printing.sharePdf(
          bytes: bytes,
          filename: 'comprobante-${_receipt!.saleCode}.pdf',
        );
      } else {
        await Printing.layoutPdf(
          name: 'Comprobante ${_receipt!.saleCode}',
          onLayout: (_) async => bytes,
        );
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('No pudimos generar el comprobante PDF.')),
        );
      }
    } finally {
      if (mounted) setState(() => _pdfBusy = false);
    }
  }

  Future<Uint8List> _buildPdf(SaleReceipt receipt) async {
    final document = pw.Document();
    final client = receipt.client == null
        ? 'No disponible'
        : '${receipt.client!.name} ${receipt.client!.lastName}';
    document.addPage(
      pw.MultiPage(
        pageFormat: pdf.PdfPageFormat.a4,
        build: (_) => [
          pw.Text('FASHIONSTORE', style: pw.TextStyle(fontSize: 18, fontWeight: pw.FontWeight.bold)),
          pw.SizedBox(height: 8),
          pw.Text('COMPROBANTE DE VENTA', style: pw.TextStyle(fontSize: 14, fontWeight: pw.FontWeight.bold)),
          pw.SizedBox(height: 14),
          pw.Text('Código: ${receipt.saleCode}'),
          pw.Text('Fecha: ${_date(receipt.completedDate)}'),
          pw.Text('Cliente: $client'),
          pw.Text('Sucursal: ${receipt.branch.name}'),
          pw.Text('Dirección: ${receipt.branch.address}'),
          pw.SizedBox(height: 18),
          pw.TableHelper.fromTextArray(
            headers: const ['Producto', 'Cantidad', 'Precio', 'Descuento', 'Subtotal'],
            data: receipt.products.map((item) => [
              '${item.name ?? 'Producto'}${item.size == null && item.color == null ? '' : ' (${item.size ?? ''}${item.color == null ? '' : ' · ${item.color}'})'}',
              '${item.quantity}',
              formatCatalogMoney(item.unitPrice),
              formatCatalogMoney(item.unitDiscount),
              formatCatalogMoney(item.lineSubtotal),
            ]).toList(growable: false),
          ),
          pw.SizedBox(height: 18),
          pw.Align(
            alignment: pw.Alignment.centerRight,
            child: pw.Column(
              crossAxisAlignment: pw.CrossAxisAlignment.end,
              children: [
                pw.Text('Subtotal: ${formatCatalogMoney(receipt.subtotal)}'),
                pw.Text('Descuentos: ${formatCatalogMoney(receipt.discountTotal)}'),
                pw.SizedBox(height: 4),
                pw.Text('Total: ${formatCatalogMoney(receipt.total)}', style: pw.TextStyle(fontWeight: pw.FontWeight.bold)),
              ],
            ),
          ),
          pw.SizedBox(height: 18),
          pw.Text('PAGO', style: pw.TextStyle(fontWeight: pw.FontWeight.bold)),
          pw.Text('Medio: ${receipt.payment.method}'),
          pw.Text('Estado: ${receipt.payment.state}'),
          pw.Text('Importe: ${formatCatalogMoney(receipt.payment.amount)}'),
        ],
      ),
    );
    return document.save();
  }
}

enum _ReceiptPdfAction { share, print }
