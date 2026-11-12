import QtQuick

// "Who's playing?" when TV mode starts on a PC with several people (Settings > People): big
// round avatars, left and right to choose, A to pick. Each person has their own favourites,
// collections, backlog, notes and playtime (personal.py).
Rectangle {
    id: who
    objectName: "tvWho"
    required property var theme
    signal done()
    color: theme.background
    visible: false
    property int at: 0
    readonly property var people: app.profiles
    readonly property var palette: ["#ffb547", "#8ab4f8", "#8fd6a4", "#ff8a80", "#d2bcfd", "#7fd0ff", "#ffb1c8", "#d7e075"]

    function show() {
        at = Math.max(0, people.indexOf(app.profile))
        visible = true
        forceActiveFocus()
    }
    function choose(i) {
        app.uiSound("select")
        app.switchProfile(people[i])
        visible = false
        done()
    }
    Keys.onPressed: event => {
        event.accepted = true
        if (event.key === Qt.Key_Left) { at = (at + people.length - 1) % people.length; app.uiSound("move") }
        else if (event.key === Qt.Key_Right) { at = (at + 1) % people.length; app.uiSound("move") }
        else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) choose(at)
        else if (event.key === Qt.Key_Escape || event.key === Qt.Key_Backspace) { visible = false; done() }  // B: keep who it was
    }

    Column {
        anchors.centerIn: parent
        spacing: who.height * 0.06
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: qsTr("Who's playing?")
            color: who.theme.onSurface
            font.pixelSize: Math.round(who.height * 0.055); font.weight: Font.DemiBold
        }
        Row {
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: who.height * 0.05
            Repeater {
                model: who.people
                Column {
                    id: person
                    required property string modelData
                    required property int index
                    readonly property bool current: index === who.at
                    readonly property real size: who.height * 0.17
                    spacing: 16
                    Rectangle {
                        anchors.horizontalCenter: parent.horizontalCenter
                        width: person.size; height: width; radius: width / 2
                        color: who.palette[person.index % who.palette.length]
                        scale: person.current ? 1.12 : 0.92
                        opacity: person.current ? 1 : 0.6
                        Behavior on scale { enabled: !app.light; NumberAnimation { duration: 180; easing.type: Easing.OutBack } }
                        Behavior on opacity { NumberAnimation { duration: 150 } }
                        border.width: person.current ? 5 : 0
                        border.color: who.theme.onSurface
                        Text {
                            anchors.centerIn: parent
                            text: person.modelData.charAt(0).toUpperCase()
                            color: "#1b1b1f"
                            font.pixelSize: Math.round(person.size * 0.45); font.weight: Font.Bold
                        }
                        TapHandler { onTapped: who.choose(person.index) }
                        HoverHandler { cursorShape: Qt.PointingHandCursor; onHoveredChanged: if (hovered) who.at = person.index }
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: person.modelData
                        color: person.current ? who.theme.onSurface : who.theme.onSurfaceVariant
                        font.pixelSize: Math.round(who.height * 0.03); font.weight: person.current ? Font.DemiBold : Font.Normal
                    }
                }
            }
        }
    }
}
