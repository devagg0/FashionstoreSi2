import 'dart:io';
import 'dart:math' as math;
import 'dart:typed_data';
import 'dart:ui';

import 'package:flutter_pose_detection/flutter_pose_detection.dart';

import 'virtual_try_on_models.dart';

abstract interface class PoseDetectionEngine {
  Future<void> initialize();
  Future<PoseDetectionFrame> detect(Uint8List imageBytes);
  void dispose();
}

class PoseDetectionFrame {
  const PoseDetectionFrame({required this.landmarks});

  final Map<LandmarkType, BodyLandmarkPoint> landmarks;
}

class MediaPipePoseDetectionEngine implements PoseDetectionEngine {
  MediaPipePoseDetectionEngine({NpuPoseDetector? detector})
    : _detector =
          detector ?? NpuPoseDetector(config: PoseDetectorConfig.accurate());

  final NpuPoseDetector _detector;

  @override
  Future<void> initialize() async {
    await _detector.initialize();
  }

  @override
  Future<PoseDetectionFrame> detect(Uint8List imageBytes) async {
    final result = await _detector.detectPose(imageBytes);
    final pose = result.firstPose;
    if (pose == null) return const PoseDetectionFrame(landmarks: {});
    return PoseDetectionFrame(
      landmarks: {
        for (final type in const [
          LandmarkType.leftShoulder,
          LandmarkType.rightShoulder,
          LandmarkType.leftHip,
          LandmarkType.rightHip,
        ])
          type: _landmark(pose.getLandmark(type)),
      },
    );
  }

  static BodyLandmarkPoint _landmark(PoseLandmark landmark) =>
      BodyLandmarkPoint(
        x: landmark.x,
        y: landmark.y,
        visibility: landmark.visibility,
      );

  @override
  void dispose() => _detector.dispose();
}

class BodyPoseDetectionFailure implements Exception {
  const BodyPoseDetectionFailure(this.message);

  final String message;
}

class BodyPoseDetectionService {
  BodyPoseDetectionService({PoseDetectionEngine? engine})
    : _engine = engine ?? MediaPipePoseDetectionEngine();

  final PoseDetectionEngine _engine;
  bool _initialized = false;

  Future<BodyPoseAnalysis> analyzePhoto(String imagePath) async {
    try {
      if (!_initialized) {
        await _engine.initialize();
        _initialized = true;
      }
      final imageBytes = await File(imagePath).readAsBytes();
      final frame = await _engine.detect(imageBytes);
      return _buildAnalysis(frame.landmarks);
    } on BodyPoseDetectionFailure {
      rethrow;
    } catch (_) {
      throw const BodyPoseDetectionFailure(
        'No pudimos analizar la postura de la foto.',
      );
    }
  }

  BodyPoseAnalysis _buildAnalysis(
    Map<LandmarkType, BodyLandmarkPoint> landmarks,
  ) {
    final leftShoulder = _required(landmarks, LandmarkType.leftShoulder);
    final rightShoulder = _required(landmarks, LandmarkType.rightShoulder);
    final leftHip = _required(landmarks, LandmarkType.leftHip);
    final rightHip = _required(landmarks, LandmarkType.rightHip);
    const threshold = .5;
    if ([
      leftShoulder,
      rightShoulder,
      leftHip,
      rightHip,
    ].any((point) => point.visibility < threshold)) {
      throw const BodyPoseDetectionFailure(
        'No identificamos con suficiente claridad hombros y cadera. Intenta otra foto.',
      );
    }

    final shoulderCenter = _midpoint(leftShoulder, rightShoulder);
    final hipCenter = _midpoint(leftHip, rightHip);
    final torsoCenter = Offset(
      shoulderCenter.dx,
      (shoulderCenter.dy + hipCenter.dy) / 2,
    );
    final shoulderWidth = _distance(leftShoulder, rightShoulder);
    final torsoHeight = (hipCenter.dy - shoulderCenter.dy).abs();
    return BodyPoseAnalysis(
      leftShoulder: leftShoulder,
      rightShoulder: rightShoulder,
      leftHip: leftHip,
      rightHip: rightHip,
      shoulderCenter: shoulderCenter,
      torsoCenter: torsoCenter,
      hipCenter: hipCenter,
      shoulderWidth: shoulderWidth,
      torsoHeight: torsoHeight,
      // Normalized values reserved for the future garment transform.
      // Calibrado CU27: 1.35 dejaba la prenda demasiado ancha; 1.15 cubre
      // hombros con un pequeño margen de caída sin verse sobredimensionada.
      garmentScale: shoulderWidth * 1.15,
      garmentOffset: Offset(
        shoulderCenter.dx,
        shoulderCenter.dy - torsoHeight * .12,
      ),
    );
  }

  static BodyLandmarkPoint _required(
    Map<LandmarkType, BodyLandmarkPoint> landmarks,
    LandmarkType type,
  ) =>
      landmarks[type] ??
      (throw const BodyPoseDetectionFailure(
        'No se encontró un punto corporal necesario.',
      ));

  static Offset _midpoint(BodyLandmarkPoint first, BodyLandmarkPoint second) =>
      Offset((first.x + second.x) / 2, (first.y + second.y) / 2);

  static double _distance(BodyLandmarkPoint first, BodyLandmarkPoint second) {
    final dx = first.x - second.x;
    final dy = first.y - second.y;
    return math.sqrt(dx * dx + dy * dy);
  }

  void dispose() => _engine.dispose();
}
