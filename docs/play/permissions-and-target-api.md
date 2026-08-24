# Android permissions & target-API audit (PLAY-3)

Record of what the app requests and why, so the Play submission has no
unexplained permissions and the target API is a deliberate, pinned value.

## Target / compile SDK

Pinned explicitly in `mobile/android/app/build.gradle.kts` rather than inherited
from `flutter.*`, so a Flutter upgrade can't silently change what the app targets:

| Setting | Value | Notes |
| --- | --- | --- |
| `minSdk` | 24 | Floor required by google_sign_in (Credential Manager). |
| `targetSdk` | 36 | Android 16. (35/Android 15 was the 2025 floor; `androidx.core:1.17` also requires compiling against ≥36.) **Confirm the current Play requirement at submission.** |
| `compileSdk` | 36 | Kept equal to `targetSdk`; also the minimum some androidx deps require. |

> Play raises the minimum target API about once a year. When it moves, bump
> `targetSdk` **and** `compileSdk` together and re-run the mobile build.

## Permissions

The **explicitly declared** permission set (`AndroidManifest.xml`) is minimal:

| Permission | Where | Justification |
| --- | --- | --- |
| `INTERNET` | main manifest | All API calls. Flutter only injects it into debug/profile automatically, so release must declare it or every network call fails. |

**Merged in by plugins** (appear in the final merged manifest, not our source):

| Permission | Source | Justification |
| --- | --- | --- |
| `POST_NOTIFICATIONS` | firebase_messaging | Android 13+ runtime permission for match-alert notifications. |
| `WAKE_LOCK` / FCM receivers | firebase_messaging / play-services | Standard FCM message delivery. |

**Deliberately absent:**

- **`QUERY_ALL_PACKAGES`** — not declared. Package visibility is handled by the
  standard Flutter `<queries>` block (a single `PROCESS_TEXT` intent), which is
  scoped and doesn't trigger the sensitive-permission review that
  `QUERY_ALL_PACKAGES` does.
- No location, contacts, storage, camera, microphone, SMS, or phone permissions.

## Verify before submission

- Run the mobile build and open the **merged** manifest
  (`mobile/build/app/outputs/.../AndroidManifest.xml` or the AAB) to confirm the
  merged permission set matches the table above — plugins can add permissions on
  upgrade.
- Check the Play Console **pre-launch report** for permission or target-API
  policy warnings.
