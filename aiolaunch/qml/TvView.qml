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

    // The focused game's own colour (from its cover) tints the glow and the active tab.
    property string gameAccent: ""
    property color accent: gameAccent || theme.primary
    Behavior on accent { enabled: !app.light; ColorAnimation { duration: 450 } }
    readonly property var tint: {
        const c = tv.accent
        const lum = 0.299 * c.r + 0.587 * c.g + 0.114 * c.b
        return Object.assign({}, tv.theme, { primary: c.toString(), onPrimary: lum > 0.55 ? "#1b1b1f" : "#ffffff" })
    }
    onCurChanged: gameAccent = cur.key ? app.gameColour(cur.key) : ""
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
            if (g.job) out.push({ label: "Cancel " + ({ install: "install", update: "update" }[g.job] || "removal") + " · " + c.storeName, act: "cancel", key: c.key })
            else if (g.installed) {
                out.push({ label: "Play on " + c.storeName, act: "play", key: c.key })
                if (g.update) out.push({ label: "Update on " + c.storeName, act: "update", key: c.key })
                if (g.store !== "battlenet") removable.push(c)
            }
            else out.push({ label: "Install from " + c.storeName, act: "install", key: c.key })
        }
        for (const c of removable) out.push({ label: "Uninstall from " + c.storeName, act: "uninstall", key: c.key })
        out.push({ label: cur.hidden ? "Unhide game" : "Hide game", act: cur.hidden ? "unhide" : "hide", key: cur.key })
        out.push({ label: "Close", act: "close", key: "" })
        return out
    }

    function grab() { grid.forceActiveFocus(); sync() }
    onVisibleChanged: if (visible) grab()
    Component.onCompleted: if (visible) Qt.callLater(grab)
    Connections {
        target: app
        function onGameChanged(key) { tv.sync(); if (panel.visible) panel.rows = tv.buildActions() }
        function onGameColourReady(key, colour) { if (key === tv.cur.key) tv.gameAccent = colour }
    }

    // One of the two full-screen art images that take turns (see stage).
    component ArtLayer: ArtImage {
        property string tag: ""
        anchors.fill: parent
        sourceSize.width: app.light ? 1280 : 1920
        horizontalAlignment: Image.AlignRight
        Behavior on opacity { enabled: !app.light; NumberAnimation { duration: 450; easing.type: Easing.InOutQuad } }
        onStatusChanged: {
            if (stage.incoming !== tag) return
            if (status === Image.Ready) {
                stage.showA = tag === "a"; stage.none = false; stage.incoming = ""
            } else if (status === Image.Error && at >= sources.length - 1) {
                stage.none = true; stage.incoming = ""
            }
        }
    }

    Rectangle { anchors.fill: parent; color: theme.background }

    // ---------------------------------------------------------------- full-screen artwork
    // The focused game's wide art fills the screen and cross-fades to the next game's.
    // Two images take turns: the incoming one loads hidden, then fades in over the other.
    Item {
        id: stage
        anchors.fill: parent
        visible: tv.visible
        property bool showA: true
        property bool none: true      // no wide art for this game: show its blurred cover instead
        property string incoming: ""  // "a" or "b" while that image loads the next game's art
        function load(list) {
            if (!list || !list.length) { none = true; incoming = ""; return }
            const next = showA ? artB : artA
            incoming = next.tag
            next.sources = list
            if (next.status === Image.Ready && next.at === 0) { showA = next.tag === "a"; none = false; incoming = "" }
        }
        // Wait until the focus settles, so fast scrolling does not load every game on the way.
        Timer { id: settle; interval: 140; onTriggered: stage.load(tv.cur.heroes) }
        Connections {
            target: tv
            function onCurChanged() {
                if (JSON.stringify(tv.cur.heroes || []) !== stage.lastSig) {
                    stage.lastSig = JSON.stringify(tv.cur.heroes || [])
                    settle.restart()
                }
            }
        }
        property string lastSig: ""

        ArtLayer { id: artA; tag: "a"; opacity: !stage.none && stage.showA ? 1 : 0 }
        ArtLayer { id: artB; tag: "b"; opacity: !stage.none && !stage.showA ? 1 : 0 }

        Image {
            id: backdrop
            anchors.fill: parent
            source: stage.none && !app.light ? (tv.cur.cover || "") : ""
            asynchronous: true
            fillMode: Image.PreserveAspectCrop
            sourceSize.width: 200
            visible: false
        }
        MultiEffect {
            anchors.fill: parent
            source: backdrop
            visible: stage.none && !app.light && GraphicsInfo.api !== GraphicsInfo.Software && backdrop.status === Image.Ready
            blurEnabled: true
            blur: 1.0
            blurMax: 64
            opacity: 0.45
        }

        // Shade: dark on the left for the title, and at the bottom for the covers.
        Rectangle {
            anchors.fill: parent
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: Qt.alpha(theme.background, 0.88) }
                GradientStop { position: 0.38; color: Qt.alpha(theme.background, 0.45) }
                GradientStop { position: 0.7; color: Qt.alpha(theme.background, 0.0) }
            }
        }
        Rectangle {
            anchors.fill: parent
            gradient: Gradient {
                GradientStop { position: 0.0; color: Qt.alpha(theme.background, 0.55) }
                GradientStop { position: 0.16; color: Qt.alpha(theme.background, 0.0) }
                GradientStop { position: 0.5; color: Qt.alpha(theme.background, 0.0) }
                GradientStop { position: 0.82; color: Qt.alpha(theme.background, 0.85) }
                GradientStop { position: 1.0; color: theme.background }
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 48
        anchors.bottomMargin: 28
        spacing: 18

        // Store tabs. On narrower screens (the Steam Deck) the stores you are not on show only
        // their logo, and the row never pushes the layout wider than the screen.
        RowLayout {
            readonly property bool compact: tv.width < 1500
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            clip: true
            spacing: 12
            Text { text: "AIO Launch"; color: theme.onSurface; font.pixelSize: 30; font.weight: Font.Bold; Layout.rightMargin: 20 }
            Repeater {
                model: tv.storeIds
                Rectangle {
                    required property string modelData
                    readonly property bool active: library.storeFilter === modelData
                    readonly property var info: app.storesInfo.find(s => s.id === modelData) || ({ name: "All games", color: "" })
                    implicitWidth: tabRow.implicitWidth + 36
                    implicitHeight: 46
                    radius: 23
                    color: active ? tv.tint.primary : "transparent"
                    border.width: active ? 0 : 1
                    border.color: theme.outlineVariant
                    Row {
                        id: tabRow
                        anchors.centerIn: parent
                        spacing: 9
                        StoreIcon {
                            visible: parent.parent.modelData !== ""
                            anchors.verticalCenter: parent.verticalCenter
                            size: 20
                            store: parent.parent.modelData
                            color: parent.parent.active ? tv.tint.onPrimary : (parent.parent.info.color || theme.onSurfaceVariant)
                        }
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            visible: !parent.parent.parent.compact || parent.parent.active || parent.parent.modelData === ""
                            text: parent.parent.info.name
                            color: parent.parent.active ? tv.tint.onPrimary : theme.onSurfaceVariant
                            font.pixelSize: 18
                            font.weight: parent.parent.active ? Font.DemiBold : Font.Normal
                        }
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

        // The focused game, big, over its artwork.
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            ColumnLayout {
                anchors { left: parent.left; bottom: parent.bottom; bottomMargin: 6 }
                width: Math.min(parent.width * 0.62, 980)
                spacing: 12
                LogoTitle {
                    Layout.fillWidth: true
                    logos: tv.cur.logos || []
                    title: tv.cur.title || ""
                    color: theme.onSurface
                    pixelSize: Math.round(Math.min(72, Math.max(40, tv.height * 0.06)))
                    logoHeight: Math.round(Math.min(170, Math.max(90, tv.height * 0.15)))
                    maxWidth: Math.min(width, 640)
                }
                Row {
                    spacing: 14
                    Repeater {
                        model: tv.cur.key ? (tv.cur.copies.length ? tv.cur.copies : [{ key: tv.cur.key, storeColor: tv.cur.storeColor }]) : []
                        StoreIcon {
                            required property var modelData
                            anchors.verticalCenter: parent.verticalCenter
                            size: 24
                            store: modelData.key.split(":")[0]
                            color: modelData.storeColor || "white"
                        }
                    }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        color: theme.onSurface
                        opacity: 0.85
                        font.pixelSize: 19
                        text: {
                            if (!tv.cur.key) return ""
                            const stores = tv.cur.copies.length ? tv.cur.copies.map(c => c.storeName).join(", ") : tv.cur.storeName
                            const pct = Math.max(0, Math.floor(tv.cur.progress)) + "%"
                            const state = tv.cur.job === "install" ? "Installing " + pct
                                        : tv.cur.job === "update" ? "Updating " + pct
                                        : tv.cur.job ? "Removing…"
                                        : tv.cur.installed ? (tv.cur.update ? "Update available" : "Installed") : "Not installed"
                            return stores + "  ·  " + state
                        }
                    }
                }
                Text {
                    readonly property string played: tv.cur.key ? app.playedText(tv.cur.playtime, tv.cur.lastPlayed) : ""
                    visible: played !== ""
                    text: played
                    color: theme.onSurfaceVariant
                    font.pixelSize: 17
                }
            }
        }

        // One row of covers along the bottom; left / right to browse.
        GridView {
            id: grid
            objectName: "tvGrid"
            Layout.fillWidth: true
            Layout.preferredHeight: Math.round(Math.max(220, tv.height * 0.34))
            focus: true
            clip: false
            model: library
            flow: GridView.FlowTopToBottom
            cellHeight: height
            cellWidth: Math.round(height / 1.46)
            cacheBuffer: cellWidth * 4
            keyNavigationEnabled: true
            boundsBehavior: Flickable.StopAtBounds
            highlightFollowsCurrentItem: false
            // Glide just far enough to keep the focused cover (and a bit of its neighbour) in view.
            // A cover you point at is already in view, so the row never shifts under the mouse.
            function reveal() {
                if (currentIndex < 0 || width <= 0) return
                const x = currentIndex * cellWidth
                const margin = Math.min(cellWidth * 0.5, width / 4)
                let to = contentX
                if (x - contentX < margin) to = x - margin
                else if (x + cellWidth - contentX > width - margin) to = x + cellWidth - width + margin
                to = Math.max(0, Math.min(to, contentWidth - width))
                if (Math.abs(to - contentX) > 1) { glide.to = to; glide.restart() }
            }
            NumberAnimation { id: glide; target: grid; property: "contentX"; duration: app.light ? 0 : 220; easing.type: Easing.OutCubic }
            onWidthChanged: Qt.callLater(reveal)
            onCurrentIndexChanged: { tv.sync(); reveal() }
            onCountChanged: { if (currentIndex < 0 && count > 0) currentIndex = 0; tv.sync() }
            delegate: GameCard {
                required property int index
                width: grid.cellWidth
                height: grid.cellHeight
                theme: tv.tint
                cornerRadius: app.settingsMap.card_radius
                showBadge: app.settingsMap.show_badges
                showTitle: false
                dim: app.settingsMap.dim_uninstalled
                current: GridView.isCurrentItem
                // Pointing at a cover focuses it, so its artwork fills the screen.
                onHoveredChanged: if (hovered && grid.currentIndex !== index) grid.currentIndex = index
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

        // Button hints.
        Text {
            Layout.fillWidth: true
            visible: tv.width >= 1100
            horizontalAlignment: Text.AlignRight
            elide: Text.ElideLeft
            color: theme.outline
            font.pixelSize: 15
            text: pad.connected
                  ? "Ⓐ Play    Ⓧ Actions    Ⓨ Installed only    LB / RB Store    Ⓑ Exit"
                  : "Enter Play    F2 Actions    F3 Installed only    PgUp / PgDn Store    Esc Exit"
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
            else if (a.act === "update") app.update(a.key)
            else if (a.act === "cancel") app.cancel(a.key)
            else if (a.act === "uninstall") app.uninstall(a.key)
            else if (a.act === "hide" || a.act === "unhide") app.setHidden(a.key, a.act === "hide")
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
