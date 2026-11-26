import SwiftUI

@main
struct TrainerApp: App {
    @StateObject private var appModel = AppModel()

    var body: some Scene {
        WindowGroup {
            RootTabView()
                .environmentObject(appModel)
                .task {
                    await appModel.bootstrap()
                }
        }
    }
}
