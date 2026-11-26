import Charts
import SwiftUI

struct DashboardView: View {
    @EnvironmentObject var app: AppModel

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    if let dash = app.dashboard {
                        Text("Weight (EWMA)").font(.headline)
                        Chart(dash.weights) { pt in
                            if let y = pt.weightEwma ?? pt.weightKg {
                                LineMark(
                                    x: .value("Day", pt.measuredAt),
                                    y: .value("kg", y)
                                )
                            }
                        }
                        .frame(height: 180)

                        Text("Readiness").font(.headline)
                        Chart(dash.readiness) { pt in
                            if let y = pt.readinessScore {
                                BarMark(
                                    x: .value("Day", pt.day),
                                    y: .value("Score", y)
                                )
                                .foregroundStyle(color(for: pt.dayState))
                            }
                        }
                        .frame(height: 180)

                        Text("Showing-up streak").font(.headline)
                        let shown = dash.streaks.filter { $0.showedUp == true }.count
                        Text("\(shown) of last \(dash.streaks.count) days")
                            .font(.title2)

                        Text("Curriculum").font(.headline)
                        ForEach(dash.curriculum.keys.sorted(), id: \.self) { key in
                            HStack {
                                Text(key)
                                Spacer()
                                Text("\(dash.curriculum[key] ?? 0)")
                            }
                        }
                    } else {
                        ProgressView("Loading…")
                    }
                }
                .padding()
            }
            .navigationTitle("Progress")
            .refreshable { await app.refreshPlan() }
        }
    }

    private func color(for state: String?) -> Color {
        switch state {
        case "GREEN": return .green
        case "AMBER": return .orange
        case "RED", "DELOAD": return .red
        default: return .gray
        }
    }
}
