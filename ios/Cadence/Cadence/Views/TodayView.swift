import SwiftUI

struct TodayView: View {
    @EnvironmentObject var app: AppModel

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    if let plan = app.plan {
                        stateBanner(plan)
                        if let opener = plan.opener {
                            Text(opener)
                                .font(.title3)
                                .foregroundStyle(.primary)
                        }
                        if let n = plan.nutrition {
                            groupCard("Nutrition") {
                                Text("Protein floor: \(Int(n.proteinFloorG ?? 0))g")
                                if n.surfaceCalories == false {
                                    Text("Calories hidden today — consistency only")
                                        .foregroundStyle(.secondary)
                                }
                                if let tip = n.firstIntake?.suggestion {
                                    Text(tip)
                                }
                            }
                        }
                        if let w = plan.workout {
                            groupCard("Movement") {
                                Text(w.title ?? "Workout")
                                Text("\(w.minutes ?? 0) min · RPE ≤ \(Int(w.rpeCap ?? 7))")
                                    .foregroundStyle(.secondary)
                            }
                        }
                        if let s = plan.study {
                            groupCard("Study") {
                                Text(s.taskTitle ?? "Study block")
                                Text("\(s.minutes ?? 0) minutes")
                                    .foregroundStyle(.secondary)
                            }
                        }
                        if let tasks = plan.microTasks, !tasks.isEmpty {
                            groupCard("Micro-tasks") {
                                ForEach(tasks) { task in
                                    HStack {
                                        Image(systemName: task.isDone ? "checkmark.circle.fill" : "circle")
                                            .foregroundStyle(task.isDone ? .green : .secondary)
                                        VStack(alignment: .leading) {
                                            Text(task.title)
                                            if let m = task.minutes {
                                                Text("\(m) min")
                                                    .font(.caption)
                                                    .foregroundStyle(.secondary)
                                            }
                                        }
                                        Spacer()
                                        if !task.isDone {
                                            Button("Done") {
                                                Task { await app.completeTask(task.id) }
                                            }
                                            .buttonStyle(.bordered)
                                        }
                                    }
                                    .padding(.vertical, 4)
                                }
                            }
                        }
                    } else if app.isLoading {
                        ProgressView("Loading plan…")
                    } else {
                        Text("No plan yet. Pull to refresh or simulate a bad day.")
                            .foregroundStyle(.secondary)
                    }

                    if let err = app.errorMessage {
                        Text(err).foregroundStyle(.red).font(.caption)
                    }
                }
                .padding()
            }
            .navigationTitle("Today")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Menu {
                        Button("Refresh") { Task { await app.refreshPlan(rebuild: true) } }
                        Button("Simulate bad day") { Task { await app.simulateBadDay() } }
                    } label: {
                        Image(systemName: "ellipsis.circle")
                    }
                }
            }
            .refreshable { await app.refreshPlan(rebuild: true) }
        }
    }

    @ViewBuilder
    private func stateBanner(_ plan: DailyPlan) -> some View {
        HStack {
            Text(plan.dayState)
                .font(.headline)
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(color(for: plan.dayState).opacity(0.2))
                .clipShape(Capsule())
            if let score = plan.readinessScore {
                Text(String(format: "Readiness %.0f%%", score * 100))
                    .foregroundStyle(.secondary)
            }
            Spacer()
        }
    }

    private func groupCard<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title).font(.headline)
            content()
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private func color(for state: String) -> Color {
        switch state {
        case "GREEN": return .green
        case "AMBER": return .orange
        default: return .red
        }
    }
}
