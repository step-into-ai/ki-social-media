# Third-party components

The original KI Social Media source is MIT licensed. Third-party components keep
their respective licenses. No ownership of third-party platform content is claimed.

| Component | Use | License / upstream |
| --- | --- | --- |
| AndroidX / Jetpack Compose | Android UI, lifecycle, WebView helpers | Apache-2.0, https://android.googlesource.com/platform/frameworks/support/ |
| Kotlin runtime | Android language runtime | Apache-2.0, https://github.com/JetBrains/kotlin |
| OkHttp / Okio | Android networking | Apache-2.0, https://github.com/square/okhttp and https://github.com/square/okio |
| Gradle wrapper | Build tooling | Apache-2.0, https://github.com/gradle/gradle |
| Playwright Docker seccomp profile | Chromium user-namespace sandbox support | Apache-2.0, https://github.com/microsoft/playwright/blob/main/utils/docker/seccomp_profile.json |
| Agent Reach 1.6.1 | Optional platform toolkit | MIT, https://github.com/Panniantong/Agent-Reach/tree/v1.6.1 |
| yt-dlp | Metadata and optional audio extraction | Unlicense; see dependencies/exceptions, https://github.com/yt-dlp/yt-dlp |
| whisper.cpp 1.9.5 | Optional local language/transcription CLI | MIT, https://github.com/ggml-org/whisper.cpp |
| Whisper Tiny model | Optional local speech model | MIT, https://github.com/openai/whisper |

Apache-2.0 and dependency notices for the Android binary are also included in the
APK's `assets/NOTICE.txt`. Upstream dependencies of optional tools are installed
with their package metadata and license files. Linux packages in the operator-built
container retain their license documentation under `/usr/share/doc`; in particular,
FFmpeg licensing depends on the Debian package build and Chromium has its own
third-party notices. They are not relicensed by this project.

The browser/Node toolkit downloaded by Agent Reach remains an optional upstream
installation in the operator's private data volume. Its own licenses apply.
YouTube, TikTok and X names identify supported services and do not imply endorsement.
