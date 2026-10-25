// Experimental native-endian loads backed by two methods added to a COPY of
// the SDK platform kernel. Both inline to the VM's existing typed-data load.
// No FFI, native function call, temporary lane array, or per-load view creation.
import 'dart:typed_data';

@pragma('vm:prefer-inline')
Float32x4 loadUnalignedChecked(ByteData bytes, int byteOffset) =>
    (bytes as dynamic).loadFloat32x4Unaligned(byteOffset) as Float32x4;

// Caller must establish 0 <= byteOffset <= bytes.lengthInBytes - 16.
@pragma('vm:prefer-inline')
Float32x4 loadUnalignedUnchecked(ByteData bytes, int byteOffset) =>
    (bytes as dynamic).unsafeLoadFloat32x4Unaligned(byteOffset) as Float32x4;
