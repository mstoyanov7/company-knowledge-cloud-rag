"""Regression fixture for the corrupted-setup-answer bug.

The "how to setup flutter embedded hmi" question used to produce a corrupted,
metadata-only answer even though the OneNote page contains a full setup
procedure. This fixture provides:

* ``FLUTTER_HMI_HTML`` - realistic OneNote page HTML (parser input).
* ``FLUTTER_HMI_CLEAN_TEXT`` - the clean Markdown-like text a healthy parser
  should produce (used directly by chunking/retrieval/context tests so they do
  not depend on the parser).
* ``flutter_hmi_document`` - builds a ``SourceDocument`` from the clean text.

OneNote-only. No SharePoint behavior.
"""

from __future__ import annotations

from datetime import UTC, datetime

from shared_schemas import SourceDocument


# A realistic OneNote HTML export. Commands live in their own <p> elements (as
# OneNote emits monospace code lines), the configuration section is an ordered
# list, and troubleshooting is a real table.
FLUTTER_HMI_HTML = """
<html>
<head><title>Flutter Embedded HMI Setup</title></head>
<body>
  <h1>Flutter Embedded HMI Setup</h1>

  <p>Projects Setup - 02 Flutter Embedded HMI Setup</p>
  <p>Flutter / Linux / Wayland / EGL</p>
  <p>Section: Projects Setup</p>
  <p>Repository: flutter-embedded-hmi</p>
  <p>Owner: HMI Platform Team</p>
  <p>Summary: Setup guide for a Flutter Linux embedded HMI shell with native plugin integration, Wayland runtime, and external texture rendering.</p>

  <h2>Overview</h2>
  <p>This project provides a Flutter-based embedded HMI shell for Linux targets. It supports screen layout, navigation, theme configuration, platform channels, external texture integration, and deployment into a Wayland compositor environment.</p>

  <h2>Prerequisites</h2>
  <ul>
    <li>Ubuntu 22.04 or compatible Linux development environment.</li>
    <li>Flutter stable SDK with Linux desktop support enabled.</li>
    <li>clang, cmake, ninja-build, pkg-config.</li>
    <li>GTK development packages for local desktop testing.</li>
    <li>Wayland, EGL, and OpenGL ES development packages.</li>
    <li>Target compositor or local Weston runtime.</li>
    <li>C++17 compiler for native plugin code.</li>
  </ul>

  <h2>Install</h2>
  <p>sudo apt update</p>
  <p>sudo apt install -y clang cmake ninja-build pkg-config libgtk-3-dev libwayland-dev libegl1-mesa-dev libgles2-mesa-dev</p>
  <p>flutter config --enable-linux-desktop</p>
  <p>flutter doctor</p>
  <p>git clone https://github.com/company/flutter-embedded-hmi.git</p>
  <p>cd flutter-embedded-hmi</p>
  <p>flutter pub get</p>

  <h2>Configuration</h2>
  <ol>
    <li>Edit config/hmi_profile.yaml.</li>
    <li>Set displayWidth and displayHeight to match the target screen.</li>
    <li>Set useExternalRenderer to true when native texture rendering is required.</li>
    <li>Set texturePluginName to the registered Linux plugin name.</li>
    <li>Set compositorMode to wayland for embedded target testing.</li>
    <li>Set assetMode to bundled for production builds.</li>
  </ol>

  <h2>Run</h2>
  <p>flutter run -d linux</p>
  <p>flutter build linux --release</p>
  <p>WAYLAND_DISPLAY=wayland-0 ./build/linux/x64/release/bundle/flutter_embedded_hmi</p>

  <h2>Verification</h2>
  <ul>
    <li>Flutter window starts and loads the home screen.</li>
    <li>Navigation between pages works.</li>
    <li>Native plugin registration appears in logs.</li>
    <li>External texture is created and updated.</li>
    <li>Wayland compositor does not report surface creation errors.</li>
    <li>Frame rendering remains stable during page transitions.</li>
  </ul>

  <h2>Troubleshooting</h2>
  <table>
    <tr><th>Problem</th><th>Suggested Check</th></tr>
    <tr><td>If MissingPluginException appears</td><td>confirm the plugin is included in generated_plugin_registrant.cc and packaged in the bundle.</td></tr>
    <tr><td>If Wayland surface fails</td><td>confirm WAYLAND_DISPLAY and XDG_RUNTIME_DIR are valid.</td></tr>
    <tr><td>If external texture stays black</td><td>verify the native renderer posts new frames and texture ID is passed to Dart.</td></tr>
    <tr><td>If GTK build works but embedded launcher fails</td><td>inspect whether the launcher loads plugin shared libraries.</td></tr>
    <tr><td>If EGL initialization fails</td><td>confirm GPU device permissions and EGL driver availability.</td></tr>
  </table>
</body>
</html>
"""


# Clean Markdown-like text that a healthy parser produces from the HTML above.
# Code/commands live in fenced ```bash blocks, configuration stays a numbered
# list, and troubleshooting is a Markdown table. Used by chunking/retrieval/
# context/fallback tests so they do not depend on the parser implementation.
FLUTTER_HMI_CLEAN_TEXT = """# Flutter Embedded HMI Setup

Projects Setup - 02 Flutter Embedded HMI Setup

Flutter / Linux / Wayland / EGL

Section: Projects Setup

Repository: flutter-embedded-hmi

Owner: HMI Platform Team

Summary: Setup guide for a Flutter Linux embedded HMI shell with native plugin integration, Wayland runtime, and external texture rendering.

## Overview

This project provides a Flutter-based embedded HMI shell for Linux targets. It supports screen layout, navigation, theme configuration, platform channels, external texture integration, and deployment into a Wayland compositor environment.

## Prerequisites

- Ubuntu 22.04 or compatible Linux development environment.
- Flutter stable SDK with Linux desktop support enabled.
- clang, cmake, ninja-build, pkg-config.
- GTK development packages for local desktop testing.
- Wayland, EGL, and OpenGL ES development packages.
- Target compositor or local Weston runtime.
- C++17 compiler for native plugin code.

## Install

```bash
sudo apt update
sudo apt install -y clang cmake ninja-build pkg-config libgtk-3-dev libwayland-dev libegl1-mesa-dev libgles2-mesa-dev
flutter config --enable-linux-desktop
flutter doctor
git clone https://github.com/company/flutter-embedded-hmi.git
cd flutter-embedded-hmi
flutter pub get
```

## Configuration

1. Edit config/hmi_profile.yaml.
2. Set displayWidth and displayHeight to match the target screen.
3. Set useExternalRenderer to true when native texture rendering is required.
4. Set texturePluginName to the registered Linux plugin name.
5. Set compositorMode to wayland for embedded target testing.
6. Set assetMode to bundled for production builds.

## Run

```bash
flutter run -d linux
flutter build linux --release
WAYLAND_DISPLAY=wayland-0 ./build/linux/x64/release/bundle/flutter_embedded_hmi
```

## Verification

- Flutter window starts and loads the home screen.
- Navigation between pages works.
- Native plugin registration appears in logs.
- External texture is created and updated.
- Wayland compositor does not report surface creation errors.
- Frame rendering remains stable during page transitions.

## Troubleshooting

| Problem | Suggested Check |
| --- | --- |
| If MissingPluginException appears | confirm the plugin is included in generated_plugin_registrant.cc and packaged in the bundle. |
| If Wayland surface fails | confirm WAYLAND_DISPLAY and XDG_RUNTIME_DIR are valid. |
| If external texture stays black | verify the native renderer posts new frames and texture ID is passed to Dart. |
| If GTK build works but embedded launcher fails | inspect whether the launcher loads plugin shared libraries. |
| If EGL initialization fails | confirm GPU device permissions and EGL driver availability. |"""


def flutter_hmi_document(
    *,
    content_text: str = FLUTTER_HMI_CLEAN_TEXT,
    tenant_id: str = "local-tenant",
    acl_tags: tuple[str, ...] = ("employees",),
) -> SourceDocument:
    """Build a ``SourceDocument`` for the Flutter Embedded HMI setup page."""

    return SourceDocument(
        tenant_id=tenant_id,
        source_system="onenote",
        source_container="sites/projects/Projects Setup",
        source_item_id="onenote:flutter-embedded-hmi",
        source_url="https://contoso.example.test/onenote/flutter-embedded-hmi",
        title="Flutter Embedded HMI Setup",
        file_name="Flutter Embedded HMI Setup.one",
        file_extension="one",
        mime_type="text/html",
        section_path="Projects Setup / 02 Flutter Embedded HMI Setup",
        last_modified_utc=datetime(2026, 5, 20, tzinfo=UTC),
        acl_tags=list(acl_tags),
        content_hash="flutter-hmi-hash",
        content_text=content_text,
        tags=["onenote", "projects-setup", "flutter", "setup"],
        metadata={
            "notebook_id": "nb-projects",
            "notebook_name": "Projects Setup",
            "section_id": "sec-flutter-hmi",
            "section_name": "02 Flutter Embedded HMI Setup",
            "page_id": "flutter-embedded-hmi",
            "last_edited_by": "HMI Platform Team",
        },
    )
