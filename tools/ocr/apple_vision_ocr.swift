import AppKit
import Foundation
import Vision

guard CommandLine.arguments.count == 2 else {
    fputs("usage: apple_vision_ocr.swift IMAGE\n", stderr)
    exit(64)
}
let imageURL = URL(fileURLWithPath: CommandLine.arguments[1])
guard let image = NSImage(contentsOf: imageURL),
      let data = image.tiffRepresentation,
      let representation = NSBitmapImageRep(data: data),
      let cgImage = representation.cgImage else {
    fputs("image_unreadable\n", stderr)
    exit(65)
}

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.recognitionLanguages = ["ru-RU", "en-US"]
request.usesLanguageCorrection = false
request.minimumTextHeight = 0.005

let handler = VNImageRequestHandler(cgImage: cgImage, orientation: .up, options: [:])
do {
    try handler.perform([request])
} catch {
    fputs("vision_request_failed\n", stderr)
    exit(70)
}

var observations: [[String: Any]] = []
for observation in request.results ?? [] {
    guard let candidate = observation.topCandidates(1).first else { continue }
    let box = observation.boundingBox
    let top = 1.0 - Double(box.origin.y + box.height)
    let bottom = 1.0 - Double(box.origin.y)
    observations.append([
        "text": candidate.string,
        "confidence": Double(candidate.confidence),
        "region": [Double(box.origin.x), top, Double(box.origin.x + box.width), bottom]
    ])
}
observations.sort {
    let left = $0["region"] as! [Double]
    let right = $1["region"] as! [Double]
    if abs(left[1] - right[1]) > 0.005 { return left[1] < right[1] }
    return left[0] < right[0]
}
let output: [String: Any] = [
    "adapter": "apple-vision-accurate",
    "language_correction": false,
    "observations": observations
]
let outputData = try JSONSerialization.data(withJSONObject: output, options: [.sortedKeys])
FileHandle.standardOutput.write(outputData)
