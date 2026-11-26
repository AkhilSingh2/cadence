import SwiftUI

struct RootTabView: View {
    var body: some View {
        TabView {
            TodayView()
                .tabItem { Label("Today", systemImage: "sun.max") }
            ChatView()
                .tabItem { Label("Chat", systemImage: "bubble.left.and.bubble.right") }
            VoiceCheckInView()
                .tabItem { Label("Voice", systemImage: "mic") }
            DashboardView()
                .tabItem { Label("Progress", systemImage: "chart.line.uptrend.xyaxis") }
            LogView()
                .tabItem { Label("Log", systemImage: "square.and.pencil") }
        }
    }
}
