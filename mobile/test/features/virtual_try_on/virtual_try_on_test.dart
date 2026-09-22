import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_pose_detection/flutter_pose_detection.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/core/theme/app_theme.dart';
import 'package:mobile/features/catalog/catalog_service.dart';
import 'package:mobile/features/catalog/catalog_models.dart';
import 'package:mobile/features/catalog/product_detail_screen.dart';
import 'package:mobile/features/virtual_try_on/virtual_try_on_models.dart';
import 'package:mobile/features/virtual_try_on/body_pose_detection_service.dart';
import 'package:mobile/features/virtual_try_on/virtual_try_on_service.dart';
import 'package:mobile/features/virtual_try_on/virtual_try_on_screen.dart';

import '../catalog/catalog_test_data.dart';

void main() {
  testWidgets('abre el vestidor desde una prenda y muestra la foto capturada', (
    tester,
  ) async {
    final capturedPhoto = File(
      '${Directory.systemTemp.path}/virtual-try-on-captured.jpg',
    );
    await capturedPhoto.writeAsBytes(base64Decode(
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
    ));
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        home: ProductDetailScreen(
          productId: 10,
          catalogGateway: _CatalogGateway(),
          virtualTryOnGateway: _CameraGateway(capturedPhoto.path),
          bodyPoseService: BodyPoseDetectionService(engine: _PoseEngine()),
        ),
      ),
    );
    await tester.pumpAndSettle();

    final tryOnButton = find.byKey(const Key('openVirtualTryOnButton'));
    await tester.drag(
      find.byKey(const Key('productDetailScrollView')),
      const Offset(0, -900),
    );
    await tester.pumpAndSettle();
    await tester.tap(tryOnButton);
    await tester.pumpAndSettle();
    expect(find.byType(VirtualTryOnScreen), findsOneWidget);

    final captureButton = find.byKey(const Key('captureVirtualTryOnButton'));
    await tester.drag(
      find.byKey(const Key('virtualTryOnScrollView')),
      const Offset(0, -500),
    );
    await tester.pumpAndSettle();
    await tester.tap(captureButton);
    await tester.pump();
    expect(find.byKey(const Key('virtualTryOnPhotoPreview')), findsOneWidget);
    expect(find.byKey(const Key('virtualTryOnGarmentOverlay')), findsOneWidget);
    await capturedPhoto.delete();
  });
}

class _CameraGateway implements VirtualTryOnGateway {
  _CameraGateway(this.path);

  final String path;

  @override
  Future<VirtualTryOnPhoto?> capturePhoto() async =>
      VirtualTryOnPhoto(path: path);
}

class _PoseEngine implements PoseDetectionEngine {
  @override
  Future<void> initialize() async {}

  @override
  Future<PoseDetectionFrame> detect(Uint8List imageBytes) async {
    const point = BodyLandmarkPoint(x: .5, y: .5, visibility: 1);
    return const PoseDetectionFrame(
      landmarks: {
        LandmarkType.leftShoulder: point,
        LandmarkType.rightShoulder: point,
        LandmarkType.leftHip: point,
        LandmarkType.rightHip: point,
      },
    );
  }

  @override
  void dispose() {}
}

class _CatalogGateway implements CatalogGateway {
  @override
  Future<CatalogProductDetail> loadProductDetail(int productId) async =>
      catalogDetail(
        gallery: const [
          CatalogImageData(
            id: 1,
            url: 'https://cdn.test/chaqueta-transparent.png',
            isPrimary: true,
          ),
        ],
      );

  @override
  Future<CatalogPage> loadProducts(CatalogFilters filters) =>
      throw UnimplementedError();
}
