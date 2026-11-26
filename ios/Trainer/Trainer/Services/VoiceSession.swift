import AVFoundation
import Foundation
import Speech

/// On-device STT + WebSocket session to /v1/voice. TTS via AVSpeechSynthesizer.
@MainActor
final class VoiceSession: NSObject, ObservableObject {
    @Published var transcript = ""
    @Published var partial = ""
    @Published var assistantLines: [String] = []
    @Published var isListening = false
    @Published var status = "Idle"

    private let audioEngine = AVAudioEngine()
    private var recognitionRequest: SFSpeechAudioBufferRecognitionRequest?
    private var recognitionTask: SFSpeechRecognitionTask?
    private let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-IN"))
    private var webSocket: URLSessionWebSocketTask?
    private let synthesizer = AVSpeechSynthesizer()
    private var debounceTask: Task<Void, Never>?

    private let baseURL: String
    private let userId: String

    init(baseURL: String, userId: String) {
        self.baseURL = baseURL
        self.userId = userId
    }

    func prepare() async throws {
        let speech = await withCheckedContinuation { (cont: CheckedContinuation<Bool, Never>) in
            SFSpeechRecognizer.requestAuthorization { status in
                cont.resume(returning: status == .authorized)
            }
        }
        guard speech else { throw VoiceError.speechDenied }
        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.playAndRecord, mode: .measurement, options: [.defaultToSpeaker, .allowBluetooth])
        try session.setActive(true, options: .notifyOthersOnDeactivation)
    }

    func connect() {
        let http = baseURL.replacingOccurrences(of: "http://", with: "ws://")
            .replacingOccurrences(of: "https://", with: "wss://")
        let urlString = http.trimmingCharacters(in: CharacterSet(charactersIn: "/")) + "/voice"
        guard let url = URL(string: urlString) else { return }
        let task = URLSession.shared.webSocketTask(with: url)
        webSocket = task
        task.resume()
        send(dict: ["type": "hello", "user_id": userId])
        listenSocket()
        status = "Connected"
    }

    func startListening() throws {
        recognitionTask?.cancel()
        recognitionRequest = SFSpeechAudioBufferRecognitionRequest()
        guard let recognitionRequest else { return }
        recognitionRequest.shouldReportPartialResults = true

        let input = audioEngine.inputNode
        let format = input.outputFormat(forBus: 0)
        input.removeTap(onBus: 0)
        input.installTap(onBus: 0, bufferSize: 1024, format: format) { buffer, _ in
            recognitionRequest.append(buffer)
        }
        audioEngine.prepare()
        try audioEngine.start()
        isListening = true
        status = "Listening"

        recognitionTask = recognizer?.recognitionTask(with: recognitionRequest) { [weak self] result, error in
            guard let self else { return }
            Task { @MainActor in
                if let result {
                    self.partial = result.bestTranscription.formattedString
                    self.schedulePartialSend(self.partial)
                    if result.isFinal {
                        self.transcript = self.partial
                    }
                }
                if error != nil {
                    self.stopListening(sendFinal: false)
                }
            }
        }
    }

    func stopListening(sendFinal: Bool = true) {
        audioEngine.stop()
        audioEngine.inputNode.removeTap(onBus: 0)
        recognitionRequest?.endAudio()
        recognitionTask?.cancel()
        isListening = false
        status = "Processing"
        if sendFinal {
            let text = transcript.isEmpty ? partial : transcript
            if !text.isEmpty {
                send(dict: [
                    "type": "final_turn",
                    "text": text,
                    "turn_class": "morning_checkin"
                ])
            }
        }
    }

    private func schedulePartialSend(_ text: String) {
        debounceTask?.cancel()
        debounceTask = Task {
            try? await Task.sleep(nanoseconds: 300_000_000)
            guard !Task.isCancelled else { return }
            send(dict: ["type": "partial_transcript", "text": text])
        }
    }

    private func listenSocket() {
        webSocket?.receive { [weak self] result in
            guard let self else { return }
            Task { @MainActor in
                switch result {
                case .failure(let error):
                    self.status = "Socket error: \(error.localizedDescription)"
                case .success(let message):
                    if case .string(let text) = message {
                        self.handleSocketMessage(text)
                    }
                    self.listenSocket()
                }
            }
        }
    }

    private func handleSocketMessage(_ text: String) {
        guard let data = text.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let type = obj["type"] as? String else { return }
        switch type {
        case "assistant_sentence":
            if let line = obj["text"] as? String {
                assistantLines.append(line)
                speak(line)
            }
            status = "Speaking"
        case "assistant_end":
            status = "Done"
        case "error":
            status = (obj["detail"] as? String) ?? "error"
        default:
            break
        }
    }

    private func speak(_ text: String) {
        let utter = AVSpeechUtterance(string: text)
        utter.voice = AVSpeechSynthesisVoice(language: "en-IN") ?? AVSpeechSynthesisVoice(language: "en-US")
        utter.rate = AVSpeechUtteranceDefaultSpeechRate * 0.95
        synthesizer.speak(utter)
    }

    private func send(dict: [String: Any]) {
        guard let data = try? JSONSerialization.data(withJSONObject: dict),
              let str = String(data: data, encoding: .utf8) else { return }
        webSocket?.send(.string(str)) { _ in }
    }

    enum VoiceError: Error { case speechDenied }
}
