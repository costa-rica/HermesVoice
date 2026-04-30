import SwiftUI

struct VerifyView: View {
    let challengeID: String
    let email: String

    @EnvironmentObject private var sessionStore: SessionStore
    @State private var code = ""
    @State private var errorMessage: String?

    var body: some View {
        Form {
            Section {
                Text("Enter the verification code sent to \(email).")
                    .font(.footnote)
                    .foregroundStyle(.secondary)

                TextField("Code", text: $code)
                    .keyboardType(.numberPad)
                    .textContentType(.oneTimeCode)
            }

            if let errorMessage {
                Section {
                    Text(errorMessage)
                        .font(.footnote)
                        .foregroundStyle(.red)
                }
            }

            Section {
                Button(action: submit) {
                    if sessionStore.isLoading {
                        ProgressView()
                            .frame(maxWidth: .infinity)
                    } else {
                        Text("Verify")
                            .frame(maxWidth: .infinity)
                    }
                }
                .disabled(sessionStore.isLoading || code.isEmpty)
            }
        }
        .navigationTitle("Verify")
    }

    private func submit() {
        errorMessage = nil
        Task {
            do {
                try await sessionStore.verify(challengeID: challengeID, code: code)
            } catch {
                errorMessage = error.localizedDescription
            }
        }
    }
}
