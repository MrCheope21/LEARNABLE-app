import XCTest

/// The MVP vertical slice, end to end on a simulator against a real backend (AI_PROVIDER=mock,
/// seeded by backend/scripts/seed_demo.py). Run by .github/workflows/ios.yml (input `e2e`); locally, see
/// docs/DEVELOPMENT.md "End-to-end acceptance run".
///
/// One long test on purpose: each step depends on the state the previous one created, exactly
/// as for a real user.
final class VerticalSliceAcceptanceTests: XCTestCase {
    private let email = "demo@example.com"
    private let password = "learnable-demo-2026"
    private let course = "Diritto bancario (demo)"
    /// Close to the seeded material, so the mock evaluator (keyword overlap) grades it correct.
    private let answer = "Il deposito bancario e il contratto con cui la banca acquista la proprieta "
        + "del denaro depositato. Il depositante ha diritto alla restituzione."

    private var app: XCUIApplication!

    override func setUp() {
        continueAfterFailure = false
        app = XCUIApplication()
        app.launchArguments += ["-AppleLanguages", "(en)", "-AppleLocale", "en_US"]
        app.launch()
    }

    func testLearnReviewAndProgressLoop() {
        step(1, "sign in with the seeded account")
        signInIfNeeded()

        step(2, "open the Courses tab")
        tap(app.tabBars.buttons["Courses"], "the Courses tab")

        step(3, "open the seeded course")
        let courseRow = app.buttons.matching(identifier: "course.row")
            .matching(NSPredicate(format: "label CONTAINS %@", course)).firstMatch
        tap(courseRow, "the seeded course row")
        waitFor(element(containing: "Today"), "the course dashboard")

        step(4, "open a chapter")
        tap(app.buttons.matching(identifier: "chapter.row").firstMatch, "a chapter row")

        step(5, "open a topic")
        tap(app.buttons.matching(identifier: "topic.row").firstMatch, "a topic row")

        step(6, "open a concept")
        tap(app.buttons.matching(identifier: "concept.row").firstMatch, "a concept row")

        step(7, "activate the concept")
        // Activate, or Learn Now when a previous run already activated it.
        let next = waitFor(
            app.buttons.matching(
                NSPredicate(
                    format: "identifier IN %@", ["concept.activate", "concept.learnNow"] as NSArray
                )
            ).firstMatch,
            "Activate or Learn Now on the concept"
        )
        if next.identifier == "concept.activate" {
            tap(next, "Activate")
        }

        step(8, "wait for learning items")
        let learnNow = waitFor(app.buttons["concept.learnNow"], "learning items", timeout: 60)

        step(9, "start LEARN")
        tap(learnNow, "Learn Now")

        step(10, "see the introduction")
        let ready = waitFor(app.buttons["study.ready"], "the LEARN introduction")

        step(11, "open the source passage")
        tap(app.buttons.matching(identifier: "source.row").firstMatch, "a source row")
        tap(waitFor(app.buttons["source.done"], "the source passage"), "Done on the source")

        step(12, "begin recall")
        tap(ready, "I'm ready")

        step(13, "type an answer")
        let editor = waitFor(app.textViews["study.answer"], "the answer editor")
        enter(answer, into: editor, "the answer editor")

        step(14, "submit")
        submitAnswer()

        step(15, "see the backend's evaluation")
        // Any element type: SwiftUI exposes the combined outcome header as static text.
        let outcome = waitFor(
            app.descendants(matching: .any).matching(identifier: "study.outcome").firstMatch,
            "the evaluation", timeout: 30
        )
        waitFor(app.buttons["study.continue"], "Continue after a graded answer")

        step(16, "disagree with the grade: Hard")
        tap(app.buttons["study.disagree"], "Disagree with the grade?")
        let hard = app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Hard'")).firstMatch
        tap(waitFor(hard, "the override menu"), "Hard")
        waitFor(element(containing: "Graded by you"), "the overridden grade")
        XCTAssertTrue(outcome.label.contains("Hard"), "Outcome shows \(outcome.label)")

        step(17, "finish the session")
        finishSession()

        step(18, "Home shows the course")
        tap(app.tabBars.buttons["Home"], "the Home tab")
        waitFor(element(containing: course), "the course on Home")

        step(19, "Progress shows curriculum and memory separately")
        tap(app.tabBars.buttons["Progress"], "the Progress tab")
        waitFor(element(containing: "Curriculum Progress"), "curriculum progress")
        waitFor(element(containing: "Memory Progress"), "memory progress")
        waitFor(element(containing: "Upcoming Reviews"), "the review load")

        step(20, "Review tab lists the course")
        tap(app.tabBars.buttons["Review"], "the Review tab")
        waitFor(element(containing: course), "the course on the Review tab")

        step(21, "relaunch: still signed in, data reloads")
        app.terminate()
        app.launch()
        waitFor(app.tabBars.buttons["Home"], "the signed-in app after relaunch")
        waitFor(element(containing: course), "the course after relaunch")
        print("ACCEPTANCE COMPLETE 21/21")
    }

    // MARK: - Steps

    private func step(_ number: Int, _ name: String) {
        // Greppable in the xcodebuild log, so a failure reports how far the run got (X/21).
        print("ACCEPTANCE STEP \(number)/21: \(name)")
    }

    private func signInIfNeeded() {
        let emailField = app.textFields["Email"]
        guard emailField.waitForExistence(timeout: 10) else { return }
        enter(email, into: emailField, "Email")
        let passwordField = app.secureTextFields["Password"]
        enter(password, into: passwordField, "Password")
        tap(
            app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Sign In'")).firstMatch,
            "Sign In"
        )
        waitFor(app.tabBars.buttons["Courses"], "the signed-in app", timeout: 20)
        dismissSavePasswordPrompt()
    }

    /// iOS offers to save the credentials to the keychain after a sign-in with password fields
    /// (AutoFill). The sheet is modal and covers the app, so nothing underneath is hittable;
    /// a real user answers it before going on, and so does the test.
    private func dismissSavePasswordPrompt() {
        let prompt = app.sheets["Save Password?"]
        guard prompt.waitForExistence(timeout: 8) else { return }
        tap(prompt.buttons["Not Now"], "Not Now on the Save Password prompt")
        let gone = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "exists == false"), object: prompt
        )
        XCTAssertEqual(
            XCTWaiter().wait(for: [gone], timeout: 10), .completed,
            "the Save Password prompt didn't close"
        )
    }

    private func answerCurrentQuestion() {
        let editor = waitFor(app.textViews["study.answer"], "the answer editor")
        enter(answer, into: editor, "the answer editor")
        submitAnswer()
    }

    private func submitAnswer() {
        let submit = app.buttons["study.submit"]
        if submit.exists && !submit.isHittable {
            // The keyboard can cover the button; the editor dismisses it on a downward swipe,
            // as a user would.
            app.swipeDown()
        }
        tap(submit, "Submit")
    }

    private func finishSession() {
        for _ in 0..<6 {
            if app.buttons["study.done"].exists {
                break
            }
            if app.buttons["study.continue"].exists {
                tap(app.buttons["study.continue"], "Continue")
            } else if app.buttons["study.ready"].exists {
                tap(app.buttons["study.ready"], "I'm ready")
            } else if app.textViews["study.answer"].exists {
                answerCurrentQuestion()
                _ = app.descendants(matching: .any).matching(identifier: "study.outcome")
                    .firstMatch.waitForExistence(timeout: 30)
            } else if app.buttons["Skip for now"].exists {
                tap(app.buttons["Skip for now"], "Skip for now")
            }
            _ = app.buttons["study.done"].waitForExistence(timeout: 5)
        }
        tap(waitFor(app.buttons["study.done"], "the session summary"), "Done")
    }

    /// Taps only once the element can really receive a touch. If it exists but never becomes
    /// hittable, fails with the element and the whole accessibility tree, so the log shows what
    /// covers or disables it instead of a bare "not hittable".
    private func tap(
        _ element: XCUIElement, _ what: String, timeout: TimeInterval = 15,
        file: StaticString = #filePath, line: UInt = #line
    ) {
        waitFor(element, what, timeout: timeout, file: file, line: line)
        // Present but under the tab bar or the fold: scroll it into reach, as a user would.
        for _ in 0..<3 where !element.isHittable {
            app.swipeUp()
        }
        let hittable = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "isHittable == true"), object: element
        )
        if XCTWaiter().wait(for: [hittable], timeout: 10) != .completed {
            XCTFail(
                "\(what) exists but is not hittable.\nElement: \(element.debugDescription)"
                    + "\nApp:\n\(app.debugDescription)",
                file: file, line: line
            )
            return
        }
        element.tap()
    }

    /// Types only once the field really has keyboard focus. Right after launch a tap can land
    /// before the field accepts focus; a user would tap again, and so does the test (once).
    private func enter(
        _ text: String, into field: XCUIElement, _ what: String,
        file: StaticString = #filePath, line: UInt = #line
    ) {
        let focused = NSPredicate(format: "hasKeyboardFocus == true")
        for _ in 0..<2 {
            tap(field, what, file: file, line: line)
            let expectation = XCTNSPredicateExpectation(predicate: focused, object: field)
            if XCTWaiter().wait(for: [expectation], timeout: 5) == .completed {
                field.typeText(text)
                return
            }
        }
        XCTFail("\(what) never received keyboard focus\n\(app.debugDescription)", file: file, line: line)
    }

    /// Any element whose label contains `text` (rows combine their texts into one label).
    private func element(containing text: String) -> XCUIElement {
        app.descendants(matching: .any)
            .matching(NSPredicate(format: "label CONTAINS[c] %@", text)).firstMatch
    }

    /// Waits for the element, scrolling down as a user would: SwiftUI lists create only the
    /// rows on screen, so a row below the fold doesn't exist until it's scrolled to.
    @discardableResult
    private func waitFor(
        _ element: XCUIElement, _ what: String, timeout: TimeInterval = 15,
        file: StaticString = #filePath, line: UInt = #line
    ) -> XCUIElement {
        let deadline = Date().addingTimeInterval(timeout)
        var swipes = 0
        while !element.waitForExistence(timeout: min(2, max(0.1, deadline.timeIntervalSinceNow))) {
            if Date() >= deadline {
                XCTFail(
                    "Timed out waiting for \(what)\n\(app.debugDescription)", file: file, line: line
                )
                return element
            }
            if swipes < 5 {
                app.swipeUp()
                swipes += 1
            }
        }
        return element
    }
}
