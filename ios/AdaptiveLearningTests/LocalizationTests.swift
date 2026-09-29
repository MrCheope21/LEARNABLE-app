import XCTest

/// Checks the compiled app bundle, not the catalog source: proves Localizable.xcstrings is built
/// into the app and Italian (docs/PROJECT_SPEC.md §69) is actually shipped.
final class LocalizationTests: XCTestCase {
    private func italian(_ key: String) throws -> String {
        let path = try XCTUnwrap(
            Bundle.main.path(forResource: "it", ofType: "lproj"),
            "Italian localization is missing from the app bundle"
        )
        let bundle = try XCTUnwrap(Bundle(path: path))
        return bundle.localizedString(forKey: key, value: "<missing>", table: nil)
    }

    func testNavigationIsTranslated() throws {
        XCTAssertEqual(try italian("Courses"), "Corsi")
        XCTAssertEqual(try italian("Settings"), "Impostazioni")
        XCTAssertEqual(try italian("Sign Out"), "Esci")
        XCTAssertEqual(try italian("Study Material"), "Materiale di studio")
        XCTAssertEqual(try italian("Start Review"), "Inizia il ripasso")
        XCTAssertEqual(try italian("Disagree with the grade?"), "Non sei d'accordo con la valutazione?")
    }

    func testFormattedStringsKeepTheirPlaceholders() throws {
        XCTAssertEqual(try italian("Page %lld"), "Pagina %lld")
        XCTAssertEqual(try italian("%lld of %lld concepts active"), "%lld concetti attivi su %lld")
        XCTAssertEqual(try italian("Next review: %@"), "Prossimo ripasso: %@")
    }

    func testErrorMessagesAreTranslated() throws {
        XCTAssertEqual(
            try italian("Can't reach the server. Check your connection and try again."),
            "Impossibile raggiungere il server. Controlla la connessione e riprova."
        )
    }

    func testAppDeclaresBothLanguages() {
        let declared = Bundle.main.object(forInfoDictionaryKey: "CFBundleLocalizations") as? [String]
        XCTAssertEqual(Set(declared ?? []), ["en", "it"])
    }
}
