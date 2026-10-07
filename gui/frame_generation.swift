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
    let configuration: VTLowLatencyFrameInterpolationConfiguration
    var processedFirstFrame = false
    init(configuration: VTLowLatencyFrameInterpolationConfiguration) {
        self.configuration = configuration
    }
}

struct ProcessorCandidate: Sendable {
    let width: Int, height: Int
    let format: OSType
}

@available(macOS 26.0, *)
final class ProcessingRequest: @unchecked Sendable {
    // Parameters are frozen until the completion handler runs. No queue mutates
    // their input/output frames while the processor owns the request.
    let parameters: VTLowLatencyFrameInterpolationParameters
    init(_ parameters: VTLowLatencyFrameInterpolationParameters) { self.parameters = parameters }
}

@available(macOS 26.0, *)
final class FrameGeneration: NSObject, NSApplicationDelegate, SCStreamOutput, SCStreamDelegate, SCContentSharingPickerObserver, @unchecked Sendable {
    let gamePID: pid_t
    let parentPID: pid_t
    let baseFPS: Int
    let device = MTLCreateSystemDefaultDevice()!
    lazy var commands = device.makeCommandQueue()!
    lazy var imageContext = CIContext(mtlDevice: device, options: [.cacheIntermediates: false])
    let colorSpace = CGColorSpace(name: CGColorSpace.sRGB)!
    let background = CGColor(red: 0, green: 0, blue: 0, alpha: 1)
    let stateLock = NSLock()
    private var stoppedState = false, focusState = false, recoveringState = false
    private var generationState = 0
    var stopping: Bool {
        get { stateLock.lock(); defer { stateLock.unlock() }; return stoppedState }
        set { stateLock.lock(); stoppedState = newValue; stateLock.unlock() }
    }
    var focused: Bool {
        get { stateLock.lock(); defer { stateLock.unlock() }; return focusState }
        set { stateLock.lock(); focusState = newValue; stateLock.unlock() }
    }
    var recovering: Bool {
        get { stateLock.lock(); defer { stateLock.unlock() }; return recoveringState }
        set { stateLock.lock(); recoveringState = newValue; stateLock.unlock() }
    }
    var generation: Int { stateLock.lock(); defer { stateLock.unlock() }; return generationState }
    @discardableResult func invalidateFrames() -> Int {
        stateLock.lock(); defer { stateLock.unlock() }; generationState += 1; return generationState
    }
    let captureQueue = DispatchQueue(label: "dev.bedrockformac.frame-generation.capture", qos: .userInteractive)
    let processingQueue = DispatchQueue(label: "dev.bedrockformac.frame-generation.processing", qos: .userInteractive)
    let presentationQueue = DispatchQueue(label: "dev.bedrockformac.frame-generation.presentation", qos: .userInteractive)
    var stream: SCStream?
    var processorSession: ProcessorSession?
    var candidates: [ProcessorCandidate] = []
    var nextCandidate = 0
    var lastProcessorError: NSError?
    var sourcePool: CVPixelBufferPool?
    var outputPool: CVPixelBufferPool?
    var previous: VTFrameProcessorFrame?
    var windowID: CGWindowID = 0
    var panel: PassthroughPanel?
    var layer: CAMetalLayer?
    var statusItem: NSStatusItem?
    var monitor: Timer?
    var terminationSignal: DispatchSourceSignal?
    var pickerActive = false
    var selectingWindow = false
    var width = 0, height = 0
    var captureWidth = 0, captureHeight = 0
    var processingContentRect = CGRect.zero
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
        let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        item.button?.title = "FG"; item.button?.toolTip = "Minecraft experimental frame generation"
        let menu = NSMenu()
        let stop = NSMenuItem(title: "Stop Minecraft Frame Generation", action: #selector(stopAction), keyEquivalent: "")
        stop.target = self; menu.addItem(stop); item.menu = menu; statusItem = item
        monitor = Timer.scheduledTimer(withTimeInterval: 0.15, repeats: true) { [weak self] _ in self?.followWindow() }
        report("progress", "Preparing experimental frame generation…")
        // Ad-hoc updates may invalidate the previous global TCC grant. The
        // system picker authorizes the chosen window without a Settings loop.
        if CGPreflightScreenCaptureAccess() { Task { await start() } }
        else { presentWindowPicker() }
    }

    func presentWindowPicker() {
        guard !stopping, !selectingWindow else { return }
        selectingWindow = true
        let picker = SCContentSharingPicker.shared
        var configuration = SCContentSharingPickerConfiguration()
        configuration.allowedPickerModes = [.singleWindow]
        configuration.excludedBundleIDs = ["dev.bedrockformac.launcher"]
        configuration.allowsChangingSelectedContent = false
        picker.defaultConfiguration = configuration
        if !pickerActive { picker.add(self); pickerActive = true }
        picker.isActive = true
        report("progress", "Select the Minecraft game window in macOS's window picker to start frame generation.")
        picker.present(using: .window)
    }

    func contentSharingPicker(_ picker: SCContentSharingPicker, didCancelFor stream: SCStream?) {
        DispatchQueue.main.async {
            self.selectingWindow = false
            report("progress", "Window selection canceled. Frame generation is off.")
            self.stopAction()
        }
    }

    func contentSharingPicker(_ picker: SCContentSharingPicker, didUpdateWith filter: SCContentFilter, for stream: SCStream?) {
        DispatchQueue.main.async {
            guard !self.stopping, self.selectingWindow else { return }
            self.selectingWindow = false
            guard filter.includedWindows.count == 1, let window = filter.includedWindows.first,
                  window.owningApplication?.processID == self.gamePID,
                  window.frame.width > 200, window.frame.height > 150 else {
                self.fail("Select Minecraft's game window when starting frame generation."); return
            }
            // Keep the picker-issued filter: rebuilding it would discard its
            // authorization and incorrectly ask for global recording access.
            Task { await self.start(filter: filter, window: window) }
        }
    }

    func contentSharingPickerStartDidFailWithError(_ error: Error) {
        DispatchQueue.main.async { self.selectingWindow = false; self.fail("Could not open Minecraft's window picker: " + error.localizedDescription) }
    }

    func start() async {
        do {
            let content = try await SCShareableContent.excludingDesktopWindows(true, onScreenWindowsOnly: true)
            guard let window = content.windows.filter({ $0.owningApplication?.processID == gamePID && $0.frame.width > 200 && $0.frame.height > 150 })
                .max(by: { $0.frame.width * $0.frame.height < $1.frame.width * $1.frame.height }) else {
                throw NSError(domain: "FrameGeneration", code: 1, userInfo: [NSLocalizedDescriptionKey: "Show Minecraft's game window, then start frame generation again."])
            }
            let filter = SCContentFilter(desktopIndependentWindow: window)
            await start(filter: filter, window: window)
        } catch {
            let value = error as NSError
            if value.domain == SCStreamErrorDomain, value.code == SCStreamError.Code.userDeclined.rawValue {
                await MainActor.run { self.presentWindowPicker() }
            } else if !stopping { await MainActor.run { self.fail(error.localizedDescription) } }
        }
    }

    func start(filter: SCContentFilter, window: SCWindow) async {
        do {
            guard !stopping else { return }
            candidates.removeAll(); nextCandidate = 0
            windowID = window.windowID
            originalAspect = window.frame.width / window.frame.height
            let naturalW = max(2, Int(filter.contentRect.width * Double(filter.pointPixelScale)))
            let naturalH = max(2, Int(filter.contentRect.height * Double(filter.pointPixelScale)))
            captureWidth = naturalW; captureHeight = naturalH
            // A non-nil configuration and startSession alone do not establish
            // readiness. Some models reject dimensions on the first process call.
            var maximumScale = 1.0
            var maximumDimension = Int.max, maximumPixels = Int.max
            if #available(macOS 27.0, *) {
                if let dimension = VTLowLatencyFrameInterpolationConfiguration.maximumDimension(forSpatialScaleFactor: 1),
                   let pixels = VTLowLatencyFrameInterpolationConfiguration.maximumPixelCount(forSpatialScaleFactor: 1) {
                    maximumDimension = dimension; maximumPixels = pixels
                    maximumScale = min(1, Double(dimension) / Double(max(naturalW, naturalH)), sqrt(Double(pixels) / Double(naturalW * naturalH)))
                }
            }
            let fitted = (max(16, Int(Double(naturalW) * maximumScale) / 16 * 16),
                          max(16, Int(Double(naturalH) * maximumScale) / 16 * 16))
            // Standard video canvases are fallback candidates. Letterbox before
            // processing and crop afterwards so the game's aspect never changes.
            let dimensions = [fitted, (1920, 1080), (1280, 720), (960, 540), (640, 360)]
            let formats: [OSType] = [kCVPixelFormatType_32BGRA, kCVPixelFormatType_420YpCbCr8BiPlanarFullRange, kCVPixelFormatType_420YpCbCr8BiPlanarVideoRange]
            var seen = Set<String>()
            for (w, h) in dimensions {
                guard w <= maximumDimension, h <= maximumDimension, w * h <= maximumPixels,
                      w * h <= max(naturalW * naturalH, 640 * 360), seen.insert("\(w)x\(h)").inserted else { continue }
                if let config = VTLowLatencyFrameInterpolationConfiguration(frameWidth: w, frameHeight: h, numberOfInterpolatedFrames: 1) {
                    for format in formats where config.supportedPixelFormats.contains(format) {
                        candidates.append(ProcessorCandidate(width: w, height: h, format: format))
                    }
                }
            }
            guard !candidates.isEmpty else {
                throw NSError(domain: "FrameGeneration", code: 2, userInfo: [NSLocalizedDescriptionKey: "Apple frame interpolation does not support this window's dimensions."])
            }
            try await prepareNextProcessor()
            guard !stopping else { return }
            await MainActor.run { self.makeOverlay(window.frame) }
            let config = SCStreamConfiguration()
            // Keep original frames sharp even if the interpolation model has to
            // fall back. Convert only the model's input to its negotiated format.
            config.width = captureWidth; config.height = captureHeight; config.pixelFormat = kCVPixelFormatType_32BGRA
            config.minimumFrameInterval = CMTime(value: 1, timescale: CMTimeScale(baseFPS))
            config.queueDepth = 3; config.showsCursor = false; config.capturesAudio = false
            config.colorSpaceName = CGColorSpace.sRGB
            config.ignoreShadowsSingleWindow = true
            config.backgroundColor = background
            let capture = SCStream(filter: filter, configuration: config, delegate: self)
            try capture.addStreamOutput(self, type: .screen, sampleHandlerQueue: captureQueue)
            stream = capture
            report("progress", "Waiting for the first interpolated frame… Set Minecraft's FPS limit to \(baseFPS).")
            try await capture.startCapture()
            lastStats = CACurrentMediaTime()
            await MainActor.run { self.followWindow() }
        } catch {
            guard !stopping else { return }
            let value = error as NSError
            if value.domain == SCStreamErrorDomain, value.code == SCStreamError.Code.userDeclined.rawValue, !pickerActive {
                stream = nil
                await MainActor.run {
                    self.panel?.orderOut(nil); self.panel = nil; self.layer = nil
                    self.presentWindowPicker()
                }
            } else { await MainActor.run { self.fail(error.localizedDescription) } }
        }
    }

    func prepareNextProcessor() async throws {
        recovering = true
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            processingQueue.async {
                // The processor, configuration, pools, and history share one
                // serial owner. Keep the configuration alive for the session.
                self.processorSession?.value.endSession(); self.processorSession = nil
                self.previous = nil; self.pending = nil; self.processing = false
                self.sourcePool = nil; self.outputPool = nil
                self.lastTimestamp = -Double.infinity; self.consecutiveLate = 0
                while !self.stopping, self.nextCandidate < self.candidates.count {
                    let candidate = self.candidates[self.nextCandidate]; self.nextCandidate += 1
                    self.width = candidate.width; self.height = candidate.height
                    guard let configuration = VTLowLatencyFrameInterpolationConfiguration(frameWidth: candidate.width, frameHeight: candidate.height, numberOfInterpolatedFrames: 1) else { continue }
                    let session = ProcessorSession(configuration: configuration)
                    do {
                        let source = try self.pool(attributes: configuration.sourcePixelBufferAttributes, format: candidate.format)
                        let output = try self.pool(attributes: configuration.destinationPixelBufferAttributes, format: candidate.format)
                        try session.value.startSession(configuration: session.configuration)
                        self.processorSession = session; self.sourcePool = source; self.outputPool = output
                        let scale = min(Double(candidate.width) / Double(self.captureWidth), Double(candidate.height) / Double(self.captureHeight))
                        let w = Double(self.captureWidth) * scale, h = Double(self.captureHeight) * scale
                        self.processingContentRect = CGRect(x: (Double(candidate.width) - w) / 2, y: (Double(candidate.height) - h) / 2, width: w, height: h)
                        report("progress", "Preparing \(candidate.width) × \(candidate.height) interpolation…", ["attempt": self.nextCandidate, "pixel_format": candidate.format])
                        self.recovering = false
                        continuation.resume(); return
                    } catch {
                        session.value.endSession(); self.lastProcessorError = error as NSError
                        self.reportProcessorError(error, stage: "start", candidate: candidate)
                    }
                }
                continuation.resume(throwing: self.unavailableError())
            }
        }
    }

    func reportProcessorError(_ error: Error, stage: String, candidate: ProcessorCandidate? = nil) {
        let value = error as NSError
        report("diagnostic", "Interpolation \(stage) failed: \(value.localizedDescription)",
               ["error_domain": value.domain, "error_code": value.code, "attempt": nextCandidate,
                "width": candidate?.width ?? width, "height": candidate?.height ?? height,
                "pixel_format": candidate?.format ?? 0])
    }

    func unavailableError() -> NSError {
        let detail = lastProcessorError.map { " (\($0.domain), \($0.code): \($0.localizedDescription))" } ?? ""
        return NSError(domain: "FrameGeneration", code: 5, userInfo: [NSLocalizedDescriptionKey:
            "Apple's interpolation processor could not initialize at any compatible size. Frame generation is off; Minecraft can keep running." + detail])
    }

    func recoverProcessor(after error: Error) {
        lastProcessorError = error as NSError
        reportProcessorError(error, stage: "processing")
        guard nextCandidate < candidates.count else { failFromQueue(unavailableError().localizedDescription); return }
        recovering = true; invalidateFrames()
        previous = nil; pending = nil
        DispatchQueue.main.async {
            self.readyToDisplay = false; self.panel?.orderOut(nil)
            report("progress", "Apple rejected this interpolation mode. Trying a compatible mode…")
        }
        Task {
            do { try await self.prepareNextProcessor() }
            catch { if !self.stopping { self.failFromQueue(error.localizedDescription) } }
        }
    }

    func pool(attributes: [String: Any], format: OSType) throws -> CVPixelBufferPool {
        var attrs: [String: Any] = [:]
        attrs[kCVPixelBufferWidthKey as String] = width
        attrs[kCVPixelBufferHeightKey as String] = height
        attrs[kCVPixelBufferPixelFormatTypeKey as String] = format
        attrs[kCVPixelBufferIOSurfacePropertiesKey as String] = [:]
        attrs[kCVPixelBufferMetalCompatibilityKey as String] = true
        var resolved: CFDictionary?
        guard CVPixelBufferCreateResolvedAttributesDictionary(nil, [attributes, attrs] as CFArray, &resolved) == kCVReturnSuccess, let resolved else {
            throw NSError(domain: "FrameGeneration", code: 4, userInfo: [NSLocalizedDescriptionKey: "Apple's frame buffer requirements could not be combined."])
        }
        var result: CVPixelBufferPool?
        guard CVPixelBufferPoolCreate(nil, [kCVPixelBufferPoolMinimumBufferCountKey: 3] as CFDictionary, resolved, &result) == kCVReturnSuccess, let value = result else {
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
        metal.drawableSize = CGSize(width: captureWidth, height: captureHeight)
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
        guard !stopping, !recovering, outputType == .screen, sampleBuffer.isValid,
              let attachments = CMSampleBufferGetSampleAttachmentsArray(sampleBuffer, createIfNecessary: false) as? [[SCStreamFrameInfo: Any]],
              let raw = attachments.first?[.status] as? Int, SCFrameStatus(rawValue: raw) == .complete else { return }
        processingQueue.async {
            guard !self.stopping, !self.recovering else { return }
            if self.processing { self.pending = sampleBuffer; self.droppedCount += 1; return }
            self.process(sampleBuffer)
        }
    }

    func process(_ sample: CMSampleBuffer) {
        guard !stopping, !recovering, focused, let session = processorSession,
              let image = CMSampleBufferGetImageBuffer(sample) else { return }
        let timestamp = CMSampleBufferGetPresentationTimeStamp(sample)
        let seconds = timestamp.seconds
        guard seconds.isFinite, seconds > lastTimestamp else { return }
        lastTimestamp = seconds; captureCount += 1
        // Copy into Apple's required source attributes; retain input until completion.
        guard let source = buffer(sourcePool) else { droppedCount += 1; return }
        let input = CIImage(cvPixelBuffer: image)
        let rect = processingContentRect
        let fitted = input.transformed(by: CGAffineTransform(translationX: -input.extent.minX, y: -input.extent.minY))
            .transformed(by: CGAffineTransform(scaleX: rect.width / input.extent.width, y: rect.height / input.extent.height))
            .transformed(by: CGAffineTransform(translationX: rect.minX, y: rect.minY))
        let canvas = CGRect(x: 0, y: 0, width: width, height: height)
        let padded = fitted.composited(over: CIImage(color: .black).cropped(to: canvas))
        imageContext.render(padded, to: source, bounds: canvas, colorSpace: colorSpace)
        guard let current = VTFrameProcessorFrame(buffer: source, presentationTimeStamp: timestamp) else { return }
        guard let prior = previous else {
            previous = current
            if session.processedFirstFrame { display(image, token: generation, timestamp: seconds) }
            return
        }
        let interval = seconds - prior.presentationTimeStamp.seconds
        previous = current
        // Break interpolation across focus changes, stalls, menu/loading transitions.
        guard interval >= 1.0 / 240, interval < 0.12, let destination = buffer(outputPool) else {
            let token = invalidateFrames()
            if session.processedFirstFrame { display(image, token: token, timestamp: seconds) }
            return
        }
        let midpoint = CMTimeAdd(prior.presentationTimeStamp, CMTimeMultiplyByFloat64(CMTimeSubtract(timestamp, prior.presentationTimeStamp), multiplier: 0.5))
        guard let result = VTFrameProcessorFrame(buffer: destination, presentationTimeStamp: midpoint),
              let parameters = VTLowLatencyFrameInterpolationParameters(sourceFrame: current, previousFrame: prior, interpolationPhase: [0.5], destinationFrames: [result]) else {
            failFromQueue("Apple rejected the frame interpolation parameters."); return
        }
        processing = true
        let started = CACurrentMediaTime(), token = generation
        let request = ProcessingRequest(parameters)
        session.value.process(parameters: request.parameters) { [weak self, session, request] _, error in
            // Retain every input/output frame and the session through completion.
            withExtendedLifetime(request) {}
            guard let self else { return }
            self.processingQueue.async {
                guard self.processorSession === session else { return }
                self.processing = false
                if self.stopping { return }
                if let error {
                    let code = (error as NSError).code
                    if !session.processedFirstFrame || [-19730, -19731, -19732, -19735, -19736, -19737, -19738, -12911].contains(code) {
                        self.recoverProcessor(after: error)
                    } else { self.reportProcessorError(error, stage: "processing"); self.failFromQueue("Frame generation stopped: " + error.localizedDescription) }
                    return
                }
                if !session.processedFirstFrame {
                    session.processedFirstFrame = true
                    report("started", "Frame generation is running: \(self.width) × \(self.height) interpolation, up to \(self.baseFPS * 2) displayed FPS.",
                           ["width": self.width, "height": self.height, "base_fps": self.baseFPS, "attempt": self.nextCandidate])
                }
                let elapsed = CACurrentMediaTime() - started
                let desiredMidpoint = midpoint.seconds + 2.0 / Double(self.baseFPS)
                if elapsed <= interval && CACurrentMediaTime() < desiredMidpoint && token == self.generation {
                    self.generatedCount += 1; self.consecutiveLate = 0
                    self.display(destination, token: token, timestamp: midpoint.seconds, contentRect: rect)
                    self.display(image, token: token, timestamp: seconds)
                } else {
                    self.droppedCount += 1; self.consecutiveLate += 1
                    self.display(image, token: self.generation, timestamp: seconds)
                }
                if self.consecutiveLate >= 30 {
                    self.failFromQueue("Frame interpolation cannot keep pace at this resolution. Stop it and use a smaller Minecraft window, or select 30 → 60 FPS."); return
                }
                self.statistics()
                if let next = self.pending { self.pending = nil; self.process(next) }
            }
        }
    }

    func display(_ pixel: CVPixelBuffer, token: Int, timestamp: Double, contentRect: CGRect? = nil) {
        // A dedicated presenter submits both frames in order and schedules them
        // from capture timestamps, avoiding jitter from model completion times.
        presentationQueue.async {
            guard !self.stopping, self.focused, token == self.generation, timestamp > self.lastPresentedTimestamp, let layer = self.layer,
                  let drawable = layer.nextDrawable(), let command = self.commands.makeCommandBuffer() else { return }
            let texture = drawable.texture
            var image = CIImage(cvPixelBuffer: pixel)
            if let contentRect { image = image.cropped(to: contentRect) }
            image = image.transformed(by: CGAffineTransform(translationX: -image.extent.minX, y: -image.extent.minY))
                .transformed(by: CGAffineTransform(scaleX: Double(texture.width) / image.extent.width, y: Double(texture.height) / image.extent.height))
            self.imageContext.render(image, to: texture, commandBuffer: command,
                                     bounds: CGRect(x: 0, y: 0, width: texture.width, height: texture.height), colorSpace: self.colorSpace)
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
        let interpolationWidth = width, interpolationHeight = height
        DispatchQueue.main.async {
            let presented = Double(self.displayedCount) / interval; self.displayedCount = 0
            report("statistics", String(format: "Experimental FG: %.0f captured + %.0f generated • %.0f presented FPS • %d × %d", captured, generated, presented, interpolationWidth, interpolationHeight),
                   ["captured_fps": captured, "generated_fps": generated, "presented_fps": presented, "dropped_frames": dropped])
        }
        captureCount = 0; generatedCount = 0; droppedCount = 0; lastStats = now
    }

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        DispatchQueue.main.async { self.fail("Window capture stopped: " + error.localizedDescription) }
    }
    func failFromQueue(_ text: String) { DispatchQueue.main.async { self.fail(text) } }
    func fail(_ text: String) { guard !stopping else { return }; report("error", text); stopAction() }
    @objc func stopAction() {
        guard !stopping else { return }
        stopping = true; invalidateFrames(); monitor?.invalidate(); panel?.orderOut(nil)
        if pickerActive { SCContentSharingPicker.shared.remove(self); SCContentSharingPicker.shared.isActive = false; pickerActive = false }
        if let statusItem { NSStatusBar.system.removeStatusItem(statusItem) }
        Task {
            try? await stream?.stopCapture()
            processingQueue.async {
                // endSession drains any outstanding request before teardown.
                self.processorSession?.value.endSession(); self.processorSession = nil
                self.previous = nil; self.pending = nil; self.sourcePool = nil; self.outputPool = nil
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
