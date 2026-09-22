import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_pose_detection/flutter_pose_detection.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/features/virtual_try_on/body_pose_detection_service.dart';
import 'package:mobile/features/virtual_try_on/virtual_try_on_models.dart';

void main() {
  test('analiza una foto estática y obtiene puntos corporales', () async {
    final photo = File('${Directory.systemTemp.path}/pose-test.jpg');
    await photo.writeAsBytes(const [1, 2, 3, 4]);
    final engine = _FakePoseEngine();
    final service = BodyPoseDetectionService(engine: engine);

    final result = await service.analyzePhoto(photo.path);

    expect(engine.receivedBytes, [1, 2, 3, 4]);
    expect(result.shoulderCenter, const Offset(.5, .3));
    expect(result.hipCenter, const Offset(.5, .65));
    expect(result.torsoHeight, closeTo(.35, .0001));
    expect(result.garmentScale, closeTo(.345, .0001)); // calibrado CU27: *1.15
    expect(result.garmentOffset.dy, closeTo(.258, .0001));
    await photo.delete();
    service.dispose();
  });
}

class _FakePoseEngine implements PoseDetectionEngine {
  List<int>? receivedBytes;

  @override
  Future<void> initialize() async {}

  @override
  Future<PoseDetectionFrame> detect(Uint8List imageBytes) async {
    receivedBytes = imageBytes;
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
