import 'dart:ui';

class VirtualTryOnPhoto {
  const VirtualTryOnPhoto({required this.path});

  final String path;
}

class BodyLandmarkPoint {
  const BodyLandmarkPoint({
    required this.x,
    required this.y,
    required this.visibility,
  });

  final double x;
  final double y;
  final double visibility;

  Offset get normalizedOffset => Offset(x, y);
}

class BodyPoseAnalysis {
  const BodyPoseAnalysis({
    required this.leftShoulder,
    required this.rightShoulder,
    required this.leftHip,
    required this.rightHip,
    required this.shoulderCenter,
    required this.torsoCenter,
    required this.hipCenter,
    required this.shoulderWidth,
    required this.torsoHeight,
    required this.garmentScale,
    required this.garmentOffset,
  });

  final BodyLandmarkPoint leftShoulder;
  final BodyLandmarkPoint rightShoulder;
  final BodyLandmarkPoint leftHip;
  final BodyLandmarkPoint rightHip;
  final Offset shoulderCenter;
  final Offset torsoCenter;
  final Offset hipCenter;
  final double shoulderWidth;
  final double torsoHeight;
  final double garmentScale;
  final Offset garmentOffset;
}

enum VirtualTryOnFailureType { permissionDenied, unavailable, captureFailed }

class VirtualTryOnFailure implements Exception {
  const VirtualTryOnFailure(this.type, this.message);

  final VirtualTryOnFailureType type;
  final String message;
}
