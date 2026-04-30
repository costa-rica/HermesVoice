import SwiftUI

struct ConnectionStatusView: View {
    var body: some View {
        HStack(spacing: 12) {
            Circle()
                .fill(Color.orange)
                .frame(width: 10, height: 10)
            VStack(alignment: .leading, spacing: 4) {
                Text("Setup in progress")
                Text("M1 project scaffold is ready; auth and socket wiring follow in later phases.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 4)
    }
}
