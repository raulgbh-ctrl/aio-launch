import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Effects
import QtQuick.Layouts

// Full-screen, couch-distance view driven entirely by arrows / a controller.
FocusScope {
    id: tv
    required property var theme
    signal exit()

    property var cur: ({})
    readonly property var storeIds: [""].concat(app.storesInfo.map(s => s.id))

    function sync() { cur = app.game(library.keyAt(grid.currentIndex)) }
    function cycleStore(step) {
        const i = storeIds.indexOf(library.storeFilter)
        library.storeFilter = storeIds[(i + step + storeIds.length) % storeIds.length]
        grid.currentIndex = 0
        sync()
    }
    function accept() {
        if (!cur.key) return
        const target = app.launchTarget(cur.key)
        if (target) app.play(target)
        else panel.show()
    }
    function buildActions() {
        const out = []
        if (!cur.key) return out
        const copies = cur.copies.length ? cur.copies : [{ key: cur.key, storeName: cur.storeName }]
        const removable = []
        for (const c of copies) {
            const g = app.game(c.key)
            if (g.job) out.push({ label: "Cancel " + (g.job === "install" ? "install" : "removal") + " · " + c.storeName, act: "cancel", key: c.key })
            else if (g.installed) { out.push({ label: "Play on " + c.storeName, act: "play", key: c.key }); if (g.store !== "battlenet") removable.push(c) }
            else out.push({ label: "Install from " + c.storeName, act: "install", key: c.key })
        }
        for (const c of removable) out.push({ label: "Uninstall from " + c.storeName, act: "uninstall", key: c.key })
        out.push({ label: "Close", act: "close", key: "" })
        return out
    }

    function grab() { grid.forceActiveFocus(); sync() }
    onVisibleChanged: if (visible) grab()
    Component.onCompleted: if (visible) Qt.callLater(grab)
    Connections {
        target: app
        function onGameChanged(key) { tv.sync(); if (panel.visible) panel.rows = tv.buildActions() }
    }

    Rectangle { anchors.fill: parent; color: theme.background }

    // Soft backdrop from the focused game's cover.
    Image {
        id: backdrop
        anchors.fill: parent
        source: tv.visible ? (tv.cur.cover || "") : ""
        asynchronous: true
        fillMode: Image.PreserveAspectCrop
        sourceSize.width: 200
        visible: false
    }
    MultiEffect {
        anchors.fill: parent
        source: backdrop
        visible: GraphicsInfo.api !== GraphicsInfo.Software && backdrop.status === Image.Ready
        blurEnabled: true
        blur: 1.0
        blurMax: 64
        opacity: 0.28
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 48
        anchors.bottomMargin: 28
        spacing: 22

        // Store tabs.
        RowLayout {
            spacing: 12
            Text { text: "Kura"; color: theme.onSurface; font.pixelSize: 30; font.weight: Font.Bold; Layout.rightMargin: 20 }
            Repeater {
                model: tv.storeIds
                Rectangle {
                    required property string modelData
                    readonly property bool active: library.storeFilter === modelData
                    readonly property var info: app.storesInfo.find(s => s.id === modelData) || ({ name: "All games", color: "" })
                    implicitWidth: tabText.implicitWidth + 36
                    implicitHeight: 46
                    radius: 23
                    color: active ? theme.primary : "transparent"
                    border.width: active ? 0 : 1
                    border.color: theme.outlineVariant
                    Text {
                        id: tabText
                        anchors.centerIn: parent
                        text: parent.info.name
                        color: parent.active ? theme.onPrimary : theme.onSurfaceVariant
                        font.pixelSize: 18
                        font.weight: parent.active ? Font.DemiBold : Font.Normal
                    }
                    TapHandler { onTapped: { library.storeFilter = parent.modelData; grid.currentIndex = 0; tv.sync() } }
                }
            }
            Item { Layout.fillWidth: true }
            Text {
                visible: library.installedOnly
                text: "Installed only"
                color: theme.primary
                font.pixelSize: 16
            }
        }

        GridView {
            id: grid
            Layout.fillWidth: true
            Layout.fillHeight: true
            focus: true
            clip: true
            model: library
            readonly property int columns: Math.max(3, Math.floor(width / (app.settingsMap.card_size * 1.3)))
            cellWidth: Math.floor(width / columns)
            cellHeight: Math.round(cellWidth * 1.46)
            cacheBuffer: cellHeight * 2
            keyNavigationEnabled: true
            boundsBehavior: Flickable.StopAtBounds
            highlightMoveDuration: 160
            preferredHighlightBegin: cellHeight * 0.15
            preferredHighlightEnd: height - cellHeight * 0.15
            highlightRangeMode: GridView.ApplyRange
            onCurrentIndexChanged: tv.sync()
            onCountChanged: { if (currentIndex < 0 && count > 0) currentIndex = 0; tv.sync() }
            delegate: GameCard {
                required property int index
                width: grid.cellWidth
                height: grid.cellHeight
                theme: tv.theme
                cornerRadius: app.settingsMap.card_radius
                showBadge: app.settingsMap.show_badges
                showTitle: false
                dim: app.settingsMap.dim_uninstalled
                current: GridView.isCurrentItem
                onOpened: { grid.currentIndex = index; tv.sync(); panel.show() }
                onActivated: { grid.currentIndex = index; tv.sync(); tv.accept() }
            }
            Keys.onReturnPressed: tv.accept()
            Keys.onEnterPressed: tv.accept()
            Keys.onEscapePressed: tv.exit()
            Keys.onPressed: event => {
                if (event.key === Qt.Key_F2) { panel.show(); event.accepted = true }
                else if (event.key === Qt.Key_F3) { library.installedOnly = !library.installedOnly; event.accepted = true }
                else if (event.key === Qt.Key_PageUp) { tv.cycleStore(-1); event.accepted = true }
                else if (event.key === Qt.Key_PageDown) { tv.cycleStore(1); event.accepted = true }
            }

            Text {
                visible: grid.count === 0
                anchors.centerIn: parent
                text: app.refreshing ? "Loading your libraries…" : "No games here"
                color: theme.onSurfaceVariant
                font.pixelSize: 26
            }
        }

        // Focused game + button hints.
        RowLayout {
            spacing: 16
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4
                Text {
                    Layout.fillWidth: true
                    text: tv.cur.title || ""
                    color: theme.onSurface
                    font.pixelSize: 30
                    font.weight: Font.Bold
                    elide: Text.ElideRight
                }
                Text {
                    color: theme.onSurfaceVariant
                    font.pixelSize: 17
                    text: {
                        if (!tv.cur.key) return ""
                        const stores = tv.cur.copies.length ? tv.cur.copies.map(c => c.storeName).join(", ") : tv.cur.storeName
                        const state = tv.cur.job === "install" ? "Installing " + Math.max(0, Math.floor(tv.cur.progress)) + "%"
                                    : tv.cur.job ? "Removing…" : tv.cur.installed ? "Installed" : "Not installed"
                        return stores + "  ·  " + state
                    }
                }
            }
            Text {
                visible: tv.width >= 1100
                color: theme.outline
                font.pixelSize: 15
                text: pad.connected
                      ? "Ⓐ Play    Ⓧ Actions    Ⓨ Installed only    LB / RB Store    Ⓑ Exit"
                      : "Enter Play    F2 Actions    F3 Installed only    PgUp / PgDn Store    Esc Exit"
            }
        }
    }

    // Action panel: every choice for the focused game, one press each.
    Rectangle {
        anchors.fill: parent
        visible: panel.visible
        color: "#b0000000"
        TapHandler { onTapped: panel.hide() }
    }
    Rectangle {
        id: panel
        property var rows: []
        property int armed: -1
        function show() { if (!tv.cur.key) return; rows = tv.buildActions(); armed = -1; list.currentIndex = 0; visible = true; list.forceActiveFocus() }
        function hide() { visible = false; grid.forceActiveFocus() }
        function run(i) {
            const a = rows[i]
            if (!a) return
            if (a.act === "uninstall" && armed !== i) { armed = i; return }
            armed = -1
            if (a.act === "play") { app.preferCopy(a.key); app.play(a.key) }
            else if (a.act === "install") { app.preferCopy(a.key); app.install(a.key) }
            else if (a.act === "cancel") app.cancel(a.key)
            else if (a.act === "uninstall") app.uninstall(a.key)
            hide()
        }
        visible: false
        anchors { right: parent.right; top: parent.top; bottom: parent.bottom }
        width: Math.min(520, parent.width * 0.42)
        color: theme.surfaceContainer
        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 40
            spacing: 18
            Text {
                Layout.fillWidth: true
                text: tv.cur.title || ""
                color: theme.onSurface
                font.pixelSize: 28
                font.weight: Font.Bold
                wrapMode: Text.WordWrap
            }
            Text {
                Layout.fillWidth: true
                visible: (tv.cur.copies || []).length > 1
                text: "You own this on " + (tv.cur.copies || []).length + " stores. Choose the launcher:"
                color: theme.onSurfaceVariant
                font.pixelSize: 16
                wrapMode: Text.WordWrap
            }
            ListView {
                id: list
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                spacing: 10
                model: panel.rows
                keyNavigationWraps: true
                delegate: Rectangle {
                    required property var modelData
                    required property int index
                    width: list.width
                    height: 60
                    radius: 14
                    color: ListView.isCurrentItem ? theme.primary : theme.surfaceContainerHigh
                    Text {
                        anchors { verticalCenter: parent.verticalCenter; left: parent.left; right: parent.right; margins: 22 }
                        text: panel.armed === parent.index ? "Press again to uninstall" : parent.modelData.label
                        color: parent.ListView.isCurrentItem ? theme.onPrimary
                               : parent.modelData.act === "uninstall" ? theme.error : theme.onSurface
                        font.pixelSize: 19
                        font.weight: Font.DemiBold
                        elide: Text.ElideRight
                    }
                    TapHandler { onTapped: { list.currentIndex = parent.index; panel.run(parent.index) } }
                }
                onCurrentIndexChanged: panel.armed = -1
                Keys.onReturnPressed: panel.run(currentIndex)
                Keys.onEnterPressed: panel.run(currentIndex)
                Keys.onEscapePressed: panel.hide()
                Keys.onLeftPressed: panel.hide()
            }
        }
    }
}
