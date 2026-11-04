#!/bin/zsh
# Build Colophon.app (needs only the Command Line Tools). Output: build.noindex/Colophon.app
# (build.noindex: Spotlight and LaunchServices skip a folder with that suffix, so the build output is not a second "Colophon" next to the installed copy.)
#   ./build.sh            build only (nothing is launched)
#   ./build.sh --install  also copies the app to ~/Applications
# Test headless first:  .build/release/pdfmdedit --bench --mb 10   and   build.noindex/Colophon.app/Contents/MacOS/pdfmdedit --smoke FILE.md
set -e
cd "$(dirname "$0")"
VERSION=$(sed -n 's/^let appVersion = "\(.*\)"/\1/p' Sources/Settings/Settings.swift)
swift build -c release
APP=build.noindex/Colophon.app
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp .build/release/pdfmdedit "$APP/Contents/MacOS/pdfmdedit"
cp -R Themes "$APP/Contents/Resources/Themes"
cp Resources/pdfmd.icns "$APP/Contents/Resources/pdfmd.icns"   # made by ../scripts/build_brand.py --render
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleName</key><string>Colophon</string>
<key>CFBundleDisplayName</key><string>Colophon</string>
<key>CFBundleIdentifier</key><string>io.github.aliperdehan.pdfmdedit</string>
<key>CFBundleExecutable</key><string>pdfmdedit</string>
<key>CFBundleIconFile</key><string>pdfmd</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>$VERSION</string>
<key>CFBundleVersion</key><string>$VERSION</string>
<key>LSMinimumSystemVersion</key><string>13.0</string>
<key>NSHighResolutionCapable</key><true/>
<key>NSPrincipalClass</key><string>NSApplication</string>
<key>CFBundleDocumentTypes</key><array>
 <dict>
  <key>CFBundleTypeName</key><string>Markdown and text</string>
  <key>CFBundleTypeRole</key><string>Editor</string>
  <key>LSHandlerRank</key><string>Alternate</string>
  <key>NSDocumentClass</key><string>EditorDocument</string>
  <key>LSItemContentTypes</key><array>
   <string>net.daringfireball.markdown</string>
   <string>public.plain-text</string>
  </array>
  <key>CFBundleTypeExtensions</key><array>
   <string>md</string><string>markdown</string><string>qmd</string><string>txt</string><string>tex</string><string>typ</string>
   <string>sty</string><string>cls</string><string>csl</string><string>yaml</string><string>yml</string>
   <string>bak</string><string>hst</string>
  </array>
 </dict>
 <dict>
  <key>CFBundleTypeName</key><string>HTML document</string>
  <key>CFBundleTypeRole</key><string>Viewer</string>
  <key>LSHandlerRank</key><string>Alternate</string>
  <key>NSDocumentClass</key><string>HTMLViewerDocument</string>
  <key>LSItemContentTypes</key><array>
   <string>public.html</string>
  </array>
  <key>CFBundleTypeExtensions</key><array>
   <string>html</string><string>htm</string><string>xhtml</string>
  </array>
 </dict>
 <dict>
  <key>CFBundleTypeName</key><string>PDF document</string>
  <key>CFBundleTypeRole</key><string>Viewer</string>
  <key>LSHandlerRank</key><string>Alternate</string>
  <key>NSDocumentClass</key><string>PDFViewerDocument</string>
  <key>LSItemContentTypes</key><array>
   <string>com.adobe.pdf</string>
  </array>
  <key>CFBundleTypeExtensions</key><array>
   <string>pdf</string>
  </array>
 </dict>
</array>
</dict></plist>
PLIST
codesign --force --sign - "$APP"
echo "built $APP ($VERSION)"

if [[ "$1" == "--install" ]]; then
    DEST="$HOME/Applications"
    mkdir -p "$DEST"
    rm -rf "$DEST/pdfmdedit.app"   # the app's name before it was called Colophon (same bundle id: two copies would fight over Open With)
    rm -rf "$DEST/Colophon.app"
    cp -R "$APP" "$DEST/Colophon.app"
    echo "installed $DEST/Colophon.app (not started)"
fi
