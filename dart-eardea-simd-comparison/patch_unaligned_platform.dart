// Add two native-endian ByteData methods to a COPY of the installed platform.
// This changes SDK Dart code only. The existing VM load intrinsic is reused.
import 'dart:io';
import 'package:kernel/ast.dart';
import 'package:kernel/clone.dart';
import 'package:kernel/kernel.dart';

Future<void> main(List<String> args) async {
  if (args.length != 2 || File(args[0]).absolute.path == File(args[1]).absolute.path) {
    throw ArgumentError('Usage: patch_unaligned_platform.dart INPUT.dill NEW_OUTPUT.dill');
  }
  if (File(args[1]).existsSync()) throw StateError('Output already exists');
  final component = loadComponentFromBinary(args[0]);
  final library = component.libraries.singleWhere((l) => l.importUri.toString() == 'dart:typed_data');
  final view = library.classes.singleWhere((c) => c.name == '_ByteDataView');
  final original = view.procedures.singleWhere((p) => p.name.text == 'getFloat32x4');
  final originalBody = original.function.body;
  if (originalBody is! Block || originalBody.statements.length != 3 ||
      originalBody.statements.last is! ReturnStatement ||
      original.function.positionalParameters.length != 2) {
    throw StateError('Unexpected SDK method shape; refusing to patch');
  }
  for (final unchecked in [false, true]) {
    final name = unchecked ? 'unsafeLoadFloat32x4Unaligned' : 'loadFloat32x4Unaligned';
    if (view.procedures.any((p) => p.name.text == name)) {
      throw StateError('SDK already contains $name');
    }
    final function = CloneVisitorNotMembers().clone<FunctionNode>(original.function);
    // The optional endian argument is unused in the original SDK method. The
    // prototype explicitly promises native endian and accepts just byteOffset.
    function.positionalParameters.removeLast();
    if (unchecked) {
      // Omit the two byte-range checks; retain the original intrinsic call and
      // backing-view offset calculation. No other SDK method is changed.
      final result = (function.body as Block).statements.last;
      function.body = result..parent = function;
    }
    view.addProcedure(Procedure(Name(name), ProcedureKind.Method, function,
        fileUri: original.fileUri)
      ..fileOffset = original.fileOffset
      ..fileEndOffset = original.fileEndOffset);
    print('Added _ByteDataView.$name: ${unchecked ? "no input checks" : "two input byte-range checks"}');
  }
  component.computeCanonicalNames();
  await writeComponentToBinary(component, args[1]);
  final roundTrip = loadComponentFromBinary(args[1]);
  final roundTripView = roundTrip.libraries
      .singleWhere((l) => l.importUri.toString() == 'dart:typed_data').classes
      .singleWhere((c) => c.name == '_ByteDataView');
  for (final name in ['loadFloat32x4Unaligned', 'unsafeLoadFloat32x4Unaligned']) {
    roundTripView.procedures.singleWhere((p) => p.name.text == name);
  }
  print('Wrote and round-trip validated ${args[1]}');
}
