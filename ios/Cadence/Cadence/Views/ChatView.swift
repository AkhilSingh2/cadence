import SwiftUI

struct ChatView: View {
    @EnvironmentObject var app: AppModel
    @State private var draft = ""
    @State private var asDSA = false

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 12) {
                            ForEach(app.chatMessages) { msg in
                                HStack {
                                    if msg.role == .user { Spacer(minLength: 40) }
                                    Text(msg.text)
                                        .padding(12)
                                        .background(msg.role == .user ? Color.accentColor.opacity(0.2) : Color(.secondarySystemBackground))
                                        .clipShape(RoundedRectangle(cornerRadius: 14))
                                    if msg.role == .assistant { Spacer(minLength: 40) }
                                }
                                .id(msg.id)
                            }
                        }
                        .padding()
                    }
                    .onChange(of: app.chatMessages.count) { _, _ in
                        if let last = app.chatMessages.last {
                            withAnimation { proxy.scrollTo(last.id, anchor: .bottom) }
                        }
                    }
                }
                Divider()
                Toggle("DSA tutor mode (no full solutions)", isOn: $asDSA)
                    .padding(.horizontal)
                    .padding(.top, 8)
                HStack {
                    TextField("Message", text: $draft, axis: .vertical)
                        .textFieldStyle(.roundedBorder)
                    Button("Send") {
                        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
                        guard !text.isEmpty else { return }
                        draft = ""
                        Task { await app.sendChat(text, turnClass: asDSA ? "dsa_hint" : "chat") }
                    }
                    .buttonStyle(.borderedProminent)
                }
                .padding()
            }
            .navigationTitle("Companion")
        }
    }
}
