import Foundation
import PDFKit
import Vision
import AppKit

func renderPage(_ page: PDFPage, scale: CGFloat = 1.0) -> NSImage? {
    let bounds = page.bounds(for: .mediaBox)
    let width = max(Int(bounds.width * scale), 1)
    let height = max(Int(bounds.height * scale), 1)
    let image = NSImage(size: NSSize(width: width, height: height))
    image.lockFocus()
    guard let ctx = NSGraphicsContext.current?.cgContext else {
        image.unlockFocus()
        return nil
    }
    ctx.setFillColor(NSColor.white.cgColor)
    ctx.fill(CGRect(x: 0, y: 0, width: width, height: height))
    ctx.saveGState()
    ctx.scaleBy(x: scale, y: scale)
    page.draw(with: .mediaBox, to: ctx)
    ctx.restoreGState()
    image.unlockFocus()
    return image
}

func recognizeText(_ image: NSImage) throws -> String {
    guard let tiff = image.tiffRepresentation,
          let bitmap = NSBitmapImageRep(data: tiff),
          let cgImage = bitmap.cgImage else {
        return ""
    }
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .fast
    request.usesLanguageCorrection = true
    request.recognitionLanguages = ["zh-Hans", "en-US"]
    let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
    try handler.perform([request])
    let observations = request.results ?? []
    return observations.compactMap { $0.topCandidates(1).first?.string }.joined(separator: "\n")
}

let args = CommandLine.arguments
guard args.count >= 2 else {
    fputs("usage: swift read_pdf_ocr.swift <pdf_path> [max_pages]\n", stderr)
    exit(2)
}

let pdfURL = URL(fileURLWithPath: args[1])
let maxPages = args.count >= 3 ? (Int(args[2]) ?? 1) : 1

guard let doc = PDFDocument(url: pdfURL) else {
    fputs("failed to open pdf\n", stderr)
    exit(1)
}

let pageCount = min(doc.pageCount, maxPages)
for idx in 0..<pageCount {
    guard let page = doc.page(at: idx), let image = renderPage(page) else { continue }
    let text = try recognizeText(image)
    print("=== 第\(idx + 1)页 ===")
    print(text)
    print()
}
