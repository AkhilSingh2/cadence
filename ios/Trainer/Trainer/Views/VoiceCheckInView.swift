import SwiftUI

struct VoiceCheckInView: View {
    @EnvironmentObject var app: AppModel
    @StateObject private var sessionHolder = VoiceSessionHolder()

    var body: some View {
        NavigationStack {
            VStack(spacing: 20) {
                Text(sessionHolder.session?.status ?? "Not connected")
                    .foregroundStyle(.secondary)
                Text(sessionHolder.session?.partial ?? "")
                    .font(.title3)
                    .frame(maxWidth: .infinity, minHeight: 80, alignment: .topLeading)
                    .padding()
                    .background(Color(.secondarySystemBackground))
                    .clipShape(RoundedRectangle(cornerRadius: 12))

                ScrollView {
                    VStack(alignment: .leading, spacing: 8) {
                        ForEach(sessionHolder.session?.assistantLines ?? [], id: \.self) { line in
                            Text(line)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }

                HStack(spacing: 16) {
                    Button("Connect") {
                        Task {
                            let s = VoiceSession(baseURL: app.apiBaseURL, userId: app.userId)
                            try? await s.prepare()
                            s.connect()
                            sessionHolder.session = s
                        }
                    }
                    .buttonStyle(.bordered)

                    if sessionHolder.session?.isListening == true {
                        Button("Stop & send") {
                            sessionHolder.session?.stopListening(sendFinal: true)
                        }
                        .buttonStyle(.borderedProminent)
                    } else {
                        Button("Hold to talk") {
                            try? sessionHolder.session?.startListening()
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(sessionHolder.session == nil)
                    }
                }
                Spacer()
            }
            .padding()
            .navigationTitle("Voice")
        }
    }
}

@MainActor
final class VoiceSessionHolder: ObservableObject {
    @Published var session: VoiceSession?
}
