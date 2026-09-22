import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_pose_detection/flutter_pose_detection.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/features/virtual_try_on/body_pose_detection_service.dart';
import 'package:mobile/features/virtual_try_on/virtual_try_on_models.dart';
import 'package:mobile/features/virtual_try_on/virtual_try_on_screen.dart';

// CU27: la prenda deja de ser un overlay fijo y se ajusta con los mismos
// landmarks (hombros, torso, cadera) que ya calcula BodyPoseDetectionService.
// Esta prueba usa esa misma pose ya calculada (sin reimplementarla) y valida
// que computeGarmentRect la traduzca en escala, centro y alto correctos
// dentro del contenedor de previsualización.
void main() {
  test(
    'ajusta escala, centro y altura de la prenda según la postura detectada',
    () async {
      final photo = File('${Directory.systemTemp.path}/cu27-overlay-test.jpg');
      await photo.writeAsBytes(const [1, 2, 3, 4]);
      final service = BodyPoseDetectionService(engine: _FakePoseEngine());
      final pose = await service.analyzePhoto(photo.path);
      service.dispose();
      await photo.delete();

      // Misma pose que body_pose_detection_service_test.dart:
      // shoulderCenter (.5,.3), hipCenter (.5,.65), torsoCenter (.5,.475),
      // shoulderWidth .3, torsoHeight .35, garmentScale .345 (calibrado CU27).
      const box = Size(620, 390);
      final rect = computeGarmentRect(pose, box);

      const expectedWidth = .345 * 620; // garmentScale * ancho del box
      const expectedHeight = .35 * 390 * garmentLengthFactor; // torsoHeight * alto * factor
      const expectedCenterX = .5 * 620; // torsoCenter.dx * ancho
      const expectedCenterY = .475 * 390; // torsoCenter.dy * alto

      expect(rect.width, closeTo(expectedWidth, .001));
      expect(rect.height, closeTo(expectedHeight, .001));
      expect(rect.left, closeTo(expectedCenterX - expectedWidth / 2, .001));
      expect(rect.top, closeTo(expectedCenterY - expectedHeight / 2, .001));

      // El centro de la prenda debe coincidir con el torso detectado, no con
      // el punto fijo que usaba el overlay anterior.
      expect(rect.center.dx, closeTo(expectedCenterX, .001));
      expect(rect.center.dy, closeTo(expectedCenterY, .001));
    },
  );
}

class _FakePoseEngine implements PoseDetectionEngine {
  @override
  Future<void> initialize() async {}

  @override
  Future<PoseDetectionFrame> detect(Uint8List imageBytes) async {
    BodyLandmarkPoint point(double x, double y) =>
        BodyLandmarkPoint(x: x, y: y, visibility: .95);
    return PoseDetectionFrame(
      landmarks: {
        LandmarkType.leftShoulder: point(.35, .3),
        LandmarkType.rightShoulder: point(.65, .3),
        LandmarkType.leftHip: point(.4, .65),
        LandmarkType.rightHip: point(.6, .65),
      },
    );
  }

  @override
  void dispose() {}
}
