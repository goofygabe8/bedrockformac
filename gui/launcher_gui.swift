import AppKit
import CoreText


func pixelFont(_ size: CGFloat) -> NSFont { NSFont(name: "Monocraft", size: size) ?? NSFont.monospacedSystemFont(ofSize: size, weight: .regular) }
func rgb(_ r: CGFloat, _ g: CGFloat, _ b: CGFloat) -> NSColor { NSColor(calibratedRed: r/255, green: g/255, blue: b/255, alpha: 1) }
final class StoneBackground: NSView {
    override func draw(_ dirtyRect: NSRect) {
        rgb(24, 28, 24).setFill(); bounds.fill()
        for y in stride(from: 0, to: Int(bounds.height), by: 20) {
            for x in stride(from: 0, to: Int(bounds.width), by: 20) {
                let shade = CGFloat((x * 13 + y * 7 + (x/20)*(y/20)*17) % 19)
                rgb(28 + shade/2, 33 + shade/2, 28 + shade/3).setFill()
                NSRect(x: x, y: y, width: 20, height: 20).fill()
            }
        }
        rgb(73, 119, 35).setFill(); NSRect(x: 0, y: bounds.height-8, width: bounds.width, height: 8).fill()
        rgb(102, 156, 52).setFill(); NSRect(x: 0, y: bounds.height-3, width: bounds.width, height: 3).fill()
    }
}
final class BlockPanel: NSView {
    override func draw(_ dirtyRect: NSRect) {
        rgb(9, 12, 9).setFill(); bounds.fill()
        rgb(84, 90, 79).setFill(); bounds.insetBy(dx: 2, dy: 2).fill()
        rgb(39, 44, 38).setFill(); bounds.insetBy(dx: 4, dy: 4).fill()
    }
}
final class BlockButton: NSButton {
    var green = false
    override var intrinsicContentSize: NSSize {
        let width = (title as NSString).size(withAttributes: [.font: pixelFont(green ? 14 : 12)]).width
        return NSSize(width: width + 32, height: 36)
    }
    override func draw(_ dirtyRect: NSRect) {
        NSColor.black.setFill(); bounds.fill()
        let face = bounds.insetBy(dx: 2, dy: 2)
        let active = isEnabled
        let pressed = cell?.isHighlighted ?? false
        (green ? rgb(50, 110, 28) : rgb(81, 87, 79)).setFill(); face.fill()
        (green ? rgb(119, 191, 76) : rgb(161, 169, 151)).setFill()
        NSRect(x: face.minX, y: face.maxY-3, width: face.width, height: 3).fill()
        NSRect(x: face.minX, y: face.minY, width: 3, height: face.height).fill()
        (green ? rgb(27, 64, 18) : rgb(43, 48, 40)).setFill()
        NSRect(x: face.minX, y: face.minY, width: face.width, height: 4).fill()
        NSRect(x: face.maxX-3, y: face.minY, width: 3, height: face.height).fill()
        if pressed { NSColor.black.withAlphaComponent(0.2).setFill(); face.fill() }
        if !active { NSColor.black.withAlphaComponent(0.45).setFill(); face.fill() }
        let attrs: [NSAttributedString.Key: Any] = [.font: pixelFont(green ? 14 : 12), .foregroundColor: active ? NSColor.white : rgb(145, 151, 141)]
        let text = title as NSString; let size = text.size(withAttributes: attrs)
        let point = NSPoint(x: (bounds.width-size.width)/2, y: (bounds.height-size.height)/2 + (pressed ? -1 : 1))
        text.draw(at: NSPoint(x: point.x+1, y: point.y-2), withAttributes: [.font: attrs[.font]!, .foregroundColor: NSColor.black.withAlphaComponent(0.7)])
        text.draw(at: point, withAttributes: attrs)
    }
}
final class BlockPopUp: NSPopUpButton {
    override var intrinsicContentSize: NSSize { NSSize(width: 215, height: 36) }
    override func draw(_ dirtyRect: NSRect) {
        NSColor.black.setFill(); bounds.fill()
        rgb(114, 125, 101).setFill(); bounds.insetBy(dx: 2, dy: 2).fill()
        rgb(28, 34, 25).setFill(); bounds.insetBy(dx: 4, dy: 4).fill()
        let title = titleOfSelectedItem ?? "No versions"
        let attrs: [NSAttributedString.Key: Any] = [.font: pixelFont(12), .foregroundColor: isEnabled ? NSColor.white : NSColor.gray]
        (title as NSString).draw(at: NSPoint(x: 12, y: 10), withAttributes: attrs)
        ("v" as NSString).draw(at: NSPoint(x: bounds.width-23, y: 10), withAttributes: attrs)
    }
}

final class Launcher: NSObject, NSApplicationDelegate, NSWindowDelegate {
    let root: URL
    var window: NSWindow!
    let installed = BlockPopUp(frame: .zero, pullsDown: false)
    let releases = BlockPopUp(frame: .zero, pullsDown: false)
    let account = NSTextField(labelWithString: "Preparing your launcher…")
    let controller = NSTextField(wrappingLabelWithString: "Checking connected controllers…")
    let updateLabel = NSTextField(labelWithString: "Launcher")
    let status = NSTextField(wrappingLabelWithString: "Welcome. Your game and launcher controls are here.")
    let spinner = NSProgressIndicator()
    let signIn = BlockButton(title: "Sign In", target: nil, action: nil)
    let play = BlockButton(title: "Play Minecraft", target: nil, action: nil)
    let download = BlockButton(title: "Download", target: nil, action: nil)
    var buttons: [NSButton] = []
    var busy = false
    var runningGame = false
    var installedValues: [String] = []
    var authenticated = false
    var startup = true
    var currentAction = ""
    var openedSignIn = false
    var python: String {
        let venv = root.appendingPathComponent(".venv/bin/python").path
        if FileManager.default.isExecutableFile(atPath: venv) { return venv }
        return ["/opt/homebrew/bin/python3", "/usr/local/bin/python3", "/usr/bin/python3"].first { FileManager.default.isExecutableFile(atPath: $0) } ?? "/usr/bin/python3"
    }
    init(root: URL) { self.root = root; super.init() }
    func label(_ text: String, size: CGFloat = 13, weight: NSFont.Weight = .regular) -> NSTextField {
        let value = NSTextField(labelWithString: text)
        value.font = pixelFont(size)
        return value
    }
    func button(_ title: String, _ selector: Selector) -> NSButton {
        let value = BlockButton(title: title, target: self, action: selector)
        value.isBordered = false
        buttons.append(value)
        return value
    }
    func row(_ views: [NSView]) -> NSStackView {
        let stack = NSStackView(views: views)
        stack.orientation = .horizontal; stack.spacing = 12; stack.alignment = .centerY
        return stack
    }
    func section(_ title: String, _ views: [NSView]) -> NSView {
        let stack = NSStackView(views: [label(title, size: 15, weight: .semibold)] + views)
        stack.orientation = .vertical; stack.alignment = .leading; stack.spacing = 12
        let panel = BlockPanel()
        stack.translatesAutoresizingMaskIntoConstraints = false
        panel.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: panel.leadingAnchor, constant: 18),
            stack.trailingAnchor.constraint(equalTo: panel.trailingAnchor, constant: -18),
            stack.topAnchor.constraint(equalTo: panel.topAnchor, constant: 16),
            stack.bottomAnchor.constraint(equalTo: panel.bottomAnchor, constant: -16)])
        return panel
    }
    func applicationDidFinishLaunching(_ notification: Notification) {
        CTFontManagerRegisterFontsForURL(root.appendingPathComponent("Monocraft.ttf") as CFURL, .process, nil)
        NSApp.applicationIconImage = NSImage(contentsOf: root.appendingPathComponent("AppIcon.icns"))
        NSApp.setActivationPolicy(.regular)
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 840, height: 700), styleMask: [.titled, .closable, .miniaturizable], backing: .buffered, defer: false)
        window.title = "Minecraft Bedrock"; window.delegate = self
        window.isReleasedWhenClosed = false
        window.appearance = NSAppearance(named: .darkAqua)
        window.contentView = StoneBackground()
        window.center()
        let title = label("Bedrock for Mac", size: 30, weight: .bold)
        let subtitle = label("Minecraft Bedrock / Mac launcher", size: 12)
        subtitle.textColor = rgb(228, 194, 86)
        signIn.target = self; signIn.action = #selector(accountAction); signIn.isBordered = false; buttons.append(signIn)
        play.target = self; play.action = #selector(playAction); play.isBordered = false; play.green = true
        play.font = pixelFont(14)
        play.contentTintColor = .systemGreen
        play.keyEquivalent = "\r"; buttons.append(play)
        installed.target = self; installed.action = #selector(selectAction)
        installed.widthAnchor.constraint(equalToConstant: 225).isActive = true
        releases.widthAnchor.constraint(equalToConstant: 225).isActive = true
        download.target = self; download.action = #selector(downloadAction); download.isBordered = false; buttons.append(download)
        account.font = pixelFont(11)
        controller.font = pixelFont(11)
        updateLabel.font = pixelFont(11)
        installed.font = pixelFont(12); releases.font = pixelFont(12)
        account.textColor = .secondaryLabelColor
        controller.textColor = .secondaryLabelColor
        status.font = pixelFont(11)
        status.isSelectable = true
        status.maximumNumberOfLines = 5
        status.preferredMaxLayoutWidth = 680
        spinner.style = .spinning; spinner.controlSize = .small; spinner.isDisplayedWhenStopped = false
        let installedTitle = label("Installed", size: 12); let downloadTitle = label("Download", size: 12)
        installedTitle.widthAnchor.constraint(equalToConstant: 100).isActive = true
        downloadTitle.widthAnchor.constraint(equalToConstant: 100).isActive = true
        let game = section("PLAY", [row([installedTitle, installed, play]), row([downloadTitle, releases, download])])
        let devices = section("CONTROLLER & AUDIO", [controller, row([button("Refresh Controllers", #selector(refreshAction)), button("Audio Output…", #selector(audioAction))])])
        let updates = section("UPDATES", [row([updateLabel, button("Check for Updates", #selector(updateAction)), button("Open Releases", #selector(releasesAction))])])
        let stack = NSStackView(views: [title, subtitle, row([account, signIn]), game, devices, updates, row([spinner, status])])
        stack.orientation = .vertical; stack.alignment = .leading; stack.spacing = 18
        stack.translatesAutoresizingMaskIntoConstraints = false
        window.contentView!.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: window.contentView!.leadingAnchor, constant: 28),
            stack.trailingAnchor.constraint(equalTo: window.contentView!.trailingAnchor, constant: -28),
            stack.topAnchor.constraint(equalTo: window.contentView!.topAnchor, constant: 28),
            game.widthAnchor.constraint(equalTo: stack.widthAnchor), devices.widthAnchor.constraint(equalTo: stack.widthAnchor), updates.widthAnchor.constraint(equalTo: stack.widthAnchor),
            status.widthAnchor.constraint(equalTo: stack.widthAnchor, constant: -32)])
        let menu = NSMenu()
        let appItem = NSMenuItem(); let appMenu = NSMenu()
        appMenu.addItem(withTitle: "Quit Minecraft Launcher", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = appMenu; menu.addItem(appItem)
        let editItem = NSMenuItem(title: "Edit", action: nil, keyEquivalent: ""); let edit = NSMenu(title: "Edit")
        edit.addItem(withTitle: "Copy", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        editItem.submenu = edit; menu.addItem(editItem); NSApp.mainMenu = menu
        window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true)
        run("bootstrap")
    }
    func setBusy(_ value: Bool) {
        busy = value
        for button in buttons { button.isEnabled = !value }
        installed.isEnabled = !value && !installedValues.isEmpty
        releases.isEnabled = !value && releases.numberOfItems > 0
        play.isEnabled = !value && !installedValues.isEmpty
        download.isEnabled = !value && authenticated && releases.numberOfItems > 0
        if value { spinner.startAnimation(nil) } else { spinner.stopAnimation(nil) }
    }
    func run(_ action: String, _ arguments: [String] = []) {
        if busy { return }
        currentAction = action; openedSignIn = false; setBusy(true)
        if action == "play" { runningGame = true }
        let executable = python
        DispatchQueue.global(qos: .userInitiated).async {
            let process = Process(); process.executableURL = URL(fileURLWithPath: executable)
            process.arguments = [self.root.appendingPathComponent("gui_backend.py").path, action] + arguments
            process.currentDirectoryURL = self.root
            let pipe = Pipe(); process.standardOutput = pipe
            let errorPipe = Pipe(); process.standardError = errorPipe
            var environment = ProcessInfo.processInfo.environment
            environment["PYTHONUNBUFFERED"] = "1"
            environment["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
            process.environment = environment
            var receivedResult = false
            do {
                try process.run()
                var pending = Data()
                while true {
                    let chunk = pipe.fileHandleForReading.availableData
                    if chunk.isEmpty { break }
                    pending.append(chunk)
                    while let end = pending.firstIndex(of: 10) {
                        let line = pending.subdata(in: 0..<end)
                        pending.removeSubrange(0...end)
                        guard let message = try? JSONSerialization.jsonObject(with: line) as? [String: Any] else { continue }
                        if message["kind"] as? String == "result" { receivedResult = true }
                        DispatchQueue.main.async { self.receive(message, action: action) }
                    }
                }
                process.waitUntilExit()
                if !receivedResult {
                    let data = errorPipe.fileHandleForReading.readDataToEndOfFile()
                    let message = String(data: data, encoding: .utf8) ?? "The launcher action stopped."
                    DispatchQueue.main.async { self.receive(["kind": "result", "ok": false, "message": message], action: action) }
                }
            } catch {
                DispatchQueue.main.async { self.receive(["kind": "result", "ok": false, "message": error.localizedDescription], action: action) }
            }
        }
    }
    func receive(_ data: [String: Any], action: String) {
        if let message = data["message"] as? String, !message.isEmpty {
            status.stringValue = message
            if ["login", "play"].contains(action) && message.contains("microsoft.com/link") && !openedSignIn {
                openedSignIn = true; NSWorkspace.shared.open(URL(string: "https://www.microsoft.com/link")!)
            }
        }
        if data["kind"] as? String != "result" { return }
        let success = data["ok"] as? Bool ?? false
        status.textColor = success ? .secondaryLabelColor : .systemOrange
        if let version = data["version"] as? String { updateLabel.stringValue = "v" + version + " / Checked on startup" }
        if action == "status", success {
            authenticated = !(data["account"] as? String ?? "").isEmpty
            account.stringValue = authenticated ? "Signed in as " + (data["account"] as? String ?? "") : "Sign in with your Microsoft account to download Minecraft."
            signIn.title = authenticated ? "Sign Out" : "Sign In"
            let versions = data["installed"] as? [String] ?? []
            installedValues = versions
            installed.removeAllItems(); installed.addItems(withTitles: versions)
            if let selected = data["selected"] as? String { installed.selectItem(withTitle: selected) }
            if versions.isEmpty { installed.addItem(withTitle: "Download a version first"); installed.isEnabled = false }
            let pads = data["controllers"] as? [String] ?? []
            controller.stringValue = pads.isEmpty ? "No controller detected. Connect or pair your controller before Play." : "Connected: " + pads.joined(separator: ", ")
            controller.textColor = pads.isEmpty ? .secondaryLabelColor : .systemGreen
            play.isEnabled = !versions.isEmpty
        }
        if let values = data["releases"] as? [String] {
            releases.removeAllItems(); releases.addItems(withTitles: values)
            if !values.isEmpty { releases.selectItem(at: 0) }
        }
        if action == "play" { runningGame = false }
        setBusy(false)
        if data["restart"] as? Bool == true {
            status.stringValue = "Update installed. Reopening the launcher…"
            let process = Process(); process.executableURL = root.appendingPathComponent("launcher_gui")
            process.arguments = [root.path]
            try? process.run(); NSApp.terminate(nil); return
        }
        if action == "catalog" && success { status.stringValue = authenticated && !installedValues.isEmpty ? "Ready to play." : "Sign in and download Minecraft to get started." }
        if action == "bootstrap" && success { run("status"); return }
        if action == "status" && startup { startup = false; run("catalog"); return }
        if ["login", "logout", "download"].contains(action) && success { run("status") }
    }
    @objc func playAction() { if let value = installed.titleOfSelectedItem { run("play", [value]) } }
    @objc func downloadAction() { if let value = releases.titleOfSelectedItem { run("download", [value]) } }
    @objc func selectAction() { if let value = installed.titleOfSelectedItem { run("select", [value]) } }
    @objc func accountAction() { run(authenticated ? "logout" : "login") }
    @objc func refreshAction() { run("status") }
    @objc func audioAction() { run("audio") }
    @objc func updateAction() { run("update") }
    @objc func releasesAction() { NSWorkspace.shared.open(URL(string: "https://github.com/goofygabe8/bedrockformac/releases/latest")!) }
    func windowShouldClose(_ sender: NSWindow) -> Bool {
        if busy { sender.orderOut(nil); return false }
        return true
    }
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        window.makeKeyAndOrderFront(nil); return true
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { !busy }
}
let root = CommandLine.arguments.count > 1 ? URL(fileURLWithPath: CommandLine.arguments[1]) : URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
let delegate = Launcher(root: root)
NSApplication.shared.delegate = delegate
NSApplication.shared.run()
