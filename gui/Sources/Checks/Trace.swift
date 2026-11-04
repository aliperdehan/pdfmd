import Cocoa

/// A developer's trace for the viewer: with `PDFMDEDIT_TRACE=1` in the environment, the page, zoom, view size and scroll position are
/// written to `/tmp/pdfmdedit-trace.log` as they change, together with every moment the main thread was blocked for longer than
/// `PDFMDEDIT_TRACE_STALL` ms (default 150). Off (and free) otherwise. It exists because a lag or a runaway scroll cannot be
/// reproduced without a hand, and the log says what the program did while the hand did it.
enum Trace {
    static let on = ProcessInfo.processInfo.environment["PDFMDEDIT_TRACE"] != nil
    private static let started = Date()
    private static var handle: FileHandle? = {
        FileManager.default.createFile(atPath: "/tmp/pdfmdedit-trace.log", contents: nil)
        return FileHandle(forWritingAtPath: "/tmp/pdfmdedit-trace.log")
    }()
    private static var lastTick = Date()
    private static var timer: Timer?

    static func log(_ text: @autoclosure () -> String) {
        guard on else { return }
        let line = String(format: "%8.3f  ", Date().timeIntervalSince(started)) + text() + "\n"
        handle?.write(Data(line.utf8))
    }

    /// Starts the stall detector (a timer that only fires when the main thread is free).
    static func watchStalls() {
        guard on, timer == nil else { return }
        let limit = Double(ProcessInfo.processInfo.environment["PDFMDEDIT_TRACE_STALL"] ?? "") ?? 150
        timer = Timer.scheduledTimer(withTimeInterval: 0.02, repeats: true) { _ in
            let now = Date(); let gap = now.timeIntervalSince(lastTick) * 1000; lastTick = now
            if gap > limit { log(String(format: "STALL the main thread was blocked for %.0f ms", gap)) }
        }
        RunLoop.main.add(timer!, forMode: .common)
    }
}
