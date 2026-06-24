/**
 * macOS Vision OCR 命令行工具。
 * WHY: 利用 Apple Silicon 神经引擎硬件加速，对工程扫描件/分布图进行
 *      高精度中英文混合文字识别，零第三方依赖。
 *
 * 用法: ocr_vision <image_path>
 * 输出: 逐行输出识别到的文字（从上到下排列），置信度 > 0.3 的结果。
 * 编译: swiftc -O ocr_vision.swift -o ocr_vision
 */
import Foundation
import Vision

// ── 参数校验 ──
guard CommandLine.arguments.count > 1 else {
    fputs("用法: ocr_vision <图片路径>\n", stderr)
    exit(1)
}

let imagePath = CommandLine.arguments[1]
let imageURL = URL(fileURLWithPath: imagePath)

// ── 加载图片 ──
guard let imageSource = CGImageSourceCreateWithURL(imageURL as CFURL, nil),
      let cgImage = CGImageSourceCreateImageAtIndex(imageSource, 0, nil) else {
    fputs("错误: 无法加载图片 \(imagePath)\n", stderr)
    exit(1)
}

// ── 配置 Vision OCR 请求 ──
let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.recognitionLanguages = ["zh-Hans", "zh-Hant", "en"]
request.usesLanguageCorrection = true

// ── 执行识别 ──
let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
do {
    try handler.perform([request])
} catch {
    fputs("错误: OCR 识别失败 - \(error.localizedDescription)\n", stderr)
    exit(1)
}

// ── 输出结果 ──
guard let observations = request.results else { exit(0) }

for observation in observations {
    guard let candidate = observation.topCandidates(1).first else { continue }
    // WHY: 过滤低置信度噪声（<0.3），避免将乱码文字入库污染向量库
    if candidate.confidence > 0.3 {
        print(candidate.string)
    }
}
