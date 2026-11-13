import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtWebEngine

// Sign-in inside the app: shows the store's own login page and picks up the
// code it hands back, so there is nothing to copy or paste.
Window {
    id: w
    property var theme: app.theme
    property string store: ""
    property string storeName: ""
    property string startUrl: ""
    property bool done: false
    // The page a sign-in just failed on: not taken again on its own. Some stores send a signed-in
    // visitor straight back there, and finishing again each time made the window reload in a loop.
    property string failedUrl: ""
    // A profile that outlives the window (Blizzard: kept so Refresh can read the games later).
    property var keptProfile: null
    signal fallback()

    width: 520
    height: 760
    minimumWidth: 420
    minimumHeight: 560
    title: qsTr("Sign in to ") + storeName
    color: theme.background
    modality: Qt.ApplicationModal

    function begin(storeId, name, url) {
        store = storeId; storeName = name; startUrl = url; done = false; failedUrl = ""
        status.text = ""
        if (store === "humble") app.humbleWebStart(view.profile)  // collects the cookies as they are set
        view.url = url
        show(); raise(); requestActivate()
    }

    function finish(payload) {
        if (done) return
        done = true
        status.text = qsTr("Signing in…")
        if (store === "blizzard") app.blizzardSync()  // reads the games; app.blizzardOwned closes this
        else if (store === "humble") app.humbleWebDone(view.profile)  // reads the session cookie
        else app.loginFinish(store, payload)
    }

    // Each store ends its login on a recognisable page; that page carries the code.
    function inspect(url) {
        const u = url.toString()
        if (done || (failedUrl && u === failedUrl)) return
        if (store === "blizzard") {
            // Signed in once the account site itself (not its login or OAuth pages) has loaded.
            if (u.indexOf("https://account.battle.net/") === 0 && u.indexOf("oauth2") === -1
                    && u.indexOf("login") === -1 && !view.loading)
                finish(u)
        }
        else if (store === "humble" && u.indexOf("https://www.humblebundle.com/home/library") === 0 && !view.loading)
            finish(u)
        else if (store === "gog" && u.indexOf("on_login_success") !== -1 && u.indexOf("code=") !== -1)
            finish(u)
        else if (store === "amazon" && u.indexOf("openid.oa2.authorization_code=") !== -1)
            finish(u)
        else if (store === "epic" && u.indexOf("epicgames.com/id/api/redirect") !== -1)
            view.runJavaScript("document.body ? document.body.innerText : ''", text => {
                try {
                    const data = JSON.parse(text)
                    if (data.authorizationCode) finish(data.authorizationCode)
                    else if (data.redirectUrl === undefined) view.url = w.startUrl
                } catch (e) { /* not the JSON page yet */ }
            })
    }

    Connections {
        target: app
        function onLoginDone(storeId, ok, message) {
            if (storeId !== w.store) return
            if (ok) w.close()
            else {
                w.done = false; status.text = message
                w.failedUrl = view.url.toString()
                view.url = w.startUrl
            }
        }
    }

    WebEngineProfile {
        id: privateProfile
        // In-memory only: nothing from these logins is kept on disk.
        offTheRecord: true
        // Some stores refuse unknown browsers; present as the Chromium this engine is.
        Component.onCompleted: httpUserAgent = httpUserAgent.replace(/\s*QtWebEngine\/\S+/, "")
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            Layout.fillWidth: true
            implicitHeight: bar.implicitHeight + 20
            color: w.theme.surfaceContainer
            RowLayout {
                id: bar
                anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; margins: 12 }
                spacing: 10
                Text {
                    Layout.fillWidth: true
                    text: qsTr("Log in below. The window closes by itself when you're signed in.")
                    color: w.theme.onSurfaceVariant
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                }
                Button {
                    id: altButton
                    text: qsTr("Use my browser instead")
                    font.pixelSize: 12
                    onClicked: { w.close(); w.fallback() }
                    contentItem: Text { text: altButton.text; font: altButton.font; color: w.theme.primary }
                    background: Item { }
                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                }
            }
        }
        Rectangle {
            Layout.fillWidth: true
            height: 3
            color: "transparent"
            Rectangle {
                height: parent.height
                color: w.theme.primary
                width: parent.width * view.loadProgress / 100
                visible: view.loading
            }
        }
        Text {
            id: status
            Layout.fillWidth: true
            Layout.margins: text ? 10 : 0
            visible: text !== ""
            wrapMode: Text.WordWrap
            color: w.theme.error
            font.pixelSize: 12
        }
        WebEngineView {
            id: view
            Layout.fillWidth: true
            Layout.fillHeight: true
            profile: w.keptProfile || privateProfile
            onUrlChanged: w.inspect(url)
            onLoadingChanged: info => { if (info.status === WebEngineView.LoadSucceededStatus) w.inspect(info.url) }
            // Links that try to open new windows (help pages, sign-up) go to the normal browser.
            onNewWindowRequested: request => app.openUrl(request.requestedUrl)
        }
    }
}
