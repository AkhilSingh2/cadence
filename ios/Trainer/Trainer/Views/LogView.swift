import SwiftUI

struct LogView: View {
    @EnvironmentObject var app: AppModel
    @State private var valence = 3
    @State private var energy = 3
    @State private var stress = 3
    @State private var trigger = ""
    @State private var weightText = "70"
    @State private var preference = ""
    @State private var apiURL: String = ""

    var body: some View {
        NavigationStack {
            Form {
                Section("Mood") {
                    Stepper("Valence \(valence)", value: $valence, in: 1...5)
                    Stepper("Energy \(energy)", value: $energy, in: 1...5)
                    Stepper("Stress \(stress)", value: $stress, in: 1...5)
                    TextField("Trigger (optional)", text: $trigger)
                    Button("Save mood") {
                        Task {
                            await app.logMood(
                                valence: valence,
                                energy: energy,
                                stress: stress,
                                trigger: trigger.isEmpty ? nil : trigger
                            )
                        }
                    }
                }
                Section("Weight") {
                    TextField("kg", text: $weightText)
                        .keyboardType(.decimalPad)
                    Button("Save weight") {
                        if let kg = Double(weightText) {
                            Task { await app.logWeight(kg) }
                        }
                    }
                }
                Section("Preference memory") {
                    TextField("e.g. Dislikes mass-gainer shakes", text: $preference)
                    Button("Save preference") {
                        Task {
                            try? await app.api.addPreference(preference)
                            preference = ""
                        }
                    }
                }
                Section("API") {
                    TextField("Base URL", text: $apiURL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    Button("Save URL") {
                        app.updateAPIBase(apiURL)
                    }
                    Text("Simulator default is http://127.0.0.1:8000/v1. On a phone, use your Mac's LAN IP.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Log")
            .onAppear { apiURL = app.apiBaseURL }
        }
    }
}
