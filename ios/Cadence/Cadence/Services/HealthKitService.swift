import Foundation
import HealthKit

final class HealthKitService {
    private let store = HKHealthStore()

    private var readTypes: Set<HKObjectType> {
        var set: Set<HKObjectType> = []
        if let sleep = HKObjectType.categoryType(forIdentifier: .sleepAnalysis) { set.insert(sleep) }
        if let rhr = HKObjectType.quantityType(forIdentifier: .restingHeartRate) { set.insert(rhr) }
        if let hrv = HKObjectType.quantityType(forIdentifier: .heartRateVariabilitySDNN) { set.insert(hrv) }
        if let energy = HKObjectType.quantityType(forIdentifier: .activeEnergyBurned) { set.insert(energy) }
        if let steps = HKObjectType.quantityType(forIdentifier: .stepCount) { set.insert(steps) }
        if let mass = HKObjectType.quantityType(forIdentifier: .bodyMass) { set.insert(mass) }
        return set
    }

    func requestAuthorization() async throws {
        guard HKHealthStore.isHealthDataAvailable() else { return }
        try await store.requestAuthorization(toShare: [], read: readTypes)
    }

    func fetchRecentDailySummaries(days: Int) async throws -> [HealthDayPayload] {
        guard HKHealthStore.isHealthDataAvailable() else { return [] }
        let cal = Calendar.current
        let today = cal.startOfDay(for: Date())
        var payloads: [HealthDayPayload] = []
        let df = DateFormatter()
        df.calendar = cal
        df.dateFormat = "yyyy-MM-dd"

        for offset in 0..<days {
            guard let dayStart = cal.date(byAdding: .day, value: -offset, to: today),
                  let dayEnd = cal.date(byAdding: .day, value: 1, to: dayStart) else { continue }

            let sleep = try await sleepHours(from: dayStart, to: dayEnd)
            let rhr = try await averageQuantity(.restingHeartRate, from: dayStart, to: dayEnd, unit: HKUnit.count().unitDivided(by: .minute()))
            let hrv = try await averageQuantity(.heartRateVariabilitySDNN, from: dayStart, to: dayEnd, unit: HKUnit.secondUnit(with: .milli))
            let energy = try await sumQuantity(.activeEnergyBurned, from: dayStart, to: dayEnd, unit: .kilocalorie())
            let steps = try await sumQuantity(.stepCount, from: dayStart, to: dayEnd, unit: .count())

            payloads.append(
                HealthDayPayload(
                    day: df.string(from: dayStart),
                    sleepHours: sleep.hours,
                    sleepEfficiency: sleep.efficiency,
                    hrvSdnnMs: hrv,
                    rhrBpm: rhr,
                    activeEnergyKcal: energy,
                    steps: steps.map { Int($0) },
                    wakeDetectedAt: sleep.wakeISO,
                    hrvBaseline14d: nil,
                    rhrBaseline14d: nil,
                    source: "healthkit"
                )
            )
        }
        return payloads
    }

    private struct SleepAgg {
        var hours: Double?
        var efficiency: Double?
        var wakeISO: String?
    }

    private func sleepHours(from start: Date, to end: Date) async throws -> SleepAgg {
        guard let sleepType = HKObjectType.categoryType(forIdentifier: .sleepAnalysis) else {
            return SleepAgg()
        }
        let pred = HKQuery.predicateForSamples(withStart: start.addingTimeInterval(-12 * 3600), end: end, options: .strictEndDate)
        let samples: [HKCategorySample] = try await withCheckedThrowingContinuation { cont in
            let q = HKSampleQuery(sampleType: sleepType, predicate: pred, limit: HKObjectQueryNoLimit, sortDescriptors: nil) { _, samples, error in
                if let error { cont.resume(throwing: error); return }
                cont.resume(returning: (samples as? [HKCategorySample]) ?? [])
            }
            store.execute(q)
        }
        // Asleep values: inBed=0, asleepUnspecified=1, awake=2, asleepCore=3, asleepDeep=4, asleepREM=5
        let asleepValues: Set<Int> = [1, 3, 4, 5]
        var asleep: TimeInterval = 0
        var inBed: TimeInterval = 0
        var lastEnd: Date?
        for s in samples {
            let dur = s.endDate.timeIntervalSince(s.startDate)
            if s.value == HKCategoryValueSleepAnalysis.inBed.rawValue {
                inBed += dur
            }
            if asleepValues.contains(s.value) {
                asleep += dur
                if lastEnd == nil || s.endDate > lastEnd! { lastEnd = s.endDate }
            }
        }
        guard asleep > 0 else { return SleepAgg() }
        let iso = ISO8601DateFormatter()
        let eff = inBed > 0 ? min(asleep / inBed, 1.0) : 0.85
        return SleepAgg(hours: asleep / 3600.0, efficiency: eff, wakeISO: lastEnd.map { iso.string(from: $0) })
    }

    private func averageQuantity(_ id: HKQuantityTypeIdentifier, from: Date, to: Date, unit: HKUnit) async throws -> Double? {
        guard let type = HKQuantityType.quantityType(forIdentifier: id) else { return nil }
        let pred = HKQuery.predicateForSamples(withStart: from, end: to, options: .strictStartDate)
        let samples: [HKQuantitySample] = try await withCheckedThrowingContinuation { cont in
            let q = HKSampleQuery(sampleType: type, predicate: pred, limit: HKObjectQueryNoLimit, sortDescriptors: nil) { _, samples, error in
                if let error { cont.resume(throwing: error); return }
                cont.resume(returning: (samples as? [HKQuantitySample]) ?? [])
            }
            store.execute(q)
        }
        guard !samples.isEmpty else { return nil }
        let sum = samples.reduce(0.0) { $0 + $1.quantity.doubleValue(for: unit) }
        return sum / Double(samples.count)
    }

    private func sumQuantity(_ id: HKQuantityTypeIdentifier, from: Date, to: Date, unit: HKUnit) async throws -> Double? {
        guard let type = HKQuantityType.quantityType(forIdentifier: id) else { return nil }
        let pred = HKQuery.predicateForSamples(withStart: from, end: to, options: .strictStartDate)
        let samples: [HKQuantitySample] = try await withCheckedThrowingContinuation { cont in
            let q = HKSampleQuery(sampleType: type, predicate: pred, limit: HKObjectQueryNoLimit, sortDescriptors: nil) { _, samples, error in
                if let error { cont.resume(throwing: error); return }
                cont.resume(returning: (samples as? [HKQuantitySample]) ?? [])
            }
            store.execute(q)
        }
        guard !samples.isEmpty else { return nil }
        return samples.reduce(0.0) { $0 + $1.quantity.doubleValue(for: unit) }
    }
}
