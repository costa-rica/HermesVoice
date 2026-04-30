import SwiftUI

struct ConnectionStatusView: View {
    var body: some View {
        HStack(spacing: 12) {
            Circle()
                .fill(Color.orange)
                .frame(width: 10, height: 10)
            VStack(alignment: .leading, spacing: 4) {
                Text("Authenticated — voice not yet connected")
                Text("Push-to-talk wiring lands in Phase M3–M4.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 4)
    }
}
