import QtQuick
import QtWebEngine

// Reads the games a Blizzard account owns from account.battle.net, as the account site's own
// pages do (Blizzard has no public library API). The sign-in lives in its own browser profile,
// kept on disk, so this can run on every Refresh without asking again. Nothing here is shown.
Item {
    id: sync
    width: 1; height: 1
    opacity: 0
    property alias profile: kept
    property bool busy: false
    property int step: -1
    property var found: ({})
    readonly property var steps: [
        "https://account.battle.net/oauth2/authorization/account-settings", // renews the session
        "https://account.battle.net/api/",                                  // { authenticated: … }
        "https://account.battle.net/api/games-and-subs",
        "https://account.battle.net/api/classic-games"
    ]

    function start() {
        if (busy) return
        busy = true; found = ({}); step = 0
        guard.restart()
        view.url = steps[0]
    }
    function stop() { busy = false; step = -1; guard.stop(); settle.stop(); view.url = "about:blank" }
    function fail(message) { stop(); app.blizzardFailed(message) }
    function next() {
        step += 1
        if (step < steps.length) { view.url = steps[step]; return }
        const result = JSON.stringify({ games: found.games || [], classic: found.classic || [] })
        stop()
        app.blizzardOwned(result)
    }

    // What a JSON page says, as an object (null when it is not JSON).
    function read(then) {
        view.runJavaScript("document.body ? document.body.innerText : ''", text => {
            try { then(JSON.parse(text)) } catch (e) { then(null) }
        })
    }

    function loaded() {
        if (!busy) return
        if (step === 0) {
            if (view.url.toString().indexOf("/login") !== -1)  // sent to Blizzard's sign-in page
                return fail("the Blizzard sign-in has expired; link the account again in Accounts")
            settle.restart()  // let the sign-in redirects finish
            return
        }
        read(data => {
            if (!busy) return
            if (step === 1) {
                if (!data || data.authenticated !== true)
                    return fail("the Blizzard sign-in has expired; link the account again in Accounts")
            } else if (step === 2) {
                if (!data || !Array.isArray(data.gameAccounts))
                    return fail("could not read the games on your Blizzard account")
                found.games = data.gameAccounts
            } else if (step === 3) {
                found.classic = data && Array.isArray(data.classicGames) ? data.classicGames : []
            }
            next()
        })
    }

    Timer { id: settle; interval: 1500; onTriggered: sync.next() }
    Timer { id: guard; interval: 60000; onTriggered: if (sync.busy) sync.fail("Blizzard's account site did not answer") }

    WebEngineProfile {
        id: kept
        storageName: "blizzard"
        offTheRecord: false
        // The account site's session cookie has no expiry date; keep it across restarts anyway.
        persistentCookiesPolicy: WebEngineProfile.ForcePersistentCookies
        Component.onCompleted: httpUserAgent = httpUserAgent.replace(/\s*QtWebEngine\/\S+/, "")
    }

    WebEngineView {
        id: view
        anchors.fill: parent
        profile: kept
        onLoadingChanged: info => {
            if (info.status === WebEngineView.LoadSucceededStatus) sync.loaded()
            else if (info.status !== WebEngineView.LoadFailedStatus || !sync.busy) return
            // An HTTP error status (401 when signed out) still carries a JSON body worth reading.
            else if (sync.step === 0 || (info.errorCode >= 100 && info.errorCode < 600)) sync.loaded()
            else if (info.url.toString() === sync.steps[sync.step])  // not an earlier page cut short
                sync.fail("could not reach Blizzard's account site")
        }
    }
}
