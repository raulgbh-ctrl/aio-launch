import QtQuick

// TV mode's screensaver: after a few quiet minutes (Settings > Appearance), your recently played
// games' art drifts slowly by, with the clock and when you last played each. Any button, key,
// click or pointer movement wakes it, and that first press only wakes it (it does nothing else).
Rectangle {
    id: saver
    objectName: "tvSaver"
    required property var theme
    signal woke()
    color: "black"
    visible: false
    opacity: 0
    property var games: []
    property int at: 0
    readonly property var game: games.length ? games[at % games.length] : ({})

    function start() {
        const recent = app.recentGames.filter(g => (g.heroes || []).length || (g.covers || []).length)
        games = recent.length ? recent.slice(0, 12) : []
        at = 0
        visible = true
        fadeIn.restart()
        forceActiveFocus()
    }
    function wake() {
        if (!visible) return
        fadeIn.stop()
        visible = false
        opacity = 0
        woke()
    }
    NumberAnimation { id: fadeIn; target: saver; property: "opacity"; from: 0; to: 1; duration: 1600; easing.type: Easing.InOutQuad }
    Keys.onPressed: event => { event.accepted = true; wake() }
    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        property point first: Qt.point(-1, -1)
        onPositionChanged: mouse => {  // a nudge, not the pointer resting where it was
            if (first.x < 0) { first = Qt.point(mouse.x, mouse.y); return }
            if (Math.abs(mouse.x - first.x) + Math.abs(mouse.y - first.y) > 12) saver.wake()
        }
        onPressed: saver.wake()
        onWheel: saver.wake()
        onVisibleChanged: first = Qt.point(-1, -1)
    }

    // Two layers: the next picture fades in over the last one, each slowly drifting and growing.
    Repeater {
        model: 2
        Image {
            id: slide
            required property int index
            anchors.fill: parent
            fillMode: Image.PreserveAspectCrop
            asynchronous: true
            readonly property bool front: (saver.at % 2) === index
            source: {
                if (!saver.visible || !saver.games.length) return ""
                const g = front ? saver.game : saver.games[(saver.at + saver.games.length - 1) % saver.games.length]
                return ((g.heroes || [])[0]) || ((g.covers || [])[0]) || ""
            }
            opacity: front && status === Image.Ready ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: 2500; easing.type: Easing.InOutQuad } }
            transform: [
                Scale { id: zoom; origin.x: slide.width / 2; origin.y: slide.height / 2; xScale: 1.0; yScale: xScale },
                Translate { id: drift }
            ]
            NumberAnimation { target: drift; property: "x"; running: saver.visible && slide.front && !app.light; from: 0; to: -40; duration: 14000 }
            NumberAnimation { target: zoom; property: "xScale"; running: saver.visible && slide.front && !app.light; from: 1.0; to: 1.08; duration: 14000 }
        }
    }
    Rectangle {  // a soft darkening, for the words
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#66000000" }
            GradientStop { position: 0.55; color: "#00000000" }
            GradientStop { position: 1.0; color: "#cc000000" }
        }
    }
    Timer { interval: 12000; repeat: true; running: saver.visible && saver.games.length > 1; onTriggered: saver.at++ }

    property string clock: ""
    Timer { interval: 1000; repeat: true; triggeredOnStart: true; running: saver.visible
            onTriggered: saver.clock = Qt.formatTime(new Date(), Qt.locale().timeFormat(Locale.ShortFormat)) }
    Text {
        anchors { right: parent.right; top: parent.top; margins: saver.height * 0.06 }
        text: saver.clock
        color: "white"; opacity: 0.92
        font.pixelSize: Math.round(saver.height * 0.09); font.weight: Font.Light
    }
    Column {
        anchors { left: parent.left; bottom: parent.bottom; margins: saver.height * 0.07 }
        spacing: 8
        Text {
            text: saver.game.title || ""
            color: "white"
            font.pixelSize: Math.round(saver.height * 0.045); font.weight: Font.DemiBold
        }
        Text {
            visible: !!saver.game.lastPlayed
            text: {
                const today = new Date(); today.setHours(0, 0, 0, 0)        // calendar days, like the rest of TV mode
                const then = new Date((saver.game.lastPlayed || 0) * 1000); then.setHours(0, 0, 0, 0)
                const days = Math.round((today - then) / 86400000)
                return qsTr("Last played ") + (days <= 0 ? qsTr("today") : days === 1 ? qsTr("yesterday") : days + qsTr(" days ago"))
            }
            color: "white"; opacity: 0.75
            font.pixelSize: Math.round(saver.height * 0.024)
        }
    }
    Text {
        visible: !saver.games.length
        anchors.centerIn: parent
        text: "Cornerplay"
        color: "white"; opacity: 0.4
        font.pixelSize: Math.round(saver.height * 0.05)
    }
}
