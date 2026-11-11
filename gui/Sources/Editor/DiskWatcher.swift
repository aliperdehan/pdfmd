import Cocoa

/// Follows one file on disk: calls `onChange` (on the main thread, after a short pause so that a burst of writes is one call) when another
/// program wrote, renamed over or deleted it. A program that saves by writing a new file and renaming it over the old one leaves this
/// watcher on the old file, so after a rename or a delete it opens the new one.
final class DiskWatcher {
    private let url: URL
    private let onChange: () -> Void
    private var source: DispatchSourceFileSystemObject?
    private var directory: DispatchSourceFileSystemObject?
    private var needsReattachment = false
    private var pending: DispatchWorkItem?

    init(url: URL, onChange: @escaping () -> Void) {
        self.url = url
        self.onChange = onChange
        let fd = open(url.deletingLastPathComponent().path, O_EVTONLY)
        if fd >= 0 {
            let s = DispatchSource.makeFileSystemObjectSource(fileDescriptor: fd, eventMask: [.write], queue: .main)
            s.setEventHandler { [weak self] in
                guard let self, self.source == nil else { return }
                self.watch()
                if self.source != nil { self.fired(replaced: false) }
            }
            s.setCancelHandler { close(fd) }
            s.resume()
            directory = s
        }
        watch()
    }

    deinit { stop() }

    func stop() {
        pending?.cancel(); pending = nil
        source?.cancel(); source = nil
        directory?.cancel(); directory = nil
    }

    private func watch() {
        source?.cancel(); source = nil
        let fd = open(url.path, O_EVTONLY)
        guard fd >= 0 else { return }
        let s = DispatchSource.makeFileSystemObjectSource(fileDescriptor: fd, eventMask: [.write, .extend, .attrib, .rename, .delete], queue: .main)
        s.setEventHandler { [weak self, weak s] in self?.fired(replaced: s?.data.contains(.rename) == true || s?.data.contains(.delete) == true) }
        s.setCancelHandler { close(fd) }
        s.resume()
        source = s
    }

    private func fired(replaced: Bool) {
        needsReattachment = needsReattachment || replaced
        pending?.cancel()
        let work = DispatchWorkItem { [weak self] in
            guard let self else { return }
            if self.needsReattachment {
                self.needsReattachment = false
                self.watch()
            }
            self.onChange()
        }
        pending = work
        DispatchQueue.main.asyncAfter(deadline: .now() + Settings.number("diskChangeDelayMs") / 1000, execute: work)
    }
}
