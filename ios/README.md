# Cadence iOS

SwiftUI app (iOS 17+) with HealthKit sync, text chat, voice check-ins, and progress charts.

## Generate the Xcode project

```bash
brew install xcodegen   # once
cd ios
xcodegen generate
open Cadence.xcodeproj
```

1. Select your Team under Signing & Capabilities.
2. Enable the HealthKit capability if Xcode did not pick up entitlements.
3. Run on Simulator (API at `http://127.0.0.1:8000/v1`) or a device (set Mac LAN IP in Log → API).

## Backend must be running

```bash
./scripts/dev_up.sh
```
