import Foundation
import Darwin

/// Read actual arguments and working directories, not ps's ambiguous printable command line.
enum BuildWatcher {
    static func matches(_ args: [String], directory: URL, file: URL) -> Bool {
        guard args.contains("-w") || args.contains("--watch") else { return false }
        guard args.contains(where: { ["pdfmd", "pdfmd.py"].contains(URL(fileURLWithPath: $0).lastPathComponent) }) else { return false }
        let wanted = file.resolvingSymlinksInPath().standardizedFileURL
        return args.contains { arg in
            guard !arg.hasPrefix("-") else { return false }
            let candidate = URL(fileURLWithPath: arg, relativeTo: directory).resolvingSymlinksInPath().standardizedFileURL
            return candidate == wanted
        }
    }

    static func processArguments(_ pid: pid_t, buffer bytes: inout [UInt8]) -> [String]? {
        var size = bytes.count
        var mib: [Int32] = [CTL_KERN, KERN_PROCARGS2, pid]
        guard sysctl(&mib, 3, &bytes, &size, nil, 0) == 0, size >= MemoryLayout<Int32>.size else { return nil }
        let count = bytes.withUnsafeBytes { $0.loadUnaligned(as: Int32.self) }
        guard count > 0 else { return nil }
        var i = MemoryLayout<Int32>.size
        while i < size && bytes[i] != 0 { i += 1 } // executable path
        while i < size && bytes[i] == 0 { i += 1 }
        var args: [String] = []
        while i < size && args.count < count {
            let start = i
            while i < size && bytes[i] != 0 { i += 1 }
            guard i < size else { return nil }
            args.append(String(decoding: bytes[start..<i], as: UTF8.self))
            i += 1
        }
        return args.count == count ? args : nil
    }

    static func workingDirectory(_ pid: pid_t) -> URL? {
        var info = proc_vnodepathinfo()
        guard proc_pidinfo(pid, PROC_PIDVNODEPATHINFO, 0, &info, Int32(MemoryLayout<proc_vnodepathinfo>.size)) > 0 else { return nil }
        let path = withUnsafePointer(to: &info.pvi_cdir.vip_path) {
            $0.withMemoryRebound(to: CChar.self, capacity: Int(MAXPATHLEN)) { String(cString: $0) }
        }
        return path.isEmpty ? nil : URL(fileURLWithPath: path, isDirectory: true)
    }

    static func find(_ file: URL) -> String? {
        var argmax: Int32 = 0
        var size = MemoryLayout<Int32>.size
        var limit: [Int32] = [CTL_KERN, KERN_ARGMAX]
        guard sysctl(&limit, 2, &argmax, &size, nil, 0) == 0, argmax > 0 else { return nil }
        var buffer = [UInt8](repeating: 0, count: Int(argmax))
        var count = proc_listallpids(nil, 0)
        guard count > 0 else { return nil }
        var pids = [pid_t](repeating: 0, count: Int(count))
        count = proc_listallpids(&pids, Int32(pids.count * MemoryLayout<pid_t>.size))
        guard count > 0 else { return nil }
        for pid in pids.prefix(Int(count)) where pid > 0 {
            guard let args = processArguments(pid, buffer: &buffer), args.contains("-w") || args.contains("--watch"),
                  let directory = workingDirectory(pid), matches(args, directory: directory, file: file) else { continue }
            return args.joined(separator: " ")
        }
        return nil
    }
}
