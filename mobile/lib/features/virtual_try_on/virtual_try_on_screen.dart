import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/theme/app_theme.dart';
import '../auth/widgets/auth_components.dart';
import 'body_pose_detection_service.dart';
import 'virtual_try_on_models.dart';
import 'virtual_try_on_service.dart';

class VirtualTryOnScreen extends StatefulWidget {
  const VirtualTryOnScreen({
    super.key,
    required this.productName,
    required this.garmentImageUrl,
    this.gateway,
    this.bodyPoseService,
  });

  final String productName;
  final String? garmentImageUrl;
  final VirtualTryOnGateway? gateway;
  final BodyPoseDetectionService? bodyPoseService;

  @override
  State<VirtualTryOnScreen> createState() => _VirtualTryOnScreenState();
}

class _VirtualTryOnScreenState extends State<VirtualTryOnScreen> {
  late final VirtualTryOnGateway _gateway;
  late final BodyPoseDetectionService _bodyPoseService;
  VirtualTryOnPhoto? _photo;
  BodyPoseAnalysis? _bodyPose;
  String? _errorMessage;
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    _gateway = widget.gateway ?? VirtualTryOnService();
    _bodyPoseService = widget.bodyPoseService ?? BodyPoseDetectionService();
  }

  @override
  void dispose() {
    _bodyPoseService.dispose();
    super.dispose();
  }

  Future<void> _capturePhoto() async {
    if (_loading) return;
    setState(() {
      _loading = true;
      _errorMessage = null;
    });
    try {
      final photo = await _gateway.capturePhoto();
      if (!mounted) return;
      if (photo != null) {
        final bodyPose = await _bodyPoseService.analyzePhoto(photo.path);
        if (!mounted) return;
        setState(() {
          _photo = photo;
          _bodyPose = bodyPose;
        });
      }
    } on VirtualTryOnFailure catch (error) {
      if (mounted) setState(() => _errorMessage = error.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    body: SafeArea(
      child: CustomScrollView(
        key: const Key('virtualTryOnScrollView'),
        slivers: [
          SliverAppBar(
            pinned: true,
            backgroundColor: AppColors.linen,
            surfaceTintColor: AppColors.linen,
            leading: IconButton(
              key: const Key('virtualTryOnBackButton'),
              tooltip: 'Volver al detalle',
              onPressed: () => Navigator.of(context).pop(),
              icon: const Icon(Icons.arrow_back_rounded),
            ),
            title: const Text('VESTIDOR VIRTUAL'),
          ),
          SliverPadding(
            padding: const EdgeInsets.fromLTRB(22, 20, 22, 36),
            sliver: SliverToBoxAdapter(
              child: Center(
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 620),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'PRUEBA LA PRENDA',
                        style: TextStyle(
                          color: AppColors.terracotta,
                          fontSize: 11,
                          fontWeight: FontWeight.w800,
                          letterSpacing: 1.8,
                        ),
                      ),
                      const SizedBox(height: 8),
                      Text(
                        widget.productName,
                        style: const TextStyle(
                          color: AppColors.espresso,
                          fontSize: 27,
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                      const SizedBox(height: 8),
                      const Text(
                        'Captura una foto para verla como referencia con la prenda seleccionada superpuesta.',
                        style: TextStyle(
                          color: AppColors.muted,
                          fontSize: 14,
                          height: 1.5,
                        ),
                      ),
                      const SizedBox(height: 22),
                      _preview(),
                      if (_errorMessage != null) ...[
                        const SizedBox(height: 16),
                        AuthStatusBanner(message: _errorMessage!),
                      ],
                      if (_bodyPose != null) ...[
                        const SizedBox(height: 12),
                        Text(
                          'Postura detectada: hombros, torso y cadera listos para ajustar la prenda.',
                          key: const Key('bodyPoseDetectedMessage'),
                          style: const TextStyle(
                            color: AppColors.success,
                            fontSize: 13,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ],
                      const SizedBox(height: 18),
                      FilledButton.icon(
                        key: const Key('captureVirtualTryOnButton'),
                        onPressed: _loading ? null : _capturePhoto,
                        icon: _loading
                            ? const SizedBox.square(
                                dimension: 19,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                  color: AppColors.white,
                                ),
                              )
                            : const Icon(Icons.camera_alt_outlined),
                        label: Text(
                          _photo == null ? 'Abrir cámara' : 'Tomar otra foto',
                        ),
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

  Widget _preview() {
    final photo = _photo;
    if (photo == null) {
      return Container(
        key: const Key('virtualTryOnEmptyPreview'),
        width: double.infinity,
        height: 390,
        decoration: BoxDecoration(
          color: AppColors.white,
          border: Border.all(color: AppColors.line),
          borderRadius: BorderRadius.circular(16),
        ),
        child: const Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.camera_front_outlined,
              size: 54,
              color: AppColors.terracotta,
            ),
            SizedBox(height: 14),
            Text(
              'Tu foto aparecerá aquí',
              style: TextStyle(
                color: AppColors.espresso,
                fontWeight: FontWeight.w700,
              ),
            ),
            SizedBox(height: 6),
            Text(
              'Busca buena luz y encuadra tu figura',
              style: TextStyle(color: AppColors.muted, fontSize: 13),
            ),
          ],
        ),
      );
    }
    return ClipRRect(
      key: const Key('virtualTryOnPhotoPreview'),
      borderRadius: BorderRadius.circular(16),
      child: SizedBox(
        width: double.infinity,
        height: 390,
        child: LayoutBuilder(
          builder: (context, constraints) => Stack(
            alignment: Alignment.center,
            fit: StackFit.expand,
            children: [
              Image.file(
                File(photo.path),
                fit: BoxFit.cover,
                errorBuilder: (_, _, _) => const ColoredBox(
                  color: AppColors.white,
                  child: Center(child: Text('No se pudo mostrar la foto.')),
                ),
              ),
              if (widget.garmentImageUrl != null)
                _garmentOverlay(widget.garmentImageUrl!, constraints),
            ],
          ),
        ),
      ),
    );
  }

  // Ajusta la prenda con los landmarks ya detectados (hombros, torso y
  // cadera): escala según el ancho de hombros, se centra en el torso y su
  // altura sigue el largo de torso. Sin postura detectada, mantiene el
  // encuadre fijo anterior como respaldo.
  Widget _garmentOverlay(String garmentImageUrl, BoxConstraints constraints) {
    final pose = _bodyPose;
    if (pose == null) {
      return Positioned.fill(
        key: const Key('virtualTryOnGarmentOverlay'),
        child: Padding(
          padding: EdgeInsets.zero,
          child: GarmentOverlayImage(url: garmentImageUrl),
        ),
      );
    }

    final rect = computeGarmentRect(
      pose,
      Size(constraints.maxWidth, constraints.maxHeight),
    );

    return Positioned(
      key: const Key('virtualTryOnGarmentOverlay'),
      left: rect.left,
      top: rect.top,
      width: rect.width,
      height: rect.height,
      child: GarmentOverlayImage(url: garmentImageUrl),
    );
  }
}

// Calibrado CU27: 1.35 estiraba la prenda ~35% más allá de la cadera y se
// veía demasiado larga/holgada. 1.06 cubre el torso completo con un pequeño
// remate bajo la cadera (dobladillo), sin quedar sobredimensionada.
const double garmentLengthFactor = 1.06;

/// Calcula el rectángulo (en píxeles) donde debe dibujarse la prenda dentro
/// del contenedor de previsualización de tamaño [box], a partir de los
/// landmarks ya calculados por BodyPoseDetectionService: escala horizontal
/// según el ancho de hombros (garmentScale), escala vertical según el largo
/// de torso (torsoHeight) y posición vertical centrada en el torso
/// detectado (torsoCenter), en vez de un desplazamiento fijo desde el
/// hombro.
///
/// Al centrar la altura calibrada (torso + un pequeño remate) sobre
/// torsoCenter, el borde superior queda apenas por encima de la línea de
/// hombros de forma proporcional -justo lo necesario para que el cuello de
/// la prenda se alinee con la zona superior del torso sin verse "flotando".
///
/// shoulderWidth/torsoHeight/torsoCenter son fracciones (0-1) de la foto,
/// igual que en body_pose_detection_service_test.dart, y se llevan a
/// píxeles con el tamaño real del contenedor.
Rect computeGarmentRect(BodyPoseAnalysis pose, Size box) {
  final width = pose.garmentScale * box.width;
  final height = pose.torsoHeight * box.height * garmentLengthFactor;
  final torsoCenterY = pose.torsoCenter.dy * box.height;
  final centerX = pose.shoulderCenter.dx * box.width;
  return Rect.fromLTWH(
    centerX - width / 2,
    torsoCenterY - height / 2,
    width,
    height,
  );
}

/// Loads the PNG, trims transparent margins, then paints only the garment
/// pixels into the pose-derived rectangle. This keeps transparent canvas
/// padding from making the shirt look like a floating box.
class GarmentOverlayImage extends StatefulWidget {
  const GarmentOverlayImage({super.key, required this.url});

  final String url;

  @override
  State<GarmentOverlayImage> createState() => _GarmentOverlayImageState();
}

class _GarmentOverlayImageState extends State<GarmentOverlayImage> {
  ui.Image? _image;
  Rect? _sourceRect;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _image?.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final data = await NetworkAssetBundle(Uri.parse(widget.url))
          .load(widget.url);
      final bytes = data.buffer.asUint8List();
      final codec = await ui.instantiateImageCodec(bytes);
      final frame = await codec.getNextFrame();
      final image = frame.image;
      final sourceRect = await _opaqueBounds(image);
      if (!mounted) {
        image.dispose();
        return;
      }
      setState(() {
        _image = image;
        _sourceRect = sourceRect;
      });
    } catch (_) {
      // A failed remote image leaves the overlay empty without covering the photo.
    }
  }

  Future<Rect> _opaqueBounds(ui.Image image) async {
    final byteData = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
    if (byteData == null) {
      return Rect.fromLTWH(
        0,
        0,
        image.width.toDouble(),
        image.height.toDouble(),
      );
    }
    final pixels = byteData.buffer.asUint8List();
    var left = image.width;
    var top = image.height;
    var right = -1;
    var bottom = -1;
    for (var y = 0; y < image.height; y++) {
      for (var x = 0; x < image.width; x++) {
        final alpha = pixels[(y * image.width + x) * 4 + 3];
        if (alpha > 8) {
          if (x < left) left = x;
          if (x > right) right = x;
          if (y < top) top = y;
          if (y > bottom) bottom = y;
        }
      }
    }
    if (right < left || bottom < top) {
      return Rect.fromLTWH(
        0,
        0,
        image.width.toDouble(),
        image.height.toDouble(),
      );
    }
    return Rect.fromLTRB(
      left.toDouble(),
      top.toDouble(),
      right + 1.0,
      bottom + 1.0,
    );
  }

  @override
  Widget build(BuildContext context) {
    final image = _image;
    final sourceRect = _sourceRect;
    if (image == null || sourceRect == null) return const SizedBox.shrink();
    return CustomPaint(
      painter: _GarmentPainter(image: image, sourceRect: sourceRect),
      size: Size.infinite,
    );
  }
}

class _GarmentPainter extends CustomPainter {
  const _GarmentPainter({required this.image, required this.sourceRect});

  final ui.Image image;
  final Rect sourceRect;

  @override
  void paint(Canvas canvas, Size size) {
    final destination = Offset.zero & size;
    canvas.drawImageRect(
      image,
      sourceRect,
      destination,
      Paint()..filterQuality = FilterQuality.high,
    );
  }

  @override
  bool shouldRepaint(_GarmentPainter oldDelegate) =>
      oldDelegate.image != image || oldDelegate.sourceRect != sourceRect;
}
