import QtQuick
import QtQuick.Layouts

// Your stats in TV mode (Guide menu): the year in big type, readable from the sofa. Left and
// right change the year; up and down scroll; B goes back.
Rectangle {
    id: st
    objectName: "tvStats"
    required property var theme
    required property var tint
    signal closed()
    color: Qt.alpha(theme.background, 0.97)
    visible: false
    property var d: ({})
    property var yr: ({})
    property int yearAt: 0

    function show() { d = app.stats(); yr = d.year || {}; yearAt = 0; flick.contentY = 0; visible = true; forceActiveFocus() }
    function close() { app.uiSound("back"); visible = false; closed() }
    Keys.onPressed: event => {
        event.accepted = true
        const k = event.key, years = d.years || []
        if (k === Qt.Key_Escape || k === Qt.Key_Backspace || k === Qt.Key_Return) close()
        else if (k === Qt.Key_Down) flick.contentY = Math.min(Math.max(0, flick.contentHeight - flick.height), flick.contentY + st.height * 0.2)
        else if (k === Qt.Key_Up) flick.contentY = Math.max(0, flick.contentY - st.height * 0.2)
        else if ((k === Qt.Key_Left || k === Qt.Key_Right) && years.length > 1) {
            yearAt = (yearAt + (k === Qt.Key_Right ? 1 : years.length - 1)) % years.length
            yr = app.yearStats(years[yearAt]); app.uiSound("move")
        }
    }
    readonly property real u: height / 100   // one per cent of the screen's height

    Flickable {
        id: flick
        anchors { fill: parent; margins: st.u * 7 }
        contentHeight: col.implicitHeight
        clip: true
        interactive: false
        Behavior on contentY { enabled: !app.light; NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
        ColumnLayout {
            id: col
            width: flick.width
            spacing: st.u * 3
            Text { text: qsTr("Your ") + (st.yr.year || "") + qsTr(" in Cornerplay"); color: st.theme.onSurface
                   font.pixelSize: Math.round(st.u * 5.5); font.weight: Font.Bold }
            RowLayout {
                Layout.fillWidth: true
                spacing: st.u * 2
                Repeater {
                    model: [{ big: (st.yr.hours || 0) + " h", small: qsTr("played") },
                            { big: String(st.yr.games || 0), small: qsTr("games played") },
                            { big: String(st.yr.newCount || 0), small: qsTr("started for the first time") },
                            { big: String(st.yr.finishedCount || 0), small: qsTr("finished") },
                            { big: (st.d.totalHours || 0) + " h", small: qsTr("all time") }]
                    Rectangle {
                        required property var modelData
                        Layout.fillWidth: true
                        Layout.preferredHeight: st.u * 15
                        radius: st.u * 2
                        color: Qt.alpha(st.theme.surfaceContainerHigh, 0.9)
                        Column {
                            id: tileCol
                            anchors.centerIn: parent
                            width: parent.width - st.u * 1.5
                            spacing: st.u * 0.6
                            Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; text: modelData.big; color: st.theme.onSurface
                                   fontSizeMode: Text.HorizontalFit; minimumPixelSize: 12
                                   font.pixelSize: Math.round(st.u * 5); font.weight: Font.Bold }
                            Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; text: modelData.small; color: st.theme.onSurfaceVariant
                                   wrapMode: Text.WordWrap; maximumLineCount: 2; elide: Text.ElideRight
                                   font.pixelSize: Math.round(st.u * 2) }
                        }
                    }
                }
            }
            Text {
                visible: !!st.yr.busiestMonth
                text: qsTr("Busiest month: ") + (st.yr.busiestMonth || "") + " (" + (st.yr.busiestHours || 0) + " h)"
                      + ((st.yr.longest || {}).title ? qsTr("   ·   Longest session: ") + st.yr.longest.title + ", " + st.yr.longest.hours + " h" : "")
                color: st.theme.onSurface; font.pixelSize: Math.round(st.u * 2.6)
            }
            Item {  // hours per month
                Layout.fillWidth: true
                Layout.preferredHeight: st.u * 22
                visible: (st.yr.hours || 0) > 0
                readonly property real peak: Math.max(1, ...((st.yr.months || [0])))
                Row {
                    anchors.fill: parent
                    spacing: st.u * 1.2
                    Repeater {
                        model: st.yr.months || []
                        Item {
                            required property real modelData
                            required property int index
                            width: (parent.width - 11 * st.u * 1.2) / 12
                            height: parent.height
                            Rectangle {
                                anchors.bottom: ml.top; anchors.bottomMargin: st.u * 0.8
                                width: parent.width
                                height: Math.max(st.u * 0.5, (parent.height - st.u * 5) * modelData / parent.parent.parent.peak)
                                radius: st.u * 0.8
                                color: modelData > 0 ? st.tint.primary : Qt.alpha(st.theme.onSurface, 0.1)
                            }
                            Text { id: ml; anchors.bottom: parent.bottom; anchors.horizontalCenter: parent.horizontalCenter
                                   text: qsTr("JFMAMJJASOND")[index]; color: st.theme.onSurfaceVariant; font.pixelSize: Math.round(st.u * 2) }
                        }
                    }
                }
            }
            Text { visible: (st.yr.top || []).length > 0; text: qsTr("Most played"); color: st.theme.onSurfaceVariant
                   font.pixelSize: Math.round(st.u * 2.6); font.weight: Font.DemiBold }
            Repeater {
                model: st.yr.top || []
                RowLayout {
                    required property var modelData
                    required property int index
                    Layout.fillWidth: true
                    Text { text: (index + 1) + "."; color: st.theme.outline; font.pixelSize: Math.round(st.u * 3); Layout.preferredWidth: st.u * 5 }
                    Text { Layout.fillWidth: true; text: modelData.title; color: st.theme.onSurface; elide: Text.ElideRight
                           font.pixelSize: Math.round(st.u * 3) }
                    Text { text: modelData.hours + " h"; color: st.theme.onSurfaceVariant; font.pixelSize: Math.round(st.u * 2.8) }
                }
            }
            Text {
                Layout.fillWidth: true
                visible: !((st.yr.hours || 0) > 0)
                wrapMode: Text.WordWrap
                text: qsTr("Hours fill in from the play sessions Cornerplay sees: the games it starts, and Steam games while Cornerplay is running.")
                color: st.theme.onSurfaceVariant; font.pixelSize: Math.round(st.u * 2.4)
            }
        }
    }
    TvHints {
        anchors { left: parent.left; bottom: parent.bottom; margins: st.u * 4 }
        theme: st.theme
        hints: [{ b: "b", k: "Esc", t: qsTr("Back") }].concat((st.d.years || []).length > 1 ? [{ b: "", k: "\u2190 \u2192", t: qsTr("another year") }] : [])
    }
}
