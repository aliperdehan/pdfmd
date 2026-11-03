#!/bin/zsh
# Build pdfmdedit.app (needs only the Command Line Tools). Output: build/pdfmdedit.app
#   ./build.sh            build only (nothing is launched)
#   ./build.sh --install  also copies the app to ~/Applications
# Test headless first:  .build/release/pdfmdedit --bench --mb 10   and   build/pdfmdedit.app/Contents/MacOS/pdfmdedit --smoke FILE.md
set -e
cd "$(dirname "$0")"
VERSION=$(sed -n 's/^let appVersion = "\(.*\)"/\1/p' Sources/pdfmdedit/Settings.swift)
swift build -c release
APP=build/pdfmdedit.app
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp .build/release/pdfmdedit "$APP/Contents/MacOS/pdfmdedit"
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleName</key><string>pdfmd Edit</string>
<key>CFBundleDisplayName</key><string>pdfmd Edit</string>
<key>CFBundleIdentifier</key><string>io.github.aliperdehan.pdfmdedit</string>
<key>CFBundleExecutable</key><string>pdfmdedit</string>
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
   <string>sty</string><string>cls</string><string>csl</string><string>yaml</string><string>yml</string><string>html</string>
   <string>bak</string><string>hst</string>
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
    rm -rf "$DEST/pdfmdedit.app"
    cp -R "$APP" "$DEST/pdfmdedit.app"
    echo "installed $DEST/pdfmdedit.app (not started)"
fi
