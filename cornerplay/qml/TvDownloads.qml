import QtQuick

// Downloads in TV mode (Guide menu): the same list as the desktop panel, with the controller.
// Up and down choose; A pauses or resumes; left and right move a waiting download earlier or
// later; X cancels (press it twice); B goes back.
Rectangle {
    id: dl
    objectName: "tvDownloads"
    required property var theme
    required property var tint
    signal closed()
    color: Qt.alpha(theme.background, 0.97)
    visible: false
    property int at: 0
    property string armed: ""   // key whose cancel waits for the second X
    readonly property var rows: app.downloads
    readonly property var cur: rows[Math.min(at, rows.length - 1)] || ({})

    function show() { at = 0; armed = ""; visible = true; forceActiveFocus() }
    function close() { app.uiSound("back"); visible = false; closed() }
    Keys.onPressed: event => {
        event.accepted = true
        const k = event.key
        if (k === Qt.Key_Escape || k === Qt.Key_Backspace) { close(); return }
        if (!rows.length) return
        if (k === Qt.Key_Down && at < rows.length - 1) { at++; armed = ""; app.uiSound("move") }
        else if (k === Qt.Key_Up && at > 0) { at--; armed = ""; app.uiSound("move") }
        else if ((k === Qt.Key_Left || k === Qt.Key_Right) && cur.state === "queued") {
            app.moveDownload(cur.key, k === Qt.Key_Left ? -1 : 1); app.uiSound("move")
            const key = cur.key
            Qt.callLater(() => { dl.at = Math.max(0, dl.rows.findIndex(r => r.key === key)) })
        }
        else if (k === Qt.Key_Return || k === Qt.Key_Enter) {
            app.uiSound("select")
            if (cur.state === "paused") app.resumeDownload(cur.key)
            else if (cur.pausable) app.pauseDownload(cur.key)
        }
        else if (k === Qt.Key_F2) {
            if (armed === cur.key) { app.cancel(cur.key); armed = ""; at = Math.max(0, at - 1) }
            else armed = cur.key
            app.uiSound("select")
        }
    }

    Text {
        id: heading
        anchors { left: parent.left; top: parent.top; margins: dl.height * 0.07 }
        text: qsTr("Downloads")
        color: dl.theme.onSurface
        font.pixelSize: Math.round(dl.height * 0.05); font.weight: Font.DemiBold
    }
    Text {
        anchors { left: heading.left; top: heading.bottom; topMargin: 30 }
        visible: !dl.rows.length
        text: qsTr("Nothing is downloading.")
        color: dl.theme.onSurfaceVariant
        font.pixelSize: Math.round(dl.height * 0.028)
    }
    ListView {
        id: list
        anchors { left: parent.left; right: parent.right; top: heading.bottom; bottom: hints.top
                  leftMargin: dl.height * 0.07; rightMargin: dl.height * 0.07; topMargin: 30; bottomMargin: 20 }
        spacing: 14
        clip: true
        interactive: false
        model: dl.rows
        currentIndex: dl.at
        highlightMoveDuration: 150
        delegate: Rectangle {
            required property var modelData
            required property int index
            readonly property bool focused: index === dl.at
            width: list.width
            height: dl.height * 0.13
            radius: 18
            color: focused ? Qt.alpha(dl.theme.surfaceContainerHigh, 1) : Qt.alpha(dl.theme.surfaceContainerHigh, 0.5)
            border.width: focused ? 4 : 0; border.color: dl.theme.onSurface
            Row {
                anchors { left: parent.left; leftMargin: 18; verticalCenter: parent.verticalCenter }
                spacing: 22
                RoundedArt {
                    width: height * 0.72; height: dl.height * 0.1
                    radius: 8
                    ArtImage { anchors.fill: parent; sources: modelData.covers || []; sourceSize.width: 120 }
                }
                Column {
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 8
                    width: list.width * 0.62
                    Text { text: modelData.title; color: dl.theme.onSurface; elide: Text.ElideRight; width: parent.width
                           font.pixelSize: Math.round(dl.height * 0.03); font.weight: Font.DemiBold }
                    Text {
                        color: dl.theme.onSurfaceVariant
                        font.pixelSize: Math.round(dl.height * 0.022)
                        text: {
                            const d = modelData
                            if (dl.armed === d.key) return qsTr("Press X again to cancel")
                            if (d.state === "queued") return qsTr("Waiting its turn")
                            if (d.state === "paused") return qsTr("Paused") + (d.progress >= 0 ? "  ·  " + Math.floor(d.progress) + "%" : "")
                            const parts = [d.progress >= 0 ? Math.floor(d.progress) + "%" : qsTr("Starting…")]
                            if (d.speed > 0) parts.push(d.speed >= 1e6 ? (d.speed / 1e6).toFixed(1) + " MB/s" : Math.round(d.speed / 1e3) + " kB/s")
                            if (d.eta >= 0) parts.push(d.eta < 60 ? qsTr("under a minute left") : Math.round(d.eta / 60) + qsTr(" min left"))
                            return parts.join("  ·  ")
                        }
                    }
                    Rectangle {
                        width: parent.width; height: 8; radius: 4
                        color: Qt.alpha(dl.theme.onSurface, 0.12)
                        Rectangle { height: parent.height; radius: 4; width: parent.width * Math.max(0, modelData.progress) / 100
                                    color: modelData.state === "running" ? dl.tint.primary : dl.theme.outline }
                    }
                }
            }
        }
    }
    TvHints {
        id: hints
        anchors { left: parent.left; bottom: parent.bottom; margins: dl.height * 0.05 }
        theme: dl.theme
        hints: [{ b: "a", k: "Enter", t: dl.cur.state === "paused" ? qsTr("Resume") : qsTr("Pause") },
                { b: "x", k: "F2", t: qsTr("Cancel") }, { b: "b", k: "Esc", t: qsTr("Back") }]
               .concat(dl.cur.state === "queued" ? [{ b: "", k: "\u2190 \u2192", t: qsTr("earlier / later") }] : [])
    }
}
