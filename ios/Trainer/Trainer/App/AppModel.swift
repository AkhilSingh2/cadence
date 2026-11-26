import Foundation
import SwiftUI

@MainActor
final class AppModel: ObservableObject {
    @Published var plan: DailyPlan?
    @Published var dashboard: DashboardStats?
    @Published var chatMessages: [ChatMessage] = []
    @Published var conversationId: String?
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var apiBaseURL: String

    let userId = "00000000-0000-4000-8000-000000000001"
    let api: APIClient
    let healthKit = HealthKitService()

    init() {
        // Simulator → Mac localhost. Physical device → set your Mac LAN IP in Settings.
        #if targetEnvironment(simulator)
        let defaultURL = "http://127.0.0.1:8000/v1"
        #else
        let defaultURL = UserDefaults.standard.string(forKey: "apiBaseURL") ?? "http://127.0.0.1:8000/v1"
        #endif
        self.apiBaseURL = defaultURL
        self.api = APIClient(baseURL: defaultURL, userId: userId)
    }

    func bootstrap() async {
        isLoading = true
        defer { isLoading = false }
        do {
            try await healthKit.requestAuthorization()
            let days = try await healthKit.fetchRecentDailySummaries(days: 3)
            if !days.isEmpty {
                _ = try await api.syncHealth(days: days)
            }
            plan = try await api.todayPlan()
            dashboard = try await api.dashboard()
        } catch {
            errorMessage = error.localizedDescription
            // Still try to load plan without HealthKit (e.g. simulator without data)
            do {
                plan = try await api.todayPlan()
            } catch {
                errorMessage = error.localizedDescription
            }
        }
    }

    func refreshPlan(rebuild: Bool = false) async {
        do {
            plan = try await api.todayPlan(rebuild: rebuild)
            dashboard = try await api.dashboard()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func simulateBadDay() async {
        do {
            plan = try await api.demoBadDay()
            dashboard = try await api.dashboard()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func logMood(valence: Int, energy: Int, stress: Int, trigger: String?) async {
        do {
            plan = try await api.logMood(valence: valence, energy: energy, stress: stress, trigger: trigger)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func logWeight(_ kg: Double) async {
        do {
            try await api.logWeight(kg)
            dashboard = try await api.dashboard()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func completeTask(_ id: String) async {
        do {
            try await api.completeTask(id: id)
            await refreshPlan()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func sendChat(_ text: String, turnClass: String = "chat") async {
        let userMsg = ChatMessage(role: .user, text: text)
        chatMessages.append(userMsg)
        do {
            let resp = try await api.chat(message: text, conversationId: conversationId, turnClass: turnClass)
            conversationId = resp.conversationId
            chatMessages.append(ChatMessage(role: .assistant, text: resp.reply))
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func updateAPIBase(_ url: String) {
        apiBaseURL = url
        UserDefaults.standard.set(url, forKey: "apiBaseURL")
        api.baseURL = url
    }
}
