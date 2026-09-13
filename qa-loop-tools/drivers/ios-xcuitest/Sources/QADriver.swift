// QADriver — the ios-xcuitest backend of the qa-loop driver contract.
// Serves simulator-driving commands from a per-device directory on the HOST
// filesystem (simulator processes share it), so a tester can drive any app
// from Bash without the MCP control tool's per-device access grant.
// One long-running test method = one worker session.
//
// The TARGET APP is a runtime parameter: start.sh passes its bundle id via
// TEST_RUNNER_QA_DRIVER_BUNDLE_ID (xcodebuild strips the prefix, so it
// arrives here as QA_DRIVER_BUNDLE_ID). Nothing app-specific lives in this
// file — keep it that way; app quirks belong in the target repo's
// HARNESS_NOTES.md, not in the backend.
//
// Protocol (see qa.py, the only client you should use):
//   dir  = /private/tmp/qa-driver/<SIMULATOR_UDID>
//   cmd  = dir/cmd/<seq>.txt      (written by the client; one command)
//   out  = dir/out/<seq>.txt      (written by us: "OK <payload>" or "ERR <reason>")
//   alive= dir/alive              (touched every loop tick — the client's liveness probe)
// Coordinates are DEVICE POINTS in the app's frame (portrait 402x874 on an
// iPhone 17 Pro; landscape swaps them after `rotate`).
import XCTest

final class QADriverTests: XCTestCase {
    var app: XCUIApplication!
    var issues: [String] = []

    /// XCUITest reports element trouble ("failed to get matching snapshot", "not hittable") as test
    /// failures, and a failure ends the test method — i.e. kills the server. Swallow them here and
    /// hand them back to the client inside the command's reply instead.
    override func record(_ issue: XCTIssue) {
        issues.append(issue.compactDescription.replacingOccurrences(of: "\n", with: " "))
    }

    var bundleId: String {
        ProcessInfo.processInfo.environment["QA_DRIVER_BUNDLE_ID"] ?? ""
    }
    var root: String {
        let udid = ProcessInfo.processInfo.environment["SIMULATOR_UDID"] ?? "unknown"
        return "/private/tmp/qa-driver/\(udid)"
    }

    func testServe() throws {
        continueAfterFailure = true
        guard !bundleId.isEmpty else {
            // start.sh always sets it; a bare xcodebuild invocation did not.
            print("QADRIVER FATAL: QA_DRIVER_BUNDLE_ID is not set — launch via start.sh <udid> <bundle-id>")
            return
        }
        app = XCUIApplication(bundleIdentifier: bundleId)
        let fm = FileManager.default
        try? fm.createDirectory(atPath: root + "/cmd", withIntermediateDirectories: true)
        try? fm.createDirectory(atPath: root + "/out", withIntermediateDirectories: true)
        let start = Date()
        let maxSeconds: TimeInterval = 5 * 3600
        var tick = 0
        print("QADRIVER serving \(root) for \(bundleId)")
        while Date().timeIntervalSince(start) < maxSeconds {
            tick += 1
            fm.createFile(atPath: root + "/alive", contents: Data("\(Date().timeIntervalSince1970)".utf8))
            guard let names = try? fm.contentsOfDirectory(atPath: root + "/cmd"), !names.isEmpty else {
                Thread.sleep(forTimeInterval: 0.1); continue
            }
            let seqs = names.compactMap { Int($0.replacingOccurrences(of: ".txt", with: "")) }.sorted()
            guard let seq = seqs.first else { Thread.sleep(forTimeInterval: 0.1); continue }
            let cmdPath = root + "/cmd/\(seq).txt"
            let line = (try? String(contentsOfFile: cmdPath, encoding: .utf8))?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            try? fm.removeItem(atPath: cmdPath)
            var result: String
            issues = []
            do { result = "OK " + (try execute(line)) } catch { result = "ERR \(error)" }
            if !issues.isEmpty { result += " issues=" + issues.joined(separator: " | ") }
            let tmp = root + "/out/\(seq).tmp"
            fm.createFile(atPath: tmp, contents: Data(result.utf8))
            try? fm.moveItem(atPath: tmp, toPath: root + "/out/\(seq).txt")
            if line == "quit" { break }
        }
        print("QADRIVER done")
    }

    struct DriverError: Error, CustomStringConvertible { let description: String }

    func pt(_ x: Double, _ y: Double) -> XCUICoordinate {
        app.coordinate(withNormalizedOffset: .zero).withOffset(CGVector(dx: x, dy: y))
    }
    func num(_ s: String) throws -> Double {
        guard let v = Double(s) else { throw DriverError(description: "not a number: \(s)") }
        return v
    }
    func fmt(_ r: CGRect) -> String { "\(Int(r.minX)),\(Int(r.minY)),\(Int(r.width)),\(Int(r.height))" }
    func describe(_ e: XCUIElement) -> String {
        let ex = e.exists
        return "exists=\(ex) hittable=\(ex ? e.isHittable : false) frame=\(ex ? fmt(e.frame) : "-") label=\(ex ? e.label.replacingOccurrences(of: "\n", with: "\\n") : "") value=\(ex ? String(describing: e.value ?? "") : "") enabled=\(ex ? e.isEnabled : false)"
    }
    func byId(_ id: String) -> XCUIElement {
        app.descendants(matching: .any).matching(identifier: id).firstMatch
    }
    func typeOf(_ name: String) -> XCUIElement.ElementType {
        switch name {
        case "buttons": return .button
        case "texts", "statictexts": return .staticText
        case "textfields": return .textField
        case "images": return .image
        case "cells": return .cell
        case "alerts": return .alert
        case "sheets": return .sheet
        default: return .any
        }
    }

    func execute(_ line: String) throws -> String {
        var parts = line.split(separator: " ", omittingEmptySubsequences: true).map(String.init)
        guard let verb = parts.first else { return "empty" }
        parts.removeFirst()
        let rest = line.dropFirst(verb.count).trimmingCharacters(in: .whitespaces)
        switch verb {
        case "ping": return "pong"
        case "quit": return "bye"
        case "launch":
            // launch [KEY=VALUE ...] — relaunch the app with that environment
            // (fixture pins, date overrides — whatever the Fixture policy names).
            app = XCUIApplication(bundleIdentifier: bundleId)
            var env: [String: String] = [:]
            for kv in parts { if let eq = kv.firstIndex(of: "=") { env[String(kv[..<eq])] = String(kv[kv.index(after: eq)...]) } }
            app.launchEnvironment = env
            app.launch()
            _ = app.wait(for: .runningForeground, timeout: 10)
            return "state=\(app.state.rawValue) frame=\(fmt(app.frame)) env=\(env)"
        case "activate":
            app.activate(); _ = app.wait(for: .runningForeground, timeout: 10)
            return "state=\(app.state.rawValue)"
        case "terminate":
            app.terminate(); return "state=\(app.state.rawValue)"
        case "state": return "state=\(app.state.rawValue)"
        case "frame": return fmt(app.frame)
        case "home": XCUIDevice.shared.press(.home); return "pressed home"
        case "tap":
            guard parts.count >= 2 else { throw DriverError(description: "tap X Y") }
            pt(try num(parts[0]), try num(parts[1])).tap(); return "tapped \(parts[0]),\(parts[1])"
        case "doubletap":
            guard parts.count >= 2 else { throw DriverError(description: "doubletap X Y") }
            pt(try num(parts[0]), try num(parts[1])).doubleTap(); return "double-tapped"
        case "press":
            guard parts.count >= 3 else { throw DriverError(description: "press X Y SECONDS") }
            pt(try num(parts[0]), try num(parts[1])).press(forDuration: try num(parts[2])); return "pressed"
        case "drag", "swipe":
            // drag X1 Y1 X2 Y2 [HOLD_SECONDS] — press-hold then drag to the end point.
            guard parts.count >= 4 else { throw DriverError(description: "\(verb) X1 Y1 X2 Y2 [hold]") }
            let hold = parts.count >= 5 ? try num(parts[4]) : (verb == "swipe" ? 0.05 : 0.15)
            pt(try num(parts[0]), try num(parts[1])).press(forDuration: hold, thenDragTo: pt(try num(parts[2]), try num(parts[3])))
            return "dragged"
        case "dragslow":
            // dragslow X1 Y1 X2 Y2 VELOCITY(points/s) HOLD — a manual DragGesture at a controlled speed.
            guard parts.count >= 6 else { throw DriverError(description: "dragslow X1 Y1 X2 Y2 VELOCITY HOLD") }
            pt(try num(parts[0]), try num(parts[1])).press(forDuration: try num(parts[5]), thenDragTo: pt(try num(parts[2]), try num(parts[3])), withVelocity: XCUIGestureVelocity(rawValue: CGFloat(try num(parts[4]))), thenHoldForDuration: 0.1)
            return "dragged"
        case "type":
            app.typeText(rest); return "typed \(rest.count) chars"
        case "key":
            // key <XCUIKeyboardKey name> — e.g. key return / key delete
            let map: [String: XCUIKeyboardKey] = ["return": .return, "delete": .delete, "space": .space, "tab": .tab, "escape": .escape]
            guard let k = map[rest] else { throw DriverError(description: "unknown key \(rest)") }
            app.typeKey(k, modifierFlags: []); return "key \(rest)"
        case "selectall":
            // selectall — Cmd-A in the focused text field (select, then `type` to replace).
            app.typeKey("a", modifierFlags: .command); return "selected all"
        case "sleep":
            let s = try num(parts.first ?? "1"); Thread.sleep(forTimeInterval: s); return "slept \(s)"
        case "shot":
            // shot /absolute/host/path.png — full-resolution PNG on the HOST filesystem.
            guard let path = parts.first else { throw DriverError(description: "shot PATH") }
            let png = XCUIScreen.main.screenshot().pngRepresentation
            try png.write(to: URL(fileURLWithPath: path))
            return "wrote \(png.count) bytes to \(path)"
        case "rotate":
            let o: UIDeviceOrientation
            switch parts.first ?? "" {
            case "portrait": o = .portrait
            case "landscapeLeft", "left": o = .landscapeLeft
            case "landscapeRight", "right": o = .landscapeRight
            case "upsideDown": o = .portraitUpsideDown
            default: throw DriverError(description: "rotate portrait|landscapeLeft|landscapeRight")
            }
            XCUIDevice.shared.orientation = o
            Thread.sleep(forTimeInterval: 1.5)
            return "orientation=\(XCUIDevice.shared.orientation.rawValue) frame=\(fmt(app.frame))"
        case "find":
            // find IDENTIFIER — any element type, first match.
            return describe(byId(rest))
        case "findall":
            // findall IDENTIFIER — every match (frames), for repeated identifiers.
            let q = app.descendants(matching: .any).matching(identifier: rest)
            return "count=\(q.count) " + q.allElementsBoundByIndex.prefix(40).map { fmt($0.frame) }.joined(separator: " ")
        case "tapid":
            let e = byId(rest)
            guard e.waitForExistence(timeout: 3) else { throw DriverError(description: "no element with identifier \(rest)") }
            let f = e.frame
            pt(f.midX, f.midY).tap(); return "tapped \(rest) at \(fmt(f))"
        case "tapoffset":
            // tapoffset IDENTIFIER DX DY — tap at the element frame's origin
            // plus an offset, for stacked/overlapping elements whose centre
            // lies on a sibling (e.g. fanned cards: tap the exposed strip).
            guard parts.count >= 3 else { throw DriverError(description: "tapoffset IDENTIFIER DX DY") }
            let id = parts.dropLast(2).joined(separator: " ")
            let e = byId(id)
            guard e.waitForExistence(timeout: 3) else { throw DriverError(description: "no element with identifier \(id)") }
            let f = e.frame
            pt(f.minX + (try num(parts[parts.count - 2])), f.minY + (try num(parts[parts.count - 1]))).tap()
            return "tapped \(id) at offset from \(fmt(f))"
        case "tapbtn":
            let e = app.buttons[rest].firstMatch
            guard e.waitForExistence(timeout: 3) else { throw DriverError(description: "no button labelled \(rest)") }
            let f = e.frame; pt(f.midX, f.midY).tap(); return "tapped button \(rest) at \(fmt(f))"
        case "taptext":
            let e = app.staticTexts[rest].firstMatch
            guard e.waitForExistence(timeout: 3) else { throw DriverError(description: "no static text \(rest)") }
            let f = e.frame; pt(f.midX, f.midY).tap(); return "tapped text \(rest) at \(fmt(f))"
        case "btn":
            return describe(app.buttons[rest].firstMatch)
        case "text":
            return describe(app.staticTexts[rest].firstMatch)
        case "wait":
            // wait IDENTIFIER [SECONDS] — block until the element exists.
            let secs = parts.count >= 2 ? try num(parts[1]) : 5
            let e = byId(parts.first ?? "")
            return "exists=\(e.waitForExistence(timeout: secs)) \(describe(e))"
        case "labels":
            // labels [buttons|texts|textfields|images|cells|any] [SUBSTRING] — ONE snapshot walk (fast):
            // "[x,y,w,h] #identifier label" per element, capped.
            let t = typeOf(parts.first ?? "texts")
            let filter = parts.count >= 2 ? parts[1...].joined(separator: " ") : ""
            let snap = try app.snapshot()
            var out: [String] = []
            func walk(_ n: XCUIElementSnapshot) {
                if out.count >= 500 { return }
                if t == .any || n.elementType == t {
                    let l = n.label.replacingOccurrences(of: "\n", with: "\\n")
                    let id = n.identifier
                    if filter.isEmpty || l.localizedCaseInsensitiveContains(filter) || id.localizedCaseInsensitiveContains(filter) {
                        if !(l.isEmpty && id.isEmpty) || t != .any {
                            let v = n.value.map { String(describing: $0) } ?? ""
                            out.append("[\(fmt(n.frame))] \(id.isEmpty ? "" : "#" + id + " ")\(l)\(v.isEmpty || v == l ? "" : " value=" + v)")
                        }
                    }
                }
                for c in n.children { walk(c) }
            }
            walk(snap)
            return "count=\(out.count)\n" + out.joined(separator: "\n")
        case "alert":
            let a = app.alerts.firstMatch
            guard a.exists else { return "no alert" }
            let btns = a.buttons.allElementsBoundByIndex.map { "\($0.label)@\(fmt($0.frame))" }
            let texts = a.staticTexts.allElementsBoundByIndex.map { $0.label.replacingOccurrences(of: "\n", with: "\\n") }
            return "title=\(a.label) texts=\(texts) buttons=\(btns)"
        case "tree":
            // tree [MAXDEPTH] — indented snapshot of the hierarchy (type #id label [frame]); one IPC.
            let maxDepth = Int(parts.first ?? "") ?? 12
            let snap = try app.snapshot()
            var out: [String] = []
            func walk(_ n: XCUIElementSnapshot, _ d: Int) {
                if d > maxDepth || out.count >= 400 { return }
                let l = n.label.replacingOccurrences(of: "\n", with: "\\n")
                if !(l.isEmpty && n.identifier.isEmpty && n.children.isEmpty) {
                    out.append(String(repeating: "  ", count: d) + "\(n.elementType.rawValue) \(n.identifier.isEmpty ? "" : "#" + n.identifier + " ")\(l) [\(fmt(n.frame))]")
                }
                for c in n.children { walk(c, d + 1) }
            }
            walk(snap, 0)
            return "\n" + out.joined(separator: "\n")
        case "orientation":
            return "\(XCUIDevice.shared.orientation.rawValue)"
        default:
            throw DriverError(description: "unknown command: \(verb)")
        }
    }
}
