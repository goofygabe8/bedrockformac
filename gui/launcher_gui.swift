import AppKit
import CoreText
import CoreGraphics
import Darwin

// The update builder sets this before compiling each release.
let launcherVersion = "0.4.3"

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

final class FlippedView: NSView { override var isFlipped: Bool { true } }

final class SettingControl: NSView {
    let entry: [String: Any]
    let input: NSControl
    let readout = NSTextField(labelWithString: "")
    var key: String { entry["key"] as! String }
    init(_ entry: [String: Any], value: Any) {
        self.entry = entry
        switch entry["kind"] as? String {
        case "bool": input = NSButton(checkboxWithTitle: "Enabled", target: nil, action: nil)
        case "choice":
            let popup = BlockPopUp(frame: .zero, pullsDown: false)
            for option in entry["options"] as? [[Any]] ?? [] {
                popup.addItem(withTitle: option[1] as? String ?? "")
                popup.lastItem?.representedObject = option[0]
            }
            input = popup
        default:
            input = NSSlider(value: 0, minValue: (entry["minimum"] as? NSNumber)?.doubleValue ?? 0,
                             maxValue: (entry["maximum"] as? NSNumber)?.doubleValue ?? 1, target: nil, action: nil)
        }
        super.init(frame: .zero)
        input.font = pixelFont(11)
        let title = NSTextField(labelWithString: entry["title"] as? String ?? "")
        title.font = pixelFont(12)
        title.widthAnchor.constraint(equalToConstant: 285).isActive = true
        input.widthAnchor.constraint(equalToConstant: 235).isActive = true
        readout.font = pixelFont(11)
        readout.widthAnchor.constraint(equalToConstant: 65).isActive = true
        let top = NSStackView(views: [title, input, readout]); top.orientation = .horizontal; top.spacing = 12; top.alignment = .centerY
        let hint = NSTextField(wrappingLabelWithString: entry["hint"] as? String ?? "")
        hint.font = pixelFont(10); hint.textColor = .secondaryLabelColor
        hint.preferredMaxLayoutWidth = 675
        let recommended = NSTextField(labelWithString: "Recommended: " + display(entry["default"] ?? ""))
        recommended.font = pixelFont(10); recommended.textColor = rgb(166, 194, 131)
        let stack = NSStackView(views: [top, hint, recommended])
        stack.orientation = .vertical; stack.alignment = .leading; stack.spacing = 7
        stack.translatesAutoresizingMaskIntoConstraints = false; addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: leadingAnchor), stack.trailingAnchor.constraint(equalTo: trailingAnchor),
            stack.topAnchor.constraint(equalTo: topAnchor, constant: 10), stack.bottomAnchor.constraint(equalTo: bottomAnchor, constant: -12),
            hint.widthAnchor.constraint(equalTo: stack.widthAnchor)])
        if let slider = input as? NSSlider { slider.target = self; slider.action = #selector(sliderChanged) }
        set(value)
    }
    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }
    func display(_ value: Any) -> String {
        if entry["kind"] as? String == "bool" { return (value as? Bool ?? false) ? "On" : "Off" }
        if entry["kind"] as? String == "choice" {
            for option in entry["options"] as? [[Any]] ?? [] where equal(value, option[0]) { return option[1] as? String ?? "" }
            return String(describing: value)
        }
        let n = (value as? NSNumber)?.doubleValue ?? 0
        let scale = (entry["scale"] as? NSNumber)?.doubleValue ?? 1
        return String(format: "%.0f", n * scale) + (entry["unit"] as? String ?? "")
    }
    func equal(_ a: Any, _ b: Any) -> Bool { (a as? NSObject)?.isEqual(b) ?? false }
    func set(_ value: Any) {
        if let popup = input as? NSPopUpButton {
            if let index = popup.itemArray.firstIndex(where: { equal($0.representedObject ?? "", value) }) { popup.selectItem(at: index) }
            else { popup.addItem(withTitle: "Custom: " + String(describing: value)); popup.lastItem?.representedObject = value; popup.selectItem(at: popup.numberOfItems - 1) }
        } else if let button = input as? NSButton { button.state = (value as? Bool ?? false) ? .on : .off }
        else if let slider = input as? NSSlider { slider.doubleValue = (value as? NSNumber)?.doubleValue ?? 0; readout.stringValue = display(slider.doubleValue) }
    }
    func value() -> Any {
        if let popup = input as? NSPopUpButton { return popup.selectedItem?.representedObject ?? entry["default"]! }
        if let button = input as? NSButton { return button.state == .on }
        let slider = input as! NSSlider
        let step = (entry["step"] as? NSNumber)?.doubleValue ?? 1
        return (slider.doubleValue / step).rounded() * step
    }
    @objc func sliderChanged() { readout.stringValue = display(value()) }
}

final class SettingsEditor: NSObject, NSWindowDelegate {
    let window: NSWindow
    let info = NSTextField(wrappingLabelWithString: "Changes apply on the next Minecraft launch.")
    let presets: [String: [String: Any]]
    let defaults: [String: Any]
    let baseline: [String: Any]
    var controls: [String: SettingControl] = [:]
    var buttons: [NSButton] = []
    var saving = false
    let onSave: ([String: Any]) -> Void
    init(data: [String: Any], onSave: @escaping ([String: Any]) -> Void) {
        self.onSave = onSave
        presets = data["presets"] as? [String: [String: Any]] ?? [:]
        defaults = data["defaults"] as? [String: Any] ?? [:]
        baseline = data["values"] as? [String: Any] ?? [:]
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 820, height: 730), styleMask: [.titled, .closable, .miniaturizable], backing: .buffered, defer: false)
        super.init()
        window.title = "Minecraft Settings"; window.isReleasedWhenClosed = false; window.delegate = self
        window.appearance = NSAppearance(named: .darkAqua); window.contentView = StoneBackground(); window.center()
        let title = NSTextField(labelWithString: "Make it your Minecraft")
        title.font = pixelFont(23)
        let tabs = NSTabView(); tabs.tabViewType = .topTabsBezelBorder
        let schema = data["schema"] as? [[String: Any]] ?? []
        for name in ["Display", "Graphics", "Controls", "Sound"] {
            let scroll = NSScrollView(); scroll.hasVerticalScroller = true; scroll.drawsBackground = false; scroll.borderType = .noBorder
            let document = FlippedView(); document.translatesAutoresizingMaskIntoConstraints = false
            let stack = NSStackView(); stack.orientation = .vertical; stack.alignment = .leading; stack.spacing = 2
            stack.translatesAutoresizingMaskIntoConstraints = false; document.addSubview(stack); scroll.documentView = document
            NSLayoutConstraint.activate([
                document.widthAnchor.constraint(equalTo: scroll.contentView.widthAnchor),
                stack.leadingAnchor.constraint(equalTo: document.leadingAnchor, constant: 15),
                stack.trailingAnchor.constraint(equalTo: document.trailingAnchor, constant: -15),
                stack.topAnchor.constraint(equalTo: document.topAnchor, constant: 8),
                stack.bottomAnchor.constraint(equalTo: document.bottomAnchor, constant: -12)])
            for entry in schema where entry["section"] as? String == name {
                let key = entry["key"] as! String
                let control = SettingControl(entry, value: baseline[key] ?? entry["default"]!)
                controls[key] = control; stack.addArrangedSubview(control)
                control.widthAnchor.constraint(equalTo: stack.widthAnchor).isActive = true
            }
            let tab = NSTabViewItem(identifier: name); tab.label = name; tab.view = scroll; tabs.addTabViewItem(tab)
        }
        tabs.heightAnchor.constraint(equalToConstant: 400).isActive = true
        let presetTitle = NSTextField(labelWithString: "Graphics presets:"); presetTitle.font = pixelFont(11)
        let presetRow = NSStackView(views: [presetTitle, makeButton("Balanced", #selector(presetAction)), makeButton("Performance", #selector(presetAction)), makeButton("Quality", #selector(presetAction))])
        presetRow.orientation = .horizontal; presetRow.spacing = 10
        info.font = pixelFont(10); info.textColor = .secondaryLabelColor
        info.preferredMaxLayoutWidth = 750
        if data["pending"] as? Bool == true { info.stringValue = "Saved changes are waiting for the next Minecraft launch." }
        let footer = NSStackView(views: [makeButton("Restore Defaults", #selector(defaultsAction)), makeButton("Cancel", #selector(cancelAction)), makeButton("Save Settings", #selector(saveAction))]); footer.orientation = .horizontal; footer.spacing = 12
        let body = NSStackView(views: [title, presetRow, tabs, info, footer])
        body.orientation = .vertical; body.alignment = .leading; body.spacing = 16
        body.translatesAutoresizingMaskIntoConstraints = false; window.contentView!.addSubview(body)
        NSLayoutConstraint.activate([
            body.leadingAnchor.constraint(equalTo: window.contentView!.leadingAnchor, constant: 24),
            body.trailingAnchor.constraint(equalTo: window.contentView!.trailingAnchor, constant: -24),
            body.topAnchor.constraint(equalTo: window.contentView!.topAnchor, constant: 24),
            tabs.widthAnchor.constraint(equalTo: body.widthAnchor), info.widthAnchor.constraint(equalTo: body.widthAnchor)])
    }
    func makeButton(_ title: String, _ action: Selector) -> NSButton {
        let button = BlockButton(title: title, target: self, action: action); button.isBordered = false
        buttons.append(button); return button
    }
    @objc func presetAction(_ sender: NSButton) {
        for (key, value) in presets[sender.title] ?? [:] { controls[key]?.set(value) }
        info.stringValue = sender.title + " graphics selected. Click Save Settings to keep them."
    }
    @objc func defaultsAction() {
        for (key, value) in defaults { controls[key]?.set(value) }
        info.stringValue = "Recommended defaults selected. Click Save Settings to keep them."
    }
    @objc func cancelAction() { window.close() }
    @objc func saveAction() {
        var changes: [String: Any] = [:]
        for (key, control) in controls {
            let value = control.value()
            if !control.equal(value, baseline[key] ?? "") { changes[key] = value }
        }
        if changes.isEmpty { window.close(); return }
        setSaving(true); onSave(changes)
    }
    func setSaving(_ value: Bool) {
        saving = value
        for button in buttons { button.isEnabled = !value }
        for control in controls.values { control.input.isEnabled = !value }
        if value { info.stringValue = "Saving settings…" }
    }
    func finish(_ success: Bool, message: String) {
        setSaving(false)
        if success { window.close() } else { info.stringValue = message; info.textColor = .systemOrange }
    }
    func windowShouldClose(_ sender: NSWindow) -> Bool { !saving }
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
    let highResolution = NSButton(checkboxWithTitle: "High Resolution / Retina", target: nil, action: nil)
    var closeGameButton: NSButton!
    var showGameButton: NSButton!
    var updateButton: NSButton!
    var settingsEditor: SettingsEditor?
    var buttons: [NSButton] = []
    var busy = false
    var runningGame = false
    var playTaskActive = false
    var savedHighResolution = true
    var updatesDeferred = false
    var relaunchProcess: Process?
    var relaunchTimer: Timer?
    var gameLaunching = false
    var gamePID: pid_t?
    var gameTimer: Timer?
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
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 840, height: 760), styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = "Minecraft Bedrock"; window.delegate = self
        window.isReleasedWhenClosed = false
        window.contentMinSize = NSSize(width: 840, height: 620)
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
        highResolution.font = pixelFont(11); highResolution.target = self; highResolution.action = #selector(highResolutionAction)
        closeGameButton = button("Close Game", #selector(closeGameAction))
        showGameButton = button("Show Game", #selector(showGameAction))
        updateButton = button("Check for Updates", #selector(updateAction))
        let game = section("PLAY", [row([installedTitle, installed, play]), row([downloadTitle, releases, download]),
                                    row([highResolution, button("Settings…", #selector(settingsAction))]),
                                    row([showGameButton, closeGameButton, button("Open Game Logs", #selector(logsAction))])])
        let devices = section("CONTROLLER & AUDIO", [controller, row([button("Refresh Controllers", #selector(refreshAction)), button("Audio Output…", #selector(audioAction))])])
        let updates = section("UPDATES", [row([updateLabel, updateButton, button("Open Releases", #selector(releasesAction))])])
        let stack = NSStackView(views: [title, subtitle, row([account, signIn]), game, devices, updates, row([spinner, status])])
        stack.orientation = .vertical; stack.alignment = .leading; stack.spacing = 12
        stack.translatesAutoresizingMaskIntoConstraints = false
        let scroll = NSScrollView(); scroll.hasVerticalScroller = true; scroll.drawsBackground = false
        scroll.translatesAutoresizingMaskIntoConstraints = false; window.contentView!.addSubview(scroll)
        let document = FlippedView(); document.translatesAutoresizingMaskIntoConstraints = false
        document.addSubview(stack); scroll.documentView = document
        NSLayoutConstraint.activate([
            scroll.leadingAnchor.constraint(equalTo: window.contentView!.leadingAnchor),
            scroll.trailingAnchor.constraint(equalTo: window.contentView!.trailingAnchor),
            scroll.topAnchor.constraint(equalTo: window.contentView!.topAnchor),
            scroll.bottomAnchor.constraint(equalTo: window.contentView!.bottomAnchor),
            document.widthAnchor.constraint(equalTo: scroll.contentView.widthAnchor),
            stack.leadingAnchor.constraint(equalTo: document.leadingAnchor, constant: 28),
            stack.trailingAnchor.constraint(equalTo: document.trailingAnchor, constant: -28),
            stack.topAnchor.constraint(equalTo: document.topAnchor, constant: 28),
            stack.bottomAnchor.constraint(equalTo: document.bottomAnchor, constant: -28),
            game.widthAnchor.constraint(equalTo: stack.widthAnchor), devices.widthAnchor.constraint(equalTo: stack.widthAnchor), updates.widthAnchor.constraint(equalTo: stack.widthAnchor),
            status.widthAnchor.constraint(equalTo: stack.widthAnchor, constant: -32)])
        let menu = NSMenu()
        let appItem = NSMenuItem(); let appMenu = NSMenu()
        appMenu.addItem(withTitle: "Quit Minecraft Launcher", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = appMenu; menu.addItem(appItem)
        let editItem = NSMenuItem(title: "Edit", action: nil, keyEquivalent: ""); let edit = NSMenu(title: "Edit")
        edit.addItem(withTitle: "Copy", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        editItem.submenu = edit; menu.addItem(editItem); NSApp.mainMenu = menu
        updateLabel.stringValue = "v" + launcherVersion
        window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true)
        acknowledgeRelaunch()
        run("bootstrap")
    }
    func setBusy(_ value: Bool) {
        busy = value
        for button in buttons { button.isEnabled = !value }
        let gameOpen = runningGame || gameLaunching
        installed.isEnabled = !value && !gameOpen && !installedValues.isEmpty
        releases.isEnabled = !value && !gameOpen && releases.numberOfItems > 0
        play.isEnabled = !value && !gameOpen && !installedValues.isEmpty
        download.isEnabled = !value && !gameOpen && authenticated && releases.numberOfItems > 0
        signIn.isEnabled = !value && !gameOpen
        updateButton.isEnabled = !value && !gameOpen
        closeGameButton.isEnabled = !value && gamePID != nil
        showGameButton.isEnabled = !value && gamePID != nil
        highResolution.isEnabled = !value
        play.title = gameLaunching ? "Launching…" : (runningGame ? "Minecraft Is Open" : "Play Minecraft")
        play.invalidateIntrinsicContentSize()
        if value || gameLaunching { spinner.startAnimation(nil) } else { spinner.stopAnimation(nil) }
    }
    func run(_ action: String, _ arguments: [String] = []) {
        if busy { return }
        if action == "play" && (runningGame || gameLaunching) { return }
        currentAction = action; openedSignIn = false
        if action == "play" { gameLaunching = true; playTaskActive = true; status.stringValue = "Launching Minecraft…" }
        setBusy(true)
        let executable = python
        DispatchQueue.global(qos: .userInitiated).async {
            let process = Process(); process.executableURL = URL(fileURLWithPath: executable)
            process.arguments = [self.root.appendingPathComponent("gui_backend.py").path, action] + arguments
            process.currentDirectoryURL = self.root
            let pipe = Pipe(); process.standardOutput = pipe
            let errorPipe = Pipe(); process.standardError = errorPipe
            var environment = ProcessInfo.processInfo.environment
            environment["PYTHONUNBUFFERED"] = "1"
            environment["BEDROCK_GUI_VERSION"] = launcherVersion
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
            if action != "play" || !busy || currentAction == "play" { status.stringValue = message }
            if ["login", "play"].contains(action) && message.contains("microsoft.com/link") && !openedSignIn {
                openedSignIn = true; NSWorkspace.shared.open(URL(string: "https://www.microsoft.com/link")!)
            }
        }
        if data["kind"] as? String == "game", let pid = data["pid"] as? Int {
            trackGame(pid_t(pid)); currentAction = ""; setBusy(false); return
        }
        if data["kind"] as? String != "result" { return }
        let success = data["ok"] as? Bool ?? false
        status.textColor = success ? .secondaryLabelColor : .systemOrange
        if let deferred = data["deferred"] as? Bool { updatesDeferred = deferred }
        if let installedVersion = data["version"] as? String {
            updateLabel.stringValue = "v" + launcherVersion + (installedVersion != launcherVersion ? " / Restart to finish update" : (updatesDeferred ? " / Update after closing game" : " / Checked on startup"))
        }
        if success && data["restart"] as? Bool == true {
            restartLauncher(expectedVersion: data["version"] as? String ?? launcherVersion)
            return
        }
        if let high = data["high_resolution"] as? Bool { savedHighResolution = high; highResolution.state = high ? .on : .off }
        if action == "high-resolution" && !success { highResolution.state = savedHighResolution ? .on : .off }
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
            if let active = (data["games"] as? [[String: Any]])?.first, let pid = active["pid"] as? Int {
                if gamePID != pid_t(pid) { trackGame(pid_t(pid)) }
            }
        }
        if let values = data["releases"] as? [String] {
            releases.removeAllItems(); releases.addItems(withTitles: values)
            if !values.isEmpty { releases.selectItem(at: 0) }
        }
        if action == "settings", success {
            settingsEditor = SettingsEditor(data: data) { values in
                guard let json = try? JSONSerialization.data(withJSONObject: values), let text = String(data: json, encoding: .utf8) else { return }
                if self.busy { self.settingsEditor?.finish(false, message: "Wait for the current launcher action, then save again."); return }
                self.run("settings-save", [text])
            }
            settingsEditor?.window.makeKeyAndOrderFront(nil)
        }
        if action == "settings-save" {
            settingsEditor?.finish(success, message: data["message"] as? String ?? "Could not save settings.")
        }
        if action == "play" {
            gameTimer?.invalidate(); gameTimer = nil; gamePID = nil
            runningGame = false; gameLaunching = false; playTaskActive = false
        }
        // The game action stays alive in the background while other actions run.
        if action == currentAction || !busy { currentAction = ""; setBusy(false) }
        else { setBusy(busy) }
        if action == "catalog" && success && !runningGame && !gameLaunching { status.stringValue = authenticated && !installedValues.isEmpty ? "Ready to play." : "Sign in and download Minecraft to get started." }
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
    @objc func updateAction() {
        if let editor = settingsEditor, editor.window.isVisible {
            status.stringValue = "Save or close Settings before updating the launcher."
            editor.window.makeKeyAndOrderFront(nil); return
        }
        run("update")
    }
    func acknowledgeRelaunch() {
        let arguments = CommandLine.arguments
        guard arguments.count == 4, arguments[2] == "--relaunch-token", UUID(uuidString: arguments[3]) != nil else { return }
        let directory = root.appendingPathComponent(".launcher-relaunch", isDirectory: true)
        do {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
            let file = directory.appendingPathComponent(arguments[3] + ".json")
            let data = try JSONSerialization.data(withJSONObject: ["version": launcherVersion, "pid": ProcessInfo.processInfo.processIdentifier])
            try data.write(to: file, options: .atomic)
            try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: file.path)
        } catch {
            status.stringValue = "The launcher opened, but could not confirm its restart: " + error.localizedDescription
        }
    }
    func restartLauncher(expectedVersion: String) {
        guard relaunchProcess == nil else { return }
        currentAction = "restart"; setBusy(true)
        status.stringValue = "Update installed. Reopening the launcher…"
        let token = UUID().uuidString
        let ack = root.appendingPathComponent(".launcher-relaunch/" + token + ".json")
        let process = Process(); process.executableURL = root.appendingPathComponent("launcher_gui")
        process.arguments = [root.path, "--relaunch-token", token]
        process.currentDirectoryURL = root
        process.standardOutput = FileHandle.nullDevice; process.standardError = FileHandle.nullDevice
        let deadline = Date().addingTimeInterval(15)
        do {
            try process.run(); relaunchProcess = process
            relaunchTimer = Timer.scheduledTimer(withTimeInterval: 0.2, repeats: true) { [weak self] timer in
                guard let self = self else { timer.invalidate(); return }
                if let bytes = try? Data(contentsOf: ack),
                   let response = try? JSONSerialization.jsonObject(with: bytes) as? [String: Any],
                   response["version"] as? String == expectedVersion,
                   response["pid"] as? Int == Int(process.processIdentifier) {
                    timer.invalidate(); self.relaunchTimer = nil
                    try? FileManager.default.removeItem(at: ack)
                    NSApp.terminate(nil); return
                }
                if !process.isRunning || Date() >= deadline {
                    timer.invalidate(); self.relaunchTimer = nil
                    if process.isRunning { process.terminate() }
                    try? FileManager.default.removeItem(at: ack)
                    self.relaunchProcess = nil; self.currentAction = ""; self.setBusy(false)
                    self.status.textColor = .systemOrange
                    self.status.stringValue = "The update is installed, but reopening failed. Quit and open Minecraft Bedrock from Applications to finish."
                }
            }
        } catch {
            currentAction = ""; setBusy(false); status.textColor = .systemOrange
            status.stringValue = "The update is installed, but the launcher could not reopen: " + error.localizedDescription
        }
    }
    @objc func settingsAction() {
        if let editor = settingsEditor, editor.window.isVisible { editor.window.makeKeyAndOrderFront(nil); return }
        run("settings")
    }
    @objc func highResolutionAction() { run("high-resolution", ["{\"high_resolution\":" + (highResolution.state == .on ? "true" : "false") + "}"]) }
    @objc func closeGameAction() { run("close_game") }
    @objc func showGameAction() {
        if let pid = gamePID, let app = NSRunningApplication(processIdentifier: pid) { app.activate(options: [.activateIgnoringOtherApps]) }
        else { status.stringValue = "Switch to the Minecraft window using Command-Tab." }
    }
    @objc func logsAction() {
        let path = root.appendingPathComponent(".gui-logs")
        try? FileManager.default.createDirectory(at: path, withIntermediateDirectories: true)
        NSWorkspace.shared.open(path)
    }
    func trackGame(_ pid: pid_t) {
        gamePID = pid; gameLaunching = true; runningGame = false
        status.stringValue = "Launching Minecraft…"
        gameTimer?.invalidate()
        gameTimer = Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { [weak self] _ in self?.checkGameWindow() }
        checkGameWindow()
    }
    func checkGameWindow() {
        guard let pid = gamePID else { return }
        if kill(pid, 0) != 0 && errno == ESRCH {
            if playTaskActive { return }
            gameTimer?.invalidate(); gameTimer = nil; gamePID = nil; gameLaunching = false; runningGame = false
            if !busy { status.stringValue = "Minecraft closed. Ready to play again." }
            setBusy(busy); return
        }
        if !gameLaunching { return }
        let windows = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]] ?? []
        let visible = windows.contains { item in
            guard (item[kCGWindowOwnerPID as String] as? Int) == Int(pid),
                  let bounds = item[kCGWindowBounds as String] as? [String: Any],
                  let width = bounds["Width"] as? NSNumber, let height = bounds["Height"] as? NSNumber else { return false }
            return width.doubleValue > 200 && height.doubleValue > 150
        }
        if visible {
            gameLaunching = false; runningGame = true
            if !busy { status.stringValue = "Minecraft is open. Launcher settings apply on the next game launch." }
            setBusy(busy)
        }
    }
    @objc func releasesAction() { NSWorkspace.shared.open(URL(string: "https://github.com/goofygabe8/bedrockformac/releases/latest")!) }
    func windowShouldClose(_ sender: NSWindow) -> Bool {
        if busy || gameLaunching || runningGame { sender.orderOut(nil); return false }
        return true
    }
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        window.makeKeyAndOrderFront(nil); return true
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { !busy && !gameLaunching && !runningGame }
}
let root = CommandLine.arguments.count > 1 ? URL(fileURLWithPath: CommandLine.arguments[1]) : URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
let delegate = Launcher(root: root)
NSApplication.shared.delegate = delegate
NSApplication.shared.run()
