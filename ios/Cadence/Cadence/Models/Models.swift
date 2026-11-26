import Foundation

struct DailyPlan: Codable, Identifiable {
    var id: String?
    var day: String?
    var dayState: String
    var tone: String?
    var readinessScore: Double?
    var opener: String?
    var nutrition: NutritionBlock?
    var workout: WorkoutBlock?
    var study: StudyBlock?
    var microTasks: [MicroTask]?
    var volumeMultiplier: Double?

    enum CodingKeys: String, CodingKey {
        case id, day, tone, opener, nutrition, workout, study
        case dayState = "day_state"
        case readinessScore = "readiness_score"
        case microTasks = "micro_tasks"
        case volumeMultiplier = "volume_multiplier"
    }

    var stateColorName: String {
        switch dayState {
        case "GREEN": return "green"
        case "AMBER": return "orange"
        case "RED", "DELOAD": return "red"
        default: return "gray"
        }
    }
}

struct NutritionBlock: Codable {
    var surfaceCalories: Bool?
    var proteinFloorG: Double?
    var firstIntake: FirstIntake?
    var mealCount: Int?

    enum CodingKeys: String, CodingKey {
        case mealCount = "meal_count"
        case surfaceCalories = "surface_calories"
        case proteinFloorG = "protein_floor_g"
        case firstIntake = "first_intake"
    }
}

struct FirstIntake: Codable {
    var suggestion: String?
    var effort: String?
    var texture: String?
}

struct WorkoutBlock: Codable {
    var kind: String?
    var minutes: Int?
    var rpeCap: Double?
    var title: String?

    enum CodingKeys: String, CodingKey {
        case kind, minutes, title
        case rpeCap = "rpe_cap"
    }
}

struct StudyBlock: Codable {
    var minutes: Int?
    var taskTitle: String?
    var allowHints: Bool?
    var difficultyBias: String?

    enum CodingKeys: String, CodingKey {
        case minutes
        case taskTitle = "task_title"
        case allowHints = "allow_hints"
        case difficultyBias = "difficulty_bias"
    }
}

struct MicroTask: Codable, Identifiable {
    var id: String
    var kind: String
    var title: String
    var minutes: Int?
    var completedAt: String?
    var countsTowardStreak: Bool?

    enum CodingKeys: String, CodingKey {
        case id, kind, title, minutes
        case completedAt = "completed_at"
        case countsTowardStreak = "counts_toward_streak"
    }

    var isDone: Bool { completedAt != nil }
}

struct ChatMessage: Identifiable {
    enum Role { case user, assistant }
    let id = UUID()
    let role: Role
    let text: String
}

struct ChatResponse: Codable {
    var conversationId: String
    var reply: String
    var modelTier: String?
    var dayState: String?

    enum CodingKeys: String, CodingKey {
        case reply
        case conversationId = "conversation_id"
        case modelTier = "model_tier"
        case dayState = "day_state"
    }
}

struct DashboardStats: Codable {
    var weights: [WeightPoint]
    var readiness: [ReadinessPoint]
    var streaks: [StreakPoint]
    var curriculum: [String: Int]
}

struct WeightPoint: Codable, Identifiable {
    var id: String { measuredAt }
    var measuredAt: String
    var weightKg: Double?
    var weightEwma: Double?

    enum CodingKeys: String, CodingKey {
        case measuredAt = "measured_at"
        case weightKg = "weight_kg"
        case weightEwma = "weight_ewma"
    }
}

struct ReadinessPoint: Codable, Identifiable {
    var id: String { day }
    var day: String
    var readinessScore: Double?
    var dayState: String?

    enum CodingKeys: String, CodingKey {
        case day
        case readinessScore = "readiness_score"
        case dayState = "day_state"
    }
}

struct StreakPoint: Codable, Identifiable {
    var id: String { day }
    var day: String
    var showedUp: Bool?
    var tasksCompleted: Int?

    enum CodingKeys: String, CodingKey {
        case day
        case showedUp = "showed_up"
        case tasksCompleted = "tasks_completed"
    }
}

struct HealthDayPayload: Codable {
    var day: String
    var sleepHours: Double?
    var sleepEfficiency: Double?
    var hrvSdnnMs: Double?
    var rhrBpm: Double?
    var activeEnergyKcal: Double?
    var steps: Int?
    var wakeDetectedAt: String?
    var hrvBaseline14d: Double?
    var rhrBaseline14d: Double?
    var source: String

    enum CodingKeys: String, CodingKey {
        case day, steps, source
        case sleepHours = "sleep_hours"
        case sleepEfficiency = "sleep_efficiency"
        case hrvSdnnMs = "hrv_sdnn_ms"
        case rhrBpm = "rhr_bpm"
        case activeEnergyKcal = "active_energy_kcal"
        case wakeDetectedAt = "wake_detected_at"
        case hrvBaseline14d = "hrv_baseline_14d"
        case rhrBaseline14d = "rhr_baseline_14d"
    }
}
