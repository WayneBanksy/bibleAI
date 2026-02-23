// swift-tools-version: 5.9
// BibleTherapistCore — pure Swift library (no SwiftUI).
// SwiftUI app target lives in App/ (add to an Xcode project).

import PackageDescription

let package = Package(
    name: "BibleTherapist",
    platforms: [
        .iOS(.v17),
        .macOS(.v14),
    ],
    products: [
        .library(name: "BibleTherapistCore", targets: ["BibleTherapistCore"]),
    ],
    targets: [
        .target(
            name: "BibleTherapistCore",
            path: "Sources/BibleTherapistCore"
        ),
        .testTarget(
            name: "BibleTherapistCoreTests",
            dependencies: ["BibleTherapistCore"],
            path: "Tests/BibleTherapistCoreTests"
        ),
    ]
)
