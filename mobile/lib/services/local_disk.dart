/// design/408 - whether this build has app folders on a local disk.
///
/// The web build has none: path_provider has no web plugin and dart:io files
/// throw. Every disk store asks this before it asks for its folder, and acts as
/// unbound when the answer is no, so a web session keeps nothing locally and
/// reads everything from the server.
library;

import 'package:flutter/foundation.dart';

/// Lets a VM test take the web path without a browser.
@visibleForTesting
bool debugNoLocalDisk = false;

bool get localDiskAvailable => !kIsWeb && !debugNoLocalDisk;
