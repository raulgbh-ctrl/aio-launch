import QtQuick
import QtQuick.Effects

// The launch moment, like a console: when a game starts, its cover lifts into the middle of
// the window with a glow in its colour, "Getting ready…" and then "Starting…". It steps aside
// once the game's window takes over (Cornerplay loses focus), or after a moment.
Item {
    id: lc
    property var theme: app.theme
    property string key: ""
    property var game: ({})
    property string state_: ""   // "start", "ok", "fail"
    property color glow: theme.primary
    property Item blurSource: null   // what to frost behind the card (the library)
    property var prev: ({})          // "Previously in ...": a recap when the game was not played for a while
    readonly property bool recap: prev.days !== undefined
    anchors.fill: parent
    z: 200
    visible: opacity > 0.01
    opacity: key !== "" ? 1 : 0
    Behavior on opacity { NumberAnimation { duration: app.light ? 0 : 260; easing.type: Easing.OutCubic } }

    function show(k) {
        key = k; game = app.game(k); state_ = "start"; prev = ({})
        app.loadPreviously(k)
        const c = app.gameColour(k); glow = c || theme.primary
        lift.restart(); giveUp.restart()
    }
    function done() { key = ""; giveUp.stop(); fade.stop(); giveUp.interval = 20000 }

    Connections {
        target: app
        function onLaunching(k, st) {
            if (st === "start") lc.show(k)
            else if (k === lc.key) {
                if (st === "cancel") lc.done()
                else { lc.state_ = st; fade.interval = st === "ok" ? (lc.recap ? 10000 : 4000) : 3500; fade.restart() }
            }
        }
        function onGameColourReady(k, c) { if (k === lc.key && c) lc.glow = c }
        function onPreviouslyReady(k, info) {
            if (k !== lc.key) return
            lc.prev = info
            giveUp.interval = 40000          // time to read it while the game loads
            if (fade.running) fade.interval = 10000
        }
    }
    // The game is up: its window has the focus now.
    Connections {
        target: Qt.application
        function onStateChanged() { if (lc.key && lc.state_ === "ok" && Qt.application.state !== Qt.ApplicationActive) lc.done() }
    }
    Timer { id: fade; onTriggered: lc.done() }
    Timer { id: giveUp; interval: 20000; onTriggered: lc.done() }

    readonly property bool frost: !!blurSource && visible && !app.light && GraphicsInfo.api !== GraphicsInfo.Software
    ShaderEffectSource {  // a snapshot of the room, taken as the card appears (see show())
        id: snapRoom
        anchors.fill: parent
        visible: false
        sourceItem: lc.frost ? lc.blurSource : null
        live: false; hideSource: false
    }
    onFrostChanged: if (frost) snapRoom.scheduleUpdate()
    MultiEffect {  // the room goes soft...
        anchors.fill: parent
        visible: lc.frost
        source: snapRoom
        autoPaddingEnabled: false
        blurEnabled: true; blur: 1.0; blurMax: 56
    }
    Rectangle {  // ...and dims
        anchors.fill: parent
        color: Qt.alpha("black", 0.72)
        MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons; onClicked: lc.done(); onWheel: w => w.accepted = true }
    }
    Row {
    anchors.centerIn: parent
    spacing: 56
    Column {
        anchors.verticalCenter: parent.verticalCenter
        spacing: 26
        Item {
            id: coverBox
            anchors.horizontalCenter: parent.horizontalCenter
            width: Math.round(Math.min(lc.height * 0.36, 260)); height: Math.round(width * 1.46)
            // A glow in the game's own colour, breathing while it starts.
            RectangularShadow {
                anchors.fill: parent
                visible: !app.light && GraphicsInfo.api !== GraphicsInfo.Software
                radius: 18; blur: 70; spread: 6
                color: Qt.alpha(lc.glow, 0.55)
                SequentialAnimation on opacity {
                    running: lc.visible && lc.state_ === "start" && !app.light
                    loops: Animation.Infinite
                    NumberAnimation { from: 1; to: 0.45; duration: 900; easing.type: Easing.InOutSine }
                    NumberAnimation { from: 0.45; to: 1; duration: 900; easing.type: Easing.InOutSine }
                }
            }
            RoundedArt {
                anchors.fill: parent
                radius: 18
                Rectangle { anchors.fill: parent; color: lc.theme.surfaceContainerHigh }
                ArtImage { anchors.fill: parent; sources: lc.game.covers || []; sourceSize.width: 520 }
            }
            Rectangle { anchors.fill: parent; radius: 18; color: "transparent"; border.width: 1; border.color: Qt.alpha("white", 0.16) }
            ParallelAnimation {
                id: lift
                NumberAnimation { target: coverBox; property: "scale"; from: 0.82; to: 1; duration: 420; easing.type: Easing.OutBack; easing.overshoot: 1.3 }
                NumberAnimation { target: coverBox; property: "y"; from: 40; to: 0; duration: 420; easing.type: Easing.OutCubic }
            }
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: lc.game.title || ""
            color: "white"
            font.pixelSize: 26; font.weight: Font.Bold
        }
        Column {
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: 12
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: lc.state_ === "fail" ? qsTr("Could not start it (see the message below)")
                      : lc.state_ === "ok" ? qsTr("Starting… have fun!") : qsTr("Getting ready…")
                color: Qt.alpha("white", 0.8)
                font.pixelSize: 16
            }
            Rectangle {  // a short bar that glides back and forth while it starts
                anchors.horizontalCenter: parent.horizontalCenter
                width: 180; height: 4; radius: 2
                color: Qt.alpha("white", 0.15)
                visible: lc.state_ !== "fail"
                clip: true
                Rectangle {
                    width: lc.state_ === "ok" ? parent.width : 60; height: parent.height; radius: 2
                    color: lc.glow
                    Behavior on width { NumberAnimation { duration: 300 } }
                    SequentialAnimation on x {
                        running: lc.visible && lc.state_ === "start" && !app.light
                        loops: Animation.Infinite
                        NumberAnimation { from: 0; to: 120; duration: 800; easing.type: Easing.InOutQuad }
                        NumberAnimation { from: 120; to: 0; duration: 800; easing.type: Easing.InOutQuad }
                    }
                    onWidthChanged: if (lc.state_ === "ok") x = 0
                }
            }
        }
    }

    // Previously in ...: where you were, from your own notes and screenshots.
    Column {
        id: recapBox
        visible: lc.recap
        anchors.verticalCenter: parent.verticalCenter
        width: Math.min(460, lc.width - coverBox.width - 56 - 120)
        spacing: 16
        opacity: lc.recap ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: app.light ? 0 : 400 } }
        Text {
            text: qsTr("PREVIOUSLY")
            color: lc.glow; font.pixelSize: 13; font.weight: Font.Bold; font.letterSpacing: 2.5
        }
        Text {
            width: parent.width; wrapMode: Text.WordWrap
            color: "white"; font.pixelSize: 18; font.weight: Font.DemiBold
            text: (lc.prev.days >= 60 ? qsTr("You last played %1 months ago").arg(Math.round(lc.prev.days / 30))
                   : qsTr("You last played %1 days ago").arg(lc.prev.days || 0))
                  + (lc.prev.minutes > 0 ? qsTr(", for %1 min").arg(lc.prev.minutes) : "")
        }
        Rectangle {  // your note: where you got to, what was next
            visible: !!lc.prev.note
            width: parent.width
            height: noteText.implicitHeight + 28
            radius: 14
            color: Qt.alpha("white", 0.08)
            Rectangle { width: 3; radius: 2; height: parent.height - 24; x: 12; y: 12; color: lc.glow }
            Text {
                id: noteText
                x: 26; y: 14; width: parent.width - 40
                text: lc.prev.note || ""; textFormat: Text.PlainText
                wrapMode: Text.WordWrap; maximumLineCount: 6; elide: Text.ElideRight
                color: Qt.alpha("white", 0.92); font.pixelSize: 15; font.italic: true
            }
        }
        Row {  // the screenshots you took last time
            visible: (lc.prev.shots || []).length > 0
            spacing: 10
            Repeater {
                model: lc.prev.shots || []
                RoundedArt {
                    required property string modelData
                    width: Math.floor((recapBox.width - 20) / 3); height: Math.round(width * 9 / 16)
                    radius: 10
                    Rectangle { anchors.fill: parent; color: Qt.alpha("white", 0.06) }
                    Image { anchors.fill: parent; source: parent.modelData; fillMode: Image.PreserveAspectCrop; asynchronous: true; sourceSize.width: 320 }
                }
            }
        }
        Flow {
            width: parent.width
            spacing: 8
            Repeater {
                model: [lc.prev.hours > 0 ? qsTr("%1 h played").arg(lc.prev.hours) : "",
                        lc.prev.progress >= 0 ? qsTr("about %1% of the main story").arg(lc.prev.progress) : "",
                        lc.prev.achieved >= 0 ? qsTr("%1% of achievements").arg(Math.round(lc.prev.achieved * 100)) : ""].filter(t => t)
                Rectangle {
                    required property string modelData
                    height: 28; radius: 14; width: chip.implicitWidth + 24
                    color: Qt.alpha(lc.glow, 0.22)
                    Text { id: chip; anchors.centerIn: parent; text: parent.modelData; color: "white"; font.pixelSize: 12; font.weight: Font.DemiBold }
                }
            }
        }
    }
    }
}
