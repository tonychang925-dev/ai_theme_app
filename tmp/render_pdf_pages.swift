import Foundation
import PDFKit
import AppKit

func renderPage(_ page: PDFPage, scale: CGFloat = 2.0) -> NSImage? {
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

let args = CommandLine.arguments
guard args.count >= 4 else {
    fputs("usage: swift render_pdf_pages.swift <pdf_path> <out_dir> <max_pages>\n", stderr)
    exit(2)
}

let pdfURL = URL(fileURLWithPath: args[1])
let outDir = URL(fileURLWithPath: args[2], isDirectory: true)
let maxPages = Int(args[3]) ?? 3
try? FileManager.default.createDirectory(at: outDir, withIntermediateDirectories: true)

guard let doc = PDFDocument(url: pdfURL) else {
    fputs("failed to open pdf\n", stderr)
    exit(1)
}

let pageCount = min(doc.pageCount, maxPages)
for idx in 0..<pageCount {
    guard let page = doc.page(at: idx), let image = renderPage(page) else { continue }
    guard let tiff = image.tiffRepresentation,
          let rep = NSBitmapImageRep(data: tiff),
          let pngData = rep.representation(using: .png, properties: [:]) else {
        continue
    }
    let outPath = outDir.appendingPathComponent(String(format: "page_%02d.png", idx + 1))
    try pngData.write(to: outPath)
    print(outPath.path)
}
