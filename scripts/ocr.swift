// 用 macOS Vision 识别 PDF：段落（RecognizeDocumentsRequest）+ 单行（VNRecognizeTextRequest，用来补段落字母）
// 输出 JSON: [{page, paras:[{t,x,y,w,h}], lines:[{t,x,y,w,h}]}]，坐标为 0-1 比例，y 从上往下
// 用法: ocr in.pdf out.json [起始页] [结束页] [左边界 右边界]
//       最后两个参数（0-1）只识别页面的这一竖条，用于左右两栏的页面
import Foundation
import PDFKit
import Vision
import AppKit


let args = CommandLine.arguments
let pdf = PDFDocument(url: URL(fileURLWithPath: args[1]))!
let outPath = args[2]
let first = args.count > 3 ? Int(args[3])! : 1
let last = args.count > 4 ? Int(args[4])! : pdf.pageCount
let cropX0 = args.count > 6 ? Double(args[5])! : 0.0
let cropX1 = args.count > 6 ? Double(args[6])! : 1.0

func rect(_ r: CGRect) -> [String: Double] {
    // 裁剪坐标换算回整页坐标
    let w = cropX1 - cropX0
    return ["x": cropX0 + r.minX * w, "y": 1 - r.maxY, "w": r.width * w, "h": r.height]
}
var pages: [[String: Any]] = []
let sem = DispatchSemaphore(value: 0)

Task {
    for i in (first-1)..<last {
        guard let page = pdf.page(at: i) else { continue }
        let box = page.bounds(for: .mediaBox)
        let scale = 2400 / max(box.width, box.height)
        let img = page.thumbnail(of: NSSize(width: box.width*scale, height: box.height*scale), for: .mediaBox)
        var r = NSRect(origin: .zero, size: img.size)
        guard let full = img.cgImage(forProposedRect: &r, context: nil, hints: nil) else { continue }
        let cropRect = CGRect(x: Double(full.width) * cropX0, y: 0,
                              width: Double(full.width) * (cropX1 - cropX0), height: Double(full.height))
        guard let cg = full.cropping(to: cropRect) else { continue }
        var paras: [[String: Any]] = []
        if let obs = try? await RecognizeDocumentsRequest().perform(on: cg) {
            for o in obs {
                for p in o.document.paragraphs {
                    var d: [String: Any] = rect(p.boundingRegion.boundingBox.cgRect)
                    d["t"] = p.transcript
                    paras.append(d)
                }
            }
        }
        var lines: [[String: Any]] = []
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = true
        try? VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
        for o in req.results ?? [] {
            guard let c = o.topCandidates(1).first else { continue }
            var d: [String: Any] = rect(o.boundingBox)
            d["t"] = c.string
            lines.append(d)
        }
        pages.append(["page": i + 1, "paras": paras, "lines": lines])
        FileHandle.standardError.write("page \(i+1)/\(last)\n".data(using: .utf8)!)
    }
    sem.signal()
}
sem.wait()
try! JSONSerialization.data(withJSONObject: pages).write(to: URL(fileURLWithPath: outPath))
