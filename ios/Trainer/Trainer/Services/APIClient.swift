import Foundation

enum APIError: Error, LocalizedError {
    case badURL
    case http(Int, String)
    case decode

    var errorDescription: String? {
        switch self {
        case .badURL: return "Bad API URL"
        case .http(let code, let body): return "HTTP \(code): \(body)"
        case .decode: return "Failed to decode response"
        }
    }
}

final class APIClient {
    var baseURL: String
    let userId: String
    private let session: URLSession
    private let decoder: JSONDecoder

    init(baseURL: String, userId: String) {
        self.baseURL = baseURL
        self.userId = userId
        self.session = .shared
        self.decoder = JSONDecoder()
    }

    private func request(
        _ path: String,
        method: String = "GET",
        body: Data? = nil
    ) async throws -> Data {
        guard let url = URL(string: baseURL.trimmingCharacters(in: CharacterSet(charactersIn: "/")) + "/" + path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))) else {
            throw APIError.badURL
        }
        var req = URLRequest(url: url)
        req.httpMethod = method
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue(userId, forHTTPHeaderField: "X-User-Id")
        req.httpBody = body
        let (data, resp) = try await session.data(for: req)
        guard let http = resp as? HTTPURLResponse else { throw APIError.http(-1, "no response") }
        guard (200..<300).contains(http.statusCode) else {
            throw APIError.http(http.statusCode, String(data: data, encoding: .utf8) ?? "")
        }
        return data
    }

    func todayPlan(rebuild: Bool = false) async throws -> DailyPlan {
        let q = rebuild ? "plans/today?rebuild=true" : "plans/today"
        let data = try await request(q)
        return try decoder.decode(DailyPlan.self, from: data)
    }

    func demoBadDay() async throws -> DailyPlan {
        let data = try await request("demo/bad-day", method: "POST", body: Data("{}".utf8))
        return try decoder.decode(DailyPlan.self, from: data)
    }

    func syncHealth(days: [HealthDayPayload]) async throws -> DailyPlan {
        struct SyncBody: Codable { var days: [HealthDayPayload] }
        struct SyncResp: Codable { var plan: DailyPlan }
        let body = try JSONEncoder().encode(SyncBody(days: days))
        let data = try await request("health/sync", method: "POST", body: body)
        return try decoder.decode(SyncResp.self, from: data).plan
    }

    func logMood(valence: Int, energy: Int, stress: Int, trigger: String?) async throws -> DailyPlan {
        var dict: [String: Any] = [
            "valence": valence, "energy": energy, "stress": stress, "source": "tap"
        ]
        if let trigger { dict["trigger_text"] = trigger }
        let body = try JSONSerialization.data(withJSONObject: dict)
        struct Resp: Codable { var plan: DailyPlan }
        let data = try await request("mood", method: "POST", body: body)
        return try decoder.decode(Resp.self, from: data).plan
    }

    func logWeight(_ kg: Double) async throws {
        let body = try JSONSerialization.data(withJSONObject: ["weight_kg": kg])
        _ = try await request("weight", method: "POST", body: body)
    }

    func completeTask(id: String) async throws {
        let body = try JSONSerialization.data(withJSONObject: ["task_id": id])
        _ = try await request("tasks/complete", method: "POST", body: body)
    }

    func chat(message: String, conversationId: String?, turnClass: String) async throws -> ChatResponse {
        var dict: [String: Any] = ["message": message, "turn_class": turnClass]
        if let conversationId { dict["conversation_id"] = conversationId }
        let body = try JSONSerialization.data(withJSONObject: dict)
        let data = try await request("chat", method: "POST", body: body)
        return try decoder.decode(ChatResponse.self, from: data)
    }

    func dashboard() async throws -> DashboardStats {
        let data = try await request("dashboard")
        return try decoder.decode(DashboardStats.self, from: data)
    }

    func addPreference(_ content: String) async throws {
        let body = try JSONSerialization.data(withJSONObject: [
            "content": content,
            "metadata": ["disliked": true]
        ])
        _ = try await request("preferences", method: "POST", body: body)
    }
}
