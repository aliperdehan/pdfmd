// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "pdfmdedit",
    platforms: [.macOS(.v13)],
    targets: [.executableTarget(name: "pdfmdedit", path: "Sources")]
)
