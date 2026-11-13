import QtQuick
import "protondb.js" as ProtonDB
import QtQuick.Layouts

// A game's own page in TV mode (A on a cover): its art, what it is, how long you played,
// achievements, time to beat, your screenshots and the store's, and Play / Install, Options and
// Favourite, all with the controller. A again plays: from the shelf, A A starts a game.
// Up and down move between the buttons and the screenshots; A on a screenshot shows it full
// size (left and right browse); B goes back.
Rectangle {
    id: page
    objectName: "tvPage"
    required property var theme
    required property var tint
    property var game: ({})
    property var info: ({})
    property var ach: ({})
    property var shots: []          // yours (screenshots.py), then the store's
    property int row: 0             // 0: buttons, 1: screenshots
    property int button: 0
    property int shot: 0
    property bool viewing: false
    signal options()
    signal closed()
    color: theme.background
    visible: false

    readonly property var allShots: shots.concat((info.screenshots || []))
    readonly property var buttons: [
        { id: "main", label: game.installed ? qsTr("Play") : qsTr("Install"), icon: game.installed ? "play" : "download", primary: true },
        { id: "options", label: qsTr("Options"), icon: "ellipsis" },
        { id: "fav", label: game.favourite ? qsTr("Favourite") : qsTr("Add to favourites"), icon: game.favourite ? "star-filled" : "star" }
    ]

    function show(g, details, achievements) {
        game = g; info = details || {}; ach = achievements || {}
        shots = []; row = 0; button = 0; shot = 0; viewing = false
        app.loadScreenshots(g.key)
        visible = true
        forceActiveFocus()
    }
    function close() { app.uiSound("back"); visible = false; viewing = false; closed() }
    function press() {
        const b = buttons[button]
        app.uiSound("select")
        if (b.id === "main") {
            const target = app.launchTarget(game.key)
            if (target) app.play(target)
            else if (!game.installed && (game.copies || []).length <= 1) app.install(game.key)
            else options()   // several copies: choose which to play or install
        } else if (b.id === "options") options()
        else if (b.id === "fav") { app.toggleFavourite(game.key); game = app.game(game.key) }
    }
    Connections {
        target: app
        function onScreenshotsReady(key, rows) { if (key === page.game.key) page.shots = rows }
        function onGameChanged(key) { if (page.visible && (key === "" || key === page.game.key)) page.game = app.game(page.game.key) }
        function onDetailsReady(key, d) { if (key === page.game.key) page.info = d }
    }
    Keys.onPressed: event => {
        event.accepted = true
        const k = event.key
        if (viewing) {
            if (k === Qt.Key_Left) shot = (shot + allShots.length - 1) % allShots.length
            else if (k === Qt.Key_Right) shot = (shot + 1) % allShots.length
            else if (k === Qt.Key_Escape || k === Qt.Key_Backspace || k === Qt.Key_Return) { viewing = false; app.uiSound("back") }
            return
        }
        if (k === Qt.Key_Escape || k === Qt.Key_Backspace) close()
        else if (k === Qt.Key_F2) options()
        else if (k === Qt.Key_Up && row === 1) { row = 0; app.uiSound("move") }
        else if (k === Qt.Key_Down && row === 0 && allShots.length) { row = 1; app.uiSound("move") }
        else if (k === Qt.Key_Left) {
            if (row === 0 && button > 0) { button--; app.uiSound("move") }
            else if (row === 1 && shot > 0) { shot--; app.uiSound("move") }
        } else if (k === Qt.Key_Right) {
            if (row === 0 && button < buttons.length - 1) { button++; app.uiSound("move") }
            else if (row === 1 && shot < allShots.length - 1) { shot++; app.uiSound("move") }
        } else if (k === Qt.Key_Return || k === Qt.Key_Enter) {
            if (row === 0) press()
            else { viewing = true; app.uiSound("select") }
        }
    }

    // The game's wide art, faded into the page.
    Image {
        anchors.fill: parent
        source: (page.game.heroes || [])[0] || page.game.cover || ""
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
        opacity: 0.55
    }
    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0.0; color: Qt.alpha(page.theme.background, 0.97) }
            GradientStop { position: 0.55; color: Qt.alpha(page.theme.background, 0.75) }
            GradientStop { position: 1.0; color: Qt.alpha(page.theme.background, 0.2) }
        }
    }

    ColumnLayout {
        anchors { left: parent.left; right: parent.right; top: parent.top; margins: page.height * 0.07 }
        spacing: page.height * 0.022
        // Logo, or the title when there is none.
        Item {
            Layout.preferredHeight: page.height * 0.16
            Layout.preferredWidth: page.width * 0.42
            Image {
                id: logo
                anchors.fill: parent
                source: (page.game.logos || [])[0] || ""
                fillMode: Image.PreserveAspectFit
                horizontalAlignment: Image.AlignLeft
                asynchronous: true
            }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width
                visible: logo.status !== Image.Ready
                text: page.game.title || ""
                color: page.theme.onSurface
                wrapMode: Text.WordWrap; maximumLineCount: 2; elide: Text.ElideRight
                font.pixelSize: Math.round(page.height * 0.06); font.weight: Font.Bold; font.family: app.titleFamily
            }
        }
        Text {
            text: {
                const parts = [page.game.storeName || ""]
                const h = (page.game.playtime || 0) / 3600
                if (h > 0) parts.push((h >= 10 || h === Math.round(h) ? Math.round(h) : h.toFixed(1)) + qsTr(" h played"))
                else parts.push(qsTr("Not played yet"))
                if (page.ach.total) parts.push("🏆 " + page.ach.done + " / " + page.ach.total)
                if (page.info.ttbLabel) parts.push(page.info.ttbLabel)
                if (page.game.protondb) parts.push("ProtonDB " + ProtonDB.label(page.game.protondb))
                return parts.filter(p => p).join("   ·   ")
            }
            color: page.theme.onSurfaceVariant
            font.pixelSize: Math.round(page.height * 0.024)
        }
        // Play / Install, Options, Favourite
        Row {
            spacing: 14
            Repeater {
                model: page.buttons
                Rectangle {
                    required property var modelData
                    required property int index
                    readonly property bool focused: page.row === 0 && page.button === index
                    height: page.height * 0.075
                    width: bRow.implicitWidth + page.height * 0.06
                    radius: height / 2
                    color: modelData.primary ? page.tint.primary : Qt.alpha(page.theme.surfaceContainerHigh, 0.9)
                    border.width: focused ? 4 : 0
                    border.color: page.theme.onSurface
                    scale: focused ? 1.06 : 1
                    Behavior on scale { enabled: !app.light; NumberAnimation { duration: 120 } }
                    Row {
                        id: bRow
                        anchors.centerIn: parent
                        spacing: 10
                        Icon { anchors.verticalCenter: parent.verticalCenter; name: modelData.icon; size: page.height * 0.03
                               color: modelData.primary ? page.tint.onPrimary : page.theme.onSurface }
                        Text { anchors.verticalCenter: parent.verticalCenter; text: modelData.label
                               color: modelData.primary ? page.tint.onPrimary : page.theme.onSurface
                               font.pixelSize: Math.round(page.height * 0.027); font.weight: Font.DemiBold }
                    }
                    TapHandler { onTapped: { page.row = 0; page.button = index; page.press() } }
                }
            }
        }
        Text {
            Layout.preferredWidth: page.width * 0.55
            visible: !!page.info.description
            text: page.info.description || ""
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap; maximumLineCount: 4; elide: Text.ElideRight
            color: page.theme.onSurface; opacity: 0.9
            font.pixelSize: Math.round(page.height * 0.023)
            lineHeight: 1.15
        }
        Text {
            visible: (page.info.genres || []).length > 0 || !!page.info.developer
            text: [(page.info.genres || []).slice(0, 4).join(", "), page.info.developer || "", page.info.year || ""].filter(x => x).join("   ·   ")
            color: page.theme.onSurfaceVariant
            font.pixelSize: Math.round(page.height * 0.02)
        }
    }

    // Screenshots: yours first, then the store's.
    Column {
        anchors { left: parent.left; right: parent.right; bottom: hints.top; leftMargin: page.height * 0.07; bottomMargin: page.height * 0.03 }
        spacing: 10
        visible: page.allShots.length > 0
        Text {
            text: page.shots.length ? qsTr("Your screenshots and the store's") : qsTr("Screenshots")
            color: page.theme.onSurfaceVariant
            font.pixelSize: Math.round(page.height * 0.022); font.weight: Font.DemiBold
        }
        ListView {
            id: strip
            width: parent.width
            height: page.height * 0.17
            orientation: ListView.Horizontal
            spacing: 14
            clip: false
            interactive: false
            model: page.allShots
            currentIndex: page.shot
            highlightMoveDuration: 200
            preferredHighlightBegin: 0; preferredHighlightEnd: width * 0.6
            highlightRangeMode: ListView.ApplyRange
            delegate: Item {
                required property var modelData
                required property int index
                readonly property bool focused: page.row === 1 && page.shot === index
                width: strip.height * 16 / 9; height: strip.height
                scale: focused ? 1.08 : 1
                z: focused ? 1 : 0
                Behavior on scale { enabled: !app.light; NumberAnimation { duration: 120 } }
                RoundedArt {
                    anchors.fill: parent
                    radius: 12
                    Rectangle { anchors.fill: parent; color: page.theme.surfaceContainerHigh }
                    Image { anchors.fill: parent; source: modelData.thumb; fillMode: Image.PreserveAspectCrop; asynchronous: true
                            sourceSize.width: 480 }
                }
                Rectangle { anchors.fill: parent; radius: 12; color: "transparent"; border.width: focused ? 4 : 0; border.color: page.theme.onSurface }
                Rectangle {  // yours, marked
                    visible: !!modelData.path
                    anchors { left: parent.left; top: parent.top; margins: 8 }
                    width: mine.implicitWidth + 14; height: 24; radius: 12
                    color: Qt.alpha("black", 0.6)
                    Text { id: mine; anchors.centerIn: parent; text: qsTr("Yours"); color: "white"; font.pixelSize: 12 }
                }
                TapHandler { onTapped: { page.row = 1; page.shot = index; page.viewing = true } }
            }
        }
    }

    TvHints {
        id: hints
        anchors { left: parent.left; bottom: parent.bottom; margins: page.height * 0.05 }
        theme: page.theme
        hints: [{ b: "a", k: "Enter", t: page.viewing ? qsTr("Close") : page.row === 0 ? qsTr("Choose") : qsTr("Full size") },
                { b: "x", k: "F2", t: qsTr("Options") }, { b: "b", k: "Esc", t: qsTr("Back") }]
    }

    // A screenshot, full size.
    Rectangle {
        anchors.fill: parent
        visible: page.viewing
        color: "black"
        readonly property var cur: page.allShots[page.shot] || ({})
        Image { anchors.fill: parent; anchors.margins: page.height * 0.04; source: parent.cur.full || parent.cur.thumb || ""
                fillMode: Image.PreserveAspectFit; asynchronous: true }
        Text {
            anchors { horizontalCenter: parent.horizontalCenter; bottom: parent.bottom; bottomMargin: 18 }
            text: (page.shot + 1) + " / " + page.allShots.length
            color: Qt.alpha("white", 0.8); font.pixelSize: Math.round(page.height * 0.022)
        }
        TapHandler { onTapped: page.viewing = false }
    }
}
