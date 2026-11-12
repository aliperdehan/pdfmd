import Foundation

extension Settings {
    /// Limits come from the consumer's conversions, not tunable performance caps. Double(Int.max)
    /// rounds UP on 64-bit machines; nextDown is the last Double that can actually become an Int.
    static func numericError(_ key: String, _ value: Double) -> String? {
        guard let item = items.first(where: { $0.key == key }) else { return nil }
        switch item.kind {
        case .flag:
            return [0, 1].contains(value) ? nil : "\(key): valid range is 0 or 1"
        case .choice(let choices):
            return choices.contains(value) ? nil : "\(key): valid range is \(choices.map(formatNumber).joined(separator: ", "))"
        case .number: break
        }
        let intMax = Double(Int.max).nextDown
        var upper = Double.greatestFiniteMagnitude
        var lower = 0.0
        var exclusiveLower = false
        switch key {
        case "lineNumberMinDigits", "statusSliceChars", "pdfContentsOpenLevels", "pdfReloadRetries",
             "popFormatKeep", "popErrorsListed", "popPdfmdLines", "popLogLookahead", "highlightMarginLines",
             "pdfSidebarWidth", "pdfThumbnailWidth", "popPngScale", "popInkScale":
            upper = intMax
        case "statusDelayMs", "highlightDelayMs", "scrollDelayMs", "htmlReloadDebounceMs", "htmlCoverMs",
             "studioPreviewDelayMs", "studioScrollDelayMs", "pdfReloadDebounceMs", "pdfReloadCoverMs",
             "diskChangeDelayMs", "popRenderDelayMs", "popPreambleDelayMs":
            // Dispatch converts milliseconds (including Int milliseconds) to signed 64-bit nanoseconds.
            upper = (Double(Int64.max) / 1_000_000).nextDown
        case "studioRenderTimeout", "studioServerTimeout", "buildTimeout", "buildStopGrace",
             "popTimeoutS", "popPdfmdTimeoutS", "popFormatTimeoutS":
            upper = (Double(Int64.max) / 1_000_000_000).nextDown
        case "popWarmWaitS":
            upper = (intMax / 10).nextDown // waitIdle converts seconds * 10 to an Int loop count
        case "popBorderPt", "popMaxWidthCm":
            upper = intMax // TeX source's short-number formatter and integer consumers
        default: break
        }
        switch key {
        case "statusSliceChars", "popFormatKeep":
            lower = 1 // these counts are consumed as Ints; truncation must still leave a positive count
        case "fontSize", "buildStopGrace", "studioServerTimeout", "popTimeoutS", "popPdfmdTimeoutS",
             "popFormatTimeoutS", "popMaxWidthCm", "popPngScale", "popInkScale", "popWidth", "popHeight",
             "popPaneHeight", "popEditorHeight", "popPreviewMinHeight", "studioPaneWidth",
             "studioMinEditorWidth", "studioMinPaneWidth", "pdfZoomMinPercent", "pdfZoomMaxPercent",
             "htmlZoomStepPercent", "pdfZoomStepPercent":
            exclusiveLower = true
        default: break
        }
        guard value.isFinite, exclusiveLower ? value > lower : value >= lower, value <= upper else {
            return "\(key): valid range is \(exclusiveLower ? "greater than" : "from") \(formatNumber(lower)) to \(formatNumber(upper)) (finite)"
        }
        return nil
    }

    /// Also used for damaged preferences, so listing/get/reset can recover without an Int conversion trap.
    static func formatNumber(_ value: Double) -> String {
        if let integer = Int(exactly: value) { return String(integer) }
        return String(value)
    }
}
