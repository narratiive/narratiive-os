import AppKit
import Foundation
import Vision

guard CommandLine.arguments.count == 3 else {
    fputs("usage: ocr_rendered_slides.swift <slides-dir> <output-json>\n", stderr)
    exit(2)
}

let slidesDirectory = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
let outputURL = URL(fileURLWithPath: CommandLine.arguments[2])
let manager = FileManager.default
let slideURLs = try manager.contentsOfDirectory(
    at: slidesDirectory,
    includingPropertiesForKeys: nil,
    options: [.skipsHiddenFiles]
).filter { $0.pathExtension.lowercased() == "png" }.sorted { $0.lastPathComponent < $1.lastPathComponent }

var results: [[String: Any]] = []
for url in slideURLs {
    guard
        let image = NSImage(contentsOf: url),
        let data = image.tiffRepresentation,
        let representation = NSBitmapImageRep(data: data),
        let cgImage = representation.cgImage
    else {
        throw NSError(domain: "NarratiiveOCR", code: 1, userInfo: [NSLocalizedDescriptionKey: "Unable to read \(url.path)"])
    }
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = true
    request.recognitionLanguages = ["en-GB"]
    let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
    try handler.perform([request])
    let observations = (request.results ?? []).compactMap { observation -> [String: Any]? in
        guard let candidate = observation.topCandidates(1).first else { return nil }
        let box = observation.boundingBox
        return [
            "text": candidate.string,
            "confidence": candidate.confidence,
            "x": box.origin.x,
            "y": box.origin.y,
            "width": box.size.width,
            "height": box.size.height,
        ]
    }.sorted { left, right in
        let leftY = left["y"] as? Double ?? 0
        let rightY = right["y"] as? Double ?? 0
        if abs(leftY - rightY) > 0.015 { return leftY > rightY }
        return (left["x"] as? Double ?? 0) < (right["x"] as? Double ?? 0)
    }
    results.append([
        "file": url.lastPathComponent,
        "text": observations.compactMap { $0["text"] as? String }.joined(separator: "\n"),
        "observations": observations,
    ])
}

let encoded = try JSONSerialization.data(withJSONObject: ["slides": results], options: [.prettyPrinted, .sortedKeys])
try encoded.write(to: outputURL, options: .atomic)
