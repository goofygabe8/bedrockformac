// Optional display-side interpolation for Minecraft's finished window image.
// The game remains the input target. Captured pixels stay in memory.
// No DLL injection or game renderer changes are made by this helper.
import AppKit
import ScreenCaptureKit
@preconcurrency import VideoToolbox
import CoreMedia
import CoreVideo
import CoreImage
import Metal
import QuartzCore
import Darwin

func report(_ kind: String, _ message: String, _ extra: [String: Any] = [:]) {
    var data = extra; data["kind"] = kind; data["message"] = message
    if let bytes = try? JSONSerialization.data(withJSONObject: data), let line = String(data: bytes, encoding: .utf8) {
        print(line); fflush(stdout)
    }
}

final class PassthroughPanel: NSPanel {
    override var canBecomeKey: Bool { false }
    override var canBecomeMain: Bool { false }
}

@available(macOS 26.0, *)
final class ProcessorSession: @unchecked Sendable {
    let value = VTFrameProcessor() // Used only on the serial processing queue.
}

@available(macOS 26.0, *)
final class FrameGeneration: NSObject, NSApplicationDelegate, SCStreamOutput, SCStreamDelegate, @unchecked Sendable {
    let gamePID: pid_t
    let parentPID: pid_t
    let baseFPS: Int
    let device = MTLCreateSystemDefaultDevice()!
    lazy var commands = device.makeCommandQueue()!
    lazy var imageContext = CIContext(mtlDevice: device, options: [.cacheIntermediates: false])
    let colorSpace = CGColorSpace(name: CGColorSpace.sRGB)!
    let background = CGColor(red: 0, green: 0, blue: 0, alpha: 1)
    let stateLock = NSLock()
    private var stoppedState = false, focusState = false
    private var generationState = 0
    var stopping: Bool {
        get { stateLock.lock(); defer { stateLock.unlock() }; return stoppedState }
        set { stateLock.lock(); stoppedState = newValue; stateLock.unlock() }
    }
    var focused: Bool {
        get { stateLock.lock(); defer { stateLock.unlock() }; return focusState }
        set { stateLock.lock(); focusState = newValue; stateLock.unlock() }
    }
    var generation: Int { stateLock.lock(); defer { stateLock.unlock() }; return generationState }
    @discardableResult func invalidateFrames() -> Int {
        stateLock.lock(); defer { stateLock.unlock() }; generationState += 1; return generationState
    }
    let captureQueue = DispatchQueue(label: "dev.bedrockformac.frame-generation.capture", qos: .userInteractive)
    let processingQueue = DispatchQueue(label: "dev.bedrockformac.frame-generation.processing", qos: .userInteractive)
    let presentationQueue = DispatchQueue(label: "dev.bedrockformac.frame-generation.presentation", qos: .userInteractive)
    var stream: SCStream?
    var processor: VTFrameProcessor?
    var sourcePool: CVPixelBufferPool?
    var outputPool: CVPixelBufferPool?
    var previous: VTFrameProcessorFrame?
    var windowID: CGWindowID = 0
    var panel: PassthroughPanel?
    var layer: CAMetalLayer?
    var statusItem: NSStatusItem?
    var monitor: Timer?
    var terminationSignal: DispatchSourceSignal?
    var width = 0, height = 0
    var processing = false
    var pending: CMSampleBuffer?
    var lastTimestamp = -Double.infinity
    var lastPresentedTimestamp = -Double.infinity
    var originalAspect = 1.0
    var readyToDisplay = false
    var captureCount = 0, generatedCount = 0, displayedCount = 0, droppedCount = 0
    var lastStats = CACurrentMediaTime()
    var consecutiveLate = 0

    init(gamePID: pid_t, parentPID: pid_t, baseFPS: Int) {
        self.gamePID = gamePID; self.parentPID = parentPID; self.baseFPS = baseFPS
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        signal(SIGTERM, SIG_IGN)
        let signalSource = DispatchSource.makeSignalSource(signal: SIGTERM, queue: .main)
        signalSource.setEventHandler { [weak self] in self?.stopAction() }
        signalSource.resume(); terminationSignal = signalSource
        guard VTLowLatencyFrameInterpolationConfiguration.isSupported else {
            fail("Apple frame interpolation is unavailable on this Mac."); return
        }
        // This permission request is reached only after the user presses Start.
        guard CGPreflightScreenCaptureAccess() || CGRequestScreenCaptureAccess() else {
            report("permission", "Allow Minecraft Bedrock in System Settings → Privacy & Security → Screen & System Audio Recording, then stop and restart frame generation.")
            NSApp.terminate(nil); return
        }
        let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        item.button?.title = "FG"; item.button?.toolTip = "Minecraft experimental frame generation"
        let menu = NSMenu()
        let stop = NSMenuItem(title: "Stop Minecraft Frame Generation", action: #selector(stopAction), keyEquivalent: "")
        stop.target = self; menu.addItem(stop); item.menu = menu; statusItem = item
        report("progress", "Preparing experimental frame generation…")
        Task { await start() }
    }

    func start() async {
        do {
            let content = try await SCShareableContent.excludingDesktopWindows(true, onScreenWindowsOnly: true)
            guard let window = content.windows.filter({ $0.owningApplication?.processID == gamePID && $0.frame.width > 200 && $0.frame.height > 150 })
                .max(by: { $0.frame.width * $0.frame.height < $1.frame.width * $1.frame.height }) else {
                throw NSError(domain: "FrameGeneration", code: 1, userInfo: [NSLocalizedDescriptionKey: "Show Minecraft's game window, then start frame generation again."])
            }
            windowID = window.windowID
            originalAspect = window.frame.width / window.frame.height
            let filter = SCContentFilter(desktopIndependentWindow: window)
            let naturalW = max(2, Int(filter.contentRect.width * Double(filter.pointPixelScale)))
            let naturalH = max(2, Int(filter.contentRect.height * Double(filter.pointPixelScale)))
            // Start at native size; scale down only if Apple's processor rejects it.
            var maximumScale = 1.0
            if #available(macOS 27.0, *) {
                if let dimension = VTLowLatencyFrameInterpolationConfiguration.maximumDimension(forSpatialScaleFactor: 1),
                   let pixels = VTLowLatencyFrameInterpolationConfiguration.maximumPixelCount(forSpatialScaleFactor: 1) {
                    maximumScale = min(1, Double(dimension) / Double(max(naturalW, naturalH)), sqrt(Double(pixels) / Double(naturalW * naturalH)))
                }
            }
            let scales: [Double] = [maximumScale, maximumScale * 0.875, maximumScale * 0.75, maximumScale * 0.625, maximumScale * 0.5, maximumScale * 0.375, maximumScale * 0.25]
            var selected: VTLowLatencyFrameInterpolationConfiguration?
            for scale in scales {
                let w = max(2, Int(Double(naturalW) * scale) / 2 * 2)
                let h = max(2, Int(Double(naturalH) * scale) / 2 * 2)
                if let config = VTLowLatencyFrameInterpolationConfiguration(frameWidth: w, frameHeight: h, numberOfInterpolatedFrames: 1) {
                    selected = config; width = w; height = h; break
                }
            }
            guard let configuration = selected else {
                throw NSError(domain: "FrameGeneration", code: 2, userInfo: [NSLocalizedDescriptionKey: "Apple frame interpolation does not support this window's dimensions."])
            }
            // Prefer RGB to retain sharp UI/color; use Apple's supported YUV format otherwise.
            let formats: [OSType] = [kCVPixelFormatType_32BGRA, kCVPixelFormatType_420YpCbCr8BiPlanarFullRange, kCVPixelFormatType_420YpCbCr8BiPlanarVideoRange]
            guard let format = formats.first(where: { configuration.supportedPixelFormats.contains($0) }) else {
                throw NSError(domain: "FrameGeneration", code: 3, userInfo: [NSLocalizedDescriptionKey: "No compatible capture pixel format is available."])
            }
            sourcePool = try pool(attributes: configuration.sourcePixelBufferAttributes, format: format)
            outputPool = try pool(attributes: configuration.destinationPixelBufferAttributes, format: format)
            let session = ProcessorSession()
            // Model setup may take longer than a frame, so keep it off the main thread.
            try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
                processingQueue.async {
                    do { try session.value.startSession(configuration: configuration); continuation.resume() }
                    catch { continuation.resume(throwing: error) }
                }
            }
            processor = session.value
            if stopping { session.value.endSession(); return }
            await MainActor.run { self.makeOverlay(window.frame) }
            let config = SCStreamConfiguration()
            config.width = width; config.height = height; config.pixelFormat = format
            config.minimumFrameInterval = CMTime(value: 1, timescale: CMTimeScale(baseFPS))
            config.queueDepth = 3; config.showsCursor = false; config.capturesAudio = false
            config.colorSpaceName = CGColorSpace.sRGB
            config.ignoreShadowsSingleWindow = true
            config.backgroundColor = background
            let capture = SCStream(filter: filter, configuration: config, delegate: self)
            try capture.addStreamOutput(self, type: .screen, sampleHandlerQueue: captureQueue)
            stream = capture
            try await capture.startCapture()
            lastStats = CACurrentMediaTime()
            await MainActor.run {
                self.monitor = Timer.scheduledTimer(withTimeInterval: 0.15, repeats: true) { [weak self] _ in self?.followWindow() }
                self.followWindow()
            }
            report("started", "Experimental frame generation is ready: \(width) × \(height), up to \(baseFPS * 2) displayed FPS. Set Minecraft's FPS limit to \(baseFPS).", ["width": width, "height": height, "base_fps": baseFPS])
        } catch { await MainActor.run { self.fail(error.localizedDescription) } }
    }

    func pool(attributes: [String: Any], format: OSType) throws -> CVPixelBufferPool {
        var attrs = attributes
        attrs[kCVPixelBufferWidthKey as String] = width
        attrs[kCVPixelBufferHeightKey as String] = height
        attrs[kCVPixelBufferPixelFormatTypeKey as String] = format
        attrs[kCVPixelBufferIOSurfacePropertiesKey as String] = [:]
        attrs[kCVPixelBufferMetalCompatibilityKey as String] = true
        var result: CVPixelBufferPool?
        guard CVPixelBufferPoolCreate(nil, [kCVPixelBufferPoolMinimumBufferCountKey: 3] as CFDictionary, attrs as CFDictionary, &result) == kCVReturnSuccess, let value = result else {
            throw NSError(domain: "FrameGeneration", code: 4, userInfo: [NSLocalizedDescriptionKey: "Could not allocate frame interpolation buffers."])
        }
        return value
    }

    func buffer(_ pool: CVPixelBufferPool?) -> CVPixelBuffer? {
        guard let pool else { return nil }
        var result: CVPixelBuffer?
        let limit = [kCVPixelBufferPoolAllocationThresholdKey: 7] as CFDictionary
        guard CVPixelBufferPoolCreatePixelBufferWithAuxAttributes(nil, pool, limit, &result) == kCVReturnSuccess else { return nil }
        return result
    }

    func makeOverlay(_ frame: CGRect) {
        let view = NSView(frame: .zero); view.wantsLayer = true
        let metal = CAMetalLayer(); metal.device = device; metal.pixelFormat = .bgra8Unorm
        metal.framebufferOnly = false; metal.maximumDrawableCount = 3
        metal.colorspace = colorSpace; metal.isOpaque = true
        metal.drawableSize = CGSize(width: width, height: height)
        view.layer = metal; layer = metal
        let overlay = PassthroughPanel(contentRect: cocoaFrame(frame), styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        overlay.contentView = view; overlay.isOpaque = true; overlay.backgroundColor = .black
        overlay.ignoresMouseEvents = true; overlay.hidesOnDeactivate = false
        overlay.level = .floating; overlay.hasShadow = false
        overlay.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary, .ignoresCycle]
        panel = overlay
        NSRunningApplication(processIdentifier: gamePID)?.activate(options: [.activateIgnoringOtherApps])
    }

    func cocoaFrame(_ rect: CGRect) -> CGRect {
        let mainHeight = NSScreen.screens.first?.frame.height ?? rect.maxY
        return CGRect(x: rect.minX, y: mainHeight - rect.maxY, width: rect.width, height: rect.height)
    }

    func followWindow() {
        guard !stopping else { return }
        guard kill(gamePID, 0) == 0, kill(parentPID, 0) == 0 else { stopAction(); return }
        let windows = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]] ?? []
        guard let item = windows.first(where: { ($0[kCGWindowNumber as String] as? NSNumber)?.uint32Value == windowID }),
              let bounds = item[kCGWindowBounds as String] as? [String: Any],
              let rect = CGRect(dictionaryRepresentation: bounds as CFDictionary) else {
            focused = false; panel?.orderOut(nil); return
        }
        let newFocus = NSWorkspace.shared.frontmostApplication?.processIdentifier == gamePID
        if focused != newFocus {
            focused = newFocus
            invalidateFrames()
            processingQueue.async { self.previous = nil }
        }
        guard newFocus else { panel?.orderOut(nil); return }
        if abs(rect.width / rect.height - originalAspect) > 0.015 {
            fail("The game's window shape changed. Restart frame generation to match the new resolution."); return
        }
        panel?.setFrame(cocoaFrame(rect), display: false)
        layer?.frame = panel?.contentView?.bounds ?? .zero
        // Panel is ordered in only after a real frame has been presented.
        if readyToDisplay { panel?.orderFrontRegardless() }
    }

    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of outputType: SCStreamOutputType) {
        guard outputType == .screen, sampleBuffer.isValid,
              let attachments = CMSampleBufferGetSampleAttachmentsArray(sampleBuffer, createIfNecessary: false) as? [[SCStreamFrameInfo: Any]],
              let raw = attachments.first?[.status] as? Int, SCFrameStatus(rawValue: raw) == .complete else { return }
        processingQueue.async {
            guard !self.stopping else { return }
            if self.processing { self.pending = sampleBuffer; self.droppedCount += 1; return }
            self.process(sampleBuffer)
        }
    }

    func process(_ sample: CMSampleBuffer) {
        guard !stopping, focused, let image = CMSampleBufferGetImageBuffer(sample) else { return }
        let timestamp = CMSampleBufferGetPresentationTimeStamp(sample)
        let seconds = timestamp.seconds
        guard seconds.isFinite, seconds > lastTimestamp else { return }
        lastTimestamp = seconds; captureCount += 1
        // Copy into Apple's required source attributes; retain input until completion.
        guard let source = buffer(sourcePool) else { droppedCount += 1; return }
        imageContext.render(CIImage(cvPixelBuffer: image), to: source, bounds: CGRect(x: 0, y: 0, width: width, height: height), colorSpace: colorSpace)
        guard let current = VTFrameProcessorFrame(buffer: source, presentationTimeStamp: timestamp) else { return }
        guard let prior = previous else {
            previous = current; display(source, token: generation, timestamp: seconds); return
        }
        let interval = seconds - prior.presentationTimeStamp.seconds
        previous = current
        // Break interpolation across focus changes, stalls, menu/loading transitions.
        guard interval >= 1.0 / 240, interval < 0.12, let destination = buffer(outputPool), let processor else {
            display(source, token: invalidateFrames(), timestamp: seconds); return
        }
        let midpoint = CMTimeAdd(prior.presentationTimeStamp, CMTimeMultiplyByFloat64(CMTimeSubtract(timestamp, prior.presentationTimeStamp), multiplier: 0.5))
        guard let result = VTFrameProcessorFrame(buffer: destination, presentationTimeStamp: midpoint),
              let parameters = VTLowLatencyFrameInterpolationParameters(sourceFrame: current, previousFrame: prior, interpolationPhase: [0.5], destinationFrames: [result]) else {
            failFromQueue("Apple rejected the frame interpolation parameters."); return
        }
        processing = true
        let started = CACurrentMediaTime(), token = generation
        processor.process(parameters: parameters) { [weak self] _, error in
            guard let self else { return }
            self.processingQueue.async {
                self.processing = false
                if self.stopping { return }
                if let error { self.failFromQueue("Frame generation stopped: " + error.localizedDescription); return }
                let elapsed = CACurrentMediaTime() - started
                let desiredMidpoint = midpoint.seconds + 2.0 / Double(self.baseFPS)
                if elapsed <= interval && CACurrentMediaTime() < desiredMidpoint && token == self.generation {
                    self.generatedCount += 1; self.consecutiveLate = 0
                    self.display(destination, token: token, timestamp: midpoint.seconds)
                    self.display(source, token: token, timestamp: seconds)
                } else {
                    self.droppedCount += 1; self.consecutiveLate += 1
                    self.display(source, token: self.generation, timestamp: seconds)
                }
                if self.consecutiveLate >= 30 {
                    self.failFromQueue("Frame interpolation cannot keep pace at this resolution. Stop it and use a smaller Minecraft window, or select 30 → 60 FPS."); return
                }
                self.statistics()
                if let next = self.pending { self.pending = nil; self.process(next) }
            }
        }
    }

    func display(_ pixel: CVPixelBuffer, token: Int, timestamp: Double) {
        // A dedicated presenter submits both frames in order and schedules them
        // from capture timestamps, avoiding jitter from model completion times.
        presentationQueue.async {
            guard !self.stopping, self.focused, token == self.generation, timestamp > self.lastPresentedTimestamp, let layer = self.layer,
                  let drawable = layer.nextDrawable(), let command = self.commands.makeCommandBuffer() else { return }
            let texture = drawable.texture
            let image = CIImage(cvPixelBuffer: pixel)
            self.imageContext.render(image, to: texture, commandBuffer: command,
                                     bounds: CGRect(x: 0, y: 0, width: self.width, height: self.height), colorSpace: self.colorSpace)
            self.lastPresentedTimestamp = timestamp
            // Keep the pixel buffer out of its pool until GPU reads complete.
            command.addCompletedHandler { _ in withExtendedLifetime(pixel) {} }
            drawable.addPresentedHandler { _ in DispatchQueue.main.async { self.displayedCount += 1 } }
            let deadline = max(CACurrentMediaTime(), timestamp + 2.0 / Double(self.baseFPS))
            command.present(drawable, atTime: deadline); command.commit()
            DispatchQueue.main.async {
                guard !self.stopping, self.focused, token == self.generation else { return }
                self.readyToDisplay = true; self.panel?.orderFrontRegardless()
            }
        }
    }

    func statistics() {
        let now = CACurrentMediaTime(), interval = now - lastStats
        guard interval >= 2 else { return }
        let captured = Double(captureCount) / interval, generated = Double(generatedCount) / interval
        let dropped = droppedCount
        DispatchQueue.main.async {
            let presented = Double(self.displayedCount) / interval; self.displayedCount = 0
            report("statistics", String(format: "Experimental FG: %.0f captured + %.0f generated • %.0f presented FPS • %d × %d", captured, generated, presented, self.width, self.height),
                   ["captured_fps": captured, "generated_fps": generated, "presented_fps": presented, "dropped_frames": dropped])
        }
        captureCount = 0; generatedCount = 0; droppedCount = 0; lastStats = now
    }

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        DispatchQueue.main.async { self.fail("Window capture stopped: " + error.localizedDescription) }
    }
    func failFromQueue(_ text: String) { DispatchQueue.main.async { self.fail(text) } }
    func fail(_ text: String) { report("error", text); stopAction() }
    @objc func stopAction() {
        guard !stopping else { return }
        stopping = true; invalidateFrames(); monitor?.invalidate(); panel?.orderOut(nil)
        if let statusItem { NSStatusBar.system.removeStatusItem(statusItem) }
        Task {
            try? await stream?.stopCapture()
            processingQueue.async {
                // endSession drains any outstanding request before teardown.
                self.processor?.endSession()
                DispatchQueue.main.async { report("stopped", "Frame generation is off."); NSApp.terminate(nil) }
            }
        }
    }
}

if #available(macOS 26.0, *) {
    if CommandLine.arguments.contains("--capabilities") {
        report("capabilities", "Apple display-side interpolation", ["supported": VTLowLatencyFrameInterpolationConfiguration.isSupported])
    } else {
        let args = CommandLine.arguments
        guard args.count == 4, let pid = Int32(args[1]), let parent = Int32(args[2]), let fps = Int(args[3]), [30, 40, 60].contains(fps),
              pid > 0, parent > 0, MTLCreateSystemDefaultDevice() != nil else {
            report("error", "Launch frame generation from Minecraft Bedrock's launcher."); exit(1)
        }
        let delegate = FrameGeneration(gamePID: pid, parentPID: parent, baseFPS: fps)
        NSApplication.shared.delegate = delegate
        NSApplication.shared.run()
    }
} else { report("error", "Experimental frame generation requires macOS 26 or newer."); exit(1) }
