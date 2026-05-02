import XCTest

final class HermesVoiceUITests: XCTestCase {
    func testLaunches() {
        let app = XCUIApplication()
        app.launch()
        XCTAssertTrue(app.staticTexts["SILENT"].waitForExistence(timeout: 5))
    }
}
