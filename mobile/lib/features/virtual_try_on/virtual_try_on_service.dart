import 'package:image_picker/image_picker.dart';
import 'package:permission_handler/permission_handler.dart';

import 'virtual_try_on_models.dart';

abstract interface class VirtualTryOnGateway {
  Future<VirtualTryOnPhoto?> capturePhoto();
}

class VirtualTryOnService implements VirtualTryOnGateway {
  VirtualTryOnService({ImagePicker? picker})
    : _picker = picker ?? ImagePicker();

  final ImagePicker _picker;

  @override
  Future<VirtualTryOnPhoto?> capturePhoto() async {
    final permission = await Permission.camera.request();
    if (!permission.isGranted) {
      throw const VirtualTryOnFailure(
        VirtualTryOnFailureType.permissionDenied,
        'Necesitamos permiso para usar la cámara y probar la prenda.',
      );
    }

    try {
      final photo = await _picker.pickImage(
        source: ImageSource.camera,
        imageQuality: 88,
        maxWidth: 1600,
      );
      return photo == null ? null : VirtualTryOnPhoto(path: photo.path);
    } catch (_) {
      throw const VirtualTryOnFailure(
        VirtualTryOnFailureType.captureFailed,
        'No pudimos capturar la foto. Inténtalo nuevamente.',
      );
    }
  }
}
