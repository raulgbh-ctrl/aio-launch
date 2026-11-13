import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// The in-game panel: Guide + Y on a controller (or `cornerplay --overlay`, bound to a key in
// the desktop's settings) opens it over the game. The clock, how long this session has run,
// the battery, the game's note and the screenshots taken so far; back to the game, to
// Cornerplay, or quit. Arrows / D-pad move, A / Return chooses, B / Escape closes.
Window {
    id: ov
    required property var theme
    property var info: ({})
    property int choice: 0
    property bool confirmQuit: false
    property var now: new Date()
    signal openCornerplay()

    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
    color: "transparent"
    width: 460
    height: panel.implicitHeight
    title: qsTr("Cornerplay in-game panel")

    function toggle() {
        if (visible) { close(); return }
        info = app.overlayInfo()
        now = new Date()
        choice = 0
        confirmQuit = false
        noteField.text = info.note || ""
        show(); raise(); requestActivate()
        panel.forceActiveFocus()
    }
    function minutesText(m) {
        return m < 60 ? qsTr("%1 min").arg(m) : qsTr("%1 h %2 min").arg(Math.floor(m / 60)).arg(m % 60)
    }
    onVisibleChanged: if (!visible && info.key && noteField.text !== (info.note || "")) app.setNote(info.key, noteField.text)

    readonly property var actions: info.key
        ? [{ i: "play", t: qsTr("Back to the game"), run: () => ov.close() },
           { i: "layout-grid", t: qsTr("Open Cornerplay"), run: () => { ov.close(); ov.openCornerplay() } },
           { i: "x", t: confirmQuit ? qsTr("Press again to quit %1").arg(info.title) : qsTr("Quit the game"), danger: true,
             run: () => { if (!ov.confirmQuit) { ov.confirmQuit = true; return } app.quitGame(info.key, false); ov.close() } }]
        : [{ i: "layout-grid", t: qsTr("Open Cornerplay"), run: () => { ov.close(); ov.openCornerplay() } },
           { i: "x", t: qsTr("Close"), run: () => ov.close() }]

    Timer { interval: 15000; repeat: true; running: ov.visible; onTriggered: { ov.now = new Date(); if (ov.info.since) ov.info = Object.assign({}, ov.info, { minutes: Math.floor((Date.now() / 1000 - ov.info.since) / 60) }) } }

    Rectangle {
        id: panel
        width: parent.width
        implicitHeight: col.implicitHeight + 36
        radius: 22
        color: ov.theme.surfaceContainer
        border.width: 1
        border.color: Qt.alpha(ov.theme.outline, 0.35)
        clip: true
        focus: true
        Keys.onPressed: (event) => {
            if (noteField.activeFocus && event.key !== Qt.Key_Escape && event.key !== Qt.Key_Down) return
            if (event.key === Qt.Key_Down) { noteField.focus = false; panel.forceActiveFocus(); ov.choice = Math.min(ov.actions.length - 1, ov.choice + 1) }
            else if (event.key === Qt.Key_Up) ov.choice = Math.max(0, ov.choice - 1)
            else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) ov.actions[ov.choice].run()
            else if (event.key === Qt.Key_Escape || event.key === Qt.Key_F10 || event.key === Qt.Key_F9) ov.close()
            else return
            event.accepted = true
        }
        onActiveFocusChanged: if (!activeFocus && !noteField.activeFocus) ov.confirmQuit = false

        // the game's wide art, faded, behind the heading
        ArtImage {
            width: parent.width; height: 150
            clip: true
            sources: ov.info.heroes && ov.info.heroes.length ? ov.info.heroes : (ov.info.covers || [])
            fillMode: Image.PreserveAspectCrop
            opacity: 0.35
            visible: !!ov.info.key
        }
        Rectangle {
            width: parent.width; height: 150
            gradient: Gradient {
                GradientStop { position: 0; color: "transparent" }
                GradientStop { position: 0.8; color: ov.theme.surfaceContainer }
            }
        }

        ColumnLayout {
            id: col
            x: 18; y: 18
            width: parent.width - 36
            spacing: 12
            RowLayout {
                Layout.fillWidth: true
                Text { text: Qt.formatTime(ov.now, Qt.locale().timeFormat(Locale.ShortFormat)); color: ov.theme.onSurface
                       font.pixelSize: 30; font.weight: Font.Bold }
                Item { Layout.fillWidth: true }
                Row {
                    visible: !!ov.info.battery && ov.info.battery.percent !== undefined
                    spacing: 6
                    Icon { anchors.verticalCenter: parent.verticalCenter; name: ov.info.battery && ov.info.battery.charging ? "battery-charging" : "battery"
                           size: 16; color: ov.info.battery && ov.info.battery.percent <= 20 && !ov.info.battery.charging ? "#ff6b6b" : ov.theme.onSurfaceVariant }
                    Text { anchors.verticalCenter: parent.verticalCenter; text: (ov.info.battery ? ov.info.battery.percent : 0) + "%"
                           color: ov.theme.onSurfaceVariant; font.pixelSize: 14; font.weight: Font.DemiBold }
                }
            }
            Text {
                Layout.fillWidth: true
                text: ov.info.key ? ov.info.title : qsTr("No game is running")
                color: ov.theme.onSurface; font.pixelSize: 22; font.weight: Font.Bold; elide: Text.ElideRight
            }
            Flow {
                Layout.fillWidth: true
                visible: !!ov.info.key
                spacing: 8
                Repeater {
                    model: [qsTr("This session: ") + ov.minutesText(ov.info.minutes || 0),
                            ov.info.total ? qsTr("%1 h in all").arg(Math.round(ov.info.total + (ov.info.minutes || 0) / 60)) : "",
                            ov.info.shots ? (ov.info.shots === 1 ? qsTr("1 screenshot so far") : qsTr("%1 screenshots so far").arg(ov.info.shots)) : ""].filter(t => t)
                    delegate: Rectangle {
                        required property string modelData
                        height: 28; radius: 14; width: chipText.implicitWidth + 22
                        color: Qt.alpha(ov.theme.onSurface, 0.08)
                        Text { id: chipText; anchors.centerIn: parent; text: parent.modelData; color: ov.theme.onSurfaceVariant; font.pixelSize: 12; font.weight: Font.DemiBold }
                    }
                }
            }
            // the game's note: where you were, what to do next
            Rectangle {
                Layout.fillWidth: true
                visible: !!ov.info.key
                implicitHeight: Math.max(64, noteField.implicitHeight + 16)
                radius: 12
                color: ov.theme.surfaceContainerHigh
                border.width: noteField.activeFocus ? 1 : 0
                border.color: ov.theme.primary
                TextArea {
                    id: noteField
                    anchors.fill: parent
                    anchors.margins: 4
                    wrapMode: TextArea.Wrap
                    placeholderText: qsTr("A note for later: where you are, what to do next…")
                    placeholderTextColor: ov.theme.outline
                    color: ov.theme.onSurface
                    font.pixelSize: 13
                    background: null
                }
            }
            Repeater {
                model: ov.actions
                delegate: Rectangle {
                    id: act
                    required property var modelData
                    required property int index
                    readonly property bool on: ov.choice === index && !noteField.activeFocus
                    Layout.fillWidth: true
                    implicitHeight: 48
                    radius: 14
                    color: on ? (modelData.danger ? Qt.alpha("#ff6b6b", 0.22) : Qt.alpha(ov.theme.primary, 0.22))
                              : actHover.hovered ? ov.theme.surfaceContainerHigh : "transparent"
                    border.width: on ? 1 : 0
                    border.color: modelData.danger ? "#ff6b6b" : ov.theme.primary
                    Row {
                        x: 14; anchors.verticalCenter: parent.verticalCenter
                        spacing: 12
                        Icon { anchors.verticalCenter: parent.verticalCenter; name: act.modelData.i; size: 18
                               color: act.modelData.danger ? "#ff8a8a" : act.on ? ov.theme.primary : ov.theme.onSurfaceVariant }
                        Text { anchors.verticalCenter: parent.verticalCenter; text: act.modelData.t; font.pixelSize: 15; font.weight: Font.DemiBold
                               color: act.modelData.danger ? "#ff8a8a" : ov.theme.onSurface }
                    }
                    HoverHandler { id: actHover; onHoveredChanged: if (hovered) ov.choice = act.index }
                    TapHandler { onTapped: { ov.choice = act.index; act.modelData.run() } }
                }
            }
            Text {
                Layout.fillWidth: true
                horizontalAlignment: Text.AlignHCenter
                text: qsTr("Guide + Y opens and closes this panel")
                color: ov.theme.outline; font.pixelSize: 11
            }
        }
    }
}
