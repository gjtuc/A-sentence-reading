/// The phone has no full-screen request; its system bars stay as they are.
bool supported() => false;

bool isOn() => false;

void onChange(void Function() handler) {}

Future<bool> enter() async => false;

Future<void> exit() async {}

void onNextGesture(void Function() handler) {}

void onNextGestureSwallowed(void Function() handler) {}

void tellPeer(bool on) {}

void onPeer(void Function(bool on) handler) {}
